"""The NVIDIA driver's settings database: read everything, write CS2's profile only.

The driver keeps its 3D settings in a profile database under ProgramData, and
NVAPI is the documented way in. Reading needs nothing special.

Writing (Edy, Nov 21 2026: the NVIDIA tab changes real driver settings) is
limited on purpose: only DWORD settings, and only in CS2's own program profile
-- NVIDIA's "Counter-Strike 2" profile, or one the app makes for cs2.exe when
the driver has none -- never the global profile, so no other game changes.
The driver only saves for an administrator on most PCs, so the write goes
through the one-time helper (``nvidia.set`` in helper/broker.ps1) and never
raises a prompt. Every change is recorded with pcstate, so it is put back
whenever the app is not running.

Everything degrades quietly: on a machine with no NVIDIA driver, ``probe()``
reports that and the caller shows the display section on its own.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Dict, List, Optional

UNICODE_MAX = 2048
BINARY_MAX = 4096

# nvapi64.dll exports one symbol; everything else is fetched by id. An id this
# driver does not know returns a null pointer, so an unsupported call fails
# safely rather than jumping somewhere arbitrary.
_FN = {
    "Initialize": 0x0150E828,
    "Unload": 0xD22BDD7E,
    "GetErrorMessage": 0x6C2D048C,
    "SYS_GetDriverAndBranchVersion": 0x2926AAAD,
    "DRS_CreateSession": 0x0694D52E,
    "DRS_DestroySession": 0xDAD9CFF8,
    "DRS_LoadSettings": 0x375DBD6B,
    "DRS_GetBaseProfile": 0xDA8466A0,
    "DRS_GetCurrentGlobalProfile": 0x617BFF9F,
    "DRS_GetNumProfiles": 0x1DAE4FBC,
    "DRS_GetProfileInfo": 0x61CD6FD6,
    "DRS_FindApplicationByName": 0xEEE566B2,
    "DRS_EnumSettings": 0xAE3039DA,
    "DRS_GetSetting": 0x73BF8338,
    "DRS_EnumAvailableSettingIds": 0xF020614A,
    "DRS_GetSettingNameFromId": 0xD61CBE6E,
    # The write path, used only by write_cs2() and only on CS2's own profile.
    "DRS_SetSetting": 0x577DD202,
    "DRS_SaveSettings": 0xFCBC7E14,
    "DRS_DeleteProfileSetting": 0xE4A26362,
    "DRS_RestoreProfileDefaultSetting": 0x53F0381E,
    "DRS_CreateProfile": 0xCC176068,
    "DRS_CreateApplication": 0x4347A9DE,
    "DRS_FindProfileByName": 0x7E4A9A0B,
}

_DWORD, _BINARY, _STRING = 0, 1, 2
_SETTING_NOT_FOUND = -160
_PROFILE_NOT_FOUND = -163
_EXECUTABLE_NOT_FOUND = -166
_INHERITED = (_SETTING_NOT_FOUND, _PROFILE_NOT_FOUND, _EXECUTABLE_NOT_FOUND)
_NO_PRIVILEGE = -137          # NVAPI_INVALID_USER_PRIVILEGE: saving needs administrator
_ACCESS_DENIED = -175         # NVAPI_ACCESS_DENIED
_PROFILE_REMOVED = -169       # restoring NVIDIA's preset dropped a profile the app made

# The profile the app makes when the driver has none for CS2 (NVIDIA ships one,
# so this is the rare case). Must match broker.ps1.
OWN_PROFILE = "CS CONFIG AI - Counter-Strike 2"
CS2_EXE = "cs2.exe"
# A setting in CS2's profile that holds NVIDIA's own preset for CS2, rather
# than one the player or the app set. Putting it back means restoring the preset.
PRESET = "default"


class _BinarySetting(ctypes.Structure):
    _fields_ = [("valueLength", ctypes.c_uint32),
                ("valueData", ctypes.c_ubyte * BINARY_MAX)]


class _Value(ctypes.Union):
    _fields_ = [("u32", ctypes.c_uint32),
                ("binary", _BinarySetting),
                ("wsz", ctypes.c_uint16 * UNICODE_MAX)]


class _Setting(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("settingName", ctypes.c_uint16 * UNICODE_MAX),
        ("settingId", ctypes.c_uint32),
        ("settingType", ctypes.c_uint32),
        ("settingLocation", ctypes.c_uint32),
        ("isCurrentPredefined", ctypes.c_uint32),
        ("isPredefinedValid", ctypes.c_uint32),
        ("predefined", _Value),
        ("current", _Value),
    ]


class _Profile(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("profileName", ctypes.c_uint16 * UNICODE_MAX),
        ("gpuSupport", ctypes.c_uint32),
        ("isPredefined", ctypes.c_uint32),
        ("numOfApps", ctypes.c_uint32),
        ("numOfSettings", ctypes.c_uint32),
    ]


class _Application(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("isPredefined", ctypes.c_uint32),
        ("appName", ctypes.c_uint16 * UNICODE_MAX),
        ("userFriendlyName", ctypes.c_uint16 * UNICODE_MAX),
        ("launcher", ctypes.c_uint16 * UNICODE_MAX),
        ("fileInFolder", ctypes.c_uint16 * UNICODE_MAX),
        ("flags", ctypes.c_uint32),
        ("commandLine", ctypes.c_uint16 * UNICODE_MAX),
    ]


def _stamp(struct_type: type, revision: int) -> int:
    """NVAPI carries a struct's size and revision in its first field."""
    return ctypes.sizeof(struct_type) | (revision << 16)


