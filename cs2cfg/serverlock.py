"""CS2-only region locks through the setup-installed helper; never prompt.

Local intent describes the selection. ActiveStore rules are the source of truth.
The observer also drains persisted requests after CS2 closes. No probes here.
"""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import re
import threading
import time
import uuid
from pathlib import Path, PureWindowsPath

from . import quickfix, serverping

try:
    from . import elevated
except ImportError:
    elevated = None

GROUP = "CS CONFIG AI region lock"
DISPLAY_PREFIX = "CS CONFIG AI lock - "
SETUP_MESSAGE = 'The region lock needs the one-time setup permission. In Settings, choose "Run setup again".'
PENDING_MESSAGE = "Will apply when CS2 closes"
REGION_NAME = re.compile(r"[A-Za-z0-9 _\-.()]{1,48}")


def helper_ready():
    return elevated is not None and elevated.ready()


def cs2_program(program):
    program = str(program or "")
    if (not PureWindowsPath(program).is_absolute()
            or not re.search(r"\\game\\bin\\win64\\cs2\.exe$", program, re.I)):
        raise ValueError("CS2's full install path is unavailable. Check the CS2 installation and try again.")
    return program


def address_digest(addresses):
    return hashlib.sha256(json.dumps(sorted(addresses, key=ipaddress.IPv4Address)).encode()).hexdigest()


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def build_plan(config, selected):
    """Block every other POP, including POPs without descriptions/partner POPs.

    Shared IPs always belong to the chosen region. Fail closed on malformed
    directory data rather than silently produce an incomplete block list.
    Numbered city variants come from the ping widget's existing grouping.
    """
    if not isinstance(config, dict) or not isinstance(config.get("revision"), int):
        raise ValueError("Refresh server ping first: a full Valve directory with a revision is required.")
    rows = serverping.parse_regions(config)
    chosen = next((r for r in rows if r["code"] == selected), None)
    if chosen is None:
        raise ValueError("That region is not in the saved Valve directory. Refresh server ping.")
    allowed, pops = set(), {}
    for code, pop in config["pops"].items():
        if not isinstance(code, str) or not isinstance(pop, dict) or not isinstance(pop.get("relays", []), list):
            raise ValueError("Valve's saved directory is malformed; refresh server ping.")
        pops[code] = set()
        for relay in pop.get("relays", []):
            try:
                address = ipaddress.IPv4Address(relay["ipv4"])
                if not address.is_global:
                    raise ValueError("non-public address")
            except (TypeError, KeyError, ValueError):
                raise ValueError("Valve's saved directory contains an invalid relay; refresh server ping.") from None
            pops[code].add(str(address))
        if code in chosen["codes"]:
            allowed.update(pops[code])
    regions = []
    for code, addresses in sorted(pops.items()):
        addresses = addresses - allowed
        if code in chosen["codes"] or not addresses:
            continue
        if not isinstance(code, str) or not REGION_NAME.fullmatch(code):
            raise ValueError("A blocked POP name exceeds the helper's allowed name format (1-48 safe characters).")
        regions.append({"name": code, "cidrs": [a + "/32" for a in sorted(addresses, key=ipaddress.IPv4Address)]})
    if not 1 <= len(regions) <= 64:
        raise ValueError("The region lock helper requires 1-64 blocked POPs; no lock was created.")
    if sum(len(r["cidrs"]) for r in regions) > 2000:
        raise ValueError("The region lock exceeds the helper's 2000 CIDR limit; no lock was created.")
    blocked = set().union(*(addresses - allowed for code, addresses in pops.items() if code not in chosen["codes"]))
    if not allowed or not blocked:
        raise ValueError("The saved Valve directory is incomplete; no lock was created.")
    addresses = sorted(blocked, key=ipaddress.IPv4Address)
    plan = {"code": chosen["code"], "city": chosen["city"], "codes": sorted(chosen["codes"]),
            "revision": config["revision"], "addresses": addresses, "regions": regions,
            "address_digest": address_digest(addresses)}
    plan["digest"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def inspect_script():
    # ActiveStore is the resultant policy, including local policy merging/GPO.
    return """$ErrorActionPreference = 'Stop'
try {
  $group = GROUP_LITERAL
  $rules = @(Get-NetFirewallRule -PolicyStore ActiveStore | Where-Object { $_.Group -ceq $group } | ForEach-Object {
    $a = $_ | Get-NetFirewallAddressFilter
    $p = $_ | Get-NetFirewallPortFilter
    $app = $_ | Get-NetFirewallApplicationFilter
    $svc = $_ | Get-NetFirewallServiceFilter
    [pscustomobject]@{ group=$_.Group; display_name=$_.DisplayName; enabled=[string]$_.Enabled;
      direction=[string]$_.Direction; action=[string]$_.Action; profile=[string]$_.Profile;
      protocol=[string]$p.Protocol; remote=@($a.RemoteAddress); local=@($a.LocalAddress);
      local_port=[string]$p.LocalPort; remote_port=[string]$p.RemotePort;
      program=[string]$app.Program; service=[string]$svc.Service }
  })
  $profiles = @(Get-NetFirewallProfile -PolicyStore ActiveStore | ForEach-Object {
    [pscustomobject]@{ enabled=[string]$_.Enabled; local_rules=[string]$_.AllowLocalFirewallRules }
  })
  $processes = @(Get-Process -Name steam,cs2 -ErrorAction SilentlyContinue | ForEach-Object {
    $started = $null
    try { $started = ($_.StartTime.ToUniversalTime() - [datetime]'1970-01-01').TotalSeconds } catch {}
    [pscustomobject]@{ name=$_.ProcessName; started=$started }
  })
  @{ ok=$true; rules=$rules; profiles=$profiles; processes=$processes;
     service=[string](Get-Service MpsSvc).Status } | ConvertTo-Json -Depth 6 -Compress
} catch { @{ ok=$false; error=$_.Exception.Message } | ConvertTo-Json -Compress }
""".replace("GROUP_LITERAL", quote(GROUP))


def inspect_firewall():
    try:
        raw = quickfix._powershell(inspect_script(), timeout=25)
        result = json.loads(raw.lstrip("\ufeff"))
        if not isinstance(result, dict) or not result.get("ok"):
            raise ValueError(result.get("error", "Firewall read failed") if isinstance(result, dict) else "Invalid firewall result")
        return result
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc) or "Windows Firewall could not be read."}


