r"""Windows' own per-application graphics settings.

Settings > System > Display > Graphics, where Windows lets you say which
graphics card an application should use and whether it gets the windowed-mode
fast path. Both live in one registry value per executable, under the current
user -- no service, no elevation, nothing machine-wide:

    HKCU\Software\Microsoft\DirectX\UserGpuPreferences
        <full path to the exe> = "GpuPreference=2;SwapEffectUpgradeEnable=1;"

Two settings are worth setting for CS2 and nothing else here is:

``GpuPreference``
    Which card to render on. 0 is "let Windows decide", 1 is power saving, 2
    is high performance. It matters on a machine with two graphics adapters,
    which is most laptops and any desktop whose processor has graphics built
    in -- Windows picks per application and does not always pick the fast one.
    On a machine with one adapter it is harmless and does nothing.

``SwapEffectUpgradeEnable``
    "Optimisations for windowed games". Windows 10 2004 and later can hand a
    borderless window the same flip presentation path exclusive fullscreen
    gets, which takes a frame of latency out. It only does anything for a game
    in a window -- which is how this application sets CS2 up, so it applies.

What this deliberately does not touch: Game Mode, Auto HDR, variable refresh
rate, and the global defaults on the same settings page. Those are machine
wide or affect every application, and a per-game tool has no business
changing them on somebody's behalf.

Nothing here writes unless ``apply`` is called.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"

GPU_PREFERENCE = "GpuPreference"
WINDOWED = "SwapEffectUpgradeEnable"

HIGH_PERFORMANCE = "2"
WINDOWED_ON = "1"

# Where CS2's executable sits inside the install, which is what Windows keys
# these settings on -- not the Steam shortcut, and not the launcher.
EXE_REL = ("game", "bin", "win64", "cs2.exe")


def exe_path(install: Optional[Path]) -> Optional[Path]:
    """The executable Windows would file these settings under."""
    if not install:
        return None
    found = Path(install).joinpath(*EXE_REL)
    return found if found.is_file() else None


def parse(value: str) -> Dict[str, str]:
    """Split ``"GpuPreference=2;SwapEffectUpgradeEnable=1;"`` into its parts.

    Windows writes them in one string separated by semicolons, and other
    applications put their own settings in the same value -- AppStatus turns
    up in the wild. Anything not understood is carried through untouched
    rather than dropped, because it is not this application's to discard.
    """
    out: Dict[str, str] = {}
    for part in (value or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, setting = part.partition("=")
        out[name.strip()] = setting.strip()
    return out


def render(settings: Dict[str, str]) -> str:
    """Back into the one string Windows stores, in a stable order."""
    return "".join(f"{name}={value};" for name, value in settings.items())


def read(exe: Optional[Path]) -> Dict[str, str]:
    """What Windows currently has for this executable. Never raises."""
    if sys.platform != "win32" or not exe:
        return {}
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            value, _ = winreg.QueryValueEx(key, str(exe))
    except OSError:
        return {}
    return parse(str(value))


def wanted(current: Dict[str, str]) -> Dict[str, str]:
    """The same settings with the two this application cares about set.

    Built by copying rather than replacing, so a setting some other tool put
    in the same value survives.
    """
    out = dict(current)
    out[GPU_PREFERENCE] = HIGH_PERFORMANCE
    out[WINDOWED] = WINDOWED_ON
    return out


def describe(install: Optional[Path], multi_gpu: bool = True) -> Dict[str, Any]:
    """Everything the page needs, without changing anything."""
    exe = exe_path(install)
    if sys.platform != "win32":
        return {"supported": False, "reason": "this is a Windows setting"}
    if exe is None:
        return {"supported": False, "reason": "CS2's executable was not found"}
    current = read(exe)
    return {
        "supported": True,
        "exe": str(exe),
        "gpu_preference": current.get(GPU_PREFERENCE, ""),
        "windowed": current.get(WINDOWED, ""),
        "high_performance": current.get(GPU_PREFERENCE) == HIGH_PERFORMANCE,
        "windowed_optimised": current.get(WINDOWED) == WINDOWED_ON,
        "done": current == wanted(current),
        # Said plainly rather than hidden: on a single-adapter machine the
        # card choice genuinely does nothing, and claiming a win there would
        # be a lie somebody could measure.
        "gpu_choice_matters": bool(multi_gpu),
    }


def apply(install: Optional[Path]) -> Dict[str, Any]:
    """Write both settings. Only ever called because somebody asked."""
    exe = exe_path(install)
    if sys.platform != "win32":
        return {"ok": False, "error": "this is a Windows setting"}
    if exe is None:
        return {"ok": False, "error": "CS2's executable was not found"}

    current = read(exe)
    target = wanted(current)
    if current == target:
        return {"ok": True, "changed": False, "exe": str(exe),
                "detail": "Windows already has CS2 set to high performance"}
    try:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, str(exe), 0, winreg.REG_SZ, render(target))
    except OSError as exc:
        return {"ok": False, "error": f"could not write the setting: {exc}"}
    return {"ok": True, "changed": True, "exe": str(exe), "was": render(current),
            "now": render(target),
            "detail": "Windows will run CS2 on the high performance card, "
                      "with windowed optimisations on"}


def clear(install: Optional[Path]) -> Dict[str, Any]:
    """Put it back to letting Windows decide.

    Removes the whole value only when nothing else is left in it; otherwise
    the two settings are dropped and anything another tool wrote is kept.
    """
    exe = exe_path(install)
    if sys.platform != "win32" or exe is None:
        return {"ok": False, "error": "nothing to clear"}
    current = read(exe)
    if not current:
        return {"ok": True, "changed": False, "detail": "nothing was set"}
    left = {k: v for k, v in current.items() if k not in (GPU_PREFERENCE, WINDOWED)}
    try:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            if left:
                winreg.SetValueEx(key, str(exe), 0, winreg.REG_SZ, render(left))
            else:
                winreg.DeleteValue(key, str(exe))
    except OSError as exc:
        return {"ok": False, "error": f"could not clear the setting: {exc}"}
    return {"ok": True, "changed": True, "detail": "Windows decides again"}