def _text(array) -> str:
    out = []
    for code in array:
        if code == 0:
            break
        out.append(chr(code))
    return "".join(out)


def _wide(value: str):
    buf = (ctypes.c_uint16 * UNICODE_MAX)()
    for i, ch in enumerate(value[:UNICODE_MAX - 1]):
        buf[i] = ord(ch)
    return buf


class NeedsAdministrator(PermissionError):
    """The driver will only save settings for an administrator."""


class NvApiError(RuntimeError):
    pass


class NoNvidiaDriver(NvApiError):
    pass


# NVIDIA/nvapi: NvApiDriverSettings.h and nvapi_interface.h. These are
# recommendations, not a claim that Apply writes the driver database.
# Leave image quality and Reflex to CS2; don't force driver VSync on.
VERIFICATION_TARGETS = {
    0x1057EB71: ("Power management: Prefer maximum performance", (0x00000001,)),
    0x00A879CF: ("Vertical sync: application-controlled or Off", (0x60925292, 0x08416747)),
}

# Last resort when neither application nor global/base profiles store a value.
# Published in https://github.com/NVIDIA/nvapi/blob/main/NvApiDriverSettings.h
# These are driver defaults, independent of the recommendations above.
_DRIVER_DEFAULTS = {
    0x1057EB71: 0x00000005,  # PREFERRED_PSTATE_DEFAULT = OPTIMAL_POWER
    0x00A879CF: 0x60925292,  # VSYNCMODE_DEFAULT = PASSIVE (application-controlled)
}


@dataclass
class Setting:
    id: int
    name: str
    value: str
    predefined: bool

    @property
    def known(self) -> bool:
        """Whether the driver publishes a name for this setting.

        NVIDIA's own game profiles lean on internal ids it does not name; those
        are shown as-is rather than captioned with a guess.
        """
        return bool(self.name)


@dataclass
class ProfileView:
    name: str
    predefined: bool
    settings: List[Setting] = field(default_factory=list)
    error: str = ""


@dataclass
class Catalogue:
    """Every 3D setting the driver knows, with what the global profile does.

    Showing only the overrides made the panel look empty on a machine that has
    never been touched, which reads as "there are no 3D settings" rather than
    "nothing here has been changed". The full list is the honest view: it is
    the same list the Control Panel's Manage 3D Settings shows.

    The value column is only filled in where a profile overrides it. The driver
    refuses to publish its own defaults -- DRS_EnumAvailableSettingValues is
    rejected on this driver at every struct revision -- so a setting left alone
    is reported as "driver default" rather than captioned with a guess.
    """
    entries: List["Setting"] = field(default_factory=list)

    @property
    def overridden(self) -> int:
        return sum(1 for e in self.entries if e.value)


