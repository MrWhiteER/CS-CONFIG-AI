"""The change history: everything that changed, with Keep or Put back on each.

Three kinds of change end up here, from three places:

* **The app's own changes.** Every write the app makes already starts a backup
  set holding each file as it was before (cs2cfg/backup.py). The history is
  read straight off those sets, so nothing new has to be remembered for them:
  what a change did is the difference between the file before it and the file
  after it -- the next set's copy of the same file, or the file as it is now.
* **Changes made inside CS2.** The game writes its own settings files when it
  quits; cs2cfg/gamewatch.py compares them and hands each finding over here.
* **Changes made in NVIDIA's own tools** (cs2cfg/nvwatch.py), noticed when the
  driver's settings file moves.

Changes the player made in the app with the game closed are kept as made --
they did them on purpose -- and can still be put back. Everything else (made in
the game, made in NVIDIA's tools, or made in the app while a game was running)
waits for an answer, and the review window asks for it as soon as the game is
gone.

Put back on an app change undoes only that change, even when the same file was
changed again afterwards: the reverse of the change is merged into the file as
it is now, the same way a version-control tool would. Only when a later change
touched the very same lines does it say so and offer to go back further.
"""

from __future__ import annotations

import difflib
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import backup
from .kb import user_data_dir

# Waiting, kept, or put back. Plain words, because they are shown as they are.
WAITING, KEPT, BACK = "waiting", "kept", "back"

_LOCK = threading.RLock()
Listener = Callable[[str], None]
_listeners: List[Listener] = []


# ---------------------------------------------------------------------------
# The little bit of state the history keeps of its own
# ---------------------------------------------------------------------------

def _path() -> Path:
    return user_data_dir() / "history" / "history.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Kept short: the oldest outside changes fall off first, the same way old
    # backup sets are pruned.
    data["events"] = (data.get("events") or [])[-80:]
    data["sessions"] = (data.get("sessions") or [])[-60:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)


def add_listener(fn: Listener) -> None:
    """fn('review') when something is waiting and should be asked about now,
    fn('closed') when nothing is waiting any more."""
    _listeners.append(fn)


def _emit(what: str) -> None:
    for fn in list(_listeners):
        try:
            fn(what)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Game sessions
# ---------------------------------------------------------------------------

def session_started(at: Optional[float] = None) -> None:
    with _LOCK:
        data = _load()
        sessions = data.setdefault("sessions", [])
        if sessions and not sessions[-1].get("end"):
            return
        sessions.append({"start": at or time.time(), "end": 0})
        _save(data)


def session_ended(at: Optional[float] = None) -> None:
    with _LOCK:
        data = _load()
        sessions = data.setdefault("sessions", [])
        if sessions and not sessions[-1].get("end"):
            sessions[-1]["end"] = at or time.time()
            _save(data)


def _in_session(when: float, sessions: List[dict]) -> bool:
    for s in sessions:
        start, end = float(s.get("start") or 0), float(s.get("end") or 0)
        if start <= when and (not end or when <= end):
            return True
    return False


# ---------------------------------------------------------------------------
# Outside changes: made inside CS2, or in NVIDIA's tools
# ---------------------------------------------------------------------------

def add_event(kind: str, items: List[dict], account: str = "",
              at: Optional[float] = None) -> Optional[str]:
    """Record changes made outside the app. Returns the new entry's id."""
    items = [dict(i) for i in items if isinstance(i, dict)]
    if not items:
        return None
    when = at or time.time()
    with _LOCK:
        data = _load()
        entry_id = f"{kind}:{int(when * 1000)}"
        data.setdefault("events", []).append({
            "id": entry_id, "kind": kind, "at": when, "account": str(account or ""),
            "items": items,
        })
        _save(data)
    return entry_id


def add_game_finding(account: str, payload: dict) -> Optional[str]:
    """A gamewatch finding (``gamewatch.as_dict``), as one history entry."""
    items = []
    for source, changes in (payload.get("sources") or {}).items():
        for c in changes:
            items.append({"source": source, "key": c.get("key"),
                          "label": c.get("label") or "", "kind": c.get("kind"),
                          "was": c.get("was"), "now": c.get("now")})
    return add_event("game", items, account=account, at=payload.get("after"))


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

def _answers(data: dict) -> Dict[str, str]:
    return data.setdefault("answers", {})


def item_id(entry_id: str, index: int) -> str:
    return f"{entry_id}#{index}"


