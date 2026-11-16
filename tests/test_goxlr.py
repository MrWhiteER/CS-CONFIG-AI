"""GoXLR adapters/routes with fake HTTP, processes and directory entries only.

No server startup, elevated helper, installed GoXLR, or real profile file access.
"""
from __future__ import annotations

import copy
import io
import json
import socket
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cs2cfg import elevated, goxlr, profiles

with mock.patch.object(elevated, "ready", return_value=False), \
     mock.patch.object(elevated, "run", return_value={"ok": False}):
    from cs2cfg import webui


def status(device="Default", mic="Clean"):
    return {"mixers": {"SERIAL": {"profile_name": device, "mic_profile_name": mic}},
            "files": {"profiles": ["Default", "Match", "Recording"],
                      "mic_profiles": ["Clean", "Broadcast"]}}


class Isolated(unittest.TestCase):
    def setUp(self):
        for patch in (
            mock.patch.object(elevated, "ready", return_value=False),
            mock.patch.object(elevated, "run", side_effect=AssertionError("live helper")),
            mock.patch.object(socket, "create_connection", side_effect=AssertionError("real socket")),
            mock.patch.object(subprocess, "run", side_effect=AssertionError("real process")),
        ):
            patch.start()
            self.addCleanup(patch.stop)


class HTTP(Isolated):
    def connection(self, result="Ok", code=200, raw=None):
        patch = mock.patch.object(goxlr.http.client, "HTTPConnection")
        connection = patch.start().return_value
        self.addCleanup(patch.stop)
        connection.getresponse.return_value.status = code
        connection.getresponse.return_value.read.return_value = (
            json.dumps(result).encode() if raw is None else raw)
        return connection

    def test_fixed_loopback_endpoint_timeout_and_json(self):
        connection = self.connection({"Status": status()})
        self.assertEqual(goxlr._status(), status())
        goxlr.http.client.HTTPConnection.assert_called_once_with(
            "127.0.0.1", 14564, timeout=goxlr.TIMEOUT)
        args = connection.request.call_args.args
        self.assertEqual(args[:2], ("POST", "/api/command"))
        self.assertEqual(json.loads(args[2]), "GetStatus")
        self.assertEqual(args[3], {"Content-Type": "application/json"})
        connection.getresponse.return_value.read.assert_called_once_with(goxlr.MAX_RESPONSE + 1)
        connection.close.assert_called_once()

    def test_timeout_closes_socket(self):
        connection = self.connection()
        connection.getresponse.side_effect = socket.timeout()
        with self.assertRaises(goxlr.GoXLRError):
            goxlr._status()
        connection.close.assert_called_once()

    def test_connection_refused_closes_socket(self):
        connection = self.connection()
        connection.request.side_effect = ConnectionRefusedError()
        with self.assertRaises(goxlr.GoXLRError):
            goxlr._request("GetStatus")
        connection.close.assert_called_once()

    def test_redirect_is_not_followed(self):
        connection = self.connection(code=302)
        with self.assertRaises(goxlr.GoXLRError):
            goxlr._request("GetStatus")
        self.assertEqual(connection.request.call_count, 1)

    def test_oversized_response_rejected(self):
        self.connection(raw=b" " * (goxlr.MAX_RESPONSE + 1))
        with self.assertRaises(goxlr.GoXLRError):
            goxlr._request("GetStatus")

    def test_invalid_json_rejected(self):
        self.connection(raw=b"<html>wrong service</html>")
        with self.assertRaises(goxlr.GoXLRError):
            goxlr._status()

    def test_error_envelope_reported(self):
        self.connection({"Error": "Device disconnected"})
        with self.assertRaisesRegex(goxlr.GoXLRError, "Device disconnected"):
            goxlr._request("GetStatus")

    def test_unknown_status_shape_rejected(self):
        for response in ({}, {"Status": []}, {"Status": {}}, "Ok", []):
            with self.subTest(response=response), mock.patch.object(goxlr, "_request", return_value=response):
                with self.assertRaises(goxlr.GoXLRError):
                    goxlr._status()