@dataclass
class Probe:
    available: bool
    reason: str = ""
    driver: str = ""
    branch: str = ""
    profiles: int = 0
    catalogue: int = 0
    global_profile: Optional[ProfileView] = None
    app_profiles: Dict[str, ProfileView] = field(default_factory=dict)
    catalogue_3d: Optional[Catalogue] = None


class _Session:
    """An NVAPI DRS session. Writes go only to CS2's profile (see write_cs2)."""

    def __init__(self) -> None:
        try:
            self._dll = ctypes.WinDLL("nvapi64.dll")
        except OSError as exc:
            if getattr(exc, "winerror", None) == 5:
                raise PermissionError("NVIDIA driver access denied") from exc
            if isinstance(exc, FileNotFoundError) or getattr(exc, "winerror", None) in {2, 126}:
                raise NoNvidiaDriver("no NVIDIA driver on this machine") from exc
            raise NvApiError(f"no NVIDIA driver could be loaded: {exc}") from exc
        self._dll.nvapi_QueryInterface.restype = ctypes.c_void_p
        self._dll.nvapi_QueryInterface.argtypes = [ctypes.c_uint32]
        self._fns: Dict[str, object] = {}
        self._session = None
        self._names: Optional[Dict[int, str]] = None

    def _fn(self, name: str, *argtypes):
        key = (name, argtypes)
        if key not in self._fns:
            address = self._dll.nvapi_QueryInterface(_FN[name])
            if not address:
                raise NvApiError(f"this driver does not provide {name}")
            self._fns[key] = ctypes.CFUNCTYPE(ctypes.c_int32, *argtypes)(address)
        return self._fns[key]

    def _explain(self, code: int) -> str:
        buf = ctypes.create_string_buffer(64)
        try:
            self._fn("GetErrorMessage", ctypes.c_int32, ctypes.c_char_p)(code, buf)
        except NvApiError:
            return str(code)
        return buf.value.decode(errors="replace") or str(code)

    def _check(self, code: int, what: str) -> None:
        if code == -6:  # NVAPI_NVIDIA_DEVICE_NOT_FOUND
            raise NoNvidiaDriver("no NVIDIA GPU/driver on this machine")
        if code != 0:
            raise NvApiError(f"{what}: {self._explain(code)}")

    def __enter__(self) -> "_Session":
        self._check(self._fn("Initialize")(), "NvAPI_Initialize")
        handle = ctypes.c_void_p()
        self._check(
            self._fn("DRS_CreateSession", ctypes.POINTER(ctypes.c_void_p))(
                ctypes.byref(handle)), "opening a settings session")
        self._session = handle
        self._check(self._fn("DRS_LoadSettings", ctypes.c_void_p)(handle),
                    "loading the settings database")
        return self

    def __exit__(self, *_exc) -> None:
        if self._session is not None:
            try:
                self._fn("DRS_DestroySession", ctypes.c_void_p)(self._session)
            except NvApiError:
                pass
            self._session = None
        try:
            self._fn("Unload")()
        except NvApiError:
            pass

    # -- reads ------------------------------------------------------------
    def driver_version(self) -> tuple:
        version, branch = ctypes.c_uint32(), ctypes.create_string_buffer(64)
        self._check(
            self._fn("SYS_GetDriverAndBranchVersion",
                     ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p)(
                ctypes.byref(version), branch), "reading the driver version")
        return f"{version.value / 100:.2f}", branch.value.decode(errors="replace")

    def profile_count(self) -> int:
        count = ctypes.c_uint32()
        self._check(
            self._fn("DRS_GetNumProfiles", ctypes.c_void_p,
                     ctypes.POINTER(ctypes.c_uint32))(
                self._session, ctypes.byref(count)), "counting profiles")
        return count.value

    def setting_names(self) -> Dict[int, str]:
        """Id to name, straight from the driver rather than a bundled table.

        A table shipped with this app would drift the moment the driver added
        a setting, and a stale id is exactly the kind of thing that is easy to
        get wrong and hard to notice.
        """
        if self._names is not None:
            return self._names
        ids = (ctypes.c_uint32 * 4096)()
        count = ctypes.c_uint32(4096)
        self._check(
            self._fn("DRS_EnumAvailableSettingIds",
                     ctypes.POINTER(ctypes.c_uint32),
                     ctypes.POINTER(ctypes.c_uint32))(ids, ctypes.byref(count)),
            "listing the settings the driver knows")
        get_name = self._fn("DRS_GetSettingNameFromId", ctypes.c_uint32,
                            ctypes.POINTER(ctypes.c_uint16 * UNICODE_MAX))
        names: Dict[int, str] = {}
        for i in range(count.value):
            buf = (ctypes.c_uint16 * UNICODE_MAX)()
            if get_name(ids[i], ctypes.byref(buf)) == 0:
                names[ids[i]] = _text(buf)
        self._names = names
        return names

    def _read_profile(self, handle, fallback_name: str = "") -> ProfileView:
        info = _Profile()
        info.version = _stamp(_Profile, 1)
        code = self._fn("DRS_GetProfileInfo", ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.POINTER(_Profile))(self._session, handle,
                                                  ctypes.byref(info))
        if code != 0:
            return ProfileView(fallback_name, False,
                               error=f"could not read: {self._explain(code)}")

        view = ProfileView(_text(info.profileName) or fallback_name,
                           bool(info.isPredefined))
        if not info.numOfSettings:
            return view

        names = self.setting_names()
        block = (_Setting * info.numOfSettings)()
        for i in range(info.numOfSettings):
            block[i].version = _stamp(_Setting, 1)
        count = ctypes.c_uint32(info.numOfSettings)
        code = self._fn("DRS_EnumSettings", ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                        ctypes.POINTER(_Setting))(
            self._session, handle, 0, ctypes.byref(count),
            ctypes.cast(block, ctypes.POINTER(_Setting)))
        if code != 0:
            view.error = f"could not list settings: {self._explain(code)}"
            return view

        for i in range(count.value):
            entry = block[i]
            if entry.settingType == _DWORD:
                shown = f"0x{entry.current.u32:08X}"
            elif entry.settingType == _STRING:
                shown = _text(entry.current.wsz)
            else:
                shown = f"{entry.current.binary.valueLength} bytes"
            view.settings.append(Setting(
                id=entry.settingId,
                name=names.get(entry.settingId, _text(entry.settingName)),
                value=shown,
                predefined=bool(entry.isCurrentPredefined),
            ))
        view.settings.sort(key=lambda s: (not s.known, s.name.lower(), s.id))
        return view

    def global_profile(self) -> ProfileView:
        handle = ctypes.c_void_p()
        self._check(
            self._fn("DRS_GetBaseProfile", ctypes.c_void_p,
                     ctypes.POINTER(ctypes.c_void_p))(
                self._session, ctypes.byref(handle)), "opening the global profile")
        view = self._read_profile(handle, "Global 3D settings")
        view.name = "Global 3D settings"
        return view

    def catalogue(self, overrides: Optional[ProfileView] = None) -> Catalogue:
        """The whole 3D settings list, annotated with any override."""
        by_id = {}
        if overrides is not None:
            by_id = {s.id: s for s in overrides.settings}

        entries = []
        for setting_id, name in self.setting_names().items():
            found = by_id.get(setting_id)
            entries.append(Setting(
                id=setting_id, name=name,
                value=found.value if found else "",
                predefined=found.predefined if found else True,
            ))
        entries.sort(key=lambda s: s.name.lower())
        return Catalogue(entries)

    def _app_handle(self, executable: str):
        app = _Application()
        app.version = _stamp(_Application, 4)
        handle = ctypes.c_void_p()
        code = self._fn("DRS_FindApplicationByName", ctypes.c_void_p,
                        ctypes.c_uint16 * UNICODE_MAX,
                        ctypes.POINTER(ctypes.c_void_p),
                        ctypes.POINTER(_Application))(
            self._session, _wide(executable), ctypes.byref(handle),
            ctypes.byref(app))
        if code in (_EXECUTABLE_NOT_FOUND, _PROFILE_NOT_FOUND):
            return None
        self._check(code, "finding the application profile")
        return handle

    def app_profile(self, executable: str) -> Optional[ProfileView]:
        handle = self._app_handle(executable)
        if handle is None:
            return None
        return self._read_profile(handle, executable)

    def _global_handle(self, function: str):
        handle = ctypes.c_void_p()
        code = self._fn(function, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            self._session, ctypes.byref(handle))
        if code in (_PROFILE_NOT_FOUND, _EXECUTABLE_NOT_FOUND):
            return None
        self._check(code, "opening the global profile")
        return handle

    def _read_dword(self, handle, setting_id: int) -> Optional[int]:
        entry = _Setting()
        entry.version = _stamp(_Setting, 1)
        code = self._fn("DRS_GetSetting", ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_uint32, ctypes.POINTER(_Setting))(
            self._session, handle, setting_id, ctypes.byref(entry))
        if code in _INHERITED:
            return None
        self._check(code, "reading the effective application setting")
        if entry.settingType != _DWORD:
            raise NvApiError("expected a DWORD application setting")
        return entry.current.u32

    def effective_settings(self, executable: str, ids) -> dict:
        """Resolve app -> current global -> base -> documented driver default.

        GetSetting can return SETTING_NOT_FOUND for an inherited value. Only
        absence permits fallback; denied access and other read errors propagate.
        """
        app_handle = self._app_handle(executable)
        global_handles = {}
        values = {}
        for setting_id in ids:
            value = self._read_dword(app_handle, setting_id) if app_handle is not None else None
            if value is None:
                for function in ("DRS_GetCurrentGlobalProfile", "DRS_GetBaseProfile"):
                    if function not in global_handles:
                        global_handles[function] = self._global_handle(function)
                    handle = global_handles[function]
                    if handle is not None:
                        value = self._read_dword(handle, setting_id)
                        if value is not None:
                            break
            if value is None:
                value = _DRIVER_DEFAULTS.get(setting_id)
                if value is None:
                    raise NvApiError(f"no documented default for setting 0x{setting_id:08X}")
            values[setting_id] = value
        return values

    # -- CS2's profile: the only thing the app ever writes ------------------
    def cs2_profile(self, create: bool = False):
        """CS2's program profile: NVIDIA's own, or one the app makes if none."""
        handle = self._app_handle(CS2_EXE)
        if handle is not None or not create:
            return handle
        found = ctypes.c_void_p()
        code = self._fn("DRS_FindProfileByName", ctypes.c_void_p,
                        ctypes.c_uint16 * UNICODE_MAX, ctypes.POINTER(ctypes.c_void_p))(
            self._session, _wide(OWN_PROFILE), ctypes.byref(found))
        if code == _PROFILE_NOT_FOUND:
            info = _Profile()
            info.version = _stamp(_Profile, 1)
            for i, ch in enumerate(OWN_PROFILE):
                info.profileName[i] = ord(ch)
            self._check(self._fn("DRS_CreateProfile", ctypes.c_void_p,
                                 ctypes.POINTER(_Profile), ctypes.POINTER(ctypes.c_void_p))(
                self._session, ctypes.byref(info), ctypes.byref(found)), "making a profile for CS2")
        else:
            self._check(code, "finding the app's CS2 profile")
        app = _Application()
        app.version = _stamp(_Application, 4)
        for i, ch in enumerate(CS2_EXE):
            app.appName[i] = ord(ch)
        self._check(self._fn("DRS_CreateApplication", ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.POINTER(_Application))(
            self._session, found, ctypes.byref(app)), "adding CS2 to its profile")
        return found

    def profile_state(self, handle, setting_id: int):
        """A DWORD in CS2's profile: an int, PRESET for NVIDIA's own, or None if unset."""
        if handle is None:
            return None
        entry = _Setting()
        entry.version = _stamp(_Setting, 1)
        code = self._fn("DRS_GetSetting", ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_uint32, ctypes.POINTER(_Setting))(
            self._session, handle, setting_id, ctypes.byref(entry))
        if code in _INHERITED:
            return None
        self._check(code, "reading CS2's NVIDIA profile")
        if entry.settingType != _DWORD:
            return None
        if entry.isCurrentPredefined:
            return PRESET
        return int(entry.current.u32)

    def change(self, handle, setting_id: int, value) -> None:
        """Set an int, put back NVIDIA's preset (PRESET), or remove (None)."""
        if value is None:
            code = self._fn("DRS_DeleteProfileSetting", ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_uint32)(self._session, handle, setting_id)
            if code not in _INHERITED:
                self._check(code, "removing a setting from CS2's NVIDIA profile")
            return
        if value == PRESET:
            code = self._fn("DRS_RestoreProfileDefaultSetting", ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_uint32)(self._session, handle, setting_id)
            if code not in _INHERITED + (_PROFILE_REMOVED,):
                self._check(code, "putting back NVIDIA's own CS2 setting")
            return
        entry = _Setting()
        entry.version = _stamp(_Setting, 1)
        entry.settingId = setting_id
        entry.settingType = _DWORD
        entry.current.u32 = int(value) & 0xFFFFFFFF
        self._check(self._fn("DRS_SetSetting", ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.POINTER(_Setting))(
            self._session, handle, ctypes.byref(entry)), "changing CS2's NVIDIA profile")

    def save(self) -> None:
        code = self._fn("DRS_SaveSettings", ctypes.c_void_p)(self._session)
        if code in (_NO_PRIVILEGE, _ACCESS_DENIED):
            raise NeedsAdministrator("the NVIDIA driver only saves settings for an administrator")
        self._check(code, "saving the NVIDIA settings")