def set_answer(target: str, choice: str) -> None:
    with _LOCK:
        data = _load()
        _answers(data)[target] = choice
        _save(data)


def answer_of(target: str) -> Optional[str]:
    return _answers(_load()).get(target)


# ---------------------------------------------------------------------------
# Reading a backup set as a change
# ---------------------------------------------------------------------------

# Writes that are part of launching or of the app's own housekeeping, put
# back by the app itself. Listing them would bury the changes people made.
_ROUTINE = ("play:", "enable read-only cs2 server detection")

_TITLES: Tuple[Tuple[str, str], ...] = (
    (r"^bind (.+) to (.+)$", "BIND"),
    (r"^cs2 settings", "Game settings"),
    (r"^(web|gui) apply (.+)$", "Applied a settings preset"),
    (r"^apply (.+)$", "Applied a settings preset"),
    (r"^edited (.+)$", "Edited {0} by hand"),
    (r"^cfg rename (.+) -> (.+)$", "Renamed {0} to {1}"),
    (r"^cfg polish", "Tidied up config files"),
    (r"^apply-changes key", "Set up the apply key"),
    (r"^live-apply script", "Updated the apply key's list"),
    (r"^layout profile pins", "Changed which keys stay the same in every profile"),
    (r"^keyboard profile file", "Changed a keyboard profile"),
    (r"^restore default layout", "Put the standard keyboard back"),
    (r"^new profile (.+)$", "Made a new profile"),
    (r"^copy profile (.+) -> (.+)$", "Copied a profile"),
    (r"^delete profile (.+)$", "Deleted a profile"),
    (r"^remove profile (.+) from list$", "Took a profile off the list"),
    (r"^import profile (.+)$", "Imported a profile"),
    (r"^pull profiles from cloud", "Brought profiles in from the cloud"),
    (r"^settings sync from another pc", "Settings from your other PC"),
    (r"^starter config", "Made a starter config"),
    (r"^script builder: (.+)$", "Built a script: {0}"),
    (r"^import a saved setup", "Imported a saved setup"),
    (r"^import:", "Imported a config"),
    (r"^region lock", "Region lock settings"),
    (r"^demo: bind", "Demo key"),
    (r"^put back: (.+)$", "Put back: {0}"),
)


def title_for(note: str) -> str:
    text = re.sub(r"\s*\((web|gui)\)\s*$", "", note or "").strip()
    for pattern, template in _TITLES:
        m = re.match(pattern, text, re.IGNORECASE)
        if m and template == "BIND":
            return f"Key {m.group(2)}: {_command_words(m.group(1))}"
        if m:
            try:
                return template.format(*m.groups())
            except (IndexError, KeyError):
                return template
    if not text:
        return "A change"
    return text[0].upper() + text[1:]


def area_for(note: str, files: List[str]) -> str:
    """Which part of the app a change belongs to, for its icon."""
    low = (note or "").lower()
    names = " ".join(Path(f).name.lower() for f in files)
    if low.startswith("bind ") or "key" in low or "layout" in low or "binds" in names:
        return "keys"
    if "profile" in low:
        return "profiles"
    if "cs2_video" in names or "video" in low:
        return "picture"
    if "settings" in low or "apply" in low or "preset" in low:
        return "game"
    return "files"


def _stamp_time(stamp: str) -> float:
    try:
        return datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S").timestamp()
    except ValueError:
        return 0.0


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def _before_after(sets: List[backup.BackupSet], index: int) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """Each file of set ``index`` as it was before it, and right after it.

    ``sets`` is newest first. After = the copy taken by the next set (newer)
    that touched the same file, or the file on disk if none did.
    """
    out: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    me = sets[index]
    for original, stored in me.files.items():
        before = _read(me.path / stored) if stored else None
        after: Optional[str] = None
        found = False
        for newer in reversed(sets[:index]):
            if original in newer.files:
                kept = newer.files[original]
                after = _read(newer.path / kept) if kept else None
                found = True
                break
        if not found:
            after = _read(Path(original))
        out[original] = (before, after)
    return out


# ---------------------------------------------------------------------------
# Plain wording for a line of config
# ---------------------------------------------------------------------------

_BIND = re.compile(r'^\s*bind\s+"?([^"\s]+)"?\s+"?(.*?)"?\s*(//.*)?$', re.IGNORECASE)
_UNBIND = re.compile(r'^\s*unbind\s+"?([^"\s]+)"?', re.IGNORECASE)
_PAIR = re.compile(r'^\s*"?([A-Za-z_][\w.]*)"?\s+"?([^"/]*?)"?\s*(//.*)?$')