def parse_state(observed, config, intent=None, program=None):
    result = {"status": "unknown", "present": None, "active": False, "code": None,
              "codes": [], "city": "", "revision": None, "applied_at": None, "error": ""}
    if not isinstance(observed, dict) or not observed.get("ok"):
        result["error"] = observed.get("error", "Windows Firewall could not be read.") if isinstance(observed, dict) else "Windows Firewall could not be read."
        return result
    rules = observed.get("rules", [])
    if not isinstance(rules, list):
        result["error"] = "Windows returned unreadable firewall rules."
        return result
    if any(not isinstance(r, dict) for r in rules):
        result["error"] = "Windows returned unreadable firewall rules."
        return result
    rules = [r for r in rules if r.get("group") == GROUP]
    result.update(present=bool(rules), status="unlocked")
    if not rules:
        if isinstance(intent, dict) and intent.get("code"):
            result.update(status="missing", code=intent["code"], city=intent.get("city", ""),
                          codes=intent.get("codes", []), error="Saved lock selection exists, but its firewall rules are missing.")
        return result
    result["status"] = "damaged"
    if (isinstance(intent, dict) and isinstance(intent.get("code"), str)
            and isinstance(intent.get("codes"), list) and isinstance(intent.get("city"), str)):
        # Preserve the user's intended selection for re-apply even if filters
        # fail validation. It still cannot establish that a lock is active.
        result.update({k: intent[k] for k in ("code", "codes", "city")})
    try:
        program = cs2_program(program)
        addresses, names, by_pop = set(), [], {}
        for rule in rules:
            display = rule["display_name"]
            if not isinstance(display, str) or not display.startswith(DISPLAY_PREFIX):
                raise ValueError("Unrecognized region lock rule name")
            name = display[len(DISPLAY_PREFIX):]
            if not REGION_NAME.fullmatch(name) or name in names:
                raise ValueError("Expected one rule per blocked POP; duplicate or invalid rule name")
            names.append(name)
            remote = set()
            if not isinstance(rule["remote"], list) or not rule["remote"]:
                raise ValueError("Region lock has no remote addresses")
            for address in rule["remote"]:
                # Windows may canonicalize single-host filters to /32.
                network = ipaddress.IPv4Network(address, strict=False)
                if network.prefixlen != 32:
                    raise ValueError("Unexpected address range in lock")
                remote.add(str(network.network_address))
            by_pop[name] = remote
            addresses.update(remote)
        required = {"enabled": "true", "direction": "outbound", "action": "block", "profile": "any",
                    "local_port": "any", "remote_port": "any", "program": program.casefold(), "service": "any"}
        if any(str(r.get(k)).casefold() != v for r in rules for k, v in required.items()):
            raise ValueError("Region lock rules are disabled or their filters changed")
        if any(str(r.get("protocol")).lower() not in ("any", "256")
               or [str(a).lower() for a in r.get("local", [])] != ["any"] for r in rules):
            raise ValueError("Region lock protocol or local addresses changed")
        profiles = observed.get("profiles", [])
        if (observed.get("service") != "Running" or not isinstance(profiles, list) or len(profiles) != 3
                or any(not isinstance(p, dict) for p in profiles)
                or any(str(p.get("enabled")).lower() != "true" or str(p.get("local_rules")).lower() == "false" for p in profiles)):
            raise ValueError("Windows Firewall is off or local rules are excluded by policy")
        if not isinstance(intent, dict) or not intent.get("code"):
            candidates = [row for row in serverping.parse_regions(config)
                          if not set(row["relays"]) & addresses]
            if len(candidates) != 1:
                raise ValueError("Rules exist without saved selection; the kept region cannot be inferred uniquely. Re-apply or unlock.")
            intent = build_plan(config, candidates[0]["code"]) | {"applied_at": None}
            result["inferred"] = True
        result.update({k: intent.get(k) for k in ("code", "codes", "city", "revision", "applied_at")})
        if (not isinstance(result["code"], str) or not isinstance(result["codes"], list)
                or not result["codes"] or not isinstance(result["city"], str)
                or not isinstance(result["revision"], int)
                or (result["applied_at"] is not None and not math.isfinite(float(result["applied_at"])))):
            raise ValueError("Saved region lock selection is incomplete. Re-apply the lock.")
        if result["applied_at"] is not None:
            result["applied_at"] = float(result["applied_at"])
        try:
            plan = build_plan(config, result["code"])
        except ValueError:
            result.update(status="outdated", error="Lock cannot be checked against the saved directory. Refresh and re-apply.")
            return result
        expected = intent.get("regions", plan["regions"])
        expected_pops = {r["name"]: {str(ipaddress.IPv4Network(c).network_address) for c in r["cidrs"]} for r in expected}
        if by_pop != expected_pops or (intent.get("address_digest") and intent["address_digest"] != address_digest(addresses)):
            raise ValueError("Region lock POP rules or remote addresses differ from the saved plan. Re-apply or unlock.")
        result["active"] = True
        if (plan["revision"] != result["revision"] or plan["codes"] != result["codes"]
                or set(plan["addresses"]) != addresses or plan["regions"] != expected):
            result.update(status="outdated", error="Lock is out of date, re-apply. Valve's directory or rule addresses changed.")
        else:
            result["status"] = "locked"
    except (ValueError, TypeError, KeyError) as exc:
        result["error"] = str(exc)
    return result