def read_recommended() -> dict:
    """Small unelevated read for the receipt; no catalogue scan or write calls."""
    try:
        with _Session() as session:
            values = session.effective_settings("cs2.exe", VERIFICATION_TARGETS)
        missing = [label for setting_id, (label, allowed) in VERIFICATION_TARGETS.items()
                   if values[setting_id] not in allowed]
        return {"available": True, "matches": not missing,
                "detail": "; ".join(missing)}
    except NoNvidiaDriver as exc:
        return {"available": False, "not_applicable": True, "reason": str(exc)}
    except (NvApiError, OSError) as exc:
        return {"available": False, "reason": str(exc)}


def probe(executables: tuple = ("cs2.exe",)) -> Probe:
    """Everything worth showing about the driver's settings, read-only."""
    try:
        with _Session() as session:
            driver, branch = session.driver_version()
            result = Probe(available=True, driver=driver, branch=branch,
                           profiles=session.profile_count(),
                           catalogue=len(session.setting_names()),
                           global_profile=session.global_profile())
            result.catalogue_3d = session.catalogue(result.global_profile)
            for exe in executables:
                found = session.app_profile(exe)
                if found is not None:
                    result.app_profiles[exe] = found
            return result
    except NvApiError as exc:
        return Probe(available=False, reason=str(exc))
    except OSError as exc:                       # a driver that loads but misbehaves
        return Probe(available=False, reason=f"NVIDIA driver call failed: {exc}")


