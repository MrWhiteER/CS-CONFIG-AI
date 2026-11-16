"""Read-only console.log tail and deliberately conservative server diagnosis.

Format verified against a real CS2 console.log (-condebug), Nov 2026:

* At queue time CS2 prints ``Measured RTT to N POPs.  mm_dedicated_search_maxping=M``,
  one ``  code: Nms via ...`` line per POP (a ``-- below this line ping exceeds
  mm_dedicated_search_maxping --`` marker splits them) and ``Confirmed best
  official datacenter ping: N ms``.
* On connecting to a match it selects a relay:
  ``[#id SDR server ...] Selecting sgp#111 (...) as primary.  (Ping = 79 = 78+1+0
  (front+interior+remote)``. When interior+remote is a few ms, the server sits
  at that relay's POP.
* When the connection closes, ``Summary of connection [#id SDR server ...]`` is
  followed by ``Remote host is in data center 'sgp'``: the authoritative answer.

No process handles, injection, GSI installation or network lookups.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_STAMP = re.compile(r"^\d\d/\d\d \d\d:\d\d:\d\d ")
# Interior+remote at or under this many ms means "the server is at this relay".
NEAR_MS = 10


class ConsoleParser:
    def __init__(self):
        self.reset()

    def reset(self):
        self.server = None
        self.reported = {}          # server id -> region already reported
        self.queue = None           # last completed queue-time measurement
        self._building = None
        self._summary = None
        self._summary_left = 0

    def _known(self, code, config):
        pops = config.get("pops", {}) if isinstance(config, dict) else {}
        return code if code in pops else None

    def _event(self, server, code, source):
        if self.reported.get(server) == code:
            return None
        self.reported[server] = code
        return {"region": code, "server": server, "source": source,
                "queue": dict(self.queue) if self.queue else None}

    def feed(self, line, config):
        line = _STAMP.sub("", line.rstrip("\r"))

        # Queue-time ping table.
        start = re.search(r"Measured RTT to \d+ POPs\.\s+mm_dedicated_search_maxping=(\d+)", line)
        if start:
            self._building = {"max_ping": int(start[1]), "pings": {}, "under": [], "best_official": None}
            self._below = False
            return None
        if self._building is not None:
            if "below this line ping exceeds" in line:
                self._below = True
                return None
            row = re.match(r"\s+([a-z0-9]+): (\d+)ms via", line)
            if row:
                self._building["pings"][row[1]] = int(row[2])
                if not self._below:
                    self._building["under"].append(row[1])
                return None
            best = re.search(r"Confirmed best official datacenter ping: (\d+) ms", line)
            if best:
                self._building["best_official"] = int(best[1])
                self.queue, self._building = self._building, None
                return None
            if re.match(r"\s", line) or line.startswith("Obtained direct RTT") or line.startswith("("):
                return None
            # Anything else ends the table even without the closing line.
            self.queue, self._building = self._building, None

        # Relay chosen on connect: the server is at that POP when the back
        # half of the route is only a few ms.
        chosen = re.search(r"\[#(\d+) SDR server[^\]]*\] Selecting ([a-z0-9]+)#\d+ \([^)]*\) as primary\."
                           r"\s+\(Ping = \d+ = \d+\+(\d+)\+(\d+) \(front\+interior\+remote\)", line)
        if chosen:
            self.server = chosen[1]
            if int(chosen[3]) + int(chosen[4]) <= NEAR_MS:
                code = self._known(chosen[2], config)
                if code:
                    return self._event(chosen[1], code, "console.log: relay chosen on connect")
            return None

        # Authoritative answer when the connection closes.
        summary = re.search(r"Summary of connection \[#(\d+) SDR server", line)
        if summary:
            self._summary, self._summary_left = summary[1], 8
            return None
        if self._summary and self._summary_left:
            self._summary_left -= 1
            where = re.search(r"Remote host is in data center ['\"]([a-z0-9_-]+)['\"]", line, re.I)
            if where:
                server, self._summary = self._summary, None
                code = self._known(where[1].lower(), config)
                if code:
                    self.server = server
                    return self._event(server, code, "console.log: connection summary")
        return None


def queue_reason(queue, expected):
    """What CS2 itself measured when it queued, in plain words, or None."""
    if not queue or queue.get("max_ping") is None:
        return None
    limit, best = queue["max_ping"], queue.get("best_official")
    mine = [queue["pings"][c] for c in expected if c in queue.get("pings", {})]
    tail = f" Your ping to your chosen region was {min(mine)} ms." if mine else ""
    if best is not None and best > limit:
        return {"code": "queue_max_ping",
                "text": f"No official CS2 server was under your matchmaking max ping ({limit} ms) when you queued; "
                        f"the closest official one was {best} ms, so CS2 widened the search.{tail}"}
    if mine and min(mine) > limit:
        return {"code": "queue_region_slow",
                "text": f"When you queued, your ping to your chosen region was {min(mine)} ms, above your "
                        f"matchmaking max ping ({limit} ms), so CS2 did not treat it as a near server."}
    return None


def likely_reason(actual, expected, firewall, restart, max_ping, survey, now=None):
    """Ordered evidence checks. Unknown evidence never turns into a certainty."""
    now = time.time() if now is None else now
    rows = survey.get("regions", [])
    actual_row = next((r for r in rows if actual in r.get("codes", [r.get("code")])), {})
    actual_ping = actual_row.get("ping_ms")
    if (firewall.get("present") is False and max_ping is not None
            and actual_ping is not None and max_ping >= actual_ping):
        return {"code": "max_ping", "text": f"Likely: no region lock is active and your saved max ping ({max_ping} ms) allows this region's last measured relay ping ({actual_ping:g} ms)."}
    if firewall.get("status") in ("outdated", "damaged") or (firewall.get("code") and not firewall.get("active")):
        return {"code": "rules", "text": "Likely: region lock rules are missing, disabled or out of date. Refresh the directory and re-apply the lock."}
    if firewall.get("status") == "unknown":
        return {"code": "unknown", "text": "The likely reason is unknown: Windows Firewall could not be checked. Check lock status before queuing again."}
    if restart is True:
        return {"code": "restart", "text": "Likely: Steam or CS2 has not restarted since this lock was applied, so matchmaking may still use cached relay measurements."}
    # ICMP silence is not proof of outage. Only a recent, completed sweep can
    # support this possibility; do not claim a later sweep was queue-time data.
    stamp = survey.get("updated_at")
    wanted = [r for r in rows if set(r.get("codes", [r.get("code")])) & set(expected)]
    if (isinstance(stamp, (int, float)) and 0 <= now - stamp <= 300 and wanted
            and all(r.get("ping_ms") is None or (r.get("loss") or 0) >= 20 for r in wanted)):
        return {"code": "reachability", "text": "Likely: your preferred region may have been hard to reach. The last sweep seen before this connection was detected had no ICMP replies or high loss. ICMP silence does not confirm an outage; exact queue-time availability is unknown."}
    return {"code": "availability", "text": "Likely possibilities: if you queued in a party, the party's combined ping decides the region (we cannot see members); otherwise the region may have had no match for your mode at that time. Neither can be verified from the console log."}


class MatchWatch:
    def __init__(self, history_path: Path):
        self.path = history_path
        try:
            saved = json.loads(history_path.read_text(encoding="utf-8"))
            self.history = [r for r in saved if isinstance(r, dict) and all(k in r for k in ("time", "region", "expected", "reason", "id"))][-20:] if isinstance(saved, list) else []
        except (OSError, ValueError, TypeError):
            self.history = []
        self.notice = None
        self.status = "Waiting for CS2. Enable -condebug to detect servers."
        self.parser = ConsoleParser()
        self.log_path = None
        self.identity = None
        self.offset = 0
        self.carry = b""
        self.last_server = None
        self.was_running = False
        self.queue_survey = None
        self.latest_survey = None

    def poll(self, path, running, config, expected, firewall, restart, max_ping, survey):
        now = time.time()
        # Capture the last completed sweep before connection context, rather
        # than substituting a sweep measured after a match was detected.
        if not survey.get("running") and survey.get("updated_at"):
            import copy
            candidate = copy.deepcopy(survey)
        else:
            candidate = self.latest_survey or {}
        self.latest_survey = candidate
        if not path:
            self.status = "CS2 installation not found; console detection unavailable."
            return
        path = Path(path)
        try:
            with path.open("rb") as handle:
                stat = path.stat()
                identity = (stat.st_dev, stat.st_ino)
                first = self.log_path != path or self.identity is None
                rotated = self.identity is not None and (identity != self.identity or stat.st_size < self.offset)
                if first or rotated or not running:
                    self.parser.reset()
                    self.carry = b""
                    self.last_server = None
                    # First attachment skips old sessions. A newly created or
                    # truncated log starts at byte zero and is read in full.
                    self.offset = stat.st_size if first or not running else 0
                self.log_path, self.identity = path, identity
                self.was_running = running
                if not running:
                    self.status = "Waiting for CS2; only new console connections are recorded."
                    return
                handle.seek(self.offset)
                chunk = handle.read(262144)
                self.offset = handle.tell()
        except OSError:
            # Remember a missing file so its creation can be read from zero.
            self.log_path, self.identity, self.offset = path, (-1, -1), 0
            self.was_running = running
            self.status = "console.log unavailable. Enable -condebug, restart CS2 and join a match."
            return
        self.status = "Watching CS2 console for new matches."
        lines = (self.carry + chunk).split(b"\n")
        self.carry = lines.pop()[-16384:]
        for raw in lines:
            line = raw.decode("utf-8", errors="replace")
            old_server = self.parser.server
            event = self.parser.feed(line, config)
            if self.parser.server and self.parser.server != old_server:
                self.queue_survey = candidate
            if not event or event["server"] == self.last_server:
                continue
            self.last_server = event["server"]
            wrong = event["region"] not in expected
            reason = ((queue_reason(event.get("queue"), expected)
                       or likely_reason(event["region"], expected, firewall, restart, max_ping,
                                        self.queue_survey or {}, now))
                      if wrong else {"code": "expected", "text": "Detected the expected region."})
            row = {"id": f"{time.time_ns()}-{event['server']}", "time": now,
                   "region": event["region"], "expected": list(expected), "reason": reason,
                   "source": event["source"], "wrong": wrong}
            self.history = (self.history + [row])[-20:]
            if wrong:
                self.notice = row
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(self.history, indent=2), encoding="utf-8")
                temporary.replace(self.path)
            except OSError:
                self.status += " History could not be saved."
