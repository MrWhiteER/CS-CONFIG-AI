"""What the connection is actually doing, measured on this machine.

CS2's sub-tick networking timestamps the moment you click rather than rounding
it to a tick, which makes it far less forgiving of a lossy link than CS:GO was.
A packet carrying a shot that never arrives is a shot the server never saw: the
client has already drawn the blood splatter locally, so it reads as the game
refusing to register a hit that plainly landed. Jitter does the same thing more
subtly -- timestamps arriving out of order desynchronise client and server, and
what comes back is a death behind a wall.

So "shots do not register" is usually a measurement problem, not a settings
problem, and the measurement worth making is not average ping. It is **loss and
jitter**, and *where* they start:

* the **first hop** is the router. Loss here is this room -- Wi-Fi, a bad cable,
  a saturated uplink -- and it is the case a player can actually fix.
* the **far end** is everything past it. Loss that appears only here is the ISP
  or the route, which is worth knowing precisely because no amount of tuning
  this machine will touch it.

Splitting the two is the whole point. A tool that reports one number cannot
tell somebody whether to change their Wi-Fi or ring their ISP.

Nothing here writes. It measures, and says what it found.
"""

from __future__ import annotations

import re
import statistics
import subprocess
import threading
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Where to measure to. Cloudflare and Google resolvers answer ICMP reliably and
# are close to most routes, so a loss reading against them reflects the path
# rather than a busy host deprioritising pings.
ANCHOR = "1.1.1.1"
ANCHOR_BACKUP = "8.8.8.8"

# How long the whole measurement takes, and how many probes fit in it.
#
# Five seconds, spaced rather than fired in one burst. The spacing is the part
# that matters: jitter is about whether a link is steady over time, and twenty
# packets sent back to back only describe one instant. Sixteen probes three
# tenths of a second apart still sample across a window rather than a moment.
#
# It is a real trade. A longer run is more confident -- loss of one in fifty
# shows up in sixty probes and can hide in sixteen. Five seconds is the length
# somebody will actually sit through, and a check that gets run beats a better
# one that does not, so a clean result here says "nothing obvious" rather than
# "certainly nothing".
WINDOW = 5.0
SAMPLES = 16
GAP = WINDOW / SAMPLES

# A reply slower than this is counted as lost. Half a second is far beyond
# playable, so nothing that could be played on is miscounted -- and waiting a
# full second per lost packet would push a lossy link well past the window.
PING_WAIT = 500

# What sub-tick will tolerate. These are not ping thresholds -- a 60 ms
# connection with no loss plays fine, and a 10 ms one with 2% loss does not.
LOSS_FINE = 0.0
LOSS_POOR = 1.0            # per the sub-tick guidance: ~1% is already felt
JITTER_FINE = 5.0
JITTER_POOR = 15.0

_CREATE_NO_WINDOW = 0x08000000


def _hidden() -> dict:
    """Keep console windows from flashing up when the app is a GUI process."""
    if sys.platform != "win32":
        return {}
    return {"creationflags": _CREATE_NO_WINDOW}


@dataclass
class Probe:
    """One measurement to one host."""
    host: str
    label: str
    sent: int = 0
    times: List[float] = field(default_factory=list)
    # Which probes went unanswered, by index. Kept so a drawn line can show a
    # gap where the loss was instead of closing over it as if nothing happened.
    misses: List[int] = field(default_factory=list)
    error: str = ""

    @property
    def received(self) -> int:
        """Derived rather than tallied.

        It was a field the parser set and the live sweep forgot to, so a run
        being watched reported every reply as lost while holding the timings
        that proved otherwise -- and then replaced a perfectly good measurement
        with the fallback host. Counting the replies themselves cannot drift
        from the replies.
        """
        return len(self.times)

    @property
    def reachable(self) -> bool:
        return self.received > 0

    @property
    def loss(self) -> float:
        if not self.sent:
            return 0.0
        return round((self.sent - self.received) / self.sent * 100, 1)

    @property
    def average(self) -> float:
        return round(statistics.fmean(self.times), 1) if self.times else 0.0

    @property
    def worst(self) -> float:
        return round(max(self.times), 1) if self.times else 0.0

    @property
    def best(self) -> float:
        return round(min(self.times), 1) if self.times else 0.0

    @property
    def jitter(self) -> float:
        """Mean deviation between consecutive replies.

        Consecutive rather than standard deviation on purpose: what upsets
        sub-tick is one packet arriving late relative to the one before it, not
        the spread of the whole sample. A link that drifts slowly from 20 ms to
        40 ms has a wide spread and low jitter, and plays fine.
        """
        if len(self.times) < 2:
            return 0.0
        steps = [abs(b - a) for a, b in zip(self.times, self.times[1:])]
        return round(statistics.fmean(steps), 1)


