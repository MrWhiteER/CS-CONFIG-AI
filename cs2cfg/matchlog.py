"""Your own CS2 matches, recorded from the game itself.

FACEIT publishes a match history; Valve's matchmaking does not, not without an
API key and a per-account match code. So the CS2 half of the combined stats
list is written down locally while you play, from CS2's game state feed (GSI):
a small cfg file in CS2's cfg folder tells the game to POST its state to this
app. That needs no admin rights, no sign-in and no key, and it only ever
describes the player at this keyboard.

What one match records is your own line, the same columns FACEIT's list has:
kills, deaths, assists, MVPs, ADR, HS%, multi-kills, the map, the mode, the
final score and whether you won. There is no ten-player scoreboard: GSI only
describes other players to spectators and GOTV.

How a round is counted. While you are alive, ``player.state`` carries this
round's kills, headshot kills and damage. When you die the player block
switches to whoever you spectate, so payloads about anyone else are ignored and
the last values seen for you stand. A round is closed when the next one's
freeze time starts (or the match ends), using the largest values seen since the
last close -- the counters only ever go up within a round, and reset in the
freeze time that follows it.

Only finished matches (``map.phase == "gameover"``) are kept. A match you leave
early never reaches the list. Deathmatch, casual and the like are skipped by
mode; see :data:`COUNTED_MODES`.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import maps

CFG_NAME = "gamestate_integration_cs2cfg_stats.cfg"
ENDPOINT = "/api/stats/gsi"
MAX_BODY = 64 * 1024
TOKEN_FILE = "stats-gsi-token"
STORE_NAME = "cs2-matches.json"
KEEP = 500

COMPONENTS = ("provider", "map", "round", "player_id", "player_state",
              "player_match_stats")

# GSI's map.mode values for the modes that make a stats line worth keeping.
# Premier reports as "competitive" on some builds, so both are listed.
COUNTED_MODES = {
    "competitive": "Competitive",
    "premier": "Premier",
    "scrimcomp2v2": "Wingman",
    "wingman": "Wingman",
}

STEAM64_BASE = 76561197960265728

# A FACEIT match is played in CS2 too, so the recorder sees it. It is shown
# once, as FACEIT: a CS2 row is dropped when a FACEIT match on the same map
# was played within this many seconds of it.
FACEIT_WINDOW = 20 * 60


def account_to_steam64(account_id: Any) -> str:
    try:
        return str(int(str(account_id)) + STEAM64_BASE)
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# The cfg file CS2 reads at start-up.


def install_token(directory: Path) -> str:
    """The shared secret CS2 sends back. Never shown in the UI."""
    path = Path(directory) / TOKEN_FILE
    try:
        token = path.read_text(encoding="ascii").strip()
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
            return token
    except (FileNotFoundError, UnicodeError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    path.write_text(token, encoding="ascii")
    return token


def cfg_text(port: int, token: str) -> str:
    if not 1 <= int(port) <= 65535 or len(token) != 64 \
            or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("invalid stats GSI configuration")
    data = "\n".join(f'        "{key}" "1"' for key in COMPONENTS)
    return ('"CS2 Auto Config stats"\n{\n'
            f'    "uri" "http://127.0.0.1:{port}{ENDPOINT}"\n'
            '    "timeout" "2.0"\n    "buffer" "0.1"\n    "throttle" "0.5"\n'
            '    "heartbeat" "10.0"\n'
            f'    "auth" {{ "token" "{token}" }}\n    "data"\n    {{\n{data}\n    }}\n}}\n')


def write_cfg(install: Path, port: int, token: str) -> Optional[Path]:
    """Write the cfg if it is missing or different. Returns the path written.

    CS2 only reads GSI files at start-up, so a change (a new port) takes
    effect from the next launch. Unchanged files are left alone.
    """
    path = Path(install) / "game" / "csgo" / "cfg" / CFG_NAME
    if path.is_symlink() or not path.parent.is_dir():
        raise OSError("CS2 cfg folder unavailable")
    text = cfg_text(port, token)
    try:
        if path.read_text(encoding="utf-8") == text:
            return None
    except (FileNotFoundError, UnicodeError):
        pass
    path.write_text(text, encoding="utf-8")
    return path


def remove_cfg(install: Path) -> None:
    (Path(install) / "game" / "csgo" / "cfg" / CFG_NAME).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Reading one payload.


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _scalars(value: Any, keys) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in keys
            and isinstance(v, (str, int, float)) and not isinstance(v, bool)}


def parse_payload(raw: bytes, token: str) -> Dict[str, Any]:
    """Check the secret and keep only the fields the recorder reads."""
    if len(raw) > MAX_BODY:
        raise ValueError("GSI body too large")
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid GSI JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("expected a GSI object")
    auth = body.get("auth")
    supplied = auth.get("token") if isinstance(auth, dict) else None
    if not (token and isinstance(supplied, str) and supplied.isascii()
            and hmac.compare_digest(supplied, token)):
        raise PermissionError("invalid GSI token")

    game = body.get("map") if isinstance(body.get("map"), dict) else {}
    player = body.get("player") if isinstance(body.get("player"), dict) else {}
    return {
        "provider": _scalars(body.get("provider"), ("steamid", "timestamp")),
        "map": {
            **_scalars(game, ("name", "mode", "phase", "round")),
            "team_ct": _scalars(game.get("team_ct"), ("score",)),
            "team_t": _scalars(game.get("team_t"), ("score",)),
        } if game else {},
        "round": _scalars(body.get("round"), ("phase",)),
        "player": {
            **_scalars(player, ("steamid", "team", "activity")),
            "state": _scalars(player.get("state"),
                              ("health", "round_kills", "round_killhs",
                               "round_totaldmg")),
            "match_stats": _scalars(player.get("match_stats"),
                                    ("kills", "assists", "deaths", "mvps", "score")),
        } if player else {},
    }


# ---------------------------------------------------------------------------
# Turning a stream of payloads into finished matches.


class Recorder:
    """Follows one match at a time; hands each finished one to ``on_finish``."""

    def __init__(self, on_finish: Callable[[Dict[str, Any]], None],
                 clock: Callable[[], float] = time.time):
        self.on_finish = on_finish
        self.clock = clock
        self.match: Optional[Dict[str, Any]] = None
        self.lock = threading.Lock()

    # One round's counters, as the largest values seen since the last close.
    @staticmethod
    def _blank_round() -> Dict[str, int]:
        return {"kills": 0, "hs": 0, "dmg": 0, "seen": 0}

    def _start(self, me: str, game: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "steamid": me, "map": str(game.get("name") or ""),
            "mode": str(game.get("mode") or ""), "started_at": int(self.clock()),
            "rounds": [], "current": self._blank_round(), "phase": "",
            "stats": {}, "team": "", "score": {"ct": 0, "t": 0}, "done": False,
        }

    def _close_round(self, m: Dict[str, Any]) -> None:
        cur = m["current"]
        if cur["seen"]:
            m["rounds"].append({"kills": cur["kills"], "hs": cur["hs"], "dmg": cur["dmg"]})
        m["current"] = self._blank_round()

    def feed(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self._feed(payload)

    def _feed(self, p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        me = str(p.get("provider", {}).get("steamid") or "")
        game = p.get("map") or {}
        if not me or not game.get("name"):
            # Main menu: whatever was in progress was left, not finished.
            self.match = None
            return None
        mode = str(game.get("mode") or "").lower()
        if mode not in COUNTED_MODES:
            self.match = None
            return None

        m = self.match
        if m is None or m["map"] != game.get("name") or m["steamid"] != me or m["done"]:
            if m is not None and m["done"] and m["map"] == game.get("name") \
                    and game.get("phase") == "gameover":
                return None  # still on the end screen of the one just saved
            m = self.match = self._start(me, game)

        phase = str(game.get("phase") or "")
        if phase == "warmup":
            # Warm-up kills are not the match. Start clean when it goes live.
            m["current"] = self._blank_round()
            m["rounds"] = []
            m["started_at"] = int(self.clock())
            return None

        m["score"] = {"ct": _int(game.get("team_ct", {}).get("score")),
                      "t": _int(game.get("team_t", {}).get("score"))}

        round_phase = str(p.get("round", {}).get("phase") or "")
        if round_phase == "freezetime" and m["phase"] != "freezetime":
            self._close_round(m)
        if round_phase:
            m["phase"] = round_phase

        player = p.get("player") or {}
        if str(player.get("steamid") or "") == me:
            if player.get("team") in ("CT", "T"):
                m["team"] = player["team"]
            if player.get("match_stats"):
                m["stats"] = dict(player["match_stats"])
            st = player.get("state") or {}
            if round_phase != "freezetime" and phase == "live" and st:
                cur = m["current"]
                cur["kills"] = max(cur["kills"], _int(st.get("round_kills")))
                cur["hs"] = max(cur["hs"], _int(st.get("round_killhs")))
                cur["dmg"] = max(cur["dmg"], _int(st.get("round_totaldmg")))
                cur["seen"] = 1

        if phase == "gameover":
            self._close_round(m)
            m["done"] = True
            done = summarize(m, int(self.clock()))
            if done is not None:
                self.on_finish(done)
            return done
        return None


def summarize(m: Dict[str, Any], ended_at: int) -> Optional[Dict[str, Any]]:
    """One finished match as a list row, in the same shape FACEIT's rows use."""
    ct, t = m["score"]["ct"], m["score"]["t"]
    # A match only caught at its end screen (the app started late) has no
    # rounds of yours in it; an empty line would only drag the averages down.
    if not m["rounds"]:
        return None
    rounds = ct + t or len(m["rounds"])
    team = m["team"]
    mine, theirs = (ct, t) if team == "CT" else (t, ct) if team == "T" else (max(ct, t), min(ct, t))
    s = m["stats"]
    kills, deaths = _int(s.get("kills")), _int(s.get("deaths"))
    hs = sum(r["hs"] for r in m["rounds"])
    dmg = sum(r["dmg"] for r in m["rounds"])
    multi = {n: sum(1 for r in m["rounds"] if r["kills"] == n) for n in (2, 3, 4)}
    multi[5] = sum(1 for r in m["rounds"] if r["kills"] >= 5)
    return {
        "source": "cs2",
        "match_id": f"cs2-{m['steamid']}-{ended_at}",
        "steamid": m["steamid"],
        "map": m["map"],
        "mode": COUNTED_MODES.get(m["mode"].lower(), m["mode"]),
        "won": mine > theirs,
        "tied": mine == theirs,
        "score": f"{mine} / {theirs}",
        "rounds": rounds,
        "started_at": m["started_at"],
        "played_at": ended_at,
        "kills": kills,
        "deaths": deaths,
        "assists": _int(s.get("assists")),
        "mvps": _int(s.get("mvps")),
        "kd": round(kills / deaths, 2) if deaths else float(kills),
        "kr": round(kills / rounds, 2),
        "adr": round(dmg / rounds, 1),
        "hs_percent": round(100 * hs / kills) if kills else 0,
        "double": multi[2], "triple": multi[3], "quadro": multi[4], "penta": multi[5],
        "elo": None, "elo_delta": None,
    }


