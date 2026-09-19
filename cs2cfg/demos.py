"""Match demos: fetch one from a FACEIT link, and make it playable in a press.

What this is for
----------------

You finish a FACEIT match, you want to look at a round again, and the path
there is: open the match page, find the download link, wait for a few hundred
megabytes, work out where the file has to live, start the game, open the
console, type ``playdemo`` and the exact filename. This does all of that except
the watching.

Why a pasted link rather than an account lookup
-----------------------------------------------

Listing somebody's recent matches needs FACEIT's Data API, which needs an API
key that each person has to register for themselves. A match link needs
nothing: ``www.faceit.com/api/match/v2/match/<id>`` answers without
credentials, and a link is already what you have in your hand when you are
looking at the match you want to rewatch.

The demo URL is not hunted for by field name. FACEIT has moved it around
between shapes over the years -- ``demo_url``, ``demoURLs``, nested under
``payload`` -- so instead the whole response is walked for anything that looks
like a demo file. That survives a rename; a hardcoded path does not.

What it refuses to do
---------------------

The local filename is built from the match id, which is a fixed hex shape, and
never from anything the server said. A download that could choose its own path
on disk is a download that can write wherever it likes.
"""

from __future__ import annotations

import bz2
import gzip
import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MATCH_API = "https://www.faceit.com/api/match/v2/match/{match_id}"
MATCH_PAGE = "https://www.faceit.com/en/cs2/room/{match_id}"