_labels_cache: Optional[Dict[str, str]] = None


# Groups whose labels are too short to stand alone ("Length", "Style"):
# these get the group's name in front, so "Crosshair length".
_NAMED_GROUPS = ("crosshair_main", "input_viewmodel", "game_radar")


def _load_labels() -> Dict[str, str]:
    path = Path(__file__).with_name("knowledge") / "cfg_settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    groups = {}
    for section in data.get("sections") or []:
        for group in section.get("groups") or []:
            groups[group.get("id")] = group.get("label") or ""
    out = {}
    for name, spec in (data.get("settings") or {}).items():
        label = str(spec.get("label") or "")
        if not label:
            continue
        group = groups.get(spec.get("group"), "")
        if spec.get("group") in _NAMED_GROUPS and group and group.lower() not in label.lower():
            label = f"{group} {label[:1].lower()}{label[1:]}"
        out[name.lower()] = label
    return out


def _setting_label(name: str) -> str:
    global _labels_cache
    if _labels_cache is None:
        _labels_cache = _load_labels()
    return _labels_cache.get(name.lower(), "")


_PREFIXES = ("cl_", "r_", "snd_", "sv_", "mat_", "net_", "cq_", "hud_", "m_",
             "setting.", "voice_", "ui_", "joy_", "rate", "fps_")


def _setting_words(name: str) -> str:
    label = _setting_label(name)
    if label:
        return label
    bare = name
    for prefix in _PREFIXES:
        if bare.lower().startswith(prefix) and len(bare) > len(prefix):
            bare = bare[len(prefix):]
            break
    bare = bare.replace("_", " ").replace(".", " ").strip()
    return (bare[:1].upper() + bare[1:]) if bare else name


def _key_label(binding: str) -> str:
    try:
        from .keys import label
        return label(binding)
    except Exception:
        return binding


def _command_words(command: str) -> str:
    """A command in words: "+jump" -> "Jump", "+smoke_left_click" -> "Smoke left click"."""
    command = (command or "").strip().strip('"')
    try:
        from .scriptnames import describe_body, readable_alias
        said = describe_body(command, {})
        if said and said != command:
            return said
        if command and " " not in command and ";" not in command:
            return readable_alias(command)
    except Exception:
        pass
    return command


def _parse_line(line: str) -> Optional[Tuple[str, str, str]]:
    """(key, name shown, value shown) for a line that sets one thing."""
    text = line.strip()
    if not text or text.startswith("//") or text in ("{", "}"):
        return None
    m = _BIND.match(text)
    if m:
        return ("bind:" + m.group(1).lower(), "Key " + _key_label(m.group(1)),
                _command_words(m.group(2)))
    m = _UNBIND.match(text)
    if m:
        return ("bind:" + m.group(1).lower(), "Key " + _key_label(m.group(1)), "nothing")
    m = _PAIR.match(text)
    if m and m.group(1).lower() not in ("exec", "alias", "echo", "say", "say_team",
                                         "host_writeconfig", "unbindall"):
        name = m.group(1)
        return ("set:" + name.lower(), _setting_words(name), m.group(2))
    # Comments, separators, script lines, generated dates: not a setting a
    # person changed, and showing them would be showing code.
    return None


def _settings_file(path: str) -> bool:
    name = Path(path).name.lower()
    return name.endswith((".cfg", ".vcfg")) or name == "cs2_video.txt"


def describe_diff(before: Optional[str], after: Optional[str]) -> List[dict]:
    """What changed between two versions of a file, as plain items."""
    if before is None and after is None:
        return []
    if before is None:
        before = ""
    if after is None:
        after = ""
    old_lines, new_lines = before.splitlines(), after.splitlines()
    items: List[dict] = []
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        was: Dict[str, Tuple[str, str]] = {}
        now: Dict[str, Tuple[str, str]] = {}
        order: List[str] = []
        for line in old_lines[i1:i2]:
            parsed = _parse_line(line)
            if parsed:
                was[parsed[0]] = (parsed[1], parsed[2])
                if parsed[0] not in order:
                    order.append(parsed[0])
        for line in new_lines[j1:j2]:
            parsed = _parse_line(line)
            if parsed:
                now[parsed[0]] = (parsed[1], parsed[2])
                if parsed[0] not in order:
                    order.append(parsed[0])
        for key in order:
            a, b = was.get(key), now.get(key)
            if a and b and a[1] == b[1]:
                continue        # moved or re-commented, same effect
            items.append({"what": (b or a)[0],
                          "was": a[1] if a else None,
                          "now": b[1] if b else None})
    return items[:60]


