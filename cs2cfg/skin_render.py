"""Turning one chosen weapon-and-finish into a model to look at -- and
nothing surviving the look.

This runs a tool the user installed themselves (ValveResourceFormat /
Source2Viewer-CLI -- the one Valve's own developer wiki points modders at)
against the VPK the game already has on disk, the same way this project
would shell out to ``ffmpeg`` if a feature ever needed it: the tool is never
fetched or run by anything other than the user's own choice to install it
and point this application at it.

The output lives in a throwaway temp directory for exactly as long as it
takes to read the bytes back into memory, then the directory -- and
everything the tool wrote into it -- is gone. Nothing from this module is
ever written into this application's own data folder, cached to disk
longer than one call, or kept in the inventory data :mod:`cs2cfg.inventory`
holds. Ask again later and the tool runs again.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, NamedTuple, Optional

from . import vpk

TIMEOUT = 60.0
PREF_KEY = "source2viewer_path"

VMAT_DIR = "materials/models/weapons/customization/paints/vmats/"
_TEXTURE_PARAM = re.compile(
    r'm_name = "(?P<name>g_t[A-Za-z]+)"\s*\r?\n\s*m_pValue = resource:"(?P<path>[^"]+)"')
_PAINT_STYLE = re.compile(r'F_PAINT_STYLE\s*=\s*(\d+)')

# Valve's weapon shader (csgo_customweapon.vfx) picks how a skin's texture
# maps onto the model by this flag. Style 7 ("Gunsmith" -- the case-hardened
# / patina finishes) is a small tileable pattern meant to repeat across the
# gun; everything else observed (6, "Custom Paint Job", covers Workshop
# designs like Asiimov or Kill Confirmed) is one image mapped 1:1 over the
# whole weapon. Tiling one of those produces exactly the shattered-looking
# mess a repeated detailed image makes across many small UV triangles --
# confirmed by rendering Kill Confirmed (style 6) both ways. Unrecognised
# styles default to not tiling, since direct 1:1 is the common case.
_TILED_PAINT_STYLES = {7}

# A model render can need up to three invocations of the tool in a row
# (legacy-skin texture resolution runs its own lookup pass before the
# export). The tool is a ~100MB self-contained .NET app with no warm start
# of its own, and running more than one copy of it at once -- someone
# opening a second skin before the first finished -- made launches of it
# contend badly enough to look hung rather than just slow. One at a time,
# server-wide, fixes that: a browser click that is abandoned for a newer
# one still finishes its own turn, it just finishes it quickly because
# nothing else is competing for the same disk and CPU.
_TOOL_LOCK = threading.Lock()


class RenderError(RuntimeError):
    """The tool could not be run, or did not produce a usable model."""


def tool_path(prefs: Dict[str, str]) -> Optional[Path]:
    """Where the user said their copy of the tool lives, if it is actually
    there right now -- never assumed, always checked fresh."""
    raw = (prefs or {}).get(PREF_KEY, "")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def status(prefs: Dict[str, str]) -> Dict[str, Any]:
    raw = (prefs or {}).get(PREF_KEY, "")
    found = tool_path(prefs)
    return {
        "configured": bool(raw),
        "found": found is not None,
        "path": raw,
    }


def render(dir_vpk: Path, model_path: str, tool_exe: Path,
          timeout: float = TIMEOUT) -> bytes:
    """Export one weapon model out of the VPK and hand back the raw glTF
    binary. Never raises past a clear :class:`RenderError`; never leaves
    anything behind once it returns."""
    compiled = model_path if model_path.endswith("_c") else model_path + "_c"

    with tempfile.TemporaryDirectory(prefix="cs2cfg_skin_") as tmp:
        tmp_path = Path(tmp)
        args = [str(tool_exe), "-i", str(dir_vpk), "--vpk_filepath", compiled,
               "-o", str(tmp_path), "-d", "--gltf_export_format", "glb",
               "--gltf_export_materials"]
        try:
            with _TOOL_LOCK:
                result = subprocess.run(args, timeout=timeout, capture_output=True)
        except subprocess.TimeoutExpired:
            raise RenderError("the viewer tool took too long to answer")
        except OSError as exc:
            raise RenderError(f"could not run the viewer tool: {exc}")

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or b"").decode("utf-8", "replace")[:300]
            raise RenderError(f"the viewer tool could not export that model: {detail}".strip())

        glbs = list(tmp_path.rglob("*.glb"))
        if not glbs:
            raise RenderError("the viewer tool did not produce a model file")
        return glbs[0].read_bytes()
    # The temp directory, and anything exported into it, is removed here --
    # the whole reason this is a context manager rather than a plain path.


class TextureInfo(NamedTuple):
    path: str
    tiled: bool  # whether this texture repeats across the model's UVs, or
                 # is a single direct 1:1 image the way most skins' are


def _composite_texture_path(index: Dict[str, "vpk.Entry"], paintkit: str) -> Optional[str]:
    """A newer skin's own colour texture, found directly by name -- no tool
    invocation needed, since it is just another file in the VPK."""
    wanted = f"{paintkit}_albedo"
    for path in index:
        if "/paintkits/" in path and wanted in path and path.endswith(".vtex_c"):
            return path
    return None


def _legacy_vmat_path(index: Dict[str, "vpk.Entry"], paintkit: str) -> Optional[str]:
    """An older skin's single material file, if it has one. Tried by exact
    name first, then by the weapon-specific variants Valve sometimes used
    (``<paintkit>_<weapon>.vmat_c``)."""
    exact = f"{VMAT_DIR}{paintkit}.vmat_c"
    if exact in index:
        return exact
    prefix = f"{VMAT_DIR}{paintkit}_"
    for path in index:
        if path.startswith(prefix) and path.endswith(".vmat_c"):
            return path
    return None


def _legacy_pattern_texture(dir_vpk: Path, vmat_path: str, tool_exe: Path,
                            timeout: float) -> Optional[TextureInfo]:
    """The skin-specific texture an older single-material skin uses, and
    whether it is meant to tile.

    ``-d`` (the normal decompile/convert path) crashes on these -- it tries
    to resolve the material through its shader, and the shader format CS2
    now ships is newer than this build of the tool understands. ``-a``
    sidesteps that entirely: it just prints the resource's own raw data,
    which already lists every texture the material points at by name, and
    the paint style that says how it is meant to be mapped onto the model
    (see ``_TILED_PAINT_STYLES``). ``g_tPattern`` is the skin's own colour
    map; ``g_tColor`` is a shared default every weapon's base material
    points at when it has no pattern of its own, so it is only a fallback.
    """
    args = [str(tool_exe), "-i", str(dir_vpk), "--vpk_filepath", vmat_path, "-a"]
    try:
        with _TOOL_LOCK:
            result = subprocess.run(args, timeout=timeout, capture_output=True)
    except (subprocess.TimeoutExpired, OSError):
        return None
    text = result.stdout.decode("utf-8", "replace")
    by_name = {m.group("name"): m.group("path") for m in _TEXTURE_PARAM.finditer(text)}
    style_m = _PAINT_STYLE.search(text)
    tiled = bool(style_m) and int(style_m.group(1)) in _TILED_PAINT_STYLES
    for name in ("g_tPattern", "g_tColor"):
        if name in by_name:
            return TextureInfo(by_name[name], tiled)
    return None


def texture_path(dir_vpk: Path, tool_exe: Path, weapon_class: str, paintkit: str,
                 timeout: float = TIMEOUT) -> Optional[TextureInfo]:
    """Which texture (if any) actually gives this weapon/paintkit combo its
    colour -- preferring a newer skin's own ready-made texture, falling
    back to resolving an older skin's single material. ``None`` means no
    texture could be identified, not that the lookup failed silently."""
    index = vpk.read_index(dir_vpk)
    composite = _composite_texture_path(index, paintkit)
    if composite:
        return TextureInfo(composite, tiled=False)
    vmat = _legacy_vmat_path(index, paintkit)
    if vmat:
        resolved = _legacy_pattern_texture(dir_vpk, vmat, tool_exe, timeout)
        if resolved:
            path = resolved.path if resolved.path.endswith("_c") else resolved.path + "_c"
            return TextureInfo(path, resolved.tiled)
    return None


def render_texture(dir_vpk: Path, texture_path_: str, tool_exe: Path,
                   timeout: float = TIMEOUT) -> bytes:
    """Export one texture out of the VPK and hand back the decoded image
    bytes. Same ephemeral guarantee as :func:`render`."""
    compiled = texture_path_ if texture_path_.endswith("_c") else texture_path_ + "_c"

    with tempfile.TemporaryDirectory(prefix="cs2cfg_skintex_") as tmp:
        tmp_path = Path(tmp)
        args = [str(tool_exe), "-i", str(dir_vpk), "--vpk_filepath", compiled,
               "-o", str(tmp_path), "-d"]
        try:
            with _TOOL_LOCK:
                result = subprocess.run(args, timeout=timeout, capture_output=True)
        except subprocess.TimeoutExpired:
            raise RenderError("the viewer tool took too long to answer")
        except OSError as exc:
            raise RenderError(f"could not run the viewer tool: {exc}")

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or b"").decode("utf-8", "replace")[:300]
            raise RenderError(f"the viewer tool could not export that texture: {detail}".strip())

        images = [p for p in tmp_path.rglob("*")
                 if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        if not images:
            raise RenderError("the viewer tool did not produce an image file")
        return images[0].read_bytes()
