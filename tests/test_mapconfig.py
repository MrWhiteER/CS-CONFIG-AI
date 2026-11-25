"""Map configs: warmup / 5v5 configs that only last while on their map."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import applynow, cfgscan, gamewatch, mapconfig  # noqa: E402
from sandbox import redirect_backups, redirect_layouts  # noqa: E402

FILES = {
    "mrwhiteer/autoexec.vcfg": (
        'exec "mrwhiteer/mainsettings/key_binds.vcfg"\n'
        'exec "mrwhiteer/mainsettings/settings.vcfg"\n'
        'bind "scancode69" "exec cs2cfg_apply_now"\n'
    ),
    "mrwhiteer/mainsettings/key_binds.vcfg": (
        'bind "scancode8" "+use"\n'
        'bind "mouse3" "say custom text"\n'
        'bind "mouse4" "player_ping"\n'
        'bind "scancode65" "exec mrwhiteer/lan/warmup.vcfg"\n'
    ),
    "mrwhiteer/mainsettings/settings.vcfg": (
        'sensitivity "1.1"\n'
        'cl_crosshairsize "2"\n'
    ),
    "mrwhiteer/lan/warmup.vcfg": (
        'sv_cheats 1\n'
        'bot_quota 10\n'
        'cl_crosshairsize "5"\n'
        'bind "e" "+invsmoke; !health"\n'
        'bind "mouse3" "noclip"\n'
        'bind "scancode49" "matchpause"\n'
        'alias "!health" "ent_fire !self sethealth 999999"\n'
    ),
}


class MapCase(unittest.TestCase):
    def setUp(self):
        redirect_backups(self)
        redirect_layouts(self)
        self.sandbox = Path(tempfile.mkdtemp(prefix="cs2cfg-maps-"))
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.cfg_root = self.sandbox / "cfg"
        for relative, text in FILES.items():
            path = self.cfg_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        patch = mock.patch.object(mapconfig, "_store", return_value=self.sandbox / "map-setups.json")
        patch.start()
        self.addCleanup(patch.stop)
        shared = mock.patch.object(mapconfig, "_shared", None)
        shared.start()
        self.addCleanup(shared.stop)
        self.result = cfgscan.scan(self.cfg_root / "mrwhiteer", cfg_root=self.cfg_root)
        # This fixture explicitly knows that the practice-only key was empty.
        # Missing custom lines alone are not evidence of an unbound game key.
        mapconfig.remember_baseline(self.result, {"scancode49": ""})

    def turn_on(self, maps=()):
        return mapconfig.set_setup(self.result, "mrwhiteer/lan/warmup.vcfg", True, list(maps))


class TestPicking(MapCase):
    def test_lists_configs_loaded_in_game_with_plain_names(self):
        out = mapconfig.summary(self.result)
        files = [s["file"] for s in out["setups"]]
        self.assertIn("mrwhiteer/lan/warmup.vcfg", files)
        self.assertNotIn("mrwhiteer/autoexec.vcfg", files)
        warm = next(s for s in out["setups"] if s["file"].endswith("warmup.vcfg"))
        self.assertEqual(warm["name"], "Warmup")
        self.assertIn("E", warm["keys"])
        self.assertIn("Mouse 3", warm["keys"])
        self.assertEqual(out["apply_key"], "F12")

    def test_startup_configs_refused(self):
        with self.assertRaises(ValueError):
            mapconfig.set_setup(self.result, "mrwhiteer/autoexec.vcfg", True, [])

    def test_maps_saved_as_ids_and_shown_as_names(self):
        out = self.turn_on(["Mirage", "de_dust2"])
        warm = next(s for s in out["setups"] if s["on"])
        self.assertEqual([m["id"] for m in warm["maps"]], ["de_mirage", "de_dust2"])
        self.assertEqual([m["name"] for m in warm["maps"]], ["Mirage", "Dust II"])

    def test_belongs(self):
        self.turn_on(["de_mirage"])
        setups = mapconfig.setups_for(mapconfig.load(), self.result)
        self.assertTrue(mapconfig.belongs(setups, "de_mirage"))
        self.assertFalse(mapconfig.belongs(setups, "de_nuke"))
        self.assertFalse(mapconfig.belongs(setups, ""))
        self.turn_on([])
        setups = mapconfig.setups_for(mapconfig.load(), self.result)
        self.assertTrue(mapconfig.belongs(setups, "de_nuke"))


class TestPutBack(MapCase):
    def test_reset_file_puts_normal_keys_scripts_and_settings_back(self):
        self.turn_on()
        text = (self.cfg_root / mapconfig.FILE_NAME).read_text(encoding="utf-8")
        self.assertIn('bind "scancode8" "+use"', text)
        self.assertIn('bind "mouse3" "say custom text"', text)
        self.assertIn('unbind "scancode49"', text)          # nothing normal there
        self.assertIn('alias "!health" ""', text)
        self.assertIn('cl_crosshairsize "2"', text)
        # Server settings die with the practice server; never sent.
        self.assertNotIn("sv_cheats", text)
        self.assertNotIn("bot_quota", text)
        self.assertNotIn("noclip", text)

    def test_reset_file_not_scanned_and_removed_with_last_setup(self):
        self.turn_on()
        rescanned = cfgscan.scan(self.cfg_root / "mrwhiteer", cfg_root=self.cfg_root)
        self.assertFalse(any(c.relative.endswith(mapconfig.FILE_NAME) for c in rescanned.files.values()))
        mapconfig.set_setup(self.result, "mrwhiteer/lan/warmup.vcfg", False, [])
        self.assertFalse((self.cfg_root / mapconfig.FILE_NAME).exists())


class TestFollowingTheGame(MapCase):
    def setUp(self):
        super().setUp()
        self.turn_on(["de_mirage"])
        self.pressed = []
        self.front = True
        self.watch = mapconfig.MapWatch(
            lambda: self.result,
            lambda result: applynow.refresh(result, running=False),
            press=lambda key: self.pressed.append(key) or True,
            in_front=lambda: self.front)
        mapconfig._shared = self.watch

    def feed(self, map_id="", activity="menu"):
        payload = {"map": {"name": map_id} if map_id else {},
                   "player": {"activity": activity}}
        self.watch.feed(payload)

    @property
    def apply_text(self):
        return (self.cfg_root / applynow.FILE_NAME).read_text(encoding="utf-8")

    def test_on_its_map_nothing_is_undone(self):
        self.feed("de_mirage", "playing")
        self.assertTrue(self.watch.on_setup_map)
        self.assertNotIn(mapconfig.EXEC_LINE, self.apply_text)
        self.assertEqual(self.pressed, [])

    def test_leaving_to_menu_presses_apply_key_once(self):
        self.feed("de_mirage", "playing")
        self.feed()
        self.assertIn(mapconfig.EXEC_LINE, self.apply_text)
        self.assertEqual(self.pressed, ["scancode69"])
        self.feed()                       # heartbeat in the menu: no second press
        self.assertEqual(self.pressed, ["scancode69"])

    def test_waits_until_cs2_is_in_front(self):
        self.feed("de_mirage", "playing")
        self.front = False
        self.feed()
        self.assertEqual(self.pressed, [])
        self.front = True
        self.feed()
        self.assertEqual(self.pressed, ["scancode69"])

    def test_never_presses_during_another_match(self):
        self.feed("de_mirage", "playing")
        self.feed("de_nuke", "playing")
        self.assertEqual(self.pressed, [])
        self.assertIn(mapconfig.EXEC_LINE, self.apply_text)
        self.feed()
        self.assertEqual(self.pressed, ["scancode69"])

    def test_after_quit_or_crash_next_menu_puts_back(self):
        self.feed("de_mirage", "playing")
        self.watch.game_closed()
        self.assertTrue(mapconfig.load()["needs_reset"])
        fresh = mapconfig.MapWatch(lambda: self.result, lambda r: None,
                                   press=lambda key: self.pressed.append(key) or True,
                                   in_front=lambda: True)
        fresh.feed({"map": {}, "player": {"activity": "menu"}})
        self.assertEqual(self.pressed, ["scancode69"])
        self.assertFalse(mapconfig.load()["needs_reset"])

    def test_switch_off_means_no_press(self):
        data = mapconfig.load()
        data["auto_press"] = False
        mapconfig.save(data)
        self.feed("de_mirage", "playing")
        self.feed()
        self.assertEqual(self.pressed, [])
        self.assertIn(mapconfig.EXEC_LINE, self.apply_text)


class TestNotButtonsYouChanged(MapCase):
    def test_setup_binds_saved_by_cs2_are_not_reported(self):
        self.turn_on()
        owned = mapconfig.app_owned_filter(self.result)
        loaded = gamewatch.Change("Key binds", "MOUSE3", "changed", "say custom text", "noclip")
        back = gamewatch.Change("Key binds", "e", "changed", "+invsmoke; !health", "+use")
        mine = gamewatch.Change("Key binds", "mouse4", "changed", "player_ping", "+jump")
        setting = gamewatch.Change("In-game settings", "cl_crosshairsize", "changed", "2", "5")
        self.assertTrue(owned(loaded))
        self.assertTrue(owned(back))
        self.assertFalse(owned(mine))
        self.assertTrue(owned(setting))

    def test_watcher_drops_them(self):
        self.turn_on()
        gamewatch.APP_OWNED.append(mapconfig.app_owned_filter(self.result))
        self.addCleanup(gamewatch.APP_OWNED.clear)
        changes = [gamewatch.Change("Key binds", "mouse3", "changed", "say custom text", "noclip"),
                   gamewatch.Change("Key binds", "mouse4", "changed", "player_ping", "+jump")]
        kept = gamewatch.without_app_owned(changes)
        self.assertEqual([c.key for c in kept], ["mouse4"])


class TestVirtualKeys(unittest.TestCase):
    def test_common_apply_keys(self):
        self.assertEqual(mapconfig._virtual_key("scancode69"), 0x7B)   # F12
        self.assertEqual(mapconfig._virtual_key("scancode58"), 0x70)   # F1
        self.assertEqual(mapconfig._virtual_key("scancode8"), ord("E"))
        self.assertEqual(mapconfig._virtual_key("mouse4"), None)


if __name__ == "__main__":
    unittest.main()