# ---------------------------------------------------------------------------
# Undo / redo of one app change, merged into the file as it is now
# ---------------------------------------------------------------------------

class Conflict(Exception):
    """A later change touched the same lines."""


def _edits(base: List[str], other: List[str]) -> List[Tuple[int, int, List[str]]]:
    m = difflib.SequenceMatcher(a=base, b=other, autojunk=False)
    return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in m.get_opcodes()
            if tag != "equal"]


def merge(base: str, change_to: str, current: str) -> str:
    """Apply the change base -> change_to onto ``current`` (itself a later
    version of ``base``). Raises Conflict where both touched the same lines."""
    keep_end = base.endswith("\n")
    b, t, c = base.splitlines(), change_to.splitlines(), current.splitlines()
    mine = _edits(b, t)
    theirs = _edits(b, c)
    for i1, i2, _ in mine:
        for k1, k2, _ in theirs:
            # Overlapping ranges, or an insertion inside or right at the edge
            # of the other change: both are a conflict, to be safe.
            if (max(i1, k1) < min(i2, k2) or (i1 == i2 and k1 <= i1 <= k2)
                    or (k1 == k2 and i1 <= k1 <= i2)):
                raise Conflict()
    edits = sorted(mine + theirs, key=lambda e: (e[0], e[1]), reverse=True)
    out = list(b)
    for i1, i2, lines in edits:
        out[i1:i2] = lines
    text = "\n".join(out)
    if out and (keep_end or current.endswith("\n")):
        text += "\n"
    return text


def _write(path: Path, text: Optional[str], newline: str) -> None:
    if text is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if newline == "\r\n":
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def _newline(*texts: Optional[str]) -> str:
    for t in texts:
        if t and "\r\n" in t:
            return "\r\n"
    return "\n"


def _norm(text: Optional[str]) -> Optional[str]:
    return None if text is None else text.replace("\r\n", "\n")


def swing(stamp: str, direction: str, force: bool = False) -> dict:
    """Put an app change back (direction BACK) or bring it back again (KEPT).

    ``force`` goes all the way back to the file as it was before the change,
    which also undoes later changes to the same lines.
    """
    if direction != BACK and answer_of("app:" + stamp) != BACK:
        # Keeping a change that is still in place: nothing to write. Only a
        # change that was put back needs bringing back.
        set_answer("app:" + stamp, KEPT)
        return {"ok": True, "files": 0}
    sets = [s for s in backup.list_sets()]
    index = next((i for i, s in enumerate(sets) if s.stamp == stamp), None)
    if index is None:
        return {"ok": False, "error": "That change is too old: its backup has been cleared out."}
    pairs = _before_after(sets, index)
    plan: List[Tuple[Path, Optional[str], str]] = []
    for original, (before, after) in pairs.items():
        path = Path(original)
        raw_now = _read(path)
        current = _norm(raw_now)
        frm, to = (_norm(after), _norm(before)) if direction == BACK else (_norm(before), _norm(after))
        if current == to:
            continue
        if current == frm or force:
            plan.append((path, to, _newline(raw_now, before, after)))
            continue
        if frm is None or to is None or current is None:
            return {"ok": False, "conflict": True,
                    "error": "This file was changed again later, so this change "
                             "can't be taken out on its own."}
        try:
            plan.append((path, merge(frm, to, current), _newline(raw_now, before, after)))
        except Conflict:
            return {"ok": False, "conflict": True,
                    "error": "A later change touched the same lines. Putting this "
                             "back would also undo that later change."}
    if plan:
        target = next((s for s in sets if s.stamp == stamp), None)
        with backup.marked("answer"):
            session = backup.BackupSession(
                note=("put back: " if direction == BACK else "kept again: ") + (target.note if target else stamp))
            for path, _text, _nl in plan:
                session.add(path)
        for path, text, nl in plan:
            _write(path, text, nl)
    set_answer("app:" + stamp, BACK if direction == BACK else KEPT)
    return {"ok": True, "files": len(plan)}


# ---------------------------------------------------------------------------
# The list
# ---------------------------------------------------------------------------

