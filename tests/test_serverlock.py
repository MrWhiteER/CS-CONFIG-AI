"""All external effects are mocked. Fixtures are synthetic, never live relays/logs."""
import copy
import io
import json
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cs2cfg import serverlock as sl, serverping as sp, serverwatch as sw, webui

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = json.loads((FIXTURES / "server_lock_sdr.json").read_text(encoding="utf-8"))


def observed(code="dxb"):
    plan = sl.build_plan(CONFIG, code)
    meta = {k: plan[k] for k in ("code", "city", "codes", "revision")}
    meta["applied_at"] = 100
    return {"ok": True, "service": "Running", "processes": [],
            "profiles": [{"enabled": "True", "local_rules": "NotConfigured"}] * 3,
            "rules": [{"group": sl.GROUP, "description": sl.MARKER + json.dumps(meta),
                       "enabled": "True", "direction": "Outbound", "action": "Block", "profile": "Any",
                       "protocol": "UDP", "program": "Any", "service": "Any", "local": ["Any"],
                       "local_port": "Any", "remote_port": "Any", "remote": plan["addresses"]}]}


class Isolated(unittest.TestCase):
    def setUp(self):
        # A missed mock fails loudly instead of sending a probe or raising UAC.
        for obj, name in ((sl.quickfix, "_run_elevated"), (sl.quickfix, "_powershell"),
                          (sp, "urlopen"), (sp.netcheck, "_ping_once")):
            p = patch.object(obj, name, side_effect=AssertionError("Unexpected external effect: " + name))
            p.start()
            self.addCleanup(p.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)


class BlockList(Isolated):
    def test_never_blocks_selected_or_shared_ips_and_includes_hidden_and_partner_pops(self):
        plan = sl.build_plan(CONFIG, "dxb")
        self.assertEqual(plan["addresses"], ["155.133.226.68", "155.133.226.69", "155.133.226.70", "155.133.226.71"])
        self.assertEqual(plan["codes"], ["dxb"])

    def test_numbered_variants_are_all_allowed(self):
        plan = sl.build_plan(CONFIG, "bom")
        self.assertEqual(plan["codes"], ["bom", "bom2"])
        self.assertNotIn("155.133.226.69", plan["addresses"])
        self.assertNotIn("185.25.183.163", plan["addresses"])

    def test_incomplete_fallback_invalid_selection_and_malformed_addresses_fail(self):
        for config, code in ((sp.FALLBACK, "dxb"), ({}, "dxb"), (CONFIG, "fake")):
            with self.assertRaises(ValueError):
                sl.build_plan(config, code)
        for bad in ("1.2.3.4'; Remove-NetFirewallRule", "127.0.0.1", None):
            config = copy.deepcopy(CONFIG)
            config["pops"]["hidden"]["relays"][0]["ipv4"] = bad
            with self.assertRaises(ValueError):
                sl.build_plan(config, "dxb")

    def test_read_only_directory_accessor_never_fetches_and_does_not_use_fallback(self):
        path = self.root / "cache.json"
        survey = sp.ServerPing(path)
        self.assertIsNone(survey.directory_snapshot())
        path.write_text(json.dumps({"checked_at": 1, "config": CONFIG}))
        self.assertEqual(survey.directory_snapshot(), CONFIG)
        survey.config = copy.deepcopy(CONFIG)
        found = survey.directory_snapshot()
        found["pops"].clear()
        self.assertTrue(survey.directory_snapshot()["pops"])