def restart_needed(state, processes):
    """None means process start time couldn't be inspected; never claim a restart."""
    applied = state.get("applied_at")
    if not applied:
        return None if state.get("present") else False
    unknown = False
    for process in processes:
        if process.get("name") not in ("steam", "cs2"):
            continue
        started = process.get("started")
        if started is None:
            unknown = True
        elif started <= applied:
            return True
    return None if unknown else False


def ping_advice(max_ping, region):
    ping = region.get("ping_ms") if region else None
    if ping is None:
        return {"max_ping": max_ping, "recommended": None, "text": "Saved matchmaking max ping: " + (f"{max_ping} ms." if max_ping else "unavailable.")}
    recommended = max(1, math.ceil(ping + 5))
    adjust = max_ping is not None and (max_ping < ping or max_ping > recommended + 30)
    return {"max_ping": max_ping, "recommended": recommended,
            "text": (f"Saved matchmaking max ping: {max_ping} ms." if max_ping else "Saved matchmaking max ping: unavailable.")
                    + (f" Consider {recommended} ms, just above this region's relay ping. Change it in CS2; this app only reads it." if adjust else "")}


class ServerLock:
    """One observer and serialized changes, shared by HTTP and trusted callers."""
    def __init__(self, root: Path, context, directory, survey):
        from .serverwatch import MatchWatch
        self.root, self.context, self.directory, self.survey = root, context, directory, survey
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.stop_event = threading.Event()
        self.watch = MatchWatch(root / "server-matches.json")
        try:
            intent = json.loads((root / "server-lock-selection.json").read_text(encoding="utf-8"))
            self.intent = intent if isinstance(intent, dict) else None
        except (OSError, ValueError, TypeError):
            self.intent = None
        self.prepared = None
        self.data = {"firewall": parse_state({}, None), "checking": True, "busy": False,
                     "error": "", "detail": "", "preferred_code": "dxb", "processes": [],
                     "restart_needed": None, "history": [], "notice": None, "monitor": "Checking console log...",
                     "advice": ping_advice(None, None), "can_lock": False,
                     "needs_setup": not helper_ready(), "pending": (self.intent or {}).get("pending")}

    def start(self):
        threading.Thread(target=self._observe, daemon=True, name="server-lock-watch").start()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def list_regions(self):
        # Never starts a sweep: the existing survey owns measurements/network.
        rows = {r["code"]: {k: r[k] for k in ("code", "codes", "city", "country", "partner")} |
                {"ping_ms": None, "loss": None, "status": "unknown"}
                for r in serverping.parse_regions(self.directory())}
        for row in self.survey().get("regions", []):
            rows[row["code"]] = rows.get(row["code"], {}) | copy.deepcopy(row)
        return list(rows.values())

    def _observe(self):
        while not self.stop_event.is_set():
            try:
                self._observe_once()
            except Exception as exc:
                with self.lock:
                    self.data.update(checking=False, error=f"Could not check region lock: {exc}")
            self.stop_event.wait(10)

    def _observe_once(self):
        if not self.operation.acquire(blocking=False):
            return
        try:
            observed = self.refresh()
            pending = (self.intent or {}).get("pending")
            if pending and observed.get("ok") and not self._running(observed) and helper_ready():
                with self.lock:
                    self.data.update(busy=True, error="", detail="Applying queued region lock change...")
                try:
                    self._execute(pending["action"], pending.get("plan"))
                except Exception:
                    self.cancel_pending()
                    raise
        finally:
            with self.lock:
                self.data["busy"] = False
            self.operation.release()

    @staticmethod
    def _running(observed):
        processes = observed.get("processes")
        if not isinstance(processes, list) or any(not isinstance(p, dict) or not p.get("name") for p in processes):
            raise ValueError("Could not check whether CS2 is running. Try again after closing CS2.")
        return any(str(p["name"]).lower() in ("cs2", "cs2.exe") for p in processes)

    def refresh(self, observed=None):
        config, context, survey = self.directory(), self.context(), self.survey()
        observed = inspect_firewall() if observed is None else observed
        firewall = parse_state(observed, config, self.intent, context.get("program"))
        if firewall.get("inferred") and firewall["status"] == "locked":
            self._remember(build_plan(config, firewall["code"]) | {"applied_at": None,
                           "pending": (self.intent or {}).get("pending")})
        processes = observed.get("processes", [])
        restart = restart_needed(firewall, processes)
        regions = serverping.parse_regions(config)
        preferred = next((r["codes"] for r in regions if r["code"] == "dxb"), ["dxb"])
        expected = firewall["codes"] or (self.intent or {}).get("codes") or preferred
        region = next((r for r in survey.get("regions", []) if any(c in expected for c in r.get("codes", [r["code"]]))), None)
        running = any(p.get("name", "").lower() in ("cs2", "cs2.exe") for p in processes)
        self.watch.poll(context.get("console_path"), running, config, expected, firewall,
                        restart, context.get("max_ping"), survey)
        ready = helper_ready()
        try:
            cs2_program(context.get("program"))
            build_plan(config, regions[0]["code"] if regions else "dxb")
            can_lock = ready
        except ValueError:
            can_lock = False
        pending = (self.intent or {}).get("pending")
        with self.lock:
            self.data.update(firewall=firewall, checking=False, processes=processes,
                             restart_needed=restart, history=self.watch.history,
                             notice=self.watch.notice, monitor=self.watch.status,
                             condebug=context.get("condebug", False), can_lock=can_lock,
                             needs_setup=not ready, pending=copy.deepcopy(pending),
                             console_path=str(context.get("console_path") or ""),
                             advice=ping_advice(context.get("max_ping"), region), checked_at=time.time())
            if pending:
                self.data["detail"] = PENDING_MESSAGE
        return observed

    def _remember(self, intent):
        if self.intent == intent:
            return
        # Queueing requires durable intent. Atomic replacement also preserves the
        # previous selection if a write fails; never silently drop a queued job.
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "server-lock-selection.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(intent), encoding="utf-8")
        temporary.replace(path)
        self.intent = copy.deepcopy(intent)
        with self.lock:
            self.data["pending"] = copy.deepcopy((intent or {}).get("pending"))

    def prepare(self, code):
        if not helper_ready():
            return {"needs_setup": True, "detail": SETUP_MESSAGE}
        plan = build_plan(self.directory(), code)
        context, survey = self.context(), self.survey()
        cs2_program(context.get("program"))
        row = next((r for r in survey.get("regions", []) if r["code"] == code), None)
        with self.lock:
            token = uuid.uuid4().hex
            self.prepared = (token, time.time(), plan)
            return {"plan_id": token, "city": plan["city"], "revision": plan["revision"],
                    "relay_count": len(plan["addresses"]), "processes": copy.deepcopy(self.data["processes"]),
                    "advice": ping_advice(context.get("max_ping"), row)}

    def begin(self, action, plan_id=None, *, code=None):
        if action not in ("apply", "unlock"):
            raise ValueError("Unknown region lock action")
        if not helper_ready():
            with self.lock:
                self.data.update(needs_setup=True, can_lock=False, error="", detail=SETUP_MESSAGE)
            return self.snapshot()
        if not self.operation.acquire(blocking=False):
            raise ValueError("A region lock check or change is in progress. Try again in a moment.")
        try:
            plan = None
            if action == "apply":
                if code is None:
                    with self.lock:
                        prepared, self.prepared = self.prepared, None
                    if not prepared or prepared[0] != plan_id or time.time() - prepared[1] > 300:
                        raise ValueError("Review the lock warning again before applying.")
                    plan = build_plan(self.directory(), prepared[2]["code"])
                    if plan["digest"] != prepared[2]["digest"]:
                        raise ValueError("Valve's directory changed. Review the lock again.")
                else:
                    plan = build_plan(self.directory(), code)
            self.cancel_pending()
            with self.lock:
                self.data.update(busy=True, error="", detail="Checking CS2 before changing the region lock...")
            threading.Thread(target=self._change, args=(action, plan), daemon=True, name="server-lock-change").start()
        except Exception:
            with self.lock:
                self.data["busy"] = False
            self.operation.release()
            raise
        return self.snapshot()

    def cancel(self):
        if not self.operation.acquire(blocking=False):
            raise ValueError("A region lock check or change is in progress. Try again in a moment.")
        try:
            intent = dict(self.intent or {})
            intent.pop("pending", None)
            self._remember(intent or None)
            with self.lock:
                self.data.update(detail="Pending region lock change canceled.", error="")
            return self.snapshot()
        finally:
            self.operation.release()

    def _execute(self, action, plan=None):
        if action not in ("apply", "unlock"):
            raise ValueError("Unknown pending region lock action. Request the change again.")
        # Fresh process inspection on the background worker, never cached UI data.
        observed = self.refresh()
        if not observed.get("ok"):
            raise ValueError("Could not check whether CS2 is running. No firewall change was made.")
        if self._running(observed):
            pending = {"action": action, "requested_at": time.time()}
            if plan:
                pending.update(code=plan["code"], city=plan["city"], plan=plan)
            self._remember(dict(self.intent or {}) | {"pending": pending})
            with self.lock:
                self.data.update(detail=PENDING_MESSAGE, error="")
            return
        if not helper_ready():
            with self.lock:
                self.data.update(needs_setup=True, can_lock=False, detail=SETUP_MESSAGE, error="")
            return
        if action == "apply":
            current = build_plan(self.directory(), plan["code"])
            if current["digest"] != plan["digest"]:
                self.cancel_pending()
                raise ValueError("Valve's directory changed while the lock was pending. Request the lock again.")
            plan = current
            program = cs2_program(self.context().get("program"))
            # Save all selection metadata locally: helper rules have no description.
            previous_intent = copy.deepcopy(self.intent)
            self._remember(plan | {"applied_at": time.time()})
            result = elevated.run("firewall.lock", {"program": program, "regions": plan["regions"]}, wait=True)
        else:
            result = elevated.run("firewall.unlock", wait=True)
        if result.get("needs_setup"):
            if action == "apply":
                self._remember(previous_intent)
            self.cancel_pending()
            with self.lock:
                self.data.update(needs_setup=True, can_lock=False, detail=SETUP_MESSAGE, error="")
            return
        if action == "apply":
            # Conservatively include Steam/CS2 started while the helper was
            # running: they must restart to re-measure the new firewall policy.
            self._remember(plan | {"applied_at": time.time()})
        self.cancel_pending()
        observed = inspect_firewall()
        if action == "unlock" and result.get("ok") and observed.get("ok") and not [
                r for r in observed.get("rules", []) if r.get("group") == GROUP]:
            self._remember(None)
        self.refresh(observed)  # Success is always verified from effective firewall policy.
        current = self.snapshot()["firewall"]
        verified = (current["status"] == "locked" and current["code"] == plan["code"]
                    if action == "apply" else current["present"] is False)
        with self.lock:
            self.data.update(detail=("Region lock applied." if action == "apply" else "Region lock removed.")
                             + " Restart Steam and CS2 to re-measure relays." if result.get("ok") and verified else "",
                             error="" if result.get("ok") and verified else result.get("error") or result.get("detail")
                             or "Windows did not confirm the requested firewall state. Check the lock status.")

    def cancel_pending(self):
        """Clear only queued work; caller holds operation for serialization."""
        if (self.intent or {}).get("pending"):
            intent = dict(self.intent)
            intent.pop("pending", None)
            self._remember(intent or None)

    def _change(self, action, plan=None):
        try:
            self._execute(action, plan)
        except Exception as exc:
            with self.lock:
                self.data.update(error=str(exc), detail="")
        finally:
            with self.lock:
                self.data["busy"] = False
            self.operation.release()