def _app_entries(data: dict, limit: int) -> List[dict]:
    sets = backup.list_sets()
    answers = _answers(data)
    sessions = data.get("sessions") or []
    out = []
    for index, s in enumerate(sets):
        if s.origin or (s.note or "").lower().startswith(_ROUTINE):
            continue
        entry_id = "app:" + s.stamp
        when = _stamp_time(s.stamp)
        answer = answers.get(entry_id)
        during_game = _in_session(when, sessions)
        status = answer or (WAITING if during_game else KEPT)
        items: List[dict] = []
        for original, (before, after) in _before_after(sets, index).items():
            if not _settings_file(original):
                continue
            for item in describe_diff(before, after):
                item["file"] = Path(original).name
                items.append(item)
        if not items:
            continue            # wrote the same thing back; nothing to show
        out.append({
            "id": entry_id, "kind": "app", "at": when, "status": status,
            "title": title_for(s.note), "area": area_for(s.note, list(s.files)),
            "origin": "In CS2 Auto Config" + (" while CS2 was running" if during_game else ""),
            "items": items, "can_put_back": True,
        })
        if len(out) >= limit:
            break
    return out


_GAME_TITLES = {"Key binds": "keys", "In-game settings": "game",
                "Picture quality": "picture", "Stick binds": "keys",
                "Machine settings": "game"}
# The ones the app can write back into the player's config.
GAME_ANSWERABLE = {"Key binds", "In-game settings", "Picture quality"}


def _game_item_words(item: dict) -> dict:
    source = item.get("source") or ""
    key = str(item.get("key") or "")
    if source in ("Key binds", "Stick binds"):
        what = "Key " + _key_label(key)
        was = _command_words(item["was"]) if item.get("was") else None
        now = _command_words(item["now"]) if item.get("now") else None
    else:
        what = _setting_label(key) or item.get("label") or _setting_words(key)
        was, now = item.get("was"), item.get("now")
    return {"what": what, "was": was, "now": now, "group": source}


def _event_entries(data: dict) -> List[dict]:
    answers = _answers(data)
    out = []
    for ev in reversed(data.get("events") or []):
        kind = ev.get("kind")
        items = []
        statuses = []
        for n, raw in enumerate(ev.get("items") or []):
            target = item_id(ev["id"], n)
            if kind == "game":
                words = _game_item_words(raw)
                can = (raw.get("source") in GAME_ANSWERABLE)
            else:
                words = {"what": raw.get("name") or raw.get("key"), "was": raw.get("was"),
                         "now": raw.get("now"), "group": raw.get("profile") or ""}
                can = bool(raw.get("can_put_back"))
            status = answers.get(target) or (WAITING if can or kind == "nvidia" else KEPT)
            statuses.append(status)
            items.append({**words, "id": target, "status": status, "can_put_back": can})
        if not items:
            continue
        if WAITING in statuses:
            status = WAITING
        elif all(s == BACK for s in statuses):
            status = BACK
        else:
            status = KEPT
        if kind == "game":
            title, origin = "Changed inside CS2", "In CS2's own menus"
            areas = {_GAME_TITLES.get(r.get("source"), "game") for r in ev.get("items") or []}
            area = areas.pop() if len(areas) == 1 else "game"
        else:
            title, origin, area = "Changed in NVIDIA settings", "In the NVIDIA app or Control Panel", "nvidia"
        out.append({"id": ev["id"], "kind": kind, "at": float(ev.get("at") or 0),
                    "status": status, "title": title, "area": area, "origin": origin,
                    "account": ev.get("account", ""), "items": items,
                    "can_put_back": any(i["can_put_back"] for i in items)})
    return out


def entries(limit: int = 60) -> List[dict]:
    """Every change, newest first."""
    with _LOCK:
        data = _load()
    found = _app_entries(data, limit) + _event_entries(data)
    found.sort(key=lambda e: e["at"], reverse=True)
    return found[:limit]


def waiting(limit: int = 60) -> List[dict]:
    return [e for e in entries(limit) if e["status"] == WAITING]


def event(entry_id: str) -> Optional[dict]:
    with _LOCK:
        for ev in _load().get("events") or []:
            if ev.get("id") == entry_id:
                return ev
    return None


def request_review() -> bool:
    """Ask the review window to come up, if anything is waiting."""
    if waiting(20):
        _emit("review")
        return True
    return False


def review_done() -> None:
    _emit("closed")