class Firewall(Isolated):
    def test_script_is_one_udp_remote_list_rule_for_all_programs_and_exact_group(self):
        script = sl.apply_script(sl.build_plan(CONFIG, "dxb"), 100)
        self.assertEqual(script.count("New-NetFirewallRule"), 1)
        for expected in ("-Direction Outbound", "-Action Block", "-Protocol UDP", "-Program Any", "-Service Any",
                         "-Profile Any", "-PolicyStore PersistentStore", "-RemoteAddress @(", sl.GROUP, sl.MARKER):
            self.assertIn(expected, script)
        self.assertNotIn("185.25.183.163", script)
        self.assertNotIn("185.25.183.179", script)
        self.assertIn("Where-Object { $_.Group -ceq $group }", script)
        self.assertIn("foreach ($rule in $created)", script)  # rollback on failure
        self.assertLess(script.index("New-NetFirewallRule"), script.index("foreach ($rule in $old)"))
        self.assertNotIn("netsh", script.lower())

    def test_unlock_is_group_scoped_and_cannot_remove_other_rules(self):
        script = sl.unlock_script()
        self.assertIn(sl.GROUP, script)
        self.assertIn("Where-Object { $_.Group -ceq $group }", script)
        self.assertIn("$rule | Remove-NetFirewallRule", script)
        self.assertNotIn("New-NetFirewallRule", script)
        self.assertNotIn("reset", script.lower())

    def test_apply_time_is_evaluated_in_elevated_helper_after_uac(self):
        script = sl.apply_script(sl.build_plan(CONFIG, "dxb"))
        self.assertIn("$metadata.applied_at = ([datetime]::UtcNow", script)
        self.assertLess(script.index("$metadata.applied_at ="), script.index("New-NetFirewallRule"))

    def test_read_command_with_mocked_subprocess(self):
        # Exercise the actual wrapper, but subprocess.run is still a stand-in.
        with patch.object(sl.quickfix, "_powershell", wraps=self.original_powershell), \
             patch.object(sl.quickfix.subprocess, "run", return_value=types.SimpleNamespace(stdout=json.dumps(observed()))) as run:
            result = sl.inspect_firewall()
        self.assertTrue(result["ok"])
        command = run.call_args.args[0]
        self.assertIn("-NonInteractive", command)
        self.assertIn("-PolicyStore ActiveStore", command[-1])
        self.assertNotIn("Remove-NetFirewallRule", command[-1])
        self.assertNotIn("New-NetFirewallRule", command[-1])

    # Capture before setUp replaces the function.
    original_powershell = staticmethod(sl.quickfix._powershell)

    def test_real_rules_are_required_not_a_saved_flag(self):
        self.assertEqual(sl.parse_state({"ok": True, "rules": []}, CONFIG)["status"], "unlocked")
        saved = {"code": "dxb", "codes": ["dxb"], "city": "Dubai"}
        result = sl.parse_state({"ok": True, "rules": []}, CONFIG, saved)
        self.assertEqual(result["status"], "missing")
        self.assertFalse(result["active"])

    def test_valid_rules_and_windows_host_masks(self):
        raw = observed()
        raw["rules"][0]["protocol"] = "17"
        raw["rules"][0]["remote"] = [a + "/32" for a in raw["rules"][0]["remote"]]
        result = sl.parse_state(raw, CONFIG)
        self.assertEqual(result["status"], "locked")
        self.assertTrue(result["active"])
        self.assertEqual(result["city"], "Dubai")

    def test_revision_or_address_change_is_outdated(self):
        config = copy.deepcopy(CONFIG)
        config["revision"] += 1
        self.assertEqual(sl.parse_state(observed(), config)["status"], "outdated")
        raw = observed()
        raw["rules"][0]["remote"].pop()
        self.assertEqual(sl.parse_state(raw, CONFIG)["status"], "outdated")

    def test_disabled_or_narrowed_filters_and_firewall_off_are_not_active(self):
        for key, value in (("enabled", "False"), ("direction", "Inbound"), ("protocol", "TCP"),
                           ("program", "cs2.exe"), ("profile", "Private"), ("remote_port", "27015")):
            raw = observed()
            raw["rules"][0][key] = value
            self.assertFalse(sl.parse_state(raw, CONFIG)["active"], key)
        for field, value in (("enabled", "False"), ("local_rules", "False")):
            raw = observed()
            raw["profiles"][0][field] = value
            self.assertFalse(sl.parse_state(raw, CONFIG)["active"])

    def test_unreadable_or_malformed_state_does_not_claim_unlock(self):
        for raw in ({}, {"ok": False, "error": "denied"}, {"ok": True, "rules": [None]}):
            self.assertIsNone(sl.parse_state(raw, CONFIG)["present"])
        raw = observed()
        raw["rules"][0]["description"] = "unexpected"
        self.assertEqual(sl.parse_state(raw, CONFIG)["status"], "damaged")

    def test_restart_checks_process_start_times_even_after_app_restart(self):
        state = sl.parse_state(observed(), CONFIG)
        self.assertTrue(sl.restart_needed(state, [{"name": "steam", "started": 50}]))
        self.assertFalse(sl.restart_needed(state, [{"name": "steam", "started": 101}]))
        self.assertIsNone(sl.restart_needed(state, [{"name": "cs2", "started": None}]))