class Discovery(Isolated):
    def test_utility_wins_only_with_valid_status(self):
        with mock.patch.object(goxlr, "_status", return_value=status()), \
             mock.patch.object(goxlr, "_processes") as processes:
            found = goxlr.detect()
        self.assertEqual(found["backend"], "utility")
        self.assertEqual(found["serial"], "SERIAL")
        self.assertEqual(found["current"], {"device": "Default", "mic": "Clean"})
        processes.assert_not_called()

    def test_no_apps_is_calm_and_does_not_list_files(self):
        with mock.patch.object(goxlr, "_status", side_effect=goxlr.GoXLRError()), \
             mock.patch.object(goxlr, "_processes", return_value=set()), \
             mock.patch.object(goxlr, "_official_profiles") as files:
            found = goxlr.detect()
        self.assertEqual(found["state"], "not_found")
        self.assertFalse(found["can_switch"])
        files.assert_not_called()

    def test_official_is_listed_without_invented_switch_support(self):
        with mock.patch.object(goxlr, "_status", side_effect=goxlr.GoXLRError()), \
             mock.patch.object(goxlr, "_processes", return_value={"goxlr app.exe"}), \
             mock.patch.object(goxlr, "_official_profiles", return_value=(["Match"], ["Clean"])):
            found = goxlr.detect()
        self.assertEqual(found["backend"], "official")
        self.assertEqual(found["profiles"], ["Match"])
        self.assertEqual(found["mic_profiles"], ["Clean"])
        self.assertEqual(found["current"], {"device": "", "mic": ""})
        self.assertFalse(found["can_switch"])

    def test_utility_running_with_web_server_off_reports_unavailable(self):
        with mock.patch.object(goxlr, "_status", side_effect=goxlr.GoXLRError()), \
             mock.patch.object(goxlr, "_processes", return_value={"goxlr-daemon.exe"}):
            self.assertEqual(goxlr.detect()["state"], "unavailable")

    def test_two_mixers_require_selection(self):
        data = status()
        data["mixers"]["SECOND"] = data["mixers"]["SERIAL"]
        found = goxlr._utility(data)
        self.assertEqual(found["serial"], "")
        self.assertFalse(found["can_switch"])
        self.assertEqual(goxlr._utility(data, "SECOND")["serial"], "SECOND")

    def test_disconnected_requested_serial_does_not_choose_another_device(self):
        found = goxlr._utility(status(), "OTHER")
        self.assertEqual(found["serial"], "")
        self.assertFalse(found["can_switch"])

    def test_daemon_without_mixer_is_not_a_connected_device(self):
        data = status()
        data["mixers"] = {}
        self.assertEqual(goxlr._utility(data)["state"], "disconnected")

    def test_names_are_deduplicated_and_paths_rejected(self):
        self.assertEqual(goxlr._names(["Match", "Match", "Alpha", "../bad", "a\\b", "", None,
                                       "nul\x00", "line\n", "x" * 241]), ["Alpha", "Match"])

    def test_official_directory_names_only_no_contents(self):
        def entry(name, is_file=True):
            path = Path(name)
            return SimpleNamespace(stem=path.stem, suffix=path.suffix,
                                   is_file=mock.Mock(return_value=is_file))
        with mock.patch.object(goxlr, "_documents", return_value=Path("redirected")), \
             mock.patch.object(Path, "iterdir", autospec=True, side_effect=[
                 [entry("Match.goxlr"), entry("A.GOXLR"), entry("noise.txt"), entry("dir.goxlr", False)],
                 [entry("Clean.goxlrMicProfile")]]) as entries, \
             mock.patch.object(Path, "open", side_effect=AssertionError("profile opened")), \
             mock.patch.object(Path, "mkdir", side_effect=AssertionError("folder created")):
            self.assertEqual(goxlr._official_profiles(), (["A", "Match"], ["Clean"]))
        self.assertEqual([call.args[0] for call in entries.call_args_list],
                         [Path("redirected/GoXLR/Profiles"), Path("redirected/GoXLR/Mic Profiles")])

    def test_missing_or_locked_directories_are_empty(self):
        with mock.patch.object(goxlr, "_documents", return_value=Path("fake")), \
             mock.patch.object(Path, "iterdir", side_effect=PermissionError()):
            self.assertEqual(goxlr._official_profiles(), ([], []))

    def test_process_listing_is_hidden_bounded_and_csv_parsed(self):
        with mock.patch.object(goxlr.sys, "platform", "win32"), \
             mock.patch.object(subprocess, "run", return_value=SimpleNamespace(
                 stdout='"GoXLR App.exe","123","Console"\n"Other.exe","1","Console"')) as run:
            self.assertIn("goxlr app.exe", goxlr._processes())
        self.assertEqual(run.call_args.args[0], ["tasklist", "/FO", "CSV", "/NH"])
        self.assertEqual(run.call_args.kwargs["timeout"], goxlr.TIMEOUT)
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)

    def test_process_timeout_is_empty(self):
        with mock.patch.object(goxlr.sys, "platform", "win32"), \
             mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("tasklist", .7)):
            self.assertEqual(goxlr._processes(), set())

    def test_redirected_documents_is_resolved_read_only(self):
        registry = mock.MagicMock()
        registry.QueryValueEx.return_value = ("redirected-documents", 1)
        with mock.patch.object(goxlr.sys, "platform", "win32"), \
             mock.patch.dict("sys.modules", {"winreg": registry}):
            self.assertEqual(goxlr._documents(), Path("redirected-documents"))
        registry.QueryValueEx.assert_called_once()
        registry.SetValueEx.assert_not_called()


