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
PROGRAM = r"C:\Games\Counter-Strike Global Offensive\game\bin\win64\cs2.exe"


def intent(code="dxb"):
    return sl.build_plan(CONFIG, code) | {"applied_at": 100}


def observed(code="dxb"):
    regions = sl.build_plan(CONFIG, code)["regions"] if code else []
    return {"ok": True, "service": "Running", "processes": [],
            "profiles": [{"enabled": "True", "local_rules": "NotConfigured"} for _ in range(3)],
            "rules": [{"group": sl.GROUP, "display_name": sl.DISPLAY_PREFIX + r["name"],
                       "enabled": "True", "direction": "Outbound", "action": "Block", "profile": "Any",
                       "protocol": "Any", "program": PROGRAM, "service": "Any", "local": ["Any"],
                       "local_port": "Any", "remote_port": "Any", "remote": r["cidrs"]} for r in regions]}


class Isolated(unittest.TestCase):
    def setUp(self):
        # A missed mock fails loudly instead of changing the firewall or probing.
        for obj, name in ((sl.quickfix, "_run_elevated"), (sl.quickfix, "_powershell"),
                          (sp, "urlopen"), (sp.netcheck, "_ping_once")):
            p = patch.object(obj, name, side_effect=AssertionError("Unexpected external effect: " + name))
            p.start()
            self.addCleanup(p.stop)
        self.helper = MagicMock(spec=["ready", "run"])
        self.helper.ready.return_value = True
        self.helper.run.side_effect = AssertionError("Unexpected helper request")
        p = patch.object(sl, "elevated", self.helper)
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
        self.assertEqual(plan["regions"], [
            {"name": "bom", "cidrs": ["155.133.226.68/32"]},
            {"name": "bom2", "cidrs": ["155.133.226.69/32"]},
            {"name": "dfjr", "cidrs": ["155.133.226.70/32"]},
            {"name": "hidden", "cidrs": ["155.133.226.71/32"]}])

    def test_numbered_variants_are_all_allowed(self):
        plan = sl.build_plan(CONFIG, "bom")
        self.assertEqual(plan["codes"], ["bom", "bom2"])
        self.assertNotIn("155.133.226.69", plan["addresses"])
        self.assertNotIn("185.25.183.163", plan["addresses"])
        self.assertFalse({"bom", "bom2"} & {r["name"] for r in plan["regions"]})

    def test_no_empty_region_when_all_its_ips_are_shared(self):
        config = copy.deepcopy(CONFIG)
        config["pops"]["shared"] = {"relays": [{"ipv4": "185.25.183.163"}]}
        self.assertNotIn("shared", [r["name"] for r in sl.build_plan(config, "dxb")["regions"]])

    def test_incomplete_fallback_invalid_selection_and_malformed_addresses_fail(self):
        for config, code in ((sp.FALLBACK, "dxb"), ({}, "dxb"), (CONFIG, "fake")):
            with self.assertRaises(ValueError):
                sl.build_plan(config, code)
        for bad in ("1.2.3.4'; Remove-NetFirewallRule", "127.0.0.1", None):
            config = copy.deepcopy(CONFIG)
            config["pops"]["hidden"]["relays"][0]["ipv4"] = bad
            with self.assertRaises(ValueError):
                sl.build_plan(config, "dxb")

    def test_helper_region_count_limits(self):
        config = {"revision": 1, "pops": {"dxb": CONFIG["pops"]["dxb"]}}
        with self.assertRaisesRegex(ValueError, "1-64"):
            sl.build_plan(config, "dxb")
        for n in range(64):
            config["pops"][f"pop{n}"] = {"relays": [{"ipv4": "8.8.8.8"}]}
        self.assertEqual(len(sl.build_plan(config, "dxb")["regions"]), 64)
        config["pops"]["extra"] = {"relays": [{"ipv4": "8.8.4.4"}]}
        with self.assertRaisesRegex(ValueError, "1-64"):
            sl.build_plan(config, "dxb")

    def test_helper_cidr_limit_counts_addresses_per_pop(self):
        config = {"revision": 1, "pops": {"dxb": CONFIG["pops"]["dxb"]}}
        relays = [{"ipv4": f"8.10.{n // 256}.{n % 256}"} for n in range(1001)]
        config["pops"].update(a={"relays": relays[:1000]}, b={"relays": relays[:1000]})
        self.assertEqual(sum(len(r["cidrs"]) for r in sl.build_plan(config, "dxb")["regions"]), 2000)
        config["pops"]["a"]["relays"] = relays
        with self.assertRaisesRegex(ValueError, "2000 CIDR"):
            sl.build_plan(config, "dxb")

    def test_helper_name_limits(self):
        for name in ("x" * 49, "", "bad;name", "bad\n", "Dubai\u00e9"):
            config = copy.deepcopy(CONFIG)
            config["pops"][name] = config["pops"].pop("hidden")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "name format"):
                sl.build_plan(config, "dxb")
        config = copy.deepcopy(CONFIG)
        config["pops"]["A Z_-.()"] = config["pops"].pop("hidden")
        self.assertIn("A Z_-.()", [r["name"] for r in sl.build_plan(config, "dxb")["regions"]])

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
    original_powershell = staticmethod(sl.quickfix._powershell)

    def parse(self, raw=None, config=None, saved=True):
        return sl.parse_state(observed() if raw is None else raw, CONFIG if config is None else config,
                              intent() if saved else None, PROGRAM)

    def test_read_command_with_mocked_subprocess(self):
        with patch.object(sl.quickfix, "_powershell", wraps=self.original_powershell), \
             patch.object(sl.quickfix.subprocess, "run", return_value=types.SimpleNamespace(stdout=json.dumps(observed()))) as run:
            self.assertTrue(sl.inspect_firewall()["ok"])
        command = run.call_args.args[0]
        self.assertIn("-NonInteractive", command)
        self.assertIn("-PolicyStore ActiveStore", command[-1])
        self.assertIn("display_name=$_.DisplayName", command[-1])
        self.assertNotIn("Remove-NetFirewallRule", command[-1])
        self.assertNotIn("New-NetFirewallRule", command[-1])

    def test_real_rules_are_required_not_a_saved_flag(self):
        self.assertEqual(self.parse(observed(None), saved=False)["status"], "unlocked")
        result = self.parse(observed(None))
        self.assertEqual(result["status"], "missing")
        self.assertFalse(result["active"])

    def test_valid_helper_rules_without_description_and_windows_host_masks(self):
        raw = observed()
        for r in raw["rules"]:
            r["protocol"] = "256"
            r["program"] = PROGRAM.upper()
            r["remote"] = [a.removesuffix("/32") for a in r["remote"]]
        result = self.parse(raw)
        self.assertEqual(result["status"], "locked")
        self.assertTrue(result["active"])
        self.assertEqual(result["city"], "Dubai")

    def test_revision_or_directory_address_change_is_outdated(self):
        config = copy.deepcopy(CONFIG)
        config["revision"] += 1
        self.assertEqual(self.parse(config=config)["status"], "outdated")
        config["pops"]["hidden"]["relays"][0]["ipv4"] = "8.8.8.8"
        self.assertEqual(self.parse(config=config)["status"], "outdated")

    def test_changed_addresses_pop_names_missing_or_duplicate_rules_are_damaged(self):
        mutations = [lambda r:r.pop(), lambda r:r.append(copy.deepcopy(r[0])),
                     lambda r:r[0].update(remote=["8.8.8.8/32"]),
                     lambda r:r[0].update(display_name=sl.DISPLAY_PREFIX + "fake"),
                     lambda r:r[0].update(remote=["155.133.226.0/24"]),
                     lambda r:r[0].update(remote=[])]
        for mutate in mutations:
            raw = observed()
            mutate(raw["rules"])
            result = self.parse(raw)
            self.assertEqual(result["status"], "damaged")
            self.assertFalse(result["active"])

    def test_disabled_narrowed_filters_wrong_program_and_firewall_off_are_not_active(self):
        for key, value in (("enabled", "False"), ("direction", "Inbound"), ("protocol", "UDP"),
                           ("program", "Any"), ("program", "cs2.exe"),
                           ("program", PROGRAM.replace("C:", "D:")), ("action", "Allow"),
                           ("service", "Steam"), ("local", ["8.8.8.8"]),
                           ("profile", "Private"), ("local_port", "27015"), ("remote_port", "27015")):
            raw = observed()
            raw["rules"][0][key] = value
            result = self.parse(raw)
            self.assertFalse(result["active"], key)
            self.assertEqual(result["code"], "dxb")
        for field, value in (("enabled", "False"), ("local_rules", "False")):
            raw = observed()
            raw["profiles"][0][field] = value
            self.assertFalse(self.parse(raw)["active"])
        raw = observed()
        raw["service"] = "Stopped"
        self.assertFalse(self.parse(raw)["active"])

    def test_inference_without_intent_requires_unique_kept_region_and_complete_rules(self):
        for code in ("dxb", "bom", "dfjr"):
            result = sl.parse_state(observed(code), CONFIG, program=PROGRAM)
            self.assertEqual(result["status"], "locked")
            self.assertEqual(result["code"], code)
            self.assertTrue(result["inferred"])
            self.assertIsNone(result["applied_at"])
        raw = observed()
        raw["rules"] = [r for r in raw["rules"] if not r["display_name"].endswith("dfjr")]
        result = self.parse(raw, saved=False)
        self.assertEqual(result["status"], "damaged")
        self.assertIn("cannot be inferred uniquely", result["error"])
        raw = observed()
        raw["rules"][0]["remote"] = ["8.8.8.8/32"]
        self.assertEqual(self.parse(raw, saved=False)["status"], "damaged")

    def test_unreadable_or_malformed_state_does_not_claim_unlock(self):
        for raw in ({}, {"ok": False, "error": "denied"}, {"ok": True, "rules": [None]}):
            self.assertIsNone(self.parse(raw)["present"])
        raw = observed()
        raw["rules"][0]["display_name"] = "unexpected"
        self.assertEqual(self.parse(raw)["status"], "damaged")
        self.assertFalse(sl.parse_state(observed(), CONFIG, intent(), None)["active"])

    def test_address_digest_is_checked(self):
        saved = intent() | {"address_digest": "wrong"}
        self.assertEqual(sl.parse_state(observed(), CONFIG, saved, PROGRAM)["status"], "damaged")

    def test_restart_checks_process_start_times_even_after_app_restart(self):
        state = self.parse()
        self.assertTrue(sl.restart_needed(state, [{"name": "steam", "started": 50}]))
        self.assertFalse(sl.restart_needed(state, [{"name": "steam", "started": 101}]))
        self.assertIsNone(sl.restart_needed(state, [{"name": "cs2", "started": None}]))
        self.assertIsNone(sl.restart_needed(self.parse(saved=False), []))

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
    def test_real_cs2_log_names_the_server_and_the_queue_reason(self):
        """Lines from a real CS2 console.log (Nov 2026): queued from Dubai, landed in Singapore."""
        config = {"pops": {c: {} for c in ("dfjr", "sgp", "dxb", "fra", "maa2", "par")}}
        parser = sw.ConsoleParser()
        lines = (FIXTURES / "server_lock_console_real.log").read_text(encoding="utf-8").splitlines()
        events = [e for e in (parser.feed(line, config) for line in lines) if e]
        self.assertEqual([e["region"] for e in events], ["sgp"])
        queue = events[0]["queue"]
        self.assertEqual((queue["max_ping"], queue["best_official"], queue["under"]), (40, 80, ["dfjr"]))
        self.assertEqual(queue["pings"]["dxb"], 114)
        reason = sw.queue_reason(queue, ["dxb"])
        self.assertEqual(reason["code"], "queue_max_ping")
        self.assertIn("114 ms", reason["text"])

    def test_lines_that_do_not_locate_a_server_are_ignored(self):
        for lines in (("[Networking] Remote host is in data center 'dxb'",),
                      ("Summary of connection [#1 SDR server]", "[Networking] Remote host is in data center 'madeup'"),
                      ("Connected to 155.133.226.68:27015", "Selecting dxb#1 as primary"),
                      ("[#1 SDR server steamid:9 vport 0] Selecting dxb#1 (1.2.3.4:27015) as primary.  "
                       "(Ping = 150 = 80+60+10 (front+interior+remote).  Rank=1 Score=1)",)):
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
            handle.write("Summary of connection [#1 SDR server steamid:9]:\n[Networking] Remote host is in data center 'bom")
        poll()
        self.assertEqual(watch.history, [])
        with log.open("a") as handle:
            handle.write("2'\n")
        poll()
        poll()
        self.assertEqual(len(watch.history), 1)
        self.assertEqual(watch.notice["region"], "bom2")
        log.write_text("Summary of connection [#2 SDR server]:\n[Networking] Remote host is in data center 'dxb'\n")
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
        log.write_text("".join(f"Summary of connection [#{i} SDR server]:\n[Networking] Remote host is in data center 'bom2'\n" for i in range(25)))
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
            log.write_text("[#1 SDR server steamid:9 vport 0] Selecting fra#1 (1.2.3.4:27015) as primary.  "
                           "(Ping = 150 = 80+60+10 (front+interior+remote).  Rank=1 Score=1)\n")
            poll()
            survey = {"updated_at": 999, "regions": [{"code": "dxb", "ping_ms": 15, "loss": 0}]}
            with log.open("a") as handle:
                handle.write("Summary of connection [#1 SDR server]:\n[Networking] Remote host is in data center 'bom2'\n")
            poll()
        self.assertEqual(watch.history[-1]["reason"]["code"], "reachability")