@dataclass
class Adapter:
    name: str = ""
    description: str = ""
    speed: str = ""
    media: str = ""

    @property
    def wireless(self) -> bool:
        blob = f"{self.media} {self.description} {self.name}".lower()
        return "802.11" in blob or "wi-fi" in blob or "wifi" in blob or "wireless" in blob


@dataclass
class Finding:
    """Something worth telling the player, in their terms."""
    severity: str              # "bad" | "warn" | "good"
    title: str
    detail: str


@dataclass
class Survey:
    adapter: Optional[Adapter] = None
    gateway: Optional[Probe] = None
    internet: Optional[Probe] = None
    findings: List[Finding] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not any(f.severity == "bad" for f in self.findings)


def _run(args: List[str], timeout: int) -> str:
    try:
        done = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, **_hidden())
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout or ""


def adapter() -> Optional[Adapter]:
    """The connection actually carrying traffic right now."""
    out = _run(["powershell", "-NoProfile", "-Command",
                "Get-NetAdapter | Where-Object Status -eq Up | "
                "Sort-Object -Property InterfaceMetric | Select-Object -First 1 "
                "Name,InterfaceDescription,LinkSpeed,PhysicalMediaType | ConvertTo-Json"], 40)
    if not out.strip():
        return None
    import json
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if isinstance(data, list):
        data = data[0] if data else {}
    return Adapter(
        name=str(data.get("Name") or ""),
        description=str(data.get("InterfaceDescription") or ""),
        speed=str(data.get("LinkSpeed") or ""),
        media=str(data.get("PhysicalMediaType") or ""),
    )


def gateway_address() -> str:
    """The router this machine talks through, or "" if it cannot be read."""
    out = _run(["powershell", "-NoProfile", "-Command",
                "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | "
                "Sort-Object -Property RouteMetric | "
                "Select-Object -First 1).NextHop"], 30)
    found = out.strip().splitlines()
    return found[0].strip() if found else ""


# ping.exe writes "time=12ms", "time<1ms", and localised variants. The number
# is what matters; the surrounding word is not worth depending on.
_TIME = re.compile(r"[=<]\s*(\d+(?:\.\d+)?)\s*ms", re.I)


def ping(host: str, label: str, count: int = SAMPLES) -> Probe:
    """Measure one host, counting what came back rather than trusting a summary.

    The reply lines are parsed instead of ping's own statistics block because
    that block is localised -- on a non-English Windows the words change and a
    summary parser silently reports a perfect connection.
    """
    found = Probe(host=host, label=label, sent=count)
    if not host:
        found.error = "no address to measure"
        found.sent = 0
        return found

    # -w keeps one dead host from stalling the whole check.
    out = _run(["ping", "-n", str(count), "-w", str(PING_WAIT), host],
               int(count * (GAP + 1)) + 15)
    if not out.strip():
        found.error = "ping could not be run"
        found.sent = 0
        return found

    for line in out.splitlines():
        match = _TIME.search(line)
        if match and "ttl" in line.lower():
            found.times.append(float(match.group(1)))
    if not found.received:
        found.error = f"{host} did not answer"
    return found


def _judge(probe: Probe, where: str, findings: List[Finding]) -> None:
    if probe is None or not probe.sent:
        return
    if not probe.reachable:
        findings.append(Finding("warn", f"{probe.label} did not answer",
                                f"{probe.host} ignored every probe. Many routers and "
                                "some networks drop pings on purpose, so this is not "
                                "proof of a fault -- it just means this half could "
                                "not be measured."))
        return

    if probe.loss > LOSS_POOR:
        findings.append(Finding("bad", f"{probe.loss}% packet loss {where}",
                                "Sub-tick sends the exact moment you clicked. A lost "
                                "packet is a shot the server never saw, however clearly "
                                "it landed on your screen. Anything above zero is felt; "
                                "this is well above."))
    elif probe.loss > LOSS_FINE:
        findings.append(Finding("warn", f"{probe.loss}% packet loss {where}",
                                "Low, but not nothing. Under sub-tick even occasional "
                                "loss shows up as the odd shot that does not count."))

    if probe.jitter >= JITTER_POOR:
        findings.append(Finding("bad", f"{probe.jitter} ms jitter {where}",
                                "Replies arriving at uneven intervals desynchronise the "
                                "client and the server. It reads as dying behind cover, "
                                "or hitting someone who has already moved."))
    elif probe.jitter >= JITTER_FINE:
        findings.append(Finding("warn", f"{probe.jitter} ms jitter {where}",
                                "Enough unevenness to notice in a duel, though not enough "
                                "to be the whole story on its own."))


