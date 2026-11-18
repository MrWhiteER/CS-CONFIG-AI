"""Your past CS2 matches, read from Steam's "Personal Game Data" page.

Steam keeps every Premier, Competitive and Wingman match you played, with the
ten-player scoreboard, at ``steamcommunity.com/profiles/<id>/gcpd/730``. The
page is only shown to its owner, so it is read with the app's one shared Steam
sign-in (:mod:`steamweb`), in a hidden window. The app never sees a password:
it only reads the page Steam renders.

Reading happens in the page itself (``SCRAPER_JS``): it returns the scoreboard
HTML of the first page plus every "load more" page Steam's own button would
fetch. Parsing is done here, in Python, where it can be tested.

There is no ADR or multi-kill count on that page: Steam does not publish them.
"""

from __future__ import annotations

import calendar
import re
import threading
import time
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional

from . import maps

TABS = {
    "matchhistorypremier": "Premier",
    "matchhistorycompetitivepermap": "Competitive",
    "matchhistorywingman": "Wingman",
}
PAGE = "https://steamcommunity.com/profiles/{steam64}/gcpd/730/?tab={tab}"
MAX_PAGES = 40          # "load more" pages per tab; each is a handful of matches

# Runs inside the gcpd page and leaves {signed_in, me, pages: [html, ...]} as
# JSON in window.__cs2h. Not returned directly: older pywebview builds do not
# wait for a promise, so the result is polled for instead.
SCRAPER_JS = r"""
window.__cs2h = '';
(async () => {
  const out = {signed_in: !!(window.g_steamID), me: '', pages: []};
  const self = document.querySelector('#global_actions a.user_avatar, a.user_avatar');
  out.me = self ? self.href : '';
  const root = document.querySelector('.csgo_scoreboard_root');
  if (!out.signed_in || !root) return JSON.stringify(out);
  out.pages.push(root.outerHTML);
  let token = window.g_sGcContinueToken;
  const tab = new URLSearchParams(location.search).get('tab') || '';
  for (let i = 0; token && i < %d; i++) {
    const url = location.pathname + '?ajax=1&tab=' + encodeURIComponent(tab) +
      '&continue_token=' + encodeURIComponent(token) +
      '&sessionid=' + encodeURIComponent(window.g_sessionID || '');
    let body;
    try { body = await (await fetch(url, {credentials: 'include'})).json(); }
    catch (e) { break; }
    if (!body || !body.success) break;
    if (body.html) out.pages.push(body.html);
    token = body.continue_token;
  }
  return JSON.stringify(out);
})().then(r => { window.__cs2h = r; }, () => { window.__cs2h = '{}'; });
""" % MAX_PAGES


def _int(text: str) -> int:
    m = re.search(r"-?\d+", text or "")
    return int(m.group()) if m else 0


def map_id(name: str) -> str:
    """'Mirage' -> 'de_mirage', 'Dust II' -> 'de_dust2', so map pictures and
    FACEIT names line up."""
    return maps.from_name(name)


_MODE_WORDS = re.compile(r"^(premier|competitive|wingman)\b[\s:\-]*", re.I)
_NOT_A_MAP = re.compile(r"\d{4}-\d\d-\d\d|wait time|match duration|replay|ranked|:", re.I)


def _map_from_left(left: List[str], images: List[str]) -> str:
    """The map's id from the left-hand column of one match.

    Steam writes "Premier Mirage" (mode, then map) on the first line. The
    map's picture on that page is named after the map too, which covers a
    first line that is only the mode."""
    for line in left[:2]:
        name = _MODE_WORDS.sub("", line).strip()
        if name and not _NOT_A_MAP.search(name):
            return map_id(name)
    for src in images:
        m = re.search(r"((?:de|cs|ar)_[a-z0-9_]+?)(?:_png)?\.(?:png|jpg|webp)", src or "", re.I)
        if m:
            return maps.canonical(m.group(1))
    return ""


def when(text: str) -> int:
    m = re.search(r"(\d{4})-(\d\d)-(\d\d)\s+(\d\d):(\d\d):(\d\d)", text or "")
    if not m:
        return 0
    return calendar.timegm(tuple(int(g) for g in m.groups()) + (0, 0, 0))