# ---------------------------------------------------------------------------
# Where finished matches are kept.


class Store:
    def __init__(self, directory: Path):
        self.path = Path(directory) / STORE_NAME
        self.lock = threading.Lock()

    def _read(self) -> List[Dict[str, Any]]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, UnicodeError, OSError):
            return []
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []

    def add(self, row: Dict[str, Any]) -> None:
        with self.lock:
            rows = [r for r in self._read() if r.get("match_id") != row.get("match_id")]
            rows.append(row)
            rows.sort(key=lambda r: r.get("played_at") or 0, reverse=True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rows[:KEEP], indent=1), encoding="utf-8")
            tmp.replace(self.path)

    def matches(self, steamid: str = "") -> List[Dict[str, Any]]:
        with self.lock:
            rows = self._read()
        if steamid:
            rows = [r for r in rows if str(r.get("steamid")) == str(steamid)]
        return rows


# ---------------------------------------------------------------------------
# One list out of both sources.


SUMMED = ("kills", "deaths", "assists", "rounds")


def _plain(row: Dict[str, Any]) -> Dict[str, Any]:
    """One spelling per map, and names a person reads: ``map_name`` "Dust II",
    ``mode`` "Wingman" -- never ``de_dust2`` or ``scrimcomp2v2``."""
    out = dict(row)
    out["map"] = maps.canonical(out.get("map") or "")
    out["map_name"] = maps.display(out["map"])
    out["mode"] = maps.mode(out.get("mode") or "")
    return out


