"""Hold the sound devices where the player put them.

Somebody with one headset never thinks about this. Somebody with a headset, a
pair of speakers, a stream mixer and two microphones thinks about it constantly,
because Windows keeps changing its mind: a driver update, a monitor waking, a
USB interface re-enumerating, and the default has quietly moved to the display's
HDMI output. You find out in the first round, which is the worst time.

So the choice is made here, kept here, and put back here whenever Windows loses
it.

**On writing this at all.** Two interfaces are involved and they are not the
same proposition:

* ``IMMDeviceEnumerator`` is documented. Listing endpoints, reading which one
  is default, resolving a saved id back to a device -- all of that is on solid
  ground.
* ``IPolicyConfig`` is not documented. Microsoft has never published it, and it
  is what every audio switcher on Windows uses because there is no alternative.

Elsewhere this collection refuses undocumented writes -- the NVIDIA profile
database stays read-only for exactly that reason. The difference here is that
this one is **checkable**. Every change is read straight back through the
documented enumerator, and a change that did not take is reported as a failure
rather than assumed. That is the same discipline as the display scaling: write,
then confirm through a path that does not depend on the write being right.

Per-application routing is still not done here, and still for the original
reason: that one goes through a different private interface into a registry
blob whose format is not published, and nothing reads it back. A system default
that this can verify is a different thing from a per-app override it cannot.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import POINTER, byref, c_uint32, c_void_p, c_wchar_p
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

OUTPUT = "output"
INPUT = "input"

# EDataFlow
_RENDER, _CAPTURE = 0, 1
_FLOW = {OUTPUT: _RENDER, INPUT: _CAPTURE}

# DEVICE_STATE_ACTIVE. Unplugged and disabled endpoints are deliberately not
# offered: pinning to something that is not there produces a setting that can
# never be satisfied and an error every time it is tried.
_ACTIVE = 0x1

# ERole. Console and Multimedia together are what the Windows UI calls "Set as
# Default Device". Communications is the separate "default communication
# device" and is left alone -- somebody who has pointed their chat app at a
# different microphone meant it.
_ROLES = (0, 1)

_CLSCTX_ALL = 23
_COINIT_APARTMENTTHREADED = 0x2

# How often to check that the pin still holds. Windows does not announce most
# of the ways a default moves, so this is a poll rather than a subscription;
# five seconds is well inside the gap between a device re-enumerating and the
# player noticing they are talking into the wrong microphone.
INTERVAL = 5.0


class AudioError(RuntimeError):
    pass


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort),
                ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]


class _PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]


class _PropVariant(ctypes.Structure):
    """Only as much of PROPVARIANT as a string property needs."""
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort),
                ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("value", c_void_p), ("tail", c_void_p)]


_ole32 = None


def _ole():
    global _ole32
    if _ole32 is None:
        _ole32 = ctypes.windll.ole32
    return _ole32


def _guid(text: str) -> _GUID:
    found = _GUID()
    if _ole().CLSIDFromString(c_wchar_p(text), byref(found)) != 0:
        raise AudioError(f"bad identifier {text}")
    return found


_CLSID_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
_IID_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
_CLSID_POLICY = "{870af99c-171d-4f9e-af0d-e63df40c2bc9}"
_IID_POLICY = "{f8679f50-850a-41cf-9c72-430f290290c8}"

# PKEY_Device_FriendlyName: the name the Sound panel shows.
_PKEY_FRIENDLY = ("{a45c254e-df1c-4efd-8020-67d146a850e0}", 14)

# Vtable slots. IUnknown takes 0-2 on every interface.
_ENUM_ENDPOINTS, _ENUM_DEFAULT, _ENUM_GET = 3, 4, 5
_COLL_COUNT, _COLL_ITEM = 3, 4
_DEV_PROPERTIES, _DEV_ID, _DEV_STATE = 4, 5, 6
_STORE_GET_VALUE = 5
# IPolicyConfig::SetDefaultEndpoint, after GetMixFormat, GetDeviceFormat,
# ResetDeviceFormat, SetDeviceFormat, Get/SetProcessingPeriod, Get/SetShareMode
# and Get/SetPropertyValue. Getting this wrong calls a neighbouring method with
# the wrong arguments, which is why nothing is trusted until it is read back.
_POLICY_SET_DEFAULT = 13


def _call(pointer, index, *args, argtypes=(), restype=ctypes.c_long):
    table = ctypes.cast(pointer, POINTER(POINTER(c_void_p)))[0]
    function = ctypes.CFUNCTYPE(restype, c_void_p, *argtypes)(table[index])
    return function(pointer, *args)


def _release(pointer) -> None:
    if pointer:
        _call(pointer, 2)


class _Com:
    """One COM apartment for the length of a call, released on the way out.

    Each worker initialises its own: the keeper runs on its own thread, and an
    apartment belongs to the thread that entered it.
    """

    def __enter__(self) -> "_Com":
        self._owned = _ole().CoInitializeEx(None, _COINIT_APARTMENTTHREADED) in (0, 1)
        self._held: List[Any] = []
        return self

    def __exit__(self, *_exc) -> None:
        for pointer in reversed(self._held):
            _release(pointer)
        self._held = []
        if self._owned:
            _ole().CoUninitialize()

    def keep(self, pointer):
        self._held.append(pointer)
        return pointer

    def create(self, clsid: str, iid: str):
        pointer = c_void_p()
        code = _ole().CoCreateInstance(byref(_guid(clsid)), None, _CLSCTX_ALL,
                                       byref(_guid(iid)), byref(pointer))
        if code != 0 or not pointer:
            raise AudioError(f"the audio service did not answer (0x{code & 0xFFFFFFFF:08X})")
        return self.keep(pointer)


@dataclass
class Device:
    id: str
    name: str
    kind: str
    default: bool = False

    @property
    def short(self) -> str:
        return self.name


@dataclass
class Pin:
    """What the player chose, and whether to keep putting it back."""
    output: str = ""
    input: str = ""
    enforce: bool = True

    @property
    def anything(self) -> bool:
        return bool(self.output or self.input)

    def wanted(self, kind: str) -> str:
        return self.output if kind == OUTPUT else self.input


def _device_id(com: _Com, device) -> str:
    text = c_wchar_p()
    if _call(device, _DEV_ID, byref(text), argtypes=[POINTER(c_wchar_p)]) != 0:
        return ""
    found = text.value or ""
    _ole().CoTaskMemFree(text)
    return found


def _device_name(com: _Com, device) -> str:
    store = c_void_p()
    if _call(device, _DEV_PROPERTIES, 0, byref(store),
             argtypes=[c_uint32, POINTER(c_void_p)]) != 0:
        return ""
    com.keep(store)
    key = _PropertyKey(_guid(_PKEY_FRIENDLY[0]), _PKEY_FRIENDLY[1])
    value = _PropVariant()
    if _call(store, _STORE_GET_VALUE, byref(key), byref(value),
             argtypes=[POINTER(_PropertyKey), POINTER(_PropVariant)]) != 0:
        return ""
    # VT_LPWSTR
    if value.vt != 31 or not value.value:
        return ""
    return ctypes.cast(value.value, c_wchar_p).value or ""


def _read(com: _Com, kind: str) -> List[Device]:
    enumerator = com.create(_CLSID_ENUMERATOR, _IID_ENUMERATOR)
    flow = _FLOW[kind]

    default_id = ""
    current = c_void_p()
    if _call(enumerator, _ENUM_DEFAULT, flow, _ROLES[0], byref(current),
             argtypes=[c_uint32, c_uint32, POINTER(c_void_p)]) == 0 and current:
        com.keep(current)
        default_id = _device_id(com, current)

    collection = c_void_p()
    if _call(enumerator, _ENUM_ENDPOINTS, flow, _ACTIVE, byref(collection),
             argtypes=[c_uint32, c_uint32, POINTER(c_void_p)]) != 0:
        return []
    com.keep(collection)

    count = c_uint32()
    if _call(collection, _COLL_COUNT, byref(count),
             argtypes=[POINTER(c_uint32)]) != 0:
        return []

    found: List[Device] = []
    for index in range(count.value):
        device = c_void_p()
        if _call(collection, _COLL_ITEM, index, byref(device),
                 argtypes=[c_uint32, POINTER(c_void_p)]) != 0 or not device:
            continue
        com.keep(device)
        identifier = _device_id(com, device)
        if not identifier:
            continue
        found.append(Device(id=identifier, name=_device_name(com, device) or identifier,
                            kind=kind, default=identifier == default_id))
    found.sort(key=lambda d: d.name.lower())
    return found


def devices(kind: Optional[str] = None) -> Dict[str, List[Device]]:
    """Every endpoint currently plugged in and switched on."""
    out: Dict[str, List[Device]] = {}
    kinds = [kind] if kind else [OUTPUT, INPUT]
    try:
        with _Com() as com:
            for one in kinds:
                out[one] = _read(com, one)
    except (AudioError, OSError):
        for one in kinds:
            out.setdefault(one, [])
    return out


def current(kind: str) -> Optional[Device]:
    for device in devices(kind).get(kind, []):
        if device.default:
            return device
    return None


def _set_default(com: _Com, device_id: str) -> None:
    policy = com.create(_CLSID_POLICY, _IID_POLICY)
    for role in _ROLES:
        code = _call(policy, _POLICY_SET_DEFAULT, c_wchar_p(device_id), role,
                     argtypes=[c_wchar_p, c_uint32])
        if code != 0:
            raise AudioError(f"Windows refused the change (0x{code & 0xFFFFFFFF:08X})")


def apply(device_id: str, kind: str) -> Dict[str, Any]:
    """Make one endpoint the default, and check that it actually became it.

    The check is the point. The interface that does the setting is not
    documented, so its success code is not something to take on trust; the
    documented enumerator is asked afterwards and its answer is what this
    reports.
    """
    if kind not in _FLOW:
        return {"ok": False, "error": f"unknown kind {kind!r}"}
    if not device_id:
        return {"ok": False, "error": "no device chosen"}

    try:
        with _Com() as com:
            available = {d.id: d for d in _read(com, kind)}
            if device_id not in available:
                return {"ok": False, "missing": True,
                        "error": "that device is not plugged in at the moment"}
            was = next((d.id for d in available.values() if d.default), "")
            if was == device_id:
                return {"ok": True, "changed": False,
                        "device": available[device_id].name,
                        "note": f"{available[device_id].name} was already the default"}
            _set_default(com, device_id)

        # Fresh session on purpose: the check must not be able to read back a
        # value cached by the call that made it.
        with _Com() as com:
            now = next((d for d in _read(com, kind) if d.default), None)
    except (AudioError, OSError) as exc:
        return {"ok": False, "error": str(exc)}

    if now is None or now.id != device_id:
        return {"ok": False, "error": "Windows reported success but the default "
                                      "did not move; nothing was changed"}
    return {"ok": True, "changed": True, "device": now.name,
            "note": f"{now.name} is now the default {kind}"}


class Keeper:
    """Puts the pinned devices back whenever Windows moves them.

    Runs on its own thread and only acts on a difference, so a machine that
    stays where it was put costs one enumeration every few seconds and writes
    nothing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pin = Pin()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.corrections = 0
        self.last: str = ""
        self.waiting: List[str] = []

    def set_pin(self, pin: Pin) -> None:
        with self._lock:
            self._pin = pin
        if pin.enforce and pin.anything:
            self.start()
        else:
            self.stop()

    @property
    def pin(self) -> Pin:
        with self._lock:
            return self._pin

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def check(self) -> List[str]:
        """One pass. Returns what it had to put back."""
        pin = self.pin
        if not (pin.enforce and pin.anything):
            return []

        fixed: List[str] = []
        waiting: List[str] = []
        for kind in (OUTPUT, INPUT):
            wanted = pin.wanted(kind)
            if not wanted:
                continue
            try:
                with _Com() as com:
                    found = {d.id: d for d in _read(com, kind)}
            except (AudioError, OSError):
                continue
            if wanted not in found:
                # Unplugged. Fighting over a device that is not there would
                # mean an error every few seconds for as long as it is away.
                waiting.append(kind)
                continue
            if found[wanted].default:
                continue
            result = apply(wanted, kind)
            if result.get("changed"):
                fixed.append(f"{kind} put back to {result.get('device', wanted)}")

        with self._lock:
            self.waiting = waiting
            if fixed:
                self.corrections += len(fixed)
                self.last = time.strftime("%H:%M:%S")
        return fixed

    def _watch(self) -> None:
        while not self._stop.wait(INTERVAL):
            try:
                self.check()
            except Exception:
                # A keeper that dies on one bad poll stops keeping anything.
                continue

    def status(self) -> Dict[str, Any]:
        pin = self.pin
        with self._lock:
            return {
                "enforcing": self.running,
                "corrections": self.corrections,
                "last": self.last,
                "waiting": list(self.waiting),
                # Named apart from the device lists on purpose: summary() merges
                # this in, and "output" meaning both "every output" and "the
                # pinned one" silently replaced the list with a single id.
                "pinned_output": pin.output,
                "pinned_input": pin.input,
                "enforce": pin.enforce,
            }


_keeper: Optional[Keeper] = None


def shared() -> Keeper:
    global _keeper
    if _keeper is None:
        _keeper = Keeper()
    return _keeper


def summary() -> Dict[str, Any]:
    """Everything the settings page needs."""
    found = devices()
    keeper = shared()
    pin = keeper.pin

    def shape(kind: str) -> List[Dict[str, Any]]:
        return [{"id": d.id, "name": d.name, "default": d.default,
                 "pinned": d.id == pin.wanted(kind)}
                for d in found.get(kind, [])]

    out = {"ok": True, "output": shape(OUTPUT), "input": shape(INPUT)}
    out.update(keeper.status())
    # A pin whose device is not in the list is not an error -- it is a headset
    # that is switched off. Saying which is more use than dropping the setting.
    for kind in (OUTPUT, INPUT):
        wanted = pin.wanted(kind)
        if wanted and not any(d["id"] == wanted for d in out[kind]):
            out[f"{kind}_missing"] = True
    return out