def as_dict(result: Probe) -> dict:
    def profile(view: Optional[ProfileView]) -> Optional[dict]:
        if view is None:
            return None
        return {
            "name": view.name,
            "predefined": view.predefined,
            "error": view.error,
            "settings": [
                {"id": f"0x{s.id:08X}", "name": s.name, "value": s.value,
                 "predefined": s.predefined, "known": s.known}
                for s in view.settings
            ],
        }

    return {
        "catalogue_3d": [
            {"id": f"0x{e.id:08X}", "name": e.name, "value": e.value,
             "overridden": bool(e.value)}
            for e in (result.catalogue_3d.entries if result.catalogue_3d else [])
        ],
        "overridden_count": result.catalogue_3d.overridden if result.catalogue_3d else 0,
        "available": result.available,
        "reason": result.reason,
        "driver": result.driver,
        "branch": result.branch,
        "profiles": result.profiles,
        "catalogue": result.catalogue,
        "global": profile(result.global_profile),
        "apps": {k: profile(v) for k, v in result.app_profiles.items()},
    }


# ---------------------------------------------------------------------------
# Writing CS2's NVIDIA profile (Edy, Nov 21: the NVIDIA tab changes real
# driver settings). Only ever CS2's own program profile -- never the global
# one, so no other game on the PC is touched -- and only DWORD settings.
# ---------------------------------------------------------------------------

