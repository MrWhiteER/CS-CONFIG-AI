"""Whether a narrow desktop mode fills the panel, or sits between black bars.

Stretching in CS2 is done by putting the *desktop* into a narrow mode -- 1550
wide on a 2560-wide panel -- and letting the GPU scale it back out. Whether
that scale fills the screen or preserves the aspect ratio is a driver setting,
not something the mode switch decides, so the same launch produces a stretched
picture on one machine and a picture with a black bar down each side on the
next. ``window.set_mode`` has always said as much in its docstring and left the
reader to go and fix it in the NVIDIA Control Panel.

This reads that setting and can put it right.

NVAPI's display-config call is the documented way in, and unlike the 3D profile
database in :mod:`cs2cfg.nvidia` it publishes what its values mean:
``NV_SCALING`` is an ordinary enum, so nothing here is guessed. Two things keep
the write honest anyway:

* it is a **round trip**. The whole configuration is read, one 32-bit field is
  changed, and the rest goes back exactly as the driver handed it over. Fields
  this module does not model are carried, never authored.
* it is **validated first**, with ``VALIDATE_ONLY``, the same way
  ``window.set_mode`` probes a mode with ``CDS_TEST`` before committing to it.

The previous value comes back from every change so the caller can put it back,
and the launcher does, alongside the desktop mode it already restores.

On a machine with no NVIDIA driver everything degrades quietly: ``read()``
reports why and the caller carries on without the section.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# nvapi64.dll exports one symbol; the rest are fetched by id. An id this driver
# does not know comes back as a null pointer, so an unsupported call fails
# safely instead of jumping somewhere arbitrary.
_FN = {
    "Initialize": 0x0150E828,
    "Unload": 0xD22BDD7E,
    "GetErrorMessage": 0x6C2D048C,
    "DISP_GetDisplayConfig": 0x11ABCCF8,
    "DISP_SetDisplayConfig": 0x5D8CF8DE,
}

# Struct sizes are fixed by the driver's ABI, not by this file. Each is paired
# with the revision NVAPI stamps into the first field; get either wrong and the
# call is rejected with NVAPI_INCOMPATIBLE_STRUCT_VERSION rather than
# misinterpreting memory, which is the failure mode worth having.
_PATH_INFO_SIZE = 48
_PATH_INFO_REVISION = 2
_ADVANCED_SIZE = 128
_ADVANCED_REVISION = 1

VALIDATE_ONLY = 0x00000001
SAVE_TO_PERSISTENCE = 0x00000002

# Word offsets into the advanced-target block. Only these are interpreted;
# everything after them is carried through untouched.
_OFF_VERSION, _OFF_ROTATION, _OFF_SCALING, _OFF_REFRESH = 0, 1, 2, 3

# NV_SCALING. The names are the ones the NVIDIA Control Panel puts on the same
# choices under "Adjust desktop size and position".
DEFAULT = 0
FULL_SCREEN_CLOSEST = 1          # "Full-screen", driver picks the timing
FULL_SCREEN = 2                  # "Full-screen", scaled out to the native panel
CENTRED = 3                      # "No scaling", native timing
ASPECT = 5                       # "Aspect ratio" -- this is the one with the bars
ASPECT_CLOSEST = 6
CENTRED_CLOSEST = 7
INTEGER = 8
CUSTOM = 255

NAMES: Dict[int, str] = {
    DEFAULT: "driver default",
    FULL_SCREEN_CLOSEST: "full-screen",
    FULL_SCREEN: "full-screen",
    CENTRED: "no scaling (centred)",
    ASPECT: "aspect ratio",
    ASPECT_CLOSEST: "aspect ratio",
    CENTRED_CLOSEST: "no scaling (centred)",
    INTEGER: "integer scaling",
    CUSTOM: "customised",
}

# The modes that put the picture across the whole panel. Everything else leaves
# unlit pixels somewhere -- down the sides for a mode narrower than the panel,
# which is the shape every stretched CS2 resolution has.
FILLS = frozenset({FULL_SCREEN_CLOSEST, FULL_SCREEN})

# What to set when asked to fill. FULL_SCREEN is the forcing variant: it scales
# out to the panel's native size whatever the game asked for, which is the
# "Override the scaling mode set by games and programs" box in the Control
# Panel. Without that override CS2 can ask for its own scaling and get the bars
# back, so the weaker FULL_SCREEN_CLOSEST is not good enough here.
PREFERRED = FULL_SCREEN


class ScalingError(RuntimeError):
    pass


class _PathInfo(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("source_id", ctypes.c_uint32),
        ("target_count", ctypes.c_uint32),
        ("_pad", ctypes.c_uint32),
        ("targets", ctypes.c_void_p),
        ("source_mode", ctypes.c_void_p),
        ("bits", ctypes.c_uint32),
        ("_pad2", ctypes.c_uint32),
        ("os_adapter", ctypes.c_void_p),
    ]


class _TargetInfo(ctypes.Structure):
    _fields_ = [
        ("display_id", ctypes.c_uint32),
        ("_pad", ctypes.c_uint32),
        ("details", ctypes.c_void_p),
        ("target_id", ctypes.c_uint32),
        ("_pad2", ctypes.c_uint32),
    ]


class _SourceMode(ctypes.Structure):
    """Not separately versioned; its revision rides on the path info's."""
    _fields_ = [
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("depth", ctypes.c_uint32),
        ("colour_format", ctypes.c_uint32),
        ("x", ctypes.c_int32),
        ("y", ctypes.c_int32),
        ("spanning", ctypes.c_uint32),
        ("bits", ctypes.c_uint32),
    ]