def _conclude(adapter_found, gateway: Probe, internet: Probe) -> List[Finding]:
    """What the two measurements mean together.

    Split out of survey() so a run that is watched as it happens reaches the
    same verdict as one that is waited for -- there should not be two opinions
    about the same numbers.
    """
    findings: List[Finding] = []
    if adapter_found is not None and adapter_found.wireless:
        findings.append(Finding(
            "warn", "This machine is on Wi-Fi",
            "Wi-Fi loses packets that a cable does not -- from interference, from "
            "other devices, from the radio retrying. It is the most common cause "
            "of shots not registering, and the one with the simplest fix. If a "
            "cable can reach this machine, try one before changing any setting."))

    _judge(gateway, "to your own router", findings)
    _judge(internet, "out to the internet", findings)

    near, far = gateway, internet
    if near and far and near.reachable and far.reachable:
        if near.loss > LOSS_FINE or near.jitter >= JITTER_FINE:
            findings.append(Finding(
                "bad", "The trouble starts inside your own network",
                "Your router is already losing or delaying packets before they "
                "reach the internet, so nothing beyond this building is to blame. "
                "Wi-Fi, the cable, or something else on the network saturating the "
                "line -- a download, a console updating, another PC streaming."))
        elif far.loss > LOSS_FINE or far.jitter >= JITTER_POOR:
            findings.append(Finding(
                "warn", "Your own network is clean; the trouble is past it",
                "The link to your router is fine and the problem appears beyond "
                "it. That is your ISP or the route to the server, and no setting "
                "on this machine will change it. Worth reporting to them with "
                "these numbers."))

    if not findings:
        findings.append(Finding(
            "good", "Nothing wrong with this connection",
            "No loss and steady timing, on both halves. Shots that do not "
            "register on a link measuring like this are not being lost on the "
            "way out of this machine."))
    return findings


def survey(samples: int = SAMPLES) -> Survey:
    """Measure this machine's link and say what is wrong with it, if anything.

    Takes roughly forty seconds: two runs of twenty probes, a second apart,
    because loss and jitter cannot be sampled quickly without measuring noise
    rather than the connection.
    """
    found = Survey()
    if sys.platform != "win32":
        found.error = "this check uses Windows networking tools"
        return found

    found.adapter = adapter()
    router = gateway_address()
    found.gateway = ping(router, "Your router", samples) if router else None
    found.internet = ping(ANCHOR, "The internet", samples)
    if found.internet and not found.internet.reachable:
        found.internet = ping(ANCHOR_BACKUP, "The internet", samples)

    # The same verdict the watched run reaches, from the same function.
    found.findings = _conclude(found.adapter, found.gateway, found.internet)
    return found


def as_dict(found: Survey) -> dict:
    def probe(p: Optional[Probe]) -> Optional[dict]:
        if p is None:
            return None
        return {"host": p.host, "label": p.label, "sent": p.sent,
                "received": p.received, "loss": p.loss, "average": p.average,
                "worst": p.worst, "jitter": p.jitter,
                "reachable": p.reachable, "error": p.error}

    return {
        "ok": found.ok,
        "error": found.error,
        "adapter": ({"name": found.adapter.name,
                     "description": found.adapter.description,
                     "speed": found.adapter.speed,
                     "wireless": found.adapter.wireless}
                    if found.adapter else None),
        "gateway": probe(found.gateway),
        "internet": probe(found.internet),
        "findings": [{"severity": f.severity, "title": f.title, "detail": f.detail}
                     for f in found.findings],
    }


# ---------------------------------------------------------------------------
# A measurement you can watch
# ---------------------------------------------------------------------------
#
# The original ran twenty probes per host in one ping command and returned when
# both were finished: about forty seconds staring at a spinner, and no way to
# tell a link that was fine from one that had already started dropping packets
# ten seconds in.
#
# This sends them one at a time and publishes each reply as it lands, so the
# page can draw the line as it is measured. The pacing is unchanged and
# deliberate -- roughly a second between probes. A burst of twenty back to back
# finishes in two seconds and measures nothing useful: jitter is about how
# steady a link is over time, and twenty packets sent at once only says what
# one moment looked like.
#
# Both hosts are measured at the same time on their own threads, which is what
# pays for the pacing: the whole run still takes about as long as one host used
# to, rather than twice as long.