POWER, VSYNC, LOW_LATENCY = 0x1057EB71, 0x00A879CF, 0x007BA09E
TEX_QUALITY, ANISO_OPT, THREADED = 0x00CE2691, 0x00E73211, 0x20C1221E

# What each Launcher mode sets in CS2's NVIDIA profile. Small on purpose:
# these are the driver settings that matter for CS2; picture detail itself is
# CS2's own video settings. Reflex and anti-aliasing are left to the game.
MANAGED = {
    "competitive": {POWER: 0x1, VSYNC: 0x60925292, LOW_LATENCY: 1, TEX_QUALITY: 0x14,
                    ANISO_OPT: 1, THREADED: 1},
    "balanced":    {POWER: 0x1, VSYNC: 0x60925292, LOW_LATENCY: 1, TEX_QUALITY: 0xA,
                    ANISO_OPT: 0, THREADED: 1},
    "quality":     {POWER: 0x1, VSYNC: 0x60925292, LOW_LATENCY: 1, TEX_QUALITY: 0xFFFFFFF6,
                    ANISO_OPT: 0, THREADED: 1},
}
MAX_CHANGES = 64


def known_settings() -> Dict[str, dict]:
    """Names and choices from NVIDIA's published header (knowledge/nvidia_settings.json)."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "knowledge" / "nvidia_settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["settings"]
    except (OSError, ValueError, KeyError):
        return {}


def hex_id(setting_id: int) -> str:
    return f"0x{int(setting_id):08X}"


def label_for(setting_id: int, value, known: Optional[Dict[str, dict]] = None) -> str:
    """A value in plain words, as the NVIDIA Control Panel would say it."""
    if value is None:
        return "Not set (NVIDIA's global setting)"
    if value == PRESET:
        return "NVIDIA's own setting for CS2"
    entry = (known if known is not None else known_settings()).get(hex_id(setting_id), {})
    choices = {int(k, 16): v for k, v in (entry.get("choices") or {}).items()}
    if int(value) in choices:
        return choices[int(value)]
    if setting_id == 0x10835002:
        return f"{int(value)} FPS"
    return str(int(value))


def desired(intent: str, manual: Optional[Dict[str, int]] = None) -> Dict[int, int]:
    """What CS2's profile should hold: the mode's settings, with the player's own on top."""
    want = dict(MANAGED.get(intent) or MANAGED["balanced"])
    for key, value in (manual or {}).items():
        try:
            want[int(str(key), 16)] = int(value)
        except (TypeError, ValueError):
            continue
    return want