class Switching(Isolated):
    def test_device_command_and_readback(self):
        with mock.patch.object(goxlr, "_status", side_effect=[status(), status("Match")]), \
             mock.patch.object(goxlr, "_request", return_value="Ok") as request:
            result = goxlr.Controller().switch("utility", "SERIAL", {"device": "Match"})
        self.assertEqual(result["current"]["device"], "Match")
        request.assert_called_once_with({"Command": ["SERIAL", {"LoadProfile": ["Match", False]}]})

    def test_mic_command_and_readback(self):
        with mock.patch.object(goxlr, "_status", side_effect=[status(), status(mic="Broadcast")]), \
             mock.patch.object(goxlr, "_request", return_value="Ok") as request:
            goxlr.Controller().switch("utility", "SERIAL", {"mic": "Broadcast"})
        request.assert_called_once_with({"Command": ["SERIAL", {"LoadMicProfile": ["Broadcast", False]}]})

    def test_setup_loads_both_in_order(self):
        with mock.patch.object(goxlr, "_status", side_effect=[status(), status("Match", "Broadcast")]), \
             mock.patch.object(goxlr, "_request", return_value="Ok") as request:
            goxlr.Controller().switch("utility", "SERIAL", {"device": "Match", "mic": "Broadcast"})
        self.assertEqual(request.call_args_list, [
            mock.call({"Command": ["SERIAL", {"LoadProfile": ["Match", False]}]}),
            mock.call({"Command": ["SERIAL", {"LoadMicProfile": ["Broadcast", False]}]})])

    def test_unsupported_official_fails_before_any_io(self):
        with mock.patch.object(goxlr, "_status") as probe:
            with self.assertRaisesRegex(goxlr.GoXLRError, "supported bridge"):
                goxlr.Controller().switch("official", "", {"mic": "Clean"})
        probe.assert_not_called()

    def test_stale_profile_or_serial_never_sends_command(self):
        for serial, choice in (("OTHER", {"device": "Match"}), ("SERIAL", {"mic": "Missing"}),
                               ("SERIAL", {"device": "../Match"})):
            with self.subTest(serial=serial, choice=choice), \
                 mock.patch.object(goxlr, "_status", return_value=status()), \
                 mock.patch.object(goxlr, "_request") as request:
                with self.assertRaises(goxlr.GoXLRError):
                    goxlr.Controller().switch("utility", serial, choice)
                request.assert_not_called()

    def test_bad_inputs_rejected_before_io(self):
        for serial, choice in (("", {}), ([], {"device": "Match"}), ("SERIAL", ["device"]),
                               ("SERIAL", {"delete": "Match"}), ("SERIAL", {"mic": []})):
            with self.subTest(choice=choice), mock.patch.object(goxlr, "_status") as probe:
                with self.assertRaises(goxlr.GoXLRError):
                    goxlr.Controller().switch("utility", serial, choice)
                probe.assert_not_called()

    def test_both_choices_validated_before_first_command(self):
        with mock.patch.object(goxlr, "_status", return_value=status()), \
             mock.patch.object(goxlr, "_request") as request:
            with self.assertRaises(goxlr.GoXLRError):
                goxlr.Controller().switch("utility", "SERIAL", {"device": "Match", "mic": "Missing"})
            request.assert_not_called()

    def test_acknowledgement_without_readback_is_not_success(self):
        with mock.patch.object(goxlr, "_status", return_value=status()), \
             mock.patch.object(goxlr, "_request", return_value="Ok"):
            with self.assertRaisesRegex(goxlr.GoXLRError, "not confirmed"):
                goxlr.Controller().switch("utility", "SERIAL", {"device": "Match"})

    def test_partial_setup_failure_is_not_rolled_back_with_more_commands(self):
        controller = goxlr.Controller()
        with mock.patch.object(goxlr, "_status", return_value=status()), \
             mock.patch.object(goxlr, "_request", side_effect=["Ok", goxlr.GoXLRError("timeout")]) as request:
            with self.assertRaises(goxlr.GoXLRError):
                controller.switch("utility", "SERIAL", {"device": "Match", "mic": "Broadcast"})
        self.assertEqual(request.call_count, 2)
        self.assertFalse(controller.lock.locked())

    def test_busy_operation_fails_immediately(self):
        controller = goxlr.Controller()
        controller.lock.acquire()
        try:
            with mock.patch.object(goxlr, "_status") as probe:
                with self.assertRaisesRegex(goxlr.GoXLRError, "in progress"):
                    controller.switch("utility", "SERIAL", {"device": "Match"})
                probe.assert_not_called()
        finally:
            controller.lock.release()


