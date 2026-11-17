"""Settings that follow a Steam account from one PC to the next, on their own.

The problem this solves happened for real: the app installed on a second PC,
signed into the same Steam account, and nothing there -- no autoexec, no
scripts, no binds, none of the choices made on the first machine. The manual
answers already exist (a ``.cs2setup`` file, the profile sync button), and
both need somebody to remember to press them on the right PC at the right
time. This is the same thing without the remembering.

What travels
------------

* the account's own preferences -- intent, target fps, theme, setups, the
  checkboxes -- the same list a ``.cs2setup`` carries, plus a few more;
* the account's config files: the collection folder it uses, the folder the
  app generates into, and ``autoexec.cfg`` at the top of the game's cfg
  folder. Paths are kept relative to that cfg folder, because the same game is
  on a different drive on every PC.

What does not
-------------

* ``cs2_video.txt`` and the launch options. They describe the hardware, not
  the player: a picture tuned for one GPU is wrong on another. The intent that
  produced them travels instead, and the next apply on the other PC builds the
  right ones for that machine.
* the sound devices, companion program paths, window layout -- this machine's.
* anything secret. The bundle goes to the account's own storage on the Worker
  and nowhere else, and holds nothing a ``.cs2setup`` would not.

How it decides
--------------

A three-way compare, the way any sync tool does it: the hash of what is here,
the hash of what is in the cloud, and the hash of what the two last agreed on.
Only this side changed -> push. Only the cloud changed -> pull. Both changed
(or this PC has never synced) -> the newer one wins, and since every pull
goes through a backup first, losing that race is an undo away rather than a
lost config.

Pulled config files are written only once the player has allowed the app to
write into the game's cfg folder (the first-run wizard asks). Until then the
preferences come across and the files wait.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from . import portable

SCHEMA = 1

# The Worker keeps one JSON document per account and refuses anything over
# 256 KB. The bundle is compressed before it is encoded, and capped well under
# that so the rest of the document (profile collections) still fits beside it.
MAX_PACKED = 180 * 1024
MAX_FILE = 256 * 1024

STEAM64_BASE = 76561197960265728

# Preferences that describe the player rather than this machine.
SYNCED_PREFS = tuple(dict.fromkeys(portable.CARRIED + (
    "theme",
    "hide_crosshair",
    "crosshairx_launch",
    "load_bias",
    "setups",
    "setup_live",
    "faceit_nick",
    "faceit_id",
    "demo_key",
    "demo_once",
    "win_graphics_auto",
)))

# Config files the game reads, and nothing else. A cfg folder also collects
# logs and screenshots of console output; those are not settings.
SUFFIXES = (".cfg", ".vcfg")

# Machine-wide preference keys this module owns.
AUTO_KEY = "sync_auto"           # default on once signed in
STATE_FILE = "sync_state.json"   # last agreed hash, per account
CFG_WRITE_KEY = "cfg_write_ok"   # set by the first-run wizard


class SyncError(RuntimeError):
    """Something a person can be shown."""


# --- identity ---------------------------------------------------------------

def account_from_steam64(steam_id: Any) -> str:
    """The 32-bit account id Steam uses for userdata folders."""
    try:
        value = int(str(steam_id).strip())
    except (TypeError, ValueError):
        return ""
    if value >= STEAM64_BASE:
        value -= STEAM64_BASE
    return str(value) if value > 0 else ""


# --- reading what is here ---------------------------------------------------

def _safe_relative(relative: str) -> bool:
    if not isinstance(relative, str) or not relative:
        return False
    if relative.startswith(("/", "\\")) or ":" in relative or "\\" in relative:
        return False
    if Path(relative).suffix.lower() not in SUFFIXES:
        return False
    return ".." not in Path(relative).parts


def safe_target(cfg_root: Path, relative: str) -> Optional[Path]:
    """Where a file named by the cloud may be written, or None if nowhere.

    The name came off the network. It is checked by shape first and then by
    where it actually resolves to, because the second check is the one that
    cannot be talked around.
    """
    if not _safe_relative(relative):
        return None
    root = Path(cfg_root).resolve()
    candidate = (root / Path(relative)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _relative_folder(cfg_root: Path, folder: Any) -> str:
    """A collection folder as a name under the cfg folder, or "" if outside."""
    if not folder:
        return ""
    try:
        rel = Path(str(folder)).resolve().relative_to(Path(cfg_root).resolve())
    except (ValueError, OSError):
        return ""
    text = rel.as_posix()
    return "" if text in ("", ".") else text


def collect_files(cfg_root: Path, folders: Iterable[str],
                  loose: Iterable[str] = ("autoexec.cfg",)) -> Dict[str, str]:
    """``{relative path: text}`` for every config file worth carrying."""
    root = Path(cfg_root)
    out: Dict[str, str] = {}

    def take(path: Path) -> None:
        try:
            if not path.is_file() or path.suffix.lower() not in SUFFIXES:
                return
            if path.stat().st_size > MAX_FILE:
                return
            rel = path.relative_to(root).as_posix()
            out[rel] = path.read_bytes().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            return

    for name in loose:
        take(root / name)
    for folder in folders:
        if not folder:
            continue
        base = root / folder
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                take(path)
    return out


def build(ui: Dict[str, Any], cfg_root: Optional[Path],
          generated_folder: str = "") -> Dict[str, Any]:
    """The bundle for one account: its preferences and its config files."""
    prefs = {k: ui[k] for k in SYNCED_PREFS if k in ui}
    collection = _relative_folder(cfg_root, ui.get("cfg_folder")) if cfg_root else ""
    files: Dict[str, str] = {}
    if cfg_root and Path(cfg_root).is_dir():
        folders = [f for f in dict.fromkeys((collection, generated_folder)) if f]
        files = collect_files(Path(cfg_root), folders)
    return {"prefs": prefs, "collection": collection, "files": files}


def fingerprint(bundle: Dict[str, Any]) -> str:
    body = json.dumps({"prefs": bundle.get("prefs") or {},
                       "collection": bundle.get("collection") or "",
                       "files": bundle.get("files") or {}},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def newest_local_change(cfg_root: Optional[Path], bundle: Dict[str, Any]) -> float:
    """When the files in the bundle were last touched here."""
    newest = 0.0
    if not cfg_root:
        return newest
    for rel in bundle.get("files") or {}:
        try:
            newest = max(newest, (Path(cfg_root) / rel).stat().st_mtime)
        except OSError:
            continue
    return newest


# --- the wire format ---------------------------------------------------------

def pack(bundle: Dict[str, Any], machine: str = "") -> Dict[str, Any]:
    raw = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    data = base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
    if len(data) > MAX_PACKED:
        raise SyncError(f"this account's config files are too large to sync "
                        f"({len(data) // 1024} KB packed, limit {MAX_PACKED // 1024} KB)")
    return {"schema": SCHEMA, "updated_at": time.time(),
            "hash": fingerprint(bundle), "from": machine[:64], "data": data}


def unpack(entry: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(entry, dict) or not isinstance(entry.get("data"), str):
        raise SyncError("the cloud copy is not one this version can read")
    if int(entry.get("schema") or 0) > SCHEMA:
        raise SyncError("the cloud copy was written by a newer version; update first")
    try:
        raw = zlib.decompress(base64.b64decode(entry["data"]))
        bundle = json.loads(raw.decode("utf-8"))
    except (ValueError, zlib.error) as exc:
        raise SyncError("the cloud copy is damaged") from exc
    if not isinstance(bundle, dict):
        raise SyncError("the cloud copy is damaged")
    prefs = bundle.get("prefs") if isinstance(bundle.get("prefs"), dict) else {}
    files = bundle.get("files") if isinstance(bundle.get("files"), dict) else {}
    return {
        # Only the keys this version knows to be the player's. A cloud copy
        # cannot point this machine's audio or companion paths anywhere.
        "prefs": {k: v for k, v in prefs.items() if k in SYNCED_PREFS},
        "collection": str(bundle.get("collection") or ""),
        "files": {k: v for k, v in files.items()
                  if isinstance(v, str) and _safe_relative(k)},
    }


# --- deciding ----------------------------------------------------------------

def decide(local: str, remote: Optional[str], agreed: Optional[str],
           local_empty: bool = False, local_time: float = 0.0,
           remote_time: float = 0.0) -> str:
    """``"none"``, ``"push"`` or ``"pull"``."""
    if remote is None:
        return "none" if local_empty else "push"
    if local == remote:
        return "none"
    if agreed and local == agreed:
        return "pull"
    if agreed and remote == agreed:
        return "push"
    # This PC has never synced: it is the new PC the whole feature is for,
    # and whatever it has (CS2's own defaults, an old autoexec) is not a
    # deliberate change to win over the account's real setup. It takes the
    # cloud's copy -- backed up first -- and anything only it has goes up on
    # the next round.
    if not agreed or local_empty:
        return "pull"
    # Both sides moved since they last agreed. The newer one wins; the pull
    # side is backed up, so losing is an undo away.
    return "pull" if remote_time >= local_time else "push"


# --- remembering what was agreed --------------------------------------------

def _state_path() -> Path:
    from .paths import user_data_dir

    return user_data_dir() / STATE_FILE


def load_agreed() -> Dict[str, Any]:
    try:
        held = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return held if isinstance(held, dict) else {}


def save_agreed(account: str, digest: str) -> None:
    held = load_agreed()
    held[str(account)] = {"hash": digest, "at": time.time()}
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(held, indent=1), encoding="utf-8")


# --- applying a pull ---------------------------------------------------------

def apply(bundle: Dict[str, Any], prefs: Dict[str, Any], account: str,
          cfg_root: Optional[Path], may_write: bool) -> Dict[str, Any]:
    """Bring a cloud bundle into this PC. Changes ``prefs`` in place.

    Every file write is backed up first, like every other write this app
    makes, so a pull is never a one-way door.
    """
    from . import backup, profiles
    from .cfglang import write_config_text

    changes = dict(bundle.get("prefs") or {})
    collection = bundle.get("collection") or ""
    if collection and cfg_root:
        target = safe_folder(cfg_root, collection)
        if target is not None:
            changes["cfg_folder"] = str(target)
    profiles.remember(prefs, account, changes)

    written: List[str] = []
    waiting = 0
    files = bundle.get("files") or {}
    if files and cfg_root and may_write:
        session = backup.BackupSession(note="settings sync from another PC")
        for relative, text in sorted(files.items()):
            path = safe_target(cfg_root, relative)
            if path is None:
                continue
            try:
                if path.is_file() and path.read_bytes().decode(
                        "utf-8", errors="replace") == text:
                    continue
                session.add(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                write_config_text(path, text, "utf-8")
                written.append(relative)
            except OSError:
                continue
        backup.prune()
    elif files:
        waiting = len(files)
    return {"prefs": sorted(changes), "written": written, "waiting": waiting}


def safe_folder(cfg_root: Path, relative: str) -> Optional[Path]:
    if not relative or relative.startswith(("/", "\\")) or ":" in relative:
        return None
    if ".." in Path(relative).parts:
        return None
    root = Path(cfg_root).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


# --- one round ---------------------------------------------------------------

def _machine_name() -> str:
    import platform

    return platform.node() or ""


def run(account: Optional[str], cfg_root: Optional[Path], generated_folder: str = "",
        *, load_prefs: Callable[[], Dict[str, Any]],
        save_prefs: Callable[[Dict[str, Any]], None],
        cloud_module: Any = None, force: bool = False) -> Dict[str, Any]:
    """Compare, then push or pull. Never raises; returns what happened."""
    from . import profiles

    if cloud_module is None:
        from . import cloud as cloud_module

    out: Dict[str, Any] = {"ok": True, "action": "none", "at": time.time()}
    if not account:
        return {**out, "ok": False, "reason": "no Steam account found on this PC"}
    if not cloud_module.signed_in():
        return {**out, "ok": False, "reason": "sign in with Steam to sync"}

    session = cloud_module.load_session()
    owner = account_from_steam64(session.get("steam_id"))
    if not owner:
        return {**out, "ok": False, "reason": "attach your Steam account to sync"}
    if owner != str(account):
        return {**out, "ok": False,
                "reason": "this PC is playing on a different Steam account "
                          "from the one signed in to sync"}

    prefs = load_prefs()
    ui = profiles.ui_for(prefs, account)
    if not force and ui.get(AUTO_KEY) is False:
        return {**out, "ok": False, "reason": "automatic sync is off"}

    local = build(ui, cfg_root, generated_folder)
    local_hash = fingerprint(local)
    local_empty = not local["files"] and not local["prefs"]

    try:
        held = cloud_module.pull_settings()
    except cloud_module.CloudError as exc:
        return {**out, "ok": False, "reason": str(exc)}
    document = (held.get("settings") or {}) if held.get("found") else {}
    if not isinstance(document, dict):
        document = {}
    entries = document.get("autosync") if isinstance(document.get("autosync"), dict) else {}
    entry = entries.get(str(account))

    agreed = (load_agreed().get(str(account)) or {}).get("hash")
    remote_hash = entry.get("hash") if isinstance(entry, dict) else None
    action = decide(local_hash, remote_hash, agreed, local_empty,
                    newest_local_change(cfg_root, local),
                    float(entry.get("updated_at") or 0) if isinstance(entry, dict) else 0.0)

    try:
        if action == "push":
            packed = pack(local, _machine_name())
            entries = {**entries, str(account): packed}
            cloud_module.push_settings({**document, "autosync": entries})
            save_agreed(account, local_hash)
            out.update(action="push", files=len(local["files"]))
        elif action == "pull":
            bundle = unpack(entry)
            prefs = load_prefs()
            may_write = bool(prefs.get("ui", {}).get(CFG_WRITE_KEY))
            result = apply(bundle, prefs, account, cfg_root, may_write)
            save_prefs(prefs)
            if result["waiting"]:
                # Not agreed yet: the files have not landed. The next round
                # after permission is given will pull again.
                out.update(action="pull", **result)
            else:
                # Agreed on the cloud's copy, not on what is here now: files
                # this PC has and the cloud lacks then read as a local change
                # and go up on the next round, so the two converge.
                save_agreed(account, remote_hash)
                out.update(action="pull", **result, source=entry.get("from") or "")
        else:
            if remote_hash and remote_hash == local_hash and agreed != local_hash:
                save_agreed(account, local_hash)
    except (SyncError, cloud_module.CloudError) as exc:
        return {**out, "ok": False, "reason": str(exc)}
    return out


# --- in the background -------------------------------------------------------

class Loop:
    """Runs a round every so often while the app is open."""

    def __init__(self, round_fn: Callable[..., Dict[str, Any]],
                 every: float = 120.0, first_after: float = 5.0) -> None:
        self.round_fn = round_fn
        self.every = every
        self.first_after = first_after
        self.last: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="autosync",
                                            daemon=True)
            self._thread.start()

    def nudge(self) -> None:
        """Run the next round now rather than at the next tick."""
        self._wake.set()

    def once(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            try:
                result = self.round_fn(force=force)
            except Exception as exc:   # a sync must never take the app down
                result = {"ok": False, "action": "none", "reason": str(exc),
                          "at": time.time()}
            self.last = result
            return result

    def _loop(self) -> None:
        self._wake.wait(self.first_after)
        while True:
            self._wake.clear()
            self.once()
            self._wake.wait(self.every)