def read_cs2(ids) -> Dict[int, object]:
    """Each setting's value in CS2's profile. Reading needs no administrator."""
    with _Session() as session:
        handle = session.cs2_profile(create=False)
        return {int(i): session.profile_state(handle, int(i)) for i in ids}


def _clean(changes: Dict[int, object]) -> Dict[int, object]:
    out = {}
    for key, value in changes.items():
        setting_id = int(key)
        if not 0 < setting_id <= 0xFFFFFFFF:
            raise ValueError("not an NVIDIA setting")
        if value is not None and value != PRESET:
            value = int(value)
            if not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("not a value NVIDIA accepts")
        out[setting_id] = value
    if len(out) > MAX_CHANGES:
        raise ValueError("too many NVIDIA settings at once")
    return out


def _write_here(changes: Dict[int, object]) -> Dict[int, object]:
    """Write as this user. Returns what each setting held before."""
    with _Session() as session:
        handle = session.cs2_profile(create=True)
        before = {i: session.profile_state(handle, i) for i in changes}
        for setting_id, value in changes.items():
            session.change(handle, setting_id, value)
        session.save()
        return before


def _write_helper(changes: Dict[int, object]) -> Dict[int, object]:
    from . import elevated

    result = elevated.run("nvidia.set", {"changes": [
        {"id": i, "value": v} for i, v in changes.items()]})
    if result.get("needs_setup"):
        raise NeedsAdministrator(
            "NVIDIA only lets an administrator save its settings. Allow it once in "
            "Settings → NVIDIA (one Windows prompt, never again)")
    if not result.get("ok"):
        raise NvApiError(result.get("error") or "the NVIDIA driver refused the change")
    before = {}
    for item in result.get("before") or []:
        try:
            before[int(item["id"])] = item.get("value")
        except (KeyError, TypeError, ValueError):
            continue
    return before


