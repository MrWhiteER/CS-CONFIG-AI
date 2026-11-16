"""Section 6: URL safety, preferences and discovery without live applications."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import apps, faceit_apps, launcher


class TeamSpeakServer(unittest.TestCase):
    def test_join_url_encodes_nickname_and_port(self):
        self.assertEqual(apps.join_url({"host": "voice.example.com", "port": 9987,
                                       "nickname": "A & B?#", "enabled": True}),
                         "ts3server://voice.example.com?port=9987&nickname=A+%26+B%3F%23")

    def test_ipv6_host(self):
        self.assertTrue(apps.join_url({"host": "[::1]"}).startswith("ts3server://[::1]?"))

    def test_rejects_invalid_hosts_ports_and_nicknames(self):
        for value in ({"host": "evil/?x=y"}, {"host": "a&b"}, {"host": "a b"},
                      {"host": "https://example.com"}, {"port": 0}, {"port": 65536},
                      {"port": "oops"}, {"enabled": True}, {"nickname": "x\ny"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                apps.server(value)

    def test_no_shell_or_input_to_open_url(self):
        with mock.patch.object(apps.sys, "platform", "win32"), \
             mock.patch.object(apps.os, "startfile", create=True) as opened:
            self.assertTrue(apps.open_url("ts3server://example.com?port=9987")["ok"])
            opened.assert_called_once_with("ts3server://example.com?port=9987")
            self.assertFalse(apps.open_url("file:///x")["ok"])
            self.assertFalse(apps.open_url("cmd:bad")["ok"])

    def test_missing_protocol_handler_is_reported(self):
        with mock.patch.object(apps.sys, "platform", "win32"), \
             mock.patch.object(apps.os, "startfile", side_effect=OSError("No handler"), create=True):
            self.assertFalse(apps.open_url("ms-gamebar:")["ok"])

    def test_launcher_opens_server_without_waiting_for_a_fake_executable(self):
        with mock.patch.object(apps, "open_url", return_value={"ok": True}) as opened, \
             mock.patch("cs2cfg.companions.start") as started:
            launcher._bring_up_companions([{"url": "ts3server://example.com?port=9987"}], False,
                                          lambda *args: None)
        opened.assert_called_once()
        started.assert_not_called()


class NamedApps(unittest.TestCase):
    def test_discord_uses_process_status_instead_of_updater(self):
        with mock.patch("cs2cfg.companions.running", side_effect=lambda n: n == "Discord.exe"):
            self.assertTrue(apps.running("discord"))

    def test_configure_does_not_enable_launch_without_request(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "Discord.exe"
            exe.touch()
            with mock.patch.object(apps, "find", return_value=None):
                change = apps.configure({}, "discord", {"exe": str(exe)})
            self.assertFalse(change["companions"][0]["with_game"])
            self.assertEqual(change["companions"][0]["integration"], "discord")

    def test_configure_updates_existing_without_duplicate(self):
        entry = {"id": "discord", "name": "Discord", "exe": "Discord.exe",
                 "args": "", "with_game": False, "integration": "discord"}
        change = apps.configure({"companions": [entry]}, "discord", {"with_game": True})
        self.assertEqual(len(change["companions"]), 1)
        self.assertTrue(change["companions"][0]["with_game"])

    def test_faceit_custom_path_can_be_saved_without_enabling(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "FACEIT.exe"
            exe.touch()
            change = faceit_apps.set_with_game({}, faceit_apps.CLIENT, False, str(exe))
        self.assertEqual(change["companions"][0]["exe"], str(exe))
        self.assertFalse(change["companions"][0]["with_game"])

    def test_invalid_brand_is_rejected(self):
        with self.assertRaises(ValueError):
            apps.configure({}, "other", {})