class Reasons(Isolated):
    def reason(self, **overrides):
        args = dict(actual="bom2", expected=["dxb"], firewall={"status": "locked", "present": True, "active": True},
                    restart=False, max_ping=100, survey={"updated_at": 990, "regions": [
                        {"code": "bom", "codes": ["bom", "bom2"], "ping_ms": 80, "loss": 0},
                        {"code": "dxb", "codes": ["dxb"], "ping_ms": 20, "loss": 0}]}, now=1000)
        args.update(overrides)
        return sw.likely_reason(**args)

    def test_reason_order_maxping_before_missing_restart_and_loss(self):
        result = self.reason(firewall={"status": "missing", "present": False, "code": "dxb"}, restart=True)
        self.assertEqual(result["code"], "max_ping")
        self.assertIn("Likely", result["text"])

    def test_stale_rules_before_restart(self):
        self.assertEqual(self.reason(firewall={"status": "outdated", "present": True}, restart=True)["code"], "rules")
        self.assertEqual(self.reason(restart=True)["code"], "restart")

    def test_unknown_ping_does_not_claim_maxping_allows_region(self):
        self.assertNotEqual(self.reason(firewall={"present": False}, survey={})["code"], "max_ping")
        self.assertEqual(self.reason(firewall={"status": "unknown"})["code"], "unknown")

    def test_recent_loss_versus_stale_or_future_sweep(self):
        survey = {"updated_at": 990, "regions": [{"code": "dxb", "ping_ms": None, "loss": 100}]}
        self.assertEqual(self.reason(survey=survey)["code"], "reachability")
        for stamp in (1, 1001):
            survey["updated_at"] = stamp
            self.assertEqual(self.reason(survey=survey)["code"], "availability")

    def test_party_and_match_availability_are_possibilities_not_detected_facts(self):
        text = self.reason()["text"]
        self.assertIn("if you queued in a party", text)
        self.assertIn("cannot see members", text)
        self.assertIn("no match", text)

    def test_maxping_advice_is_read_only(self):
        for limit in (10, 150):
            self.assertEqual(sl.ping_advice(limit, {"ping_ms": 21.3})["recommended"], 27)
            self.assertIn("Consider 27", sl.ping_advice(limit, {"ping_ms": 21.3})["text"])
        self.assertNotIn("Consider", sl.ping_advice(30, {"ping_ms": 21.3})["text"])


class Console(Isolated):
    def test_assumed_fixture_requires_connected_context_and_ignores_primary_relay(self):
        parser = sw.ConsoleParser()
        events = [parser.feed(line, CONFIG) for line in (FIXTURES / "server_lock_console_assumed.log").read_text().splitlines()]
        events = [e for e in events if e]
        self.assertEqual([e["region"] for e in events], ["bom2"])
        self.assertIn("awaiting", events[0]["source"])

    def test_standalone_unknown_failed_and_disconnect_summaries_are_ignored(self):
        for lines in (("[Networking] Remote host is in data center 'dxb'",),
                      ("[#1 SDR server steamid:9] connected", "problem detected locally", "[Networking] Remote host is in data center 'dxb'"),
                      ("[#1 SDR server steamid:9] connected", "[Networking] Remote host is in data center 'madeup'"),
                      ("Summary of connection [#1 SDR server]", "[Networking] Remote host is in data center 'bom'"),
                      ("Connected to 155.133.226.68:27015", "Selecting bom#1 as primary")):
            parser = sw.ConsoleParser()
            self.assertFalse(any(parser.feed(line, CONFIG) for line in lines))

    def test_tail_partial_lines_rotation_no_replay_and_local_history(self):
        log = self.root / "console.log"
        log.write_text("old session\n")
        watch = sw.MatchWatch(self.root / "history.json")
        def poll():
            watch.poll(log, True, CONFIG, ["dxb"], {"status": "locked", "present": True}, False, 30, {})
        poll()
        with log.open("a") as handle:
            handle.write("[#1 SDR server steamid:9] connected\n[Networking] Remote host is in data center 'bom")
        poll()
        self.assertEqual(watch.history, [])
        with log.open("a") as handle:
            handle.write("2'\n")
        poll()
        poll()
        self.assertEqual(len(watch.history), 1)
        self.assertEqual(watch.notice["region"], "bom2")
        log.write_text("[#2 SDR server] connected\n[Networking] Remote host is in data center 'dxb'\n")
        poll()
        self.assertEqual(len(watch.history), 2)
        # Attaching a new observer doesn't replay a previous session's file.
        other = sw.MatchWatch(self.root / "history.json")
        other.poll(log, True, CONFIG, ["dxb"], {}, False, None, {})
        self.assertEqual(len(other.history), 2)

    def test_creating_missing_log_is_read_and_history_keeps_only_twenty(self):
        log = self.root / "console.log"
        watch = sw.MatchWatch(self.root / "history.json")
        def poll():
            watch.poll(log, True, CONFIG, ["bom", "bom2"], {}, False, None, {})
        poll()
        log.write_text("".join(f"[#{i} SDR server] connected\n[Networking] Remote host is in data center 'bom2'\n" for i in range(25)))
        poll()
        self.assertEqual(len(watch.history), 20)
        self.assertIsNone(watch.notice)
        self.assertEqual(watch.history[-1]["reason"]["code"], "expected")

    def test_later_ping_sweep_does_not_replace_connection_evidence(self):
        log = self.root / "console.log"
        log.write_text("")
        watch = sw.MatchWatch(self.root / "history.json")
        survey = {"updated_at": 990, "regions": [{"code": "dxb", "ping_ms": None, "loss": 100}]}
        def poll():
            watch.poll(log, True, CONFIG, ["dxb"], {"status": "locked", "present": True}, False, 30, survey)
        with patch.object(sw.time, "time", return_value=1000):
            poll()
            log.write_text("[#1 SDR server] connected\n")
            poll()
            survey = {"updated_at": 999, "regions": [{"code": "dxb", "ping_ms": 15, "loss": 0}]}
            with log.open("a") as handle:
                handle.write("[Networking] Remote host is in data center 'bom2'\n")
            poll()
        self.assertEqual(watch.history[-1]["reason"]["code"], "reachability")