def _faceit_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = _plain(row)
    out["source"] = "faceit"
    out["mode"] = out["mode"] or "FACEIT"
    return out


def _is_faceit(cs2: Dict[str, Any], faceit: List[Dict[str, Any]]) -> bool:
    start = int(cs2.get("started_at") or cs2.get("played_at") or 0)
    end = int(cs2.get("played_at") or 0)
    for f in faceit:
        when = int(f.get("played_at") or 0)
        if f.get("map") == cs2.get("map") and start - FACEIT_WINDOW <= when <= end + FACEIT_WINDOW:
            return True
    return False


def _recorded(steam: Dict[str, Any], local: List[Dict[str, Any]]) -> bool:
    """Steam's copy of a match this PC also recorded. The local one wins: it has ADR.

    Steam stamps a match when it starts; the recorder when warm-up ends.
    """
    when = int(steam.get("played_at") or 0)
    for r in local:
        start = int(r.get("started_at") or r.get("played_at") or 0)
        if r.get("map") == steam.get("map") and start - FACEIT_WINDOW <= when <= int(r.get("played_at") or 0):
            return True
    return False


def summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Totals over a list, worked out the same way for both sources."""
    n = len(rows)
    if not n:
        return {"matches": 0}
    total = {k: sum(int(r.get(k) or 0) for r in rows) for k in SUMMED}
    wins = sum(1 for r in rows if r.get("won"))
    adr = [float(r["adr"]) for r in rows if r.get("adr") not in (None, "")]
    hs = [float(r["hs_percent"]) for r in rows if r.get("hs_percent") not in (None, "")]
    return {
        "matches": n,
        "wins": wins,
        "win_rate": round(100 * wins / n),
        "kills": total["kills"], "deaths": total["deaths"], "assists": total["assists"],
        "kd": round(total["kills"] / total["deaths"], 2) if total["deaths"] else float(total["kills"]),
        "kr": round(total["kills"] / total["rounds"], 2) if total["rounds"] else 0.0,
        "adr": round(sum(adr) / len(adr), 1) if adr else None,
        "hs_percent": round(sum(hs) / len(hs)) if hs else None,
    }


def combined(faceit: List[Dict[str, Any]], cs2: List[Dict[str, Any]],
             source: str = "all") -> Dict[str, Any]:
    """Both lists as one, newest first, each row tagged with its ``source``.

    ``source`` filters the list: ``all``, ``faceit`` or ``cs2``. The summary
    always matches what is listed, and per-source counts are always included
    so the filter can show them.
    """
    f_rows = [_faceit_row(r) for r in faceit or []]
    cs2 = [_plain(r) for r in cs2 or []]
    local = [r for r in cs2 if r.get("origin") != "steam"]
    steam = [r for r in cs2 if r.get("origin") == "steam" and not _recorded(r, local)]
    c_rows = [dict(r, source="cs2") for r in local + steam if not _is_faceit(r, f_rows)]
    pick = {"faceit": f_rows, "cs2": c_rows}.get(source, f_rows + c_rows)
    rows = sorted(pick, key=lambda r: int(r.get("played_at") or 0), reverse=True)
    return {
        "source": source if source in ("faceit", "cs2") else "all",
        "matches": rows,
        "summary": summary(rows),
        "counts": {"all": len(f_rows) + len(c_rows), "faceit": len(f_rows), "cs2": len(c_rows)},
    }