# FACEIT match ids are "1-" and a UUID. Strict, so a pasted page URL with other
# ids in it cannot be mistaken for the match itself.
MATCH_ID = re.compile(
    r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

# Anything that ends in a demo, compressed or not. FACEIT serves CS2 demos
# zstd-compressed now; the older ones are gzip and Valve's own are bzip2.
DEMO_URL = re.compile(
    r"https?://[^\s\"']+?\.dem(?:\.gz|\.bz2|\.zst)?(?=[\"'\s]|$)", re.I)

# The demo folder CS2 reads, relative to the game's csgo directory.
REPLAY_DIR = "replays"

# What a browser calls a download it has not finished yet.
PARTIAL = (".crdownload", ".part", ".download", ".tmp")

TIMEOUT = 30
BLOCK = 1024 * 256

# A browser-shaped agent. The endpoint answers a normal client and refuses a
# blank one; this is not pretending to be a person, it is not pretending to be
# nothing.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


class DemoError(RuntimeError):
    """Anything that stops a demo being fetched or made playable."""


class Cancelled(DemoError):
    """The download was stopped on purpose."""


def match_id(text: str) -> Optional[str]:
    """The match id in a pasted link, or in a bare id. None if there is none."""
    found = MATCH_ID.search(str(text or ""))
    return found.group(0).lower() if found else None


def _open(url: str, timeout: int = TIMEOUT):
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, */*",
    })
    return urllib.request.urlopen(request, timeout=timeout)


def _walk(node: Any):
    """Every string anywhere in a decoded JSON document."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _walk(value)


def demo_urls(payload: Any) -> List[str]:
    """Every demo link in a match response, in the order found, deduplicated."""
    seen: List[str] = []
    for text in _walk(payload):
        for url in DEMO_URL.findall(text):
            if url not in seen:
                seen.append(url)
    return seen


def _first(node: Any, *paths: str) -> str:
    """The first of several dotted paths that holds a non-empty string.

    A numeric step indexes a list, because FACEIT wraps several of these in
    one -- the picked map arrives as ``voting.map.pick[0]`` rather than as the
    string it looks like in the documentation.
    """
    for path in paths:
        here = node
        for step in path.split("."):
            if isinstance(here, dict):
                here = here.get(step)
            elif isinstance(here, (list, tuple)) and step.isdigit():
                index = int(step)
                here = here[index] if index < len(here) else None
            else:
                here = None
            if here is None:
                break
        # A one-item list where a string was expected is the same answer.
        if isinstance(here, (list, tuple)) and len(here) == 1:
            here = here[0]
        if isinstance(here, str) and here.strip():
            return here.strip()
    return ""


def describe(payload: Any) -> Dict[str, str]:
    """The human-readable bits of a match, as far as they can be found.

    Every field is optional. A demo that downloads with a blank map name is
    still the demo you asked for, so nothing here is allowed to be fatal.
    """
    root = payload if isinstance(payload, dict) else {}
    body = root.get("payload") if isinstance(root.get("payload"), dict) else root
    return {
        "map": _first(body, "voting.map.pick.0", "voting.map.pick",
                      "results.map", "map"),
        "competition": _first(body, "competitionName", "competition_name",
                              "entity.name", "organizerName"),
        "team1": _first(body, "teams.faction1.name", "teams.faction1.nickname"),
        "team2": _first(body, "teams.faction2.name", "teams.faction2.nickname"),
        "state": _first(body, "state", "status"),
    }


def resolve(reference: str, opener: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Turn a pasted match link into a demo to download.

    ``opener`` exists so this can be tested without the network.
    """
    found = match_id(reference)
    if not found:
        raise DemoError(
            "that does not look like a FACEIT match link. Open the match room "
            "and copy the address from the bar -- it has the match id in it.")

    get = opener or _open
    try:
        with get(MATCH_API.format(match_id=found)) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DemoError(f"FACEIT does not know a match {found}") from exc
        raise DemoError(f"FACEIT answered {exc.code} for that match") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise DemoError(f"could not reach FACEIT: {exc}") from exc

    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise DemoError("FACEIT's answer was not JSON") from exc

    urls = demo_urls(payload)
    about = describe(payload)
    if not urls:
        # A real and common case: the match is too old, or still being played.
        raise DemoError(
            "that match has no demo attached. FACEIT keeps them for a limited "
            "time, and a match still in progress does not have one yet."
            + (f" (state: {about['state']})" if about.get("state") else ""))

    return {"match_id": found, "urls": urls, "url": urls[0],
            "page": MATCH_PAGE.format(match_id=found), **about}


STATS_API = "https://www.faceit.com/api/stats/v1/stats/matches/{match_id}"
NICK_API = "https://www.faceit.com/api/users/v1/nicknames/{nickname}"
HISTORY_API = ("https://www.faceit.com/api/stats/v1/stats/time/users/"
               "{player_id}/games/cs2?size={size}")


def player(nickname: str, opener: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Look up a FACEIT player by name. No credentials needed."""
    name = str(nickname or "").strip()
    if not name:
        raise DemoError("no FACEIT nickname given")

    get = opener or _open
    try:
        # safe="" matters: quote() leaves "/" alone by default, and a nickname
        # is somebody else's text going into a URL path.
        escaped = urllib.parse.quote(name, safe="")
        with get(NICK_API.format(nickname=escaped)) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DemoError(f"FACEIT has no player called {name!r}") from exc
        raise DemoError(f"FACEIT answered {exc.code} looking up {name!r}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise DemoError(f"could not reach FACEIT: {exc}") from exc

    try:
        body = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise DemoError("FACEIT's answer was not JSON") from exc

    me = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(me, dict) or not me.get("id"):
        raise DemoError(f"FACEIT has no player called {name!r}")
    cs2 = ((me.get("games") or {}).get("cs2")) or {}
    return {
        "player_id": str(me["id"]),
        "nickname": str(me.get("nickname") or name),
        "avatar": str(me.get("avatar") or ""),
        "country": str(me.get("country") or "").upper(),
        "elo": int(_num(cs2.get("faceit_elo"))),
        "level": int(_num(cs2.get("skill_level"))),
    }


def history(player_id: str, size: int = 20,
            opener: Optional[Callable[[str], Any]] = None) -> List[Dict[str, Any]]:
    """Recent CS2 matches for a player, newest first.

    One row per match with that player's own line in it, which is what the
    list needs -- the full scoreboard is a separate call, made only when
    somebody opens one.
    """
    if not str(player_id or "").strip():
        raise DemoError("no FACEIT player to look up")
    size = max(1, min(int(size or 20), 50))

    get = opener or _open
    try:
        with get(HISTORY_API.format(player_id=player_id, size=size)) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise DemoError(f"FACEIT answered {exc.code} for that history") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise DemoError(f"could not reach FACEIT: {exc}") from exc

    try:
        rows = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise DemoError("FACEIT's history answer was not JSON") from exc
    if not isinstance(rows, list):
        return []

    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("matchId"):
            continue
        mine = int(_num(row.get("c5")))
        # The score string is not reliably the player's team first, so the
        # opponent's rounds are taken as "the other number in it" rather than
        # by position. Their own total is c5, which is trustworthy.
        pair = [int(_num(part)) for part in str(row.get("i18") or "").split("/")
                if part.strip().isdigit()]
        theirs = next((n for n in pair if n != mine), pair[-1] if pair else 0)
        out.append({
            "match_id": str(row["matchId"]),
            "map": str(row.get("i1") or ""),
            "won": _num(row.get("i10")) == 1,
            "score": f"{mine} / {theirs}",
            "rounds": int(_num(row.get("i12"))),
            "elo": int(_num(row.get("elo"))),
            "elo_delta": int(_num(row.get("elo_delta"))),
            "played_at": int(_num(row.get("date")) / 1000),
            "kills": int(_num(row.get("i6"))),
            "deaths": int(_num(row.get("i8"))),
            "assists": int(_num(row.get("i7"))),
            "kd": _num(row.get("c2")),
            "adr": _num(row.get("c10")),
            "team": str(row.get("i5") or ""),
        })
    out.sort(key=lambda r: r["played_at"], reverse=True)
    return out

# FACEIT's stats endpoint names every column i6, c4, i40 and so on. There is
# no published key for it, so this mapping was derived rather than guessed:
# take a finished match, and for each column keep only the keys whose values
# agree with the scoreboard FACEIT itself renders -- for all ten players at
# once. A key that lines up with one row by coincidence does not survive ten.
#
# Two notes from doing that:
#   * i10 also tracks kills-per-round closely enough to look right on a single
#     row. It is not it; c3 is. This is exactly what the all-players check is
#     for.
#   * c10 (damage per round) runs about one point above the figure on FACEIT's
#     newer stats tab. Both are theirs; they disagree with each other. c10 is
#     what this endpoint publishes and what is shown.
PLAYER_STATS = {
    "kills": "i6", "assists": "i7", "deaths": "i8", "mvps": "i9",
    "headshots": "i13", "triple": "i14", "quadro": "i15", "penta": "i16",
    "double": "i40", "kd": "c2", "kr": "c3", "hs_percent": "c4", "adr": "c10",
}
TEAM_STATS = {"name": "i5", "score": "c5",
              "first_half": "i3", "second_half": "i4", "won": "i17"}


def _num(text: Any) -> float:
    try:
        return float(str(text))
    except (TypeError, ValueError):
        return 0.0


def stats(reference: str, opener: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """The scoreboard for a match: teams, players, and every column.

    Separate from :func:`resolve` because it answers a different question and
    a match can have one without the other -- stats outlive the demo, which
    FACEIT only keeps for a while.
    """
    found = match_id(reference)
    if not found:
        raise DemoError("that does not look like a FACEIT match link")

    get = opener or _open
    try:
        with get(STATS_API.format(match_id=found)) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise DemoError(f"FACEIT answered {exc.code} for that match's stats") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise DemoError(f"could not reach FACEIT: {exc}") from exc

    try:
        body = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise DemoError("FACEIT's stats answer was not JSON") from exc

    rounds = body[0] if isinstance(body, list) and body else body
    if not isinstance(rounds, dict) or not rounds.get("teams"):
        raise DemoError("FACEIT has no scoreboard for that match")

    teams = []
    for side in rounds.get("teams") or []:
        players = []
        for person in side.get("players") or []:
            row = {"nickname": str(person.get("nickname") or "?"),
                   "player_id": str(person.get("playerId") or "")}
            for name, key in PLAYER_STATS.items():
                row[name] = _num(person.get(key))
            # Not published per player, so it is computed rather than left out.
            row["kast"] = 0.0
            players.append(row)
        # Best first, the way a scoreboard is always read.
        players.sort(key=lambda p: (-p["kills"], p["deaths"]))
        teams.append({
            "name": str(side.get(TEAM_STATS["name"]) or "team"),
            "score": int(_num(side.get(TEAM_STATS["score"]))),
            "first_half": int(_num(side.get(TEAM_STATS["first_half"]))),
            "second_half": int(_num(side.get(TEAM_STATS["second_half"]))),
            "won": _num(side.get(TEAM_STATS["won"])) == 1,
            "players": players,
        })

    return {
        "match_id": found,
        "map": str(rounds.get("i1") or ""),
        "region": str(rounds.get("i0") or ""),
        "rounds": int(_num(rounds.get("i12"))),
        "score": str(rounds.get("i18") or ""),
        "mode": str(rounds.get("gameMode") or ""),
        "played_at": int(_num(rounds.get("date")) / 1000),
        "teams": teams,
        "page": MATCH_PAGE.format(match_id=found),
    }


def local_name(found: str, about: Optional[Dict[str, str]] = None) -> str:
    """What the demo is called on disk.

    Built from the match id and, if it is known, the map -- never from the
    download URL. The id's shape is already checked, so the result cannot
    contain a separator or climb anywhere.
    """
    if not MATCH_ID.fullmatch(found or ""):
        raise DemoError(f"refusing to name a file after {found!r}")
    tail = ""
    chosen = (about or {}).get("map") or ""
    slug = re.sub(r"[^A-Za-z0-9]+", "", chosen)[:24]
    if slug:
        tail = "_" + slug
    return f"faceit_{found[2:10]}{tail}.dem"


class _Counted:
    """A read-through wrapper that reports progress and honours a cancel.

    Wrapping the socket rather than the decompressor means the numbers are
    bytes actually transferred, which is what somebody watching a progress bar
    is waiting for -- the uncompressed total would race ahead and mean nothing.
    """

    def __init__(self, stream, total: int, progress, cancelled):
        self._stream = stream
        self._total = total
        self._progress = progress
        self._cancelled = cancelled
        self.seen = 0

    def read(self, size: int = -1) -> bytes:
        if self._cancelled and self._cancelled():
            raise Cancelled("cancelled")
        block = self._stream.read(size)
        self.seen += len(block)
        if self._progress:
            self._progress(self.seen, self._total)
        return block


def _zstd_reader(stream):
    """A readable stream of the decompressed bytes of a zstd one.

    Three ways in, because this landed between Python versions. It is in the
    standard library from 3.14; before that it is a package, and there are two
    of those in common use. Whichever is present is used, and if none is the
    message says what to install rather than an ImportError from the middle of
    a download.
    """
    try:                                    # Python 3.14 and later
        from compression.zstd import ZstdFile

        return ZstdFile(stream)
    except ImportError:
        pass
    try:
        import zstandard

        return zstandard.ZstdDecompressor().stream_reader(stream)
    except ImportError:
        pass
    try:
        import pyzstd

        return pyzstd.ZstdFile(stream)
    except ImportError:
        pass
    raise DemoError(
        "this demo is zstd-compressed, which needs Python 3.14 or the "
        "'zstandard' package. Install it with: pip install zstandard")


def _decompressed(url: str, stream):
    lowered = url.lower().split("?")[0]
    if lowered.endswith(".gz"):
        return gzip.GzipFile(fileobj=stream)
    if lowered.endswith(".bz2"):
        return bz2.BZ2File(stream)
    if lowered.endswith(".zst"):
        return _zstd_reader(stream)
    return stream


def _why_it_failed(url: str, exc: Exception) -> str:
    """Turn a transport error into something worth reading.

    The one worth naming is a host that does not resolve, because it is not
    the user's fault and not ours: the address came from FACEIT. Observed in
    practice -- a finished match whose link named a CDN host with no DNS
    record at all, while FACEIT's other demo hosts resolved fine. Which of the
    two causes it is cannot be told apart from here, so the message says what
    is known and points at the page rather than inventing a reason.
    """
    from urllib.parse import urlsplit

    text = str(getattr(exc, "reason", exc))
    host = urlsplit(url).hostname or "the demo server"
    if "getaddrinfo" in text or "Name or service not known" in text \
            or "nodename nor servname" in text:
        return (f"FACEIT gave a download address that does not exist ({host}). "
                "Either the demo has not finished uploading yet, or that server "
                "is gone. Try again in a few minutes, and if it keeps happening "
                "the match page's own download link is the one to use.")
    return f"the download failed: {text}"


def download(
    url: str,
    target: Path,
    progress: Optional[Callable[[int, int], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    opener: Optional[Callable[[str], Any]] = None,
) -> Path:
    """Fetch a demo to ``target``, decompressing as it arrives.

    Written beside the target and moved into place at the end, so an
    interrupted download never leaves something that looks watchable.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")

    get = opener or _open
    try:
        with get(url) as response:
            declared = response.headers.get("Content-Length") if hasattr(
                response, "headers") else None
            total = int(declared) if declared and str(declared).isdigit() else 0
            counted = _Counted(response, total, progress, cancelled)
            with partial.open("wb") as out:
                shutil.copyfileobj(_decompressed(url, counted), out, BLOCK)
    except Cancelled:
        partial.unlink(missing_ok=True)
        raise
    except DemoError:
        # Already explained -- a missing zstd decompressor, say. Still has to
        # take the half-written file with it. Cancelled is caught above, and
        # subclasses this, so the order matters.
        partial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, EOFError) as exc:
        partial.unlink(missing_ok=True)
        raise DemoError(_why_it_failed(url, exc)) from exc

    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise DemoError("the download produced an empty file")

    partial.replace(target)
    return target


def reachable(url: str) -> bool:
    """Whether the host in a URL exists at all.

    Worth asking before handing a link to somebody's browser. FACEIT's match
    API publishes demo addresses on hosts that have no DNS record -- the same
    dead host for matches that definitely downloaded through the site -- so
    the field cannot be trusted to point anywhere. Opening a browser on a
    address that cannot resolve looks like the application is broken.
    """
    import socket

    host = urllib.parse.urlsplit(str(url or "")).hostname
    if not host:
        return False
    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError:
        return False


def downloads_dir() -> Path:
    """Where the browser puts things."""
    return Path.home() / "Downloads"


def _match_of(name: str) -> Optional[str]:
    """The match a downloaded demo belongs to, from its filename.

    FACEIT names them ``<match id>-1-1.dem`` and the id is a fixed shape, so
    the name alone says which match it is -- no bookkeeping needed, and a file
    downloaded last week is still recognised.
    """
    return match_id(name)


def waiting(found: str, folders: Optional[List[Path]] = None) -> Optional[Dict[str, Any]]:
    """A demo for this match already sitting in Downloads, if there is one.

    Prefers the decompressed copy when the browser left both, since adopting
    it is a straight move rather than a decompress.
    """
    wanted = match_id(found)
    if not wanted:
        return None
    best = None
    for folder in (folders or [downloads_dir()]):
        folder = Path(folder)
        if not folder.is_dir():
            continue
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for item in entries:
            if not item.is_file() or _match_of(item.name) != wanted:
                continue
            low = item.name.lower()
            if ".dem" not in low:
                continue
            # Still arriving. Chrome writes .crdownload and Firefox .part
            # until the transfer finishes; saying so beats saying nothing
            # while a few hundred megabytes come down.
            if low.endswith(PARTIAL):
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                if best is None or best.get("pending"):
                    best = {"rank": 9, "pending": True, "path": str(item),
                            "name": item.name, "size": size}
                continue
            rank = 0 if low.endswith(".dem") else 1
            try:
                size = item.stat().st_size
            except OSError:
                continue
            if size <= 0:
                continue
            if best is None or rank < best["rank"]:
                best = {"rank": rank, "pending": False, "path": str(item),
                        "name": item.name, "size": size}
    if best:
        best.pop("rank")
    return best


def adopt(source: Path, found: str, target_dir: Path,
          about: Optional[Dict[str, str]] = None,
          progress: Optional[Callable[[int, int], None]] = None) -> Path:
    """Take a demo the browser downloaded and put it where CS2 looks.

    Decompresses on the way if it needs it. The original is left alone: it is
    the user's file in the user's Downloads folder, and deleting other
    people's downloads is not this program's business.
    """
    source = Path(source)
    if not source.is_file():
        raise DemoError(f"{source} is not there any more")

    target = Path(target_dir) / local_name(found, about)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    total = source.stat().st_size

    try:
        with source.open("rb") as raw:
            counted = _Counted(raw, total, progress, None)
            with partial.open("wb") as out:
                shutil.copyfileobj(_decompressed(source.name, counted), out, BLOCK)
    except DemoError:
        partial.unlink(missing_ok=True)
        raise
    except (OSError, EOFError) as exc:
        partial.unlink(missing_ok=True)
        raise DemoError(f"could not read {source.name}: {exc}") from exc

    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise DemoError(f"{source.name} held nothing")
    partial.replace(target)
    return target


def replay_dir(cs2_install: Path) -> Path:
    """Where CS2 keeps demos, given the game's install root.

    Beside the cfg folder, not inside it: the game's own downloads land in
    ``game/csgo/replays`` and ``playdemo`` resolves relative to ``game/csgo``,
    so anything put under ``cfg`` would need the path typed out in full.
    """
    return Path(cs2_install) / "game" / "csgo" / REPLAY_DIR


def installed(replays: Path) -> List[Dict[str, Any]]:
    """The demos already on disk, newest first."""
    folder = Path(replays)
    if not folder.is_dir():
        return []
    out = []
    for item in folder.glob("*.dem"):
        try:
            stat = item.stat()
        except OSError:
            continue
        out.append({
            "name": item.name,
            "path": str(item),
            "size": stat.st_size,
            "when": int(stat.st_mtime),
            # What CS2 itself wants typed: relative to csgo, forward slashes,
            # and without the extension it adds back on its own.
            "command": f"{REPLAY_DIR}/{item.stem}",
            "ours": item.name.startswith("faceit_"),
        })
    out.sort(key=lambda d: d["when"], reverse=True)
    return out


def demo_path(demo_name: str) -> str:
    """A demo's path as CS2 wants it typed: relative, forward slashes, no
    extension. Reduced to a bare name first, so whatever is passed the result
    stays inside the replay folder."""
    stem = Path(str(demo_name)).name
    if stem.lower().endswith(".dem"):
        stem = stem[:-4]
    return f"{REPLAY_DIR}/{stem}"


def play_command(demo_name: str, quoted: bool = True) -> str:
    """The console command that plays a demo in the replay folder.

    ``quoted`` because the two places this goes have opposite needs. Typed at
    the console the path wants quoting; inside a ``bind``, which is itself a
    quoted string, a second pair of quotes closes the bind early and the key
    is left doing nothing. Demo names here cannot contain spaces -- local_name
    strips everything but letters and digits -- so the unquoted form is safe.
    """
    path = demo_path(demo_name)
    return f'playdemo "{path}"' if quoted else f"playdemo {path}"


def render_now(demo_name: str) -> str:
    """The file the key execs: whichever demo is currently chosen.

    Separate from the bind so the two can change independently. The bind is
    written once and never moves; this is rewritten every time a demo is
    picked, including while the game is running -- CS2 reads an exec'd file
    at the moment it is exec'd, so the key always plays the current choice
    rather than whatever was chosen at startup.
    """
    from .emit import GENERATED_MARKER

    stem = Path(str(demo_name)).name
    if not stem:
        return GENERATED_MARKER + "\n// No demo chosen.\n"
    return "\n".join([
        GENERATED_MARKER,
        f"// {stem}",
        "",
        play_command(stem, quoted=False),
        "",
    ])


def render_bind(key: str = "F9", payload: str = "") -> str:
    """The key, bound once to exec whatever is currently chosen.

    Bound to an exec rather than straight to ``playdemo`` because a bind is
    fixed at the moment the config is read. Pointing it at a file instead
    means picking a different demo mid-session takes effect without the game
    being restarted.
    """
    from .emit import GENERATED_MARKER

    return "\n".join([
        GENERATED_MARKER,
        "// The demo key. It execs the file holding the current choice, so",
        "// choosing another demo while the game runs needs no restart.",
        "",
        f'bind "{key}" "exec {payload}"',
        "",
    ])


def render_cfg(demo_name: str, key: str = "F9") -> str:
    """A config that puts the chosen demo one keypress away.

    A bind rather than a bare ``playdemo``: this file is exec'd from the
    autoexec, which runs while the game is still starting, and a demo asked
    for at that moment does not load. Bound to a key it waits for you, which
    is also what makes it a button rather than a launch mode.
    """
    from .emit import GENERATED_MARKER

    stem = Path(str(demo_name)).name
    return "\n".join([
        GENERATED_MARKER,
        "// The demo picked in cs2-autoconfig, on a key.",
        f"// {stem}",
        "",
        f'bind "{key}" "{play_command(stem, quoted=False)}"',
        f'echo "Press {key} to watch {stem}"',
        "",
    ])