class Operations(Isolated):
    def service(self):
        return sl.ServerLock(self.root, lambda:{}, lambda:CONFIG, lambda:{})

    def test_apply_requires_review_and_directory_cannot_change_between_review_and_apply(self):
        service = self.service()
        with self.assertRaises(ValueError):
            service.begin("apply", "fake")
        plan = service.prepare("dxb")
        changed = copy.deepcopy(CONFIG)
        changed["revision"] += 1
        service.directory = lambda:changed
        with self.assertRaisesRegex(ValueError, "directory changed"):
            service.begin("apply", plan["plan_id"])
        service = self.service()
        review = service.prepare("dxb")
        with patch.object(sl.time, "time", return_value=service.prepared[1] + 301):
            with self.assertRaisesRegex(ValueError, "Review"):
                service.begin("apply", review["plan_id"])

    def test_change_uses_one_elevation_and_readback_and_cancel_does_not_claim_lock(self):
        service = self.service()
        service.operation.acquire()
        with patch.object(sl.quickfix, "_run_elevated", return_value={"ok": False, "declined": True, "error": "declined"}) as elevated, \
             patch.object(sl, "inspect_firewall", return_value={"ok": True, "rules": []}):
            service._change("mock script", "apply")
        elevated.assert_called_once_with("mock script")
        self.assertEqual(service.snapshot()["firewall"]["status"], "unlocked")
        self.assertIn("declined", service.snapshot()["error"])
        self.assertFalse(service.snapshot()["busy"])

    def test_success_is_not_claimed_until_firewall_confirms(self):
        service = self.service()
        service.operation.acquire()
        with patch.object(sl.quickfix, "_run_elevated", return_value={"ok": True}), \
             patch.object(sl, "inspect_firewall", return_value={"ok": False, "error": "denied"}):
            service._change("mock", "apply")
        self.assertFalse(service.snapshot()["firewall"]["active"])
        self.assertIn("did not confirm", service.snapshot()["error"])

    def test_valid_review_applies_once_and_restores_actual_state_after_app_restart(self):
        service = self.service()
        review = service.prepare("dxb")
        def immediate(**kwargs):
            return types.SimpleNamespace(start=lambda:kwargs["target"](*kwargs.get("args", ())))
        with patch.object(sl.quickfix, "_run_elevated", return_value={"ok": True}) as elevated, \
             patch.object(sl, "inspect_firewall", return_value=observed()), \
             patch.object(sl.threading, "Thread", side_effect=immediate):
            service.begin("apply", review["plan_id"])
        elevated.assert_called_once()
        self.assertEqual(service.snapshot()["firewall"]["status"], "locked")
        self.assertEqual(service.snapshot()["error"], "")
        restarted = self.service()
        with patch.object(sl, "inspect_firewall", return_value={"ok": True, "rules": []}):
            restarted.refresh()
        self.assertEqual(restarted.snapshot()["firewall"]["status"], "missing")
        self.assertFalse(restarted.snapshot()["firewall"]["active"])

    def test_previous_region_is_not_success_for_a_different_requested_lock(self):
        service = self.service()
        service.operation.acquire()
        with patch.object(sl.quickfix, "_run_elevated", return_value={"ok": True}), \
             patch.object(sl, "inspect_firewall", return_value=observed("bom")):
            service._change("mock", "apply", "dxb")
        self.assertTrue(service.snapshot()["error"])

    def test_unlock_removes_saved_intent_only_after_success(self):
        service = self.service()
        service._remember({"code": "dxb", "codes": ["dxb"], "city": "Dubai"})
        for success in (False, True):
            service.operation.acquire()
            with patch.object(sl.quickfix, "_run_elevated", return_value={"ok": success, "error": "declined"}), \
                 patch.object(sl, "inspect_firewall", return_value={"ok": True, "rules": []}):
                service._change("mock", "unlock")
            self.assertEqual(service.snapshot()["firewall"]["status"], "unlocked" if success else "missing")