@dataclass
class Screen:
    """One display, and what the driver does with a mode that does not fit it."""
    display_id: int
    scaling: int
    width: int
    height: int
    primary: bool
    refresh: int = 0

    @property
    def fills(self) -> bool:
        return self.scaling in FILLS

    @property
    def name(self) -> str:
        return NAMES.get(self.scaling, f"unknown mode {self.scaling}")

    @property
    def bars(self) -> bool:
        """Whether a mode narrower than this panel would be letterboxed.

        ``DEFAULT`` is excluded: it means the display has never been given an
        override, and what the driver falls back to is its business, so calling
        it a fault would be claiming to know something this cannot read.
        """
        return not self.fills and self.scaling != DEFAULT


@dataclass
class Report:
    available: bool
    reason: str = ""
    screens: List[Screen] = field(default_factory=list)

    @property
    def primary(self) -> Optional[Screen]:
        return next((s for s in self.screens if s.primary), None)

    @property
    def all_fill(self) -> bool:
        return bool(self.screens) and all(s.fills for s in self.screens)


class _Config:
    """One read of the whole display configuration, kept alive for a write back.

    Every buffer the driver filled is held on the instance. A write hands the
    same memory back, which is what makes the round trip a round trip rather
    than a reconstruction.
    """

    def __init__(self) -> None:
        try:
            self._dll = ctypes.WinDLL("nvapi64.dll")
        except OSError as exc:
            raise ScalingError("no NVIDIA driver on this machine") from exc
        self._dll.nvapi_QueryInterface.restype = ctypes.c_void_p
        self._dll.nvapi_QueryInterface.argtypes = [ctypes.c_uint32]
        self._fns: Dict[tuple, object] = {}
        self.paths = None
        self.count = 0
        self._held: List[tuple] = []

    def _fn(self, name: str, *argtypes):
        key = (name, argtypes)
        if key not in self._fns:
            address = self._dll.nvapi_QueryInterface(_FN[name])
            if not address:
                raise ScalingError(f"this driver does not provide {name}")
            self._fns[key] = ctypes.CFUNCTYPE(ctypes.c_int32, *argtypes)(address)
        return self._fns[key]

    def _explain(self, code: int) -> str:
        buf = ctypes.create_string_buffer(64)
        try:
            self._fn("GetErrorMessage", ctypes.c_int32, ctypes.c_char_p)(code, buf)
        except ScalingError:
            return str(code)
        return buf.value.decode(errors="replace") or str(code)

    def _check(self, code: int, what: str) -> None:
        if code != 0:
            raise ScalingError(f"{what}: {self._explain(code)}")

    def __enter__(self) -> "_Config":
        self._check(self._fn("Initialize")(), "starting NVAPI")
        self._read()
        return self

    def __exit__(self, *_exc) -> None:
        try:
            self._fn("Unload")()
        except ScalingError:
            pass

    # -- reading ----------------------------------------------------------
    def _get(self, count, paths) -> int:
        return self._fn("DISP_GetDisplayConfig", ctypes.POINTER(ctypes.c_uint32),
                        ctypes.POINTER(_PathInfo))(count, paths)

    def _read(self) -> None:
        """The three-stage read NVAPI's display config requires.

        How many paths, then how many targets hang off each one, and only then
        the data -- each stage sizing the allocation the next stage needs.
        """
        total = ctypes.c_uint32(0)
        self._check(self._get(ctypes.byref(total), None), "counting displays")
        if not total.value:
            raise ScalingError("the driver reported no displays")

        paths = (_PathInfo * total.value)()
        version = _PATH_INFO_SIZE | (_PATH_INFO_REVISION << 16)
        for path in paths:
            path.version = version
        self._check(self._get(ctypes.byref(total), paths), "listing display paths")

        held = []
        for path in paths:
            targets = (_TargetInfo * path.target_count)()
            details = []
            for target in targets:
                buf = ctypes.create_string_buffer(_ADVANCED_SIZE)
                ctypes.memset(buf, 0, _ADVANCED_SIZE)
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[_OFF_VERSION] = (
                    _ADVANCED_SIZE | (_ADVANCED_REVISION << 16))
                target.details = ctypes.cast(buf, ctypes.c_void_p)
                details.append(buf)
            source = _SourceMode()
            path.targets = ctypes.cast(targets, ctypes.c_void_p)
            path.source_mode = ctypes.cast(ctypes.byref(source), ctypes.c_void_p)
            held.append((targets, details, source))

        self._check(self._get(ctypes.byref(total), paths), "reading display scaling")
        self.paths, self.count, self._held = paths, total.value, held

    def screens(self) -> List[Screen]:
        out: List[Screen] = []
        for targets, details, source in self._held:
            for target, buf in zip(targets, details):
                words = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))
                out.append(Screen(
                    display_id=target.display_id,
                    scaling=words[_OFF_SCALING],
                    width=source.width,
                    height=source.height,
                    primary=bool(source.bits & 1),
                    # The driver reports millihertz; 239958 is a 240 Hz panel.
                    refresh=round(words[_OFF_REFRESH] / 1000),
                ))
        return out

    # -- writing ----------------------------------------------------------
    def _field(self, display_id: int):
        for targets, details, _source in self._held:
            for target, buf in zip(targets, details):
                if target.display_id == display_id:
                    return ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))
        return None

    def apply(self, flags: int) -> int:
        return self._fn("DISP_SetDisplayConfig", ctypes.c_uint32,
                        ctypes.POINTER(_PathInfo), ctypes.c_uint32)(
            self.count, self.paths, flags)

    def set_scaling(self, display_id: int, scaling: int, commit: bool,
                    persist: bool = False) -> dict:
        words = self._field(display_id)
        if words is None:
            raise ScalingError(f"no display with id 0x{display_id:08X}")
        previous = words[_OFF_SCALING]
        if previous == scaling:
            return {"ok": True, "changed": False, "previous": previous,
                    "scaling": scaling,
                    "note": f"already set to {NAMES.get(scaling, scaling)}"}

        # Every path out of here puts the field back unless the change was
        # actually committed, so a caller that ignores the result still cannot
        # be left holding a configuration that says something untrue.
        words[_OFF_SCALING] = scaling
        code = self.apply(VALIDATE_ONLY)
        if code != 0:
            words[_OFF_SCALING] = previous
            return {"ok": False, "changed": False, "previous": previous,
                    "error": f"the driver rejected {NAMES.get(scaling, scaling)}: "
                             f"{self._explain(code)}"}
        if not commit:
            words[_OFF_SCALING] = previous
            return {"ok": True, "changed": False, "validated": True,
                    "previous": previous, "scaling": scaling,
                    "note": f"{NAMES.get(scaling, scaling)} is accepted; not applied"}

        code = self.apply(SAVE_TO_PERSISTENCE if persist else 0)
        if code != 0:
            words[_OFF_SCALING] = previous
            return {"ok": False, "changed": False, "previous": previous,
                    "error": f"could not apply {NAMES.get(scaling, scaling)}: "
                             f"{self._explain(code)}"}
        return {"ok": True, "changed": True, "previous": previous,
                "scaling": scaling, "persisted": bool(persist),
                "note": f"scaling set to {NAMES.get(scaling, scaling)}"}


