"""Read the NVIDIA driver's settings database. Read-only, by design.

The driver keeps its 3D settings in a profile database under ProgramData, and
NVAPI is the documented way in. This module opens a session, reads, and closes
it. There is deliberately no write path: ``NvAPI_DRS_SaveSettings`` is not in
the function table below, so nothing here can modify the database even by
mistake. Writing would need elevation and would land in a system-wide store
shared by every game on the machine, and the driver does not publish what its
setting values mean -- the ids and names come from the driver, but the value
encodings would have to be guessed, which is not a good enough footing for
writing into it.

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
    "DRS_GetNumProfiles": 0x1DAE4FBC,
    "DRS_GetProfileInfo": 0x61CD6FD6,
    "DRS_FindApplicationByName": 0xEEE566B2,
    "DRS_EnumSettings": 0xAE3039DA,
    "DRS_EnumAvailableSettingIds": 0xF020614A,
    "DRS_GetSettingNameFromId": 0xD61CBE6E,
}

_DWORD, _BINARY, _STRING = 0, 1, 2


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


class NvApiError(RuntimeError):
    pass


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
    """An NVAPI DRS session. Read-only: there is no save() here."""

    def __init__(self) -> None:
        try:
            self._dll = ctypes.WinDLL("nvapi64.dll")
        except OSError as exc:
            raise NvApiError("no NVIDIA driver on this machine") from exc
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

    def app_profile(self, executable: str) -> Optional[ProfileView]:
        app = _Application()
        app.version = _stamp(_Application, 4)
        handle = ctypes.c_void_p()
        code = self._fn("DRS_FindApplicationByName", ctypes.c_void_p,
                        ctypes.c_uint16 * UNICODE_MAX,
                        ctypes.POINTER(ctypes.c_void_p),
                        ctypes.POINTER(_Application))(
            self._session, _wide(executable), ctypes.byref(handle),
            ctypes.byref(app))
        if code != 0:
            return None
        return self._read_profile(handle, executable)


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