class Api(Isolated):
    def handler(self, path, body, token="test"):
        state = types.SimpleNamespace(token="test", lock=threading.Lock(), server_lock=MagicMock())
        handler = webui.make_handler(state).__new__(webui.make_handler(state))
        handler.path = path
        raw = json.dumps(body).encode()
        handler.headers = {"Host": "127.0.0.1:8765", "X-CS2CFG-Token": token, "Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        handler._send_json = MagicMock()
        return handler, state.server_lock

    def test_bad_token_never_reaches_lock(self):
        handler, service = self.handler("/api/servers/lock/change", {"action": "unlock", "confirmed": True}, "wrong")
        handler.do_POST()
        service.begin.assert_not_called()
        self.assertEqual(handler._send_json.call_args.args[1], 403)

    def test_prepare_and_change_routes_and_confirmation(self):
        handler, service = self.handler("/api/servers/lock/prepare", {"code": "dxb"})
        service.prepare.return_value = {"plan_id": "id"}
        handler.do_POST()
        service.prepare.assert_called_once_with("dxb")
        handler, service = self.handler("/api/servers/lock/change", {"action": "apply", "plan_id": "id", "confirmed": True})
        service.begin.return_value = {}
        handler.do_POST()
        service.begin.assert_called_once_with("apply", "id")
        handler, service = self.handler("/api/servers/lock/change", {"action": "unlock"})
        handler.do_POST()
        service.begin.assert_not_called()

    def test_get_is_cached_and_does_not_elevate_or_probe(self):
        handler, service = self.handler("/api/servers/lock", {})
        service.snapshot.return_value = {"busy": False}
        handler.do_GET()
        service.snapshot.assert_called_once()

    def test_enabling_log_preserves_launch_options_and_uses_backup_writer(self):
        user = types.SimpleNamespace(account_id="123")
        state = types.SimpleNamespace(user_for=lambda _:user)
        with patch.object(webui, "_active_account", return_value="123"), \
             patch.object(webui.steam, "read_launch_options", return_value='-novid +exec "my cfg"'), \
             patch.object(webui.steam, "write_launch_options") as write, \
             patch.object(webui.backup, "BackupSession", return_value="backup"):
            webui._servers_log_enable(state, {})
        write.assert_called_once_with(user, '-novid +exec "my cfg" -condebug', "backup")

    def test_enabling_log_is_idempotent_and_does_not_force_edits_while_steam_runs(self):
        user = types.SimpleNamespace(account_id="123")
        state = types.SimpleNamespace(user_for=lambda _:user)
        with patch.object(webui, "_active_account", return_value="123"), \
             patch.object(webui.steam, "read_launch_options", return_value="-condebug -novid"), \
             patch.object(webui.steam, "write_launch_options") as write:
            webui._servers_log_enable(state, {})
        write.assert_not_called()
        with patch.object(webui, "_active_account", return_value="123"), \
             patch.object(webui.steam, "read_launch_options", return_value="-novid"), \
             patch.object(webui.backup, "BackupSession"), \
             patch.object(webui.steam, "write_launch_options", side_effect=webui.steam.SteamError("Steam is running")):
            with self.assertRaises(webui.steam.SteamError):
                webui._servers_log_enable(state, {})


if __name__ == "__main__":
    unittest.main()