class Operations(Isolated):
    def setUp(self):
        super().setUp()
        self.raw = observed(None)
        self.run_thread = patch.object(sl.threading, "Thread", side_effect=lambda **kw:
            types.SimpleNamespace(start=lambda:kw["target"](*kw.get("args", ()))))
        self.run_thread.start()
        self.addCleanup(self.run_thread.stop)
        p = patch.object(sl, "inspect_firewall", side_effect=lambda:self.raw)
        p.start()
        self.addCleanup(p.stop)
        self.helper.run.side_effect = self.helper_run

    def helper_run(self, op, args=None, *, wait=True):
        self.raw = observed("dxb") if op == "firewall.lock" else observed(None)
        return {"ok": True}

    def service(self):
        return sl.ServerLock(self.root, lambda:{"program": PROGRAM}, lambda:CONFIG, lambda:{})

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
        self.helper.run.assert_not_called()

    def test_exact_helper_apply_arguments_and_local_metadata_survive_restart(self):
        service = self.service()
        review = service.prepare("dxb")
        service.begin("apply", review["plan_id"])
        self.helper.run.assert_called_once_with("firewall.lock", {"program": PROGRAM, "regions": [
            {"name": "bom", "cidrs": ["155.133.226.68/32"]},
            {"name": "bom2", "cidrs": ["155.133.226.69/32"]},
            {"name": "dfjr", "cidrs": ["155.133.226.70/32"]},
            {"name": "hidden", "cidrs": ["155.133.226.71/32"]}]}, wait=True)
        self.assertEqual(service.snapshot()["firewall"]["status"], "locked")
        self.assertEqual(service.snapshot()["error"], "")
        saved = json.loads((self.root / "server-lock-selection.json").read_text())
        for key in ("code", "codes", "city", "revision", "address_digest", "regions"):
            self.assertEqual(saved[key], intent()[key])
        self.assertGreater(saved["applied_at"], 100)
        restarted = self.service()
        restarted.refresh()
        self.assertEqual(restarted.snapshot()["firewall"]["status"], "locked")
        self.raw = observed(None)
        restarted.refresh()
        self.assertEqual(restarted.snapshot()["firewall"]["status"], "missing")
        self.assertFalse(restarted.snapshot()["firewall"]["active"])

    def test_exact_unlock_operation_and_intent_cleared_only_on_verified_success(self):
        service = self.service()
        service._remember(intent())
        self.helper.run.side_effect = None
        self.helper.run.return_value = {"ok": False, "error": "helper failed"}
        service.begin("unlock")
        self.helper.run.assert_called_once_with("firewall.unlock", wait=True)
        self.assertEqual(service.snapshot()["firewall"]["status"], "missing")
        self.assertIn("helper failed", service.snapshot()["error"])
        self.helper.run.return_value = {"ok": True}
        service.begin("unlock")
        self.assertIsNone(service.intent)
        self.assertEqual(service.snapshot()["firewall"]["status"], "unlocked")
        self.assertIn("Restart Steam and CS2", service.snapshot()["detail"])

    def test_helper_success_without_real_rules_is_not_success(self):
        service = self.service()
        self.helper.run.side_effect = None
        self.helper.run.return_value = {"ok": True}
        service.begin("apply", code="dxb")
        self.assertFalse(service.snapshot()["firewall"]["active"])
        self.assertIn("did not confirm", service.snapshot()["error"])
        self.raw = observed("bom")
        service.begin("apply", code="dxb")
        self.assertTrue(service.snapshot()["error"])

    def test_missing_module_or_not_ready_never_prompts_and_returns_needs_setup(self):
        for helper in (None, self.helper):
            self.helper.ready.return_value = False
            with patch.object(sl, "elevated", helper):
                service = self.service()
                self.assertTrue(service.prepare("dxb")["needs_setup"])
                for action in ("apply", "unlock"):
                    result = service.begin(action, code="dxb" if action == "apply" else None)
                    self.assertTrue(result["needs_setup"])
                    self.assertIn("Run setup again", result["detail"])
            self.helper.run.assert_not_called()

    def test_run_needs_setup_is_reported_without_fallback_or_changed_selection(self):
        service = self.service()
        service._remember(intent("bom"))
        self.raw = observed("bom")
        self.helper.run.side_effect = None
        self.helper.run.return_value = {"ok": False, "needs_setup": True}
        for action in ("apply", "unlock"):
            result = service.begin(action, code="dxb" if action == "apply" else None)
            self.assertTrue(result["needs_setup"])
            self.assertIn("Run setup again", result["detail"])
            self.assertEqual(service.intent["code"], "bom")
            self.assertFalse(result["busy"])

    def test_setup_missing_is_reported_before_directory_or_install_discovery(self):
        self.helper.ready.return_value = False
        service = self.service()
        service.directory = MagicMock(side_effect=AssertionError("No directory needed without setup"))
        service.context = MagicMock(side_effect=AssertionError("No install needed without setup"))
        self.assertTrue(service.begin("apply", code="dxb")["needs_setup"])
        self.assertTrue(service.begin("unlock")["needs_setup"])
        self.helper.run.assert_not_called()

    def test_steam_started_during_helper_execution_still_needs_restart(self):
        service = self.service()
        now = [100]
        def run(*args, **kwargs):
            self.raw = observed()
            self.raw["processes"] = [{"name": "steam", "started": 150}]
            now[0] = 200
            return {"ok": True}
        self.helper.run.side_effect = run
        with patch.object(sl.time, "time", side_effect=lambda:now[0]):
            result = service.begin("apply", code="dxb")
        self.assertTrue(result["restart_needed"])
        self.assertEqual(service.intent["applied_at"], 200)

    def test_helper_exception_releases_worker_and_never_uses_fallback(self):
        service = self.service()
        self.helper.run.side_effect = OSError("helper unavailable")
        service.begin("unlock")
        self.assertIn("helper unavailable", service.snapshot()["error"])
        self.assertFalse(service.snapshot()["busy"])
        self.assertTrue(service.operation.acquire(blocking=False))
        service.operation.release()

    def test_install_program_is_required_and_limits_fail_before_helper(self):
        service = self.service()
        service.context = lambda:{"program": "cs2.exe"}
        result = service.begin("apply", code="dxb")
        self.assertIn("full install path", result["error"])
        self.helper.run.assert_not_called()
        config = copy.deepcopy(CONFIG)
        config["pops"]["bad;name"] = config["pops"].pop("hidden")
        service.directory = lambda:config
        with self.assertRaisesRegex(ValueError, "name format"):
            service.begin("apply", code="dxb")
        self.helper.run.assert_not_called()

    def test_unknown_process_state_prevents_change(self):
        service = self.service()
        for raw in ({"ok": False, "error": "denied"}, {"ok": True, "rules": []}):
            self.raw = raw
            result = service.begin("unlock")
            self.assertIn("whether CS2 is running", result["error"])
        self.helper.run.assert_not_called()

    def test_queue_apply_persists_and_observer_runs_it_once_after_game_closes(self):
        service = self.service()
        self.raw["processes"] = [{"name": "CS2", "started": 50}]
        result = service.begin("apply", code="dxb")
        self.assertEqual(result["pending"]["action"], "apply")
        self.assertEqual(result["detail"], "Will apply when CS2 closes")
        self.assertEqual(result["firewall"]["status"], "unlocked")
        self.helper.run.assert_not_called()
        restarted = self.service()
        self.assertEqual(restarted.snapshot()["pending"]["code"], "dxb")
        restarted._observe_once()
        self.helper.run.assert_not_called()
        self.raw["processes"] = []
        restarted._observe_once()
        restarted._observe_once()
        self.helper.run.assert_called_once()
        self.assertIsNone(restarted.snapshot()["pending"])
        self.assertEqual(restarted.snapshot()["firewall"]["status"], "locked")

    def test_new_requests_replace_pending_and_cancel_does_not_unlock_current_rules(self):
        service = self.service()
        service._remember(intent())
        self.raw = observed()
        self.raw["processes"] = [{"name": "cs2.exe", "started": 50}]
        service.begin("apply", code="bom")
        self.assertEqual(service.snapshot()["pending"]["code"], "bom")
        service.begin("unlock")
        self.assertEqual(service.snapshot()["pending"]["action"], "unlock")
        self.assertEqual(service.snapshot()["firewall"]["code"], "dxb")
        service.begin("apply", code="dfjr")
        self.assertEqual(service.snapshot()["pending"]["code"], "dfjr")
        self.assertIsNone(service.cancel()["pending"])
        self.assertEqual(self.service().intent["code"], "dxb")
        self.raw["processes"] = []
        service._observe_once()
        self.helper.run.assert_not_called()
        self.assertEqual(service.snapshot()["firewall"]["status"], "locked")

    def test_queued_unlock_runs_once_and_failed_helper_is_not_retried(self):
        service = self.service()
        service._remember(intent())
        self.raw = observed()
        self.raw["processes"] = [{"name": "cs2", "started": 50}]
        service.begin("unlock")
        self.assertEqual(self.service().snapshot()["pending"]["action"], "unlock")
        self.raw["processes"] = []
        self.helper.run.side_effect = None
        self.helper.run.return_value = {"ok": False, "error": "failed"}
        service._observe_once()
        service._observe_once()
        self.helper.run.assert_called_once_with("firewall.unlock", wait=True)
        self.assertIsNone(service.snapshot()["pending"])

    def test_queued_unlock_success_clears_intent(self):
        service = self.service()
        service._remember(intent())
        self.raw = observed()
        self.raw["processes"] = [{"name": "cs2", "started": 50}]
        service.begin("unlock")
        self.raw["processes"] = []
        service._observe_once()
        service._observe_once()
        self.helper.run.assert_called_once_with("firewall.unlock", wait=True)
        self.assertIsNone(service.intent)
        self.assertEqual(service.snapshot()["firewall"]["status"], "unlocked")

    def test_changed_directory_invalidates_queued_plan_and_does_not_retry(self):
        service = self.service()
        self.raw["processes"] = [{"name": "cs2", "started": 50}]
        service.begin("apply", code="dxb")
        config = copy.deepcopy(CONFIG)
        config["revision"] += 1
        service.directory = lambda:config
        self.raw["processes"] = []
        with self.assertRaisesRegex(ValueError, "directory changed"):
            service._observe_once()
        self.assertIsNone(service.snapshot()["pending"])
        service._observe_once()
        self.helper.run.assert_not_called()

    def test_queue_waits_for_setup_and_unknown_process_state(self):
        service = self.service()
        self.raw["processes"] = [{"name": "cs2", "started": 50}]
        service.begin("apply", code="dxb")
        self.raw = {"ok": False, "error": "denied"}
        service._observe_once()
        self.assertIsNotNone(service.snapshot()["pending"])
        self.raw = observed(None)
        self.helper.ready.return_value = False
        service._observe_once()
        self.assertTrue(service.snapshot()["needs_setup"])
        self.helper.run.assert_not_called()
        self.helper.ready.return_value = True
        service._observe_once()
        self.helper.run.assert_called_once()

    def test_persistence_failure_cannot_claim_a_queued_or_applied_lock(self):
        service = self.service()
        self.raw["processes"] = [{"name": "cs2", "started": 50}]
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = service.begin("apply", code="dxb")
        self.assertIn("disk full", result["error"])
        self.assertIsNone(result["pending"])
        self.helper.run.assert_not_called()

    def test_inferred_selection_is_saved_with_unknown_apply_time(self):
        service = self.service()
        self.raw = observed()
        service.refresh()
        self.assertEqual(self.service().intent["address_digest"], intent()["address_digest"])
        self.assertIsNone(self.service().intent["applied_at"])

    def test_stable_python_api_uses_the_same_service_without_review(self):
        service = self.service()
        service.survey = lambda:{"regions": [{"code": "dxb", "ping_ms": 18, "loss": 0, "status": "good"}]}
        with patch.object(sl, "shared", return_value=service):
            rows = sl.list_regions()
            self.assertEqual(next(r for r in rows if r["code"] == "dxb")["ping_ms"], 18)
            self.assertEqual(next(r for r in rows if r["code"] == "bom")["status"], "unknown")
            self.assertTrue(sl.request_lock("dxb")["firewall"]["active"])
            self.assertEqual(sl.lock_status()["firewall"]["code"], "dxb")
            self.assertIsNone(sl.request_unlock()["pending"])
            self.assertEqual(sl.lock_status()["firewall"]["status"], "unlocked")
        self.assertEqual([c.args[0] for c in self.helper.run.call_args_list], ["firewall.lock", "firewall.unlock"])

    def test_helper_runs_on_the_change_worker_with_default_timeout(self):
        service = self.service()
        with patch.object(sl.threading, "Thread") as thread:
            self.assertTrue(service.begin("unlock")["busy"])
            self.helper.run.assert_not_called()
            worker = thread.call_args.kwargs
        self.assertEqual(worker["name"], "server-lock-change")
        worker["target"](*worker["args"])
        self.helper.run.assert_called_once_with("firewall.unlock", wait=True)
        self.assertFalse(service.snapshot()["busy"])

    def test_run_needs_setup_consumes_queued_attempt_without_retry(self):
        service = self.service()
        self.raw["processes"] = [{"name": "cs2", "started": 50}]
        service.begin("apply", code="dxb")
        self.raw["processes"] = []
        self.helper.run.side_effect = None
        self.helper.run.return_value = {"ok": False, "needs_setup": True}
        service._observe_once()
        self.assertTrue(service.snapshot()["needs_setup"])
        self.assertIsNone(service.snapshot()["pending"])
        service._observe_once()
        self.helper.run.assert_called_once()

    def test_list_regions_keeps_existing_survey_when_full_directory_is_unavailable(self):
        service = self.service()
        service.directory = lambda:None
        service.survey = lambda:{"regions": [{"code": "dxb", "ping_ms": 18, "status": "good"}]}
        rows = service.list_regions()
        self.assertEqual(rows[0]["ping_ms"], 18)
        rows[0]["ping_ms"] = 99
        self.assertEqual(service.list_regions()[0]["ping_ms"], 18)


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

    def test_cancel_route_is_token_protected_and_only_cancels_pending(self):
        handler, service = self.handler("/api/servers/lock/cancel", {}, token="wrong")
        handler.do_POST()
        service.cancel.assert_not_called()
        self.assertEqual(handler._send_json.call_args.args[1], 403)
        handler, service = self.handler("/api/servers/lock/cancel", {})
        service.cancel.return_value = {"pending": None}
        handler.do_POST()
        service.cancel.assert_called_once_with()
        service.begin.assert_not_called()

    def test_prepare_can_return_needs_setup_without_a_plan(self):
        handler, service = self.handler("/api/servers/lock/prepare", {"code": "dxb"})
        service.prepare.return_value = {"needs_setup": True, "detail": sl.SETUP_MESSAGE}
        handler.do_POST()
        self.assertTrue(handler._send_json.call_args.args[0]["needs_setup"])

    def test_http_and_python_share_one_service_and_same_install_discovery(self):
        from cs2cfg import cli, paths, whoami
        state = types.SimpleNamespace(server_lock=None, server_ping=None, steam_root=Path(r"C:\Steam"),
                                      cs2_install=Path(PROGRAM).parents[3], users=[])
        with patch.object(sl, "_shared", None), \
             patch.object(paths, "user_data_dir", return_value=self.root), \
             patch.object(sl.ServerLock, "start") as start, \
             patch.object(webui.steam, "list_users", return_value=[]), \
             patch.object(cli, "load_prefs", return_value={}), \
             patch.object(whoami, "current", return_value=(None, "")):
            service = webui._server_lock_service(state)
            self.assertIs(service, sl.shared())
            self.assertIs(service, webui._server_lock_service(state))
            start.assert_called_once()
            context = service.context()
        self.assertEqual(context["program"], PROGRAM)
        self.assertEqual(context["console_path"], state.cs2_install / "game" / "csgo" / "console.log")

    def test_ui_attaches_existing_python_service_without_another_observer(self):
        from cs2cfg import paths
        state = types.SimpleNamespace(server_lock=None, server_ping=None)
        with patch.object(sl, "_shared", None), \
             patch.object(paths, "user_data_dir", return_value=self.root), \
             patch.object(sl.ServerLock, "start") as start:
            python_service = sl.shared()
            self.assertIs(webui._server_lock_service(state), python_service)
            start.assert_called_once()

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