def discover_context(state=None):
    """Same read-only Steam/install discovery for HTTP, setup and the overlay."""
    from . import steam, whoami
    from .cli import load_prefs
    result = {"max_ping": None, "console_path": None, "program": None, "condebug": False}
    try:
        steam_root = getattr(state, "steam_root", None) or steam.find_steam_root()
        install = getattr(state, "cs2_install", None) or steam.find_cs2_install(steam_root)
        if install is not None:
            result["console_path"] = install / "game" / "csgo" / "console.log"
            result["program"] = str(install / "game" / "bin" / "win64" / "cs2.exe")
        users = getattr(state, "users", None) or steam.list_users(steam_root)
        known = [u.account_id for u in users]
        pinned = str(load_prefs().get("ui", {}).get("pinned_account") or "")
        account = pinned if pinned in known else whoami.current(steam_root, known)[0]
        user = next((u for u in users if u.account_id == account), users[0] if users else None)
        if user is not None:
            result["max_ping"] = serverping.read_max_ping(user.video_cfg.parent / "cs2_user_convars_0_slot0.vcfg")
            result["condebug"] = bool(re.search(r"(?:^|\s)-condebug(?=\s|$)", steam.read_launch_options(user), re.I))
    except (steam.SteamError, OSError):
        pass
    return result


_shared = None
_shared_lock = threading.Lock()


def shared(context=None, directory=None, survey=None):
    """Attach UI providers to the single service, or lazily create it for Python."""
    global _shared
    with _shared_lock:
        if _shared is None:
            from .paths import user_data_dir
            root = user_data_dir()
            cached = serverping.ServerPing(root / "sdr-relays.json")
            _shared = ServerLock(root, context or discover_context,
                                 directory or cached.directory_snapshot, survey or cached.snapshot)
            _shared.start()
        elif context is not None:
            with _shared.lock:
                _shared.context, _shared.directory, _shared.survey = context, directory, survey
        return _shared


def list_regions():
    """Return region rows with the existing survey's ping/loss/status; no probes."""
    return shared().list_regions()


def lock_status():
    """Return the shared observer snapshot, including needs_setup and pending."""
    return shared().snapshot()


def request_lock(code):
    """Trusted internal request: skip HTTP review, retain plan/helper/queue checks."""
    return shared().begin("apply", code=code)


def request_unlock():
    """Trusted internal unlock through the same background helper/queue path."""
    return shared().begin("unlock")