def write_cs2(changes: Dict[int, object], record: bool = True) -> dict:
    """Change settings in CS2's profile. Never prompts.

    Tries as this user first; the driver refuses that on most PCs, so the
    one-time administrator helper (``nvidia.set``) does it instead. Every
    change is recorded with pcstate so it is put back when the app is closed.
    """
    try:
        changes = _clean(changes)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    if not changes:
        return {"ok": True, "changed": []}
    try:
        try:
            before = _write_here(changes)
        except NeedsAdministrator:
            before = _write_helper(changes)
    except NoNvidiaDriver as exc:
        return {"ok": False, "no_driver": True, "error": str(exc)}
    except NeedsAdministrator as exc:
        return {"ok": False, "needs_setup": True, "error": str(exc)}
    except (NvApiError, OSError) as exc:
        return {"ok": False, "error": str(exc)}

    known = known_settings()
    changed = []
    for setting_id, value in changes.items():
        was = before.get(setting_id)
        if record:
            try:
                from . import pcstate
                pcstate.note("nvidia_3d", hex_id(setting_id), was, value)
            except Exception:
                pass
        if was != value:
            changed.append({"id": hex_id(setting_id),
                            "name": (known.get(hex_id(setting_id)) or {}).get("name", hex_id(setting_id)),
                            "before": label_for(setting_id, was, known),
                            "after": label_for(setting_id, value, known)})
    return {"ok": True, "changed": changed}


def apply_intent(intent: str, manual: Optional[Dict[str, int]] = None) -> dict:
    """Bring CS2's profile in line with a Launcher mode. Only what differs is written."""
    want = desired(intent, manual)
    try:
        now = read_cs2(want)
    except NoNvidiaDriver as exc:
        return {"ok": False, "no_driver": True, "error": str(exc)}
    except (NvApiError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    todo = {i: v for i, v in want.items() if now.get(i) != v}
    result = write_cs2(todo)
    if result.get("ok"):
        result["checked"] = len(want)
    return result


def panel(intent: str, manual: Optional[Dict[str, int]] = None) -> dict:
    """Everything the Settings → NVIDIA tab shows."""
    known = known_settings()
    managed = MANAGED.get(intent) or MANAGED["balanced"]
    manual = {int(str(k), 16): int(v) for k, v in (manual or {}).items()
              if str(k).lower().startswith("0x")}
    try:
        with _Session() as session:
            driver, _branch = session.driver_version()
            handle = session.cs2_profile(create=False)
            names = session.setting_names()
            ids = sorted(set(names) | set(managed) | set(manual))
            values = {i: session.profile_state(handle, i) for i in ids}
    except NoNvidiaDriver as exc:
        return {"available": False, "no_driver": True, "reason": str(exc)}
    except (NvApiError, OSError) as exc:
        return {"available": False, "reason": str(exc)}

    def row(setting_id: int) -> dict:
        entry = known.get(hex_id(setting_id)) or {}
        value = values.get(setting_id)
        return {
            "id": hex_id(setting_id),
            "name": entry.get("name") or names.get(setting_id) or hex_id(setting_id),
            "value": None if value in (None, PRESET) else int(value),
            "label": label_for(setting_id, value, known),
            "choices": [{"value": int(k, 16), "label": v}
                        for k, v in (entry.get("choices") or {}).items()],
            "range": entry.get("range"),
            "managed": setting_id in managed,
            "ours": managed.get(setting_id),
            "ours_label": label_for(setting_id, managed[setting_id], known) if setting_id in managed else None,
            "manual": setting_id in manual,
        }

    rows = [row(i) for i in ids]
    return {"available": True, "driver": driver, "intent": intent,
            "managed": [r for r in rows if r["managed"]],
            "all": sorted(rows, key=lambda r: r["name"].lower())}
