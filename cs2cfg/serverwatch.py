"""Read-only console.log tail and deliberately conservative server diagnosis.

ASSUMPTION (needs Edy's current CS2 log): a connected client socket dump can
contain [Networking] Remote host is in data center 'dxb'. We require client
connection context and never interpret Selecting/primary/backup relay lines as
the destination datacenter. An IP address or SteamID alone cannot locate an SDR
gameserver. No process handles, injection, GSI installation or network lookups.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path


class ConsoleParser:
    def __init__(self):
        self.reset()

    def reset(self):
        self.server = None
        self.remaining = 0
        self.reported = False

    def feed(self, line, config):
        # Failed attempts and disconnect summaries must not become matches.
        if re.search(r"problem detected|closed by|Closing Steam Net Connection|disconnected|Summary of connection", line, re.I):
            self.reset()
            return None
        connected = re.search(r"\[#(\d+) SDR server[^\]]*\]\s+connected\b", line, re.I)
        bound = re.search(r"\[Networking\]\s+Socket 'client' bound to .*?\[#(\d+) SDR server", line, re.I)
        if connected or bound:
            identity = (connected or bound)[1]
            if self.server != identity:
                self.reported = False
            self.server, self.remaining = identity, 80
            return None
        if not self.remaining:
            return None
        self.remaining -= 1
        match = re.search(r"\[Networking\]\s+Remote host is in data center ['\"]([a-z0-9_-]+)['\"]", line, re.I)
        if match and not self.reported:
            code = match[1].lower()
            pops = config.get("pops", {}) if isinstance(config, dict) else {}
            if code not in pops:
                return None  # Unknown code is not a geolocation guess.
            self.reported = True
            return {"region": code, "server": self.server, "source": "console.log (format awaiting local verification)"}
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
        self.status = "Watching new console connections; log format awaits verification on this PC."
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
            reason = likely_reason(event["region"], expected, firewall, restart, max_ping,
                                   self.queue_survey or {}, now) if wrong else {"code": "expected", "text": "Detected the expected region."}
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