def read() -> Report:
    """What each display does with a mode that is not its native size."""
    try:
        with _Config() as config:
            return Report(available=True, screens=config.screens())
    except ScalingError as exc:
        return Report(available=False, reason=str(exc))
    except OSError as exc:                  # a driver that loads but misbehaves
        return Report(available=False, reason=f"NVIDIA driver call failed: {exc}")


def set_scaling(display_id: int, scaling: int = PREFERRED,
                apply: bool = False, persist: bool = False) -> dict:
    """Change one display's scaling, validating before committing.

    With ``apply`` left off the change is only validated, which is how a caller
    can find out whether the driver would take it without changing anything.

    ``persist`` writes the choice into the driver's own store so it outlives
    the session. The launcher does not use it -- it puts the old value back
    on the way out -- but somebody who wants the setting to simply stay
    right does, and then the launcher finds nothing to change.
    """
    try:
        with _Config() as config:
            return config.set_scaling(display_id, scaling, commit=apply,
                                      persist=persist)
    except ScalingError as exc:
        return {"ok": False, "changed": False, "error": str(exc)}


def ensure_fill(display_id: Optional[int] = None, apply: bool = False,
                persist: bool = False) -> dict:
    """Make sure a stretched mode will reach the edges of the panel.

    Defaults to the display the desktop treats as primary, which is the one
    ``window.set_mode`` switches and therefore the one CS2 ends up on.

    Does nothing when that display already fills, so calling it on every launch
    costs a single read on a machine that is already set up correctly.
    """
    try:
        with _Config() as config:
            screens = config.screens()
            if display_id is None:
                chosen = next((s for s in screens if s.primary), None)
                if chosen is None:
                    return {"ok": False, "changed": False,
                            "error": "no primary display reported"}
            else:
                chosen = next((s for s in screens if s.display_id == display_id), None)
                if chosen is None:
                    return {"ok": False, "changed": False,
                            "error": f"no display with id 0x{display_id:08X}"}

            if chosen.fills:
                return {"ok": True, "changed": False, "already": True,
                        "display_id": chosen.display_id,
                        "previous": chosen.scaling, "scaling": chosen.scaling,
                        "note": f"the display already fills the screen ({chosen.name})"}

            result = config.set_scaling(chosen.display_id, PREFERRED,
                                        commit=apply, persist=persist)
            result["display_id"] = chosen.display_id
            result["was"] = chosen.name
            return result
    except ScalingError as exc:
        return {"ok": False, "changed": False, "error": str(exc)}


def summary() -> dict:
    """The shape the web front end and the CLI both render."""
    report = read()
    return {
        "available": report.available,
        "reason": report.reason,
        "all_fill": report.all_fill,
        "displays": [
            {
                "id": f"0x{s.display_id:08X}",
                "display_id": s.display_id,
                "scaling": s.scaling,
                "name": s.name,
                "fills": s.fills,
                "bars": s.bars,
                "primary": s.primary,
                "width": s.width,
                "height": s.height,
                "refresh": s.refresh,
            }
            for s in report.screens
        ],
    }
