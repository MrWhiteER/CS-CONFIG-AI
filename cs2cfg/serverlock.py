"""One-shot Windows Firewall region locks. No probes and no game access here.

The rule description carries the selection/revision, but rule filters and the
effective firewall policy are always read back. Saved UI state is not evidence
that a lock exists. Only quickfix's helper is elevated, never the application.
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
from pathlib import Path

from . import quickfix, serverping

GROUP = "CS CONFIG AI region lock"
MARKER = "CS2CFG_REGION_LOCK_V1 "


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
    allowed, blocked = set(), set()
    for code, pop in config["pops"].items():
        if not isinstance(pop, dict) or not isinstance(pop.get("relays", []), list):
            raise ValueError("Valve's saved directory is malformed; refresh server ping.")
        for relay in pop.get("relays", []):
            try:
                address = ipaddress.IPv4Address(relay["ipv4"])
                if not address.is_global:
                    raise ValueError("non-public address")
            except (TypeError, KeyError, ValueError):
                raise ValueError("Valve's saved directory contains an invalid relay; refresh server ping.") from None
            (allowed if code in chosen["codes"] else blocked).add(str(address))
    blocked -= allowed
    if not allowed or not blocked:
        raise ValueError("The saved Valve directory is incomplete; no lock was created.")
    addresses = sorted(blocked, key=ipaddress.IPv4Address)
    plan = {"code": chosen["code"], "city": chosen["city"], "codes": sorted(chosen["codes"]),
            "revision": config["revision"], "addresses": addresses}
    plan["digest"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def apply_script(plan, applied_at=None):
    # Revalidate even internal callers: the only interpolated data is validated
    # IPv4 literals, safe metadata JSON and an internally generated rule name.
    addresses = [str(ipaddress.IPv4Address(a)) for a in plan["addresses"]]
    if not addresses:
        raise ValueError("No relay addresses to block")
    metadata = {k: plan[k] for k in ("code", "city", "codes", "revision")}
    metadata["applied_at"] = applied_at if applied_at is not None else 0
    name = "CS2CFG-Region-" + uuid.uuid4().hex
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"$group = {quote(GROUP)}\n"
        "$old = @(Get-NetFirewallRule -PolicyStore PersistentStore | Where-Object { $_.Group -ceq $group })\n"
        "$created = @()\ntry {\n"
        f"$metadata = {quote(json.dumps(metadata, separators=(',', ':')))} | ConvertFrom-Json\n"
        # Evaluate after UAC, not when the review/worker was started. Steam
        # launched while the prompt is pending still needs a restart.
        + ("$metadata.applied_at = ([datetime]::UtcNow - [datetime]'1970-01-01').TotalSeconds\n" if applied_at is None else "") +
        f"$description = {quote(MARKER)} + ($metadata | ConvertTo-Json -Depth 4 -Compress)\n"
        f"$created += New-NetFirewallRule -Name {quote(name)} -DisplayName {quote(GROUP)} "
        "-Group $group -Description $description "
        "-PolicyStore PersistentStore -Direction Outbound -Action Block -Enabled True "
        "-Profile Any -Protocol UDP -Program Any -Service Any -LocalPort Any -RemotePort Any "
        "-RemoteAddress @(" + ",".join(quote(a) for a in addresses) + ")\n"
        "foreach ($rule in $old) { $rule | Remove-NetFirewallRule -ErrorAction Stop }\n"
        "$out.ok = $true\n$out.detail = 'Region lock applied. Restart Steam and CS2.'\n"
        "} catch {\n"
        "foreach ($rule in $created) { $rule | Remove-NetFirewallRule -ErrorAction SilentlyContinue }\n"
        "throw\n}\n"
    )


def unlock_script():
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"$group = {quote(GROUP)}\n"
        "$rules = @(Get-NetFirewallRule -PolicyStore PersistentStore | Where-Object { $_.Group -ceq $group })\n"
        "foreach ($rule in $rules) { $rule | Remove-NetFirewallRule -ErrorAction Stop }\n"
        "$out.ok = $true\n$out.detail = 'Region lock removed. Restart Steam and CS2.'\n"
    )


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
    [pscustomobject]@{ group=$_.Group; description=$_.Description; enabled=[string]$_.Enabled;
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


def parse_state(observed, config, intent=None):
    result = {"status": "unknown", "present": None, "active": False, "code": None,
              "codes": [], "city": "", "revision": None, "applied_at": None, "error": ""}
    if not isinstance(observed, dict) or not observed.get("ok"):
        result["error"] = (observed or {}).get("error", "Windows Firewall could not be read.")
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
    try:
        metadata = []
        addresses = set()
        for rule in rules:
            desc = rule["description"]
            if not desc.startswith(MARKER):
                raise ValueError("Unrecognized rule metadata")
            meta = json.loads(desc[len(MARKER):])
            if (not isinstance(meta["code"], str) or not re.fullmatch(r"[a-z0-9_-]{1,32}", meta["code"])
                    or not isinstance(meta["codes"], list) or not meta["codes"]
                    or not all(isinstance(c, str) and re.fullmatch(r"[a-z0-9_-]{1,32}", c) for c in meta["codes"])
                    or not isinstance(meta["revision"], int)
                    or not isinstance(meta["city"], str) or not math.isfinite(float(meta["applied_at"]))):
                raise ValueError("Invalid rule metadata")
            metadata.append(meta)
            for address in rule["remote"]:
                # Windows may canonicalize single-host filters to /32.
                network = ipaddress.IPv4Network(address, strict=False)
                if network.prefixlen != 32:
                    raise ValueError("Unexpected address range in lock")
                addresses.add(str(network.network_address))
        if any(m != metadata[0] for m in metadata):
            raise ValueError("Mixed region lock rules")
        result.update({k: metadata[0][k] for k in ("code", "codes", "city", "revision", "applied_at")})
        result["applied_at"] = float(result["applied_at"])
        required = {"enabled": "true", "direction": "outbound", "action": "block", "profile": "any",
                    "local_port": "any", "remote_port": "any", "program": "any", "service": "any"}
        if any(str(r.get(k)).lower() != v for r in rules for k, v in required.items()):
            raise ValueError("Region lock rules are disabled or their filters changed")
        if any(str(r.get("protocol")).lower() not in ("udp", "17") or r.get("local") != ["Any"] for r in rules):
            raise ValueError("Region lock protocol or local addresses changed")
        profiles = observed.get("profiles", [])
        if (observed.get("service") != "Running" or len(profiles) != 3
                or any(str(p.get("enabled")).lower() != "true" or str(p.get("local_rules")).lower() == "false" for p in profiles)):
            raise ValueError("Windows Firewall is off or local rules are excluded by policy")
        result["active"] = True
        try:
            plan = build_plan(config, result["code"])
        except ValueError:
            result.update(status="outdated", error="Lock cannot be checked against the saved directory. Refresh and re-apply.")
            return result
        if (plan["revision"] != result["revision"] or plan["codes"] != result["codes"]
                or set(plan["addresses"]) != addresses):
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
    """Background read-only observer and serialized, explicitly requested one-shots."""
    def __init__(self, root: Path, context, directory, survey):
        from .serverwatch import MatchWatch
        self.root, self.context, self.directory, self.survey = root, context, directory, survey
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.stop_event = threading.Event()
        self.watch = MatchWatch(root / "server-matches.json")
        try:
            intent = json.loads((root / "server-lock-selection.json").read_text(encoding="utf-8"))
            self.intent = intent if isinstance(intent, dict) and isinstance(intent.get("code"), str) and isinstance(intent.get("codes"), list) else None
        except (OSError, ValueError, TypeError):
            self.intent = None
        self.prepared = None
        self.data = {"firewall": parse_state({}, None), "checking": True, "busy": False,
                     "error": "", "detail": "", "preferred_code": "dxb", "processes": [],
                     "restart_needed": None, "history": [], "notice": None, "monitor": "Checking console log…",
                     "advice": ping_advice(None, None), "can_lock": False}

    def start(self):
        threading.Thread(target=self._observe, daemon=True, name="server-lock-watch").start()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def _observe(self):
        while not self.stop_event.is_set():
            try:
                if self.operation.acquire(blocking=False):
                    try:
                        self.refresh()
                    finally:
                        self.operation.release()
            except Exception as exc:
                with self.lock:
                    self.data.update(checking=False, error=f"Could not check region lock: {exc}")
            self.stop_event.wait(10)

    def refresh(self):
        config, context, survey = self.directory(), self.context(), self.survey()
        observed = inspect_firewall()
        firewall = parse_state(observed, config, self.intent)
        if firewall["present"] and firewall.get("code"):
            self._remember({k: firewall[k] for k in ("code", "city", "codes")})
        processes = observed.get("processes", [])
        restart = restart_needed(firewall, processes)
        regions = serverping.parse_regions(config)
        preferred = next((r["codes"] for r in regions if r["code"] == "dxb"), ["dxb"])
        expected = firewall["codes"] or (self.intent or {}).get("codes") or preferred
        region = next((r for r in survey.get("regions", []) if any(c in expected for c in r.get("codes", [r["code"]]))), None)
        running = any(p.get("name") == "cs2" for p in processes)
        self.watch.poll(context.get("console_path"), running, config, expected, firewall,
                        restart, context.get("max_ping"), survey)
        try:
            build_plan(config, regions[0]["code"] if regions else "dxb")
            can_lock = True
        except ValueError:
            can_lock = False
        with self.lock:
            self.data.update(firewall=firewall, checking=False, processes=processes,
                             restart_needed=restart, history=self.watch.history,
                             notice=self.watch.notice, monitor=self.watch.status,
                             condebug=context.get("condebug", False), can_lock=can_lock,
                             console_path=str(context.get("console_path") or ""),
                             advice=ping_advice(context.get("max_ping"), region), checked_at=time.time())

    def _remember(self, intent):
        if self.intent == intent:
            return
        self.intent = intent
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / "server-lock-selection.json").write_text(json.dumps(intent), encoding="utf-8")
        except OSError:
            pass  # This is intent only. The firewall remains the source of truth.

    def prepare(self, code):
        plan = build_plan(self.directory(), code)
        context, survey = self.context(), self.survey()
        row = next((r for r in survey.get("regions", []) if r["code"] == code), None)
        with self.lock:
            token = uuid.uuid4().hex
            self.prepared = (token, time.time(), plan)
            return {"plan_id": token, "city": plan["city"], "revision": plan["revision"],
                    "relay_count": len(plan["addresses"]), "processes": self.data["processes"],
                    "advice": ping_advice(context.get("max_ping"), row)}

    def begin(self, action, plan_id=None):
        if not self.operation.acquire(blocking=False):
            raise ValueError("A region lock check or change is in progress. Try again in a moment.")
        try:
            requested_code = None
            if action == "apply":
                with self.lock:
                    prepared, self.prepared = self.prepared, None
                if not prepared or prepared[0] != plan_id or time.time() - prepared[1] > 300:
                    raise ValueError("Review the lock warning again before applying.")
                plan = build_plan(self.directory(), prepared[2]["code"])
                if plan["digest"] != prepared[2]["digest"]:
                    raise ValueError("Valve's directory changed. Review the lock again.")
                script = apply_script(plan)
                requested_code = plan["code"]
            elif action == "unlock":
                script = unlock_script()
            else:
                raise ValueError("Unknown region lock action")
            with self.lock:
                self.data.update(busy=True, error="", detail="Waiting for the administrator prompt…")
            threading.Thread(target=self._change, args=(script, action, requested_code), daemon=True, name="server-lock-change").start()
        except Exception:
            self.operation.release()
            raise
        return self.snapshot()

    def _change(self, script, action, requested_code=None):
        try:
            result = quickfix._run_elevated(script)
            if action == "unlock" and result.get("ok"):
                self._remember(None)
            self.refresh()  # Includes decline/failure/partial failure. Never set a saved 'locked' flag.
            current = self.snapshot()["firewall"]
            verified = (current["status"] == "locked" and current["code"] == requested_code
                        if action == "apply" else current["present"] is False)
            with self.lock:
                self.data.update(detail=result.get("detail", "") if result.get("ok") and verified else "",
                                 error="" if result.get("ok") and verified else result.get("error") or result.get("detail")
                                 or "Windows did not confirm the requested firewall state. Check the lock status.")
        except Exception as exc:
            with self.lock:
                self.data["error"] = str(exc)
        finally:
            with self.lock:
                self.data["busy"] = False
            self.operation.release()