class _Tables(HTMLParser):
    """Collects each match as left-hand text lines and right-hand table rows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.matches: List[Dict[str, Any]] = []
        self.side = ""          # "left" / "right" while inside one
        self.depth = 0          # table nesting inside the current side
        self.row: Optional[Dict[str, Any]] = None
        self.cell: Optional[List[str]] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "table":
            if self.side:
                self.depth += 1
            elif "csgo_scoreboard_inner_left" in cls:
                self.matches.append({"left": [], "rows": [], "images": []})
                self.side, self.depth = "left", 1
            elif "csgo_scoreboard_inner_right" in cls and self.matches:
                self.side, self.depth = "right", 1
        elif not self.side:
            return
        elif tag == "tr":
            self.row = {"cells": [], "links": [], "ids": [], "avatar": ""}
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "a" and self.row is not None and a.get("href"):
            self.row["links"].append(a["href"].rstrip("/"))
        if self.row is not None and a.get("data-miniprofile"):
            self.row["ids"].append(a["data-miniprofile"])
        if tag == "img" and a.get("src"):
            if self.side == "left":
                self.matches[-1]["images"].append(a["src"])
            elif self.row is not None and not self.row["avatar"]:
                self.row["avatar"] = a["src"]

    def handle_endtag(self, tag):
        if not self.side:
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row["cells"].append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.side == "left":
                self.matches[-1]["left"].extend(c for c in self.row["cells"] if c)
            else:
                self.matches[-1]["rows"].append(self.row)
            self.row = None
        elif tag == "table":
            self.depth -= 1
            if self.depth <= 0:
                self.side = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _is_me(row: Dict[str, Any], steam64: str, me: str) -> bool:
    account = str(int(steam64) - 76561197960265728) if steam64.isdigit() else ""
    links = row["links"]
    return bool((account and account in row["ids"])
                or any(steam64 and l.endswith("/profiles/" + steam64) for l in links)
                or any(me and l == me.rstrip("/") for l in links))


def parse(pages: List[str], steam64: str, mode: str, me: str = "") -> List[Dict[str, Any]]:
    """Scoreboard HTML -> match rows in matchlog's shape (``source`` cs2)."""
    out = []
    for html in pages:
        p = _Tables()
        p.feed(html or "")
        for m in p.matches:
            left = m["left"]
            stamp = next((when(t) for t in left if when(t)), 0)
            players, score_at, score = [], -1, (0, 0)
            for row in m["rows"]:
                cells = row["cells"]
                if len(cells) == 1 and ":" in cells[0]:
                    a, _, b = cells[0].partition(":")
                    score_at, score = len(players), (_int(a), _int(b))
                elif len(cells) >= 8 and cells[1] and cells[1][0].isdigit():
                    players.append({
                        "name": cells[0], "kills": _int(cells[2]), "assists": _int(cells[3]),
                        "deaths": _int(cells[4]), "mvps": _int(cells[5]) if cells[5] else 0,
                        "hs_percent": _int(cells[6]), "score": _int(cells[7]),
                        "ping": _int(cells[1]), "team": 0 if score_at < 0 else 1,
                        "avatar": row["avatar"] if row["avatar"].startswith("https://") else "",
                        "you": _is_me(row, steam64, me)})
            mine = next((i for i, pl in enumerate(players) if pl["you"]), -1)
            if not stamp or mine < 0 or score_at < 0:
                continue
            ours, theirs = score if mine < score_at else score[::-1]
            pl = players[mine]
            rounds = ours + theirs
            kills, deaths = pl["kills"], pl["deaths"]
            out.append({
                "source": "cs2", "origin": "steam",
                "match_id": f"steam-{steam64}-{stamp}",
                "steamid": steam64, "map": _map_from_left(left, m["images"]), "mode": mode,
                "won": ours > theirs, "tied": ours == theirs,
                "score": f"{ours} / {theirs}", "rounds": rounds,
                "started_at": stamp, "played_at": stamp,
                "kills": kills, "deaths": deaths, "assists": pl["assists"],
                "mvps": pl["mvps"], "hs_percent": pl["hs_percent"],
                "kd": round(kills / deaths, 2) if deaths else float(kills),
                "kr": round(kills / rounds, 2) if rounds else 0.0,
                "adr": None, "double": None, "triple": None, "quadro": None, "penta": None,
                "elo": None, "elo_delta": None,
                "players": players,
            })
    return out


# ---------------------------------------------------------------------------
# Reading it, in a hidden window that shares the app's Steam sign-in
# (:mod:`steamweb`).

_lock = threading.Lock()
status: Dict[str, Any] = {"state": "idle", "error": "", "updated": 0, "found": 0}


def _read_tabs(window, steam64: str) -> Optional[List[Dict[str, Any]]]:
    import json

    from . import steamweb

    rows: List[Dict[str, Any]] = []
    for tab, mode in TABS.items():
        window.load_url(PAGE.format(steam64=steam64, tab=tab))
        if not steamweb.wait_for(window, lambda u: "gcpd/730" in u or "/login" in u, 30):
            continue
        window.evaluate_js(SCRAPER_JS)
        raw, end = "", time.time() + 120
        while not raw and time.time() < end:
            time.sleep(0.5)
            raw = window.evaluate_js("window.__cs2h || ''") or ""
        if not raw:
            continue  # this tab never answered; the others may
        try:
            got = json.loads(raw)
        except ValueError:
            continue
        if not got.get("signed_in"):
            return None
        rows += parse(got.get("pages") or [], steam64, mode, got.get("me") or "")
    return rows


def sync(steam64: str, save: Callable[[Dict[str, Any]], None]) -> None:
    """Read every tab and hand each match to ``save``. Never raises."""
    from . import steamweb

    if not steamweb.available():
        status.update(state="unavailable",
                      error="Open the app's own window (not a browser tab) to read Steam history.")
        return
    if not _lock.acquire(blocking=False):
        return
    window = None
    try:
        status.update(state="reading", error="")
        window = steamweb.window(PAGE.format(steam64=steam64, tab=next(iter(TABS))))
        rows = _read_tabs(window, steam64)
        if rows is None:
            steamweb.mark({"linked": False})
            status.update(state="signed_out", error="")
            return
        for row in rows:
            save(row)
        status.update(state="done", updated=int(time.time()), found=len(rows))
    except Exception as exc:  # a window that goes away must not take the app with it
        status.update(state="error", error=str(exc)[:200])
    finally:
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass
        _lock.release()