class Endpoints(Isolated):
    def setUp(self):
        super().setUp()
        self.prefs = {"ui": {}, "accounts": {"1": {"setups": {"Match": {}, "Practice": {}},
                                                     "setup_live": "Match"}}}
        self.state = SimpleNamespace(goxlr=goxlr.Controller(), token="fake-token", lock=mock.MagicMock())
        for patch in (
            mock.patch("cs2cfg.cli.load_prefs", side_effect=lambda: copy.deepcopy(self.prefs)),
            mock.patch("cs2cfg.cli.save_prefs", side_effect=self.save),
            mock.patch.object(webui, "_active_account", return_value="1"),
            mock.patch.object(goxlr, "_status", return_value=status()),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def save(self, prefs):
        self.prefs = copy.deepcopy(prefs)

    def bind(self):
        return webui._goxlr_bind(self.state, {"setup": "Match", "serial": "SERIAL"})

    def test_binding_is_local_scoped_and_loads_actual_current_names(self):
        self.assertTrue(self.bind()["ok"])
        stored = self.prefs["ui"][goxlr.BINDINGS]["1"]["Match"]
        self.assertEqual(stored, {"backend": "utility", "serial": "SERIAL",
                                  "profiles": {"device": "Default", "mic": "Clean"}})
        self.assertNotIn(goxlr.BINDINGS, self.prefs["accounts"]["1"])
        self.assertTrue(profiles.is_machine(goxlr.BINDINGS))
        self.assertEqual(goxlr.bindings(self.prefs["ui"], "2", ["Match"]), {})

    def test_binding_requires_an_existing_setup(self):
        self.assertFalse(webui._goxlr_bind(self.state, {"setup": "Missing"})["ok"])
        self.assertNotIn(goxlr.BINDINGS, self.prefs["ui"])

    def test_official_binding_unavailable(self):
        with mock.patch.object(goxlr, "detect", return_value={"backend": "official", "can_switch": False}):
            self.assertFalse(self.bind()["ok"])

    def test_stale_serial_cannot_bind_to_another_device(self):
        self.assertFalse(webui._goxlr_bind(self.state, {"setup": "Match", "serial": "OTHER"})["ok"])

    def test_unlink_does_not_need_hardware(self):
        self.bind()
        with mock.patch.object(goxlr, "detect", side_effect=AssertionError("probe during unlink")):
            self.assertTrue(webui._goxlr_bind(self.state, {"setup": "Match", "remove": True})["ok"])
        self.assertEqual(webui._goxlr_context(self.state)["bindings"], {})

    def test_deleted_and_renamed_setups_update_bindings(self):
        self.bind()
        webui._setups_act(self.state, {"do": "rename", "name": "Match", "to": "Tournament"})
        self.assertIn("Tournament", webui._goxlr_context(self.state)["bindings"])
        webui._setups_act(self.state, {"do": "delete", "name": "Tournament"})
        self.assertEqual(webui._goxlr_context(self.state)["bindings"], {})

    def test_setup_use_rejects_stale_selection(self):
        self.bind()
        with mock.patch.object(self.state.goxlr, "switch") as switch:
            self.assertFalse(webui._goxlr_setup_use(self.state, {"setup": "Practice"})["ok"])
        switch.assert_not_called()

    def test_unbound_setup_does_not_probe_or_switch(self):
        with mock.patch.object(self.state.goxlr, "switch") as switch:
            self.assertTrue(webui._goxlr_setup_use(self.state, {"setup": "Match"})["skipped"])
        switch.assert_not_called()

    def test_bound_setup_switches_saved_device_and_profiles(self):
        self.bind()
        with mock.patch.object(self.state.goxlr, "switch", return_value={"current": {}}) as switch:
            self.assertTrue(webui._goxlr_setup_use(self.state, {"setup": "Match"})["ok"])
        switch.assert_called_once_with("utility", "SERIAL", {"device": "Default", "mic": "Clean"})

    def test_failed_bound_switch_keeps_binding_and_setup(self):
        self.bind()
        before = copy.deepcopy(self.prefs)
        with mock.patch.object(self.state.goxlr, "switch", side_effect=goxlr.GoXLRError("offline")):
            result = webui._goxlr_setup_use(self.state, {"setup": "Match"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_refresh"])
        self.assertEqual(self.prefs, before)

    def test_switch_endpoint_validates_kind(self):
        self.assertFalse(webui._goxlr_switch(self.state, {"kind": "delete"})["ok"])

    def test_switch_error_is_explicit_and_does_not_claim_a_new_current_profile(self):
        with mock.patch.object(self.state.goxlr, "switch", side_effect=goxlr.GoXLRError("offline")):
            result = webui._goxlr_switch(self.state, {"kind": "mic"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_refresh"])
        self.assertNotIn("current", result)

    def post(self, route, token="fake-token", host=True):
        cls = webui.make_handler(self.state)
        handler = cls.__new__(cls)
        handler.path = route
        handler.headers = {"Content-Length": "2", "X-CS2CFG-Token": token}
        handler.rfile = io.BytesIO(b"{}")
        handler._host_ok = mock.Mock(return_value=host)
        handler._send_json = mock.Mock()
        handler.do_POST()
        return handler._send_json.call_args

    def test_new_routes_keep_csrf_token_check(self):
        for route in ("/api/goxlr", "/api/goxlr/switch", "/api/goxlr/bind", "/api/goxlr/setup/use"):
            with self.subTest(route=route), mock.patch.object(goxlr, "detect") as probe:
                self.assertEqual(self.post(route, token="").args[1], 403)
                probe.assert_not_called()

    def test_new_routes_keep_host_check(self):
        self.assertEqual(self.post("/api/goxlr", host=False).args[1], 403)

    def test_probe_does_not_take_global_ui_lock(self):
        with mock.patch.object(webui, "_goxlr", return_value={"backend": "none"}):
            self.assertEqual(self.post("/api/goxlr").args[0]["backend"], "none")
        self.state.lock.__enter__.assert_not_called()


if __name__ == "__main__":
    unittest.main()