def _ping_once(host: str) -> "Optional[float]":
    """One probe. The round trip in milliseconds, or None if nothing came back."""
    out = _run(["ping", "-n", "1", "-w", str(PING_WAIT), host], 8)
    for line in out.splitlines():
        match = _TIME.search(line)
        if match and "ttl" in line.lower():
            return float(match.group(1))
    return None


class Run:
    """One measurement, readable while it is still going."""

    def __init__(self, samples: int = SAMPLES) -> None:
        self.samples = max(4, min(60, int(samples)))
        self.adapter: "Optional[Adapter]" = None
        self.gateway = Probe(host="", label="Your router")
        self.internet = Probe(host=ANCHOR, label="The internet")
        self.findings: List[Finding] = []
        self.error = ""
        self.done = False
        self.started = 0.0
        self._lock = threading.Lock()
        self._threads: List[threading.Thread] = []

    # -- running ----------------------------------------------------------
    def begin(self) -> None:
        if self.started:
            return
        self.started = time.time()
        if sys.platform != "win32":
            self.error = "this check uses Windows networking tools"
            self.done = True
            return

        # Which adapter is in use only decorates the result, so it is fetched
        # alongside the probing rather than before it. Both of these are
        # PowerShell starts, and doing them in sequence first spent a second
        # of a five second budget before a single packet had been sent.
        def find_adapter() -> None:
            found = adapter()
            with self._lock:
                self.adapter = found

        threading.Thread(target=find_adapter, daemon=True).start()

        router = gateway_address()
        self.gateway.host = router

        targets = [(self.gateway, router)] if router else []
        targets.append((self.internet, ANCHOR))
        for probe, host in targets:
            probe.sent = 0
            thread = threading.Thread(target=self._sweep, args=(probe, host),
                                      daemon=True)
            thread.start()
            self._threads.append(thread)

        threading.Thread(target=self._finish, daemon=True).start()

    def _sweep(self, probe: Probe, host: str) -> None:
        if not host:
            return
        for index in range(self.samples):
            began = time.monotonic()
            reply = _ping_once(host)
            with self._lock:
                probe.sent += 1
                if reply is not None:
                    probe.times.append(reply)
                else:
                    # Recorded so the drawn line has a gap where the loss was,
                    # rather than closing over it as though nothing happened.
                    probe.misses.append(probe.sent - 1)
            if index < self.samples - 1:
                # The gap is a cadence, not an addition. Starting a ping costs
                # about a tenth of a second, and sleeping the full gap on top
                # of that stretched a five second window to nearly seven.
                rest = GAP - (time.monotonic() - began)
                if rest > 0:
                    time.sleep(rest)

    def _finish(self) -> None:
        for thread in self._threads:
            thread.join()
        if self.internet.sent and not self.internet.received:
            # The anchor may simply be one that this network will not answer.
            backup = ping(ANCHOR_BACKUP, "The internet", max(4, self.samples // 2))
            if backup.received:
                with self._lock:
                    self.internet = backup
        with self._lock:
            self.findings = _conclude(self.adapter, self.gateway, self.internet)
            self.done = True

    # -- reading ----------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "running": bool(self.started) and not self.done,
                "done": self.done,
                "error": self.error,
                "samples": self.samples,
                "adapter": ({"name": self.adapter.name,
                             "description": self.adapter.description,
                             "speed": self.adapter.speed,
                             "wireless": self.adapter.wireless}
                            if self.adapter else None),
                "gateway": _probe_shape(self.gateway),
                "internet": _probe_shape(self.internet),
                "findings": [{"severity": f.severity, "title": f.title,
                              "detail": f.detail} for f in self.findings],
            }


def _probe_shape(probe: Probe) -> Dict[str, Any]:
    return {"host": probe.host, "label": probe.label, "sent": probe.sent,
            "received": probe.received, "loss": probe.loss,
            "average": probe.average, "worst": probe.worst,
            "best": probe.best, "jitter": probe.jitter,
            "times": list(probe.times), "misses": list(probe.misses),
            "reachable": probe.reachable, "error": probe.error}


_run_now: "Optional[Run]" = None


def start(samples: int = SAMPLES) -> Dict[str, Any]:
    """Begin a measurement, replacing any that has finished."""
    global _run_now
    if _run_now is not None and not _run_now.done:
        return _run_now.snapshot()
    _run_now = Run(samples)
    _run_now.begin()
    return _run_now.snapshot()


def progress() -> Dict[str, Any]:
    """Where the current measurement has got to, if there is one."""
    if _run_now is None:
        return {"ok": True, "running": False, "done": False, "idle": True}
    return _run_now.snapshot()
