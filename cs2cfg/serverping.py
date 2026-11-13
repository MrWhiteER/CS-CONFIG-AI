"""On-demand ICMP measurements to Valve SDR relays; never writes game files."""
from __future__ import annotations

import copy
import ipaddress
import json
import re
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen

from . import netcheck

SDR_URL = "https://api.steampowered.com/ISteamApps/GetSDRConfig/v1/?appid=730"
DAY = 86400
# Known public relay addresses. Discovery replaces these when available.
FALLBACK = {"pops": {
    "dxb": {"desc": "Dubai (United Arab Emirates)", "relays": [
        {"ipv4": "185.25.183.163"}, {"ipv4": "185.25.183.179"}]},
    "fra": {"desc": "Frankfurt (Germany)", "relays": [{"ipv4": "155.133.226.68"}]},
}}


def parse_regions(config: dict) -> list:
    """Group city variants, keeping valid public IPv4 targets only."""
    groups = {}
    if not isinstance(config, dict):
        return []
    pops = config.get("pops", {})
    if not isinstance(pops, dict):
        return []
    for code, pop in pops.items():
        if not isinstance(pop, dict) or not isinstance(code, str):
            continue
        desc = pop.get("desc")
        if not isinstance(desc, str) or not desc.strip():
            continue
        match = re.fullmatch(r"\s*(.*?)\s*\(([^()]+)\)\s*", desc)
        city, country = (match[1].strip(), match[2].strip()) if match else (desc.strip(), "")
        relays = []
        raw_relays = pop.get("relays", [])
        for relay in raw_relays if isinstance(raw_relays, list) else []:
            try:
                address = ipaddress.IPv4Address(relay["ipv4"])
                if address.is_global:
                    relays.append(str(address))
            except (KeyError, TypeError, ValueError, ipaddress.AddressValueError):
                continue
        if not relays:
            continue
        key = (city.casefold(), country.casefold())
        region = groups.setdefault(key, {"code": re.sub(r"\d+$", "", code),
                                        "city": city, "country": country,
                                        "codes": [], "relays": [], "pop_relays": []})
        region["codes"].append(code)
        region["relays"] = list(dict.fromkeys(region["relays"] + relays))
        region["pop_relays"].append(list(dict.fromkeys(relays)))
    return sorted(groups.values(), key=lambda row: (row["city"], row["country"]))


def classify(ping_ms, loss=0) -> str:
    # Silence is not evidence that a datacenter is down.
    if ping_ms is None or loss >= 100:
        return "unknown"
    if loss > 0 or ping_ms > 90:
        return "bad"
    return "good" if ping_ms <= 30 else "ok"


def color_stop(ping_ms):
    """Continuous data scale, shared with the UI: stop index and blend to next."""
    stops = (30, 60, 90, 130, 180)
    if ping_ms is None:
        return None
    for index, end in enumerate(stops[1:]):
        if ping_ms <= end:
            return index, max(0.0, (ping_ms - stops[index]) / (end - stops[index]))
    return 4, 0.0


def measure(region: dict) -> dict:
    """Three probes per relay; try a second relay if the first is silent."""
    tried, candidates = 0, []
    # Each numbered POP is measured; a responsive first variant must not mask
    # a better route through another variant in the same city.
    for relays in region.get("pop_relays", [region["relays"]]):
        times, sent = [], 0
        for host in relays[:2]:
            tried += 1
            samples = [netcheck._ping_once(host) for _ in range(3)]
            sent += len(samples)
            times.extend(value for value in samples if value is not None)
            if times:
                candidates.append((round(statistics.median(times), 1),
                                   round((sent - len(times)) / sent * 100, 1)))
                break
    ping_ms, loss = min(candidates) if candidates else (None, 100.0)
    return {key: region[key] for key in ("code", "city", "country", "codes")} | {
        "ping_ms": ping_ms, "loss": loss, "status": classify(ping_ms, loss),
        "relays_tried": tried}


def read_max_ping(path: Path):
    """Optional read of the active account's saved cvar."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'"mm_dedicated_search_maxping"\s+"(\d+)"', text)
        value = int(match[1]) if match else 0
        return value if 0 < value <= 5000 else None
    except OSError:
        return None


class ServerPing:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.lock = threading.Lock()
        self.config = None
        self.checked_at = 0
        self.directory_error = ""
        self.data = {"running": False, "updated_at": None, "regions": [],
                     "completed": 0, "total": 0, "source": "fallback", "error": ""}

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def _regions(self):
        now = time.time()
        if self.config is None:
            try:
                cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if parse_regions(cached["config"]):
                    self.config = cached["config"]
                    self.checked_at = float(cached["checked_at"])
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if self.config is not None and now - self.checked_at < DAY:
            return parse_regions(self.config), "cache", self.directory_error
        # Also rate-limit failed requests for the lifetime of the app.
        if now - self.checked_at < DAY:
            return parse_regions(self.config or FALLBACK), "fallback", "Valve directory unavailable; using bundled relays."
        self.checked_at = now
        try:
            with urlopen(SDR_URL, timeout=8) as response:
                config = json.loads(response.read(2_000_000))
            if not isinstance(config, dict) or not parse_regions(config):
                raise ValueError("Valve returned an empty relay directory")
            self.config = config
            self.directory_error = ""
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps({"checked_at": now, "config": config}), encoding="utf-8")
            except OSError:
                pass  # In-memory cache still works on read-only installations.
            return parse_regions(config), "live", ""
        except Exception:
            self.directory_error = "Valve directory unavailable; using saved relays. ICMP silence means unknown."
            return parse_regions(self.config or FALLBACK), "cache" if self.config else "fallback", self.directory_error

    def start(self):
        with self.lock:
            if self.data["running"]:
                return copy.deepcopy(self.data)
            self.data.update(running=True, completed=0, total=0, error="")
            result = copy.deepcopy(self.data)
        threading.Thread(target=self._sweep, daemon=True, name="server-ping").start()
        return result

    def _sweep(self):
        try:
            regions, source, error = self._regions()
            pending = [{key: row[key] for key in ("code", "city", "country", "codes")} | {
                "ping_ms": None, "loss": None, "status": "measuring", "relays_tried": 0} for row in regions]
            with self.lock:
                self.data.update(regions=pending, total=len(regions), source=source, error=error)
            with ThreadPoolExecutor(max_workers=8) as pool:
                jobs = {pool.submit(measure, region): index for index, region in enumerate(regions)}
                for future in as_completed(jobs):
                    result = future.result()
                    with self.lock:
                        self.data["regions"][jobs[future]] = result
                        self.data["completed"] += 1
            with self.lock:
                self.data["updated_at"] = time.time()
        except Exception as exc:
            with self.lock:
                self.data["error"] = f"Could not measure relays: {exc}"
        finally:
            with self.lock:
                self.data["running"] = False
