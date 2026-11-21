"""Mouse speed and polling rate, set straight on a (fake) Razer mouse."""

import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from cs2cfg import autosync, profiles
from cs2cfg.mouse import control, razer
from cs2cfg.rgb.razer_usb import REPORT_LEN
from cs2cfg.rgb.winhid import HidInfo


class FakeMouse:
    """Answers Razer reports like a mouse with a speed and a polling rate.

    ``new_poll`` picks which polling command it understands; ``asleep``
    makes it answer nothing, like a wireless mouse that is asleep.
    """

    def __init__(self, infos, dpi=800, poll=1000, new_poll=True, asleep=False):
        self.infos, self.dpi, self.poll = infos, dpi, poll
        self.new_poll, self.asleep = new_poll, asleep
        self.sent, self.answer = [], bytes(REPORT_LEN)
        outer = self

        class Handle:
            def __init__(self, path):
                self.path = path

            def set_feature(self, data):
                outer.sent.append((self.path, bytes(data[1:])))
                outer.answer = outer._answer(bytes(data[1:]))

            def get_feature(self, length, report_id=0):
                return b"\0" + outer.answer

            def close(self):
                pass

        self.Handle = Handle

    def devices(self, vendor_id=None):
        return [i for i in self.infos if vendor_id in (None, i.vendor_id)]

    def _answer(self, r):
        out = bytearray(r)
        if self.asleep:
            out[0] = razer.TIMEOUT
            return bytes(out)
        cls, cmd, args = r[6], r[7], r[8:]
        out[0] = razer.OK
        if (cls, cmd) == (0x04, 0x05):
            self.dpi = (args[1] << 8) | args[2]
        elif (cls, cmd) == (0x04, 0x85):
            out[9:13] = bytes((self.dpi >> 8, self.dpi & 0xFF, self.dpi >> 8, self.dpi & 0xFF))
        elif (cls, cmd) in ((0x00, 0x40), (0x00, 0xC0)) and not self.new_poll:
            out[0] = razer.UNSUPPORTED
        elif (cls, cmd) == (0x00, 0x40):
            self.poll = razer.POLL_NEW[args[1]]
        elif (cls, cmd) == (0x00, 0xC0):
            out[9] = {v: k for k, v in razer.POLL_NEW.items()}[self.poll]
        elif (cls, cmd) == (0x00, 0x05):
            self.poll = razer.POLL_OLD[args[0]]
        elif (cls, cmd) == (0x00, 0x85):
            out[8] = {v: k for k, v in razer.POLL_OLD.items()}[self.poll]
        else:
            out[0] = razer.UNSUPPORTED
        return bytes(out)


def cobra(**kw):
    return FakeMouse([
        HidInfo("kb-ctrl", 0x1532, 0x02A6, 1, 6, 91),        # keyboard: never touched
        HidInfo("cobra-input", 0x1532, 0x00DB, 1, 2, 0),     # no feature report
        HidInfo("cobra-ctrl", 0x1532, 0x00DB, 1, 2, 91),
    ], **kw)


class Reports(unittest.TestCase):
    def test_speed_report(self):
        r = razer.dpi_report(1600)
        self.assertEqual(len(r), 90)
        self.assertEqual((r[5], r[6], r[7]), (7, 0x04, 0x05))
        self.assertEqual(r[8:15], bytes((razer.STORE, 0x06, 0x40, 0x06, 0x40, 0, 0)))

    def test_polling_reports(self):
        self.assertEqual(razer.poll_report(500, False)[6:9], bytes((0x00, 0x05, 0x02)))
        self.assertEqual(razer.poll_report(1000, True)[6:10], bytes((0x00, 0x40, 0x00, 0x08)))


class RazerMouse(unittest.TestCase):
    def test_reads_what_the_mouse_uses(self):
        fake = cobra(dpi=1200, poll=500)
        [m] = razer.Razer(fake).find()
        self.assertEqual((m.name, m.connection, m.dpi, m.poll), ("Razer Cobra HyperSpeed", "wireless", 1200, 500))
        self.assertEqual(m.rates, (125, 500, 1000))
        self.assertEqual(m.problem, "")
        self.assertEqual({p for p, _ in fake.sent}, {"cobra-ctrl"})

    def test_sets_speed_and_rate_and_reads_back(self):
        fake = cobra()
        m = razer.Razer(fake).set("razer-00db", dpi=1600, poll=500)
        self.assertEqual((fake.dpi, fake.poll), (1600, 500))
        self.assertEqual((m.dpi, m.poll), (1600, 500))

    def test_older_polling_command(self):
        fake = cobra(new_poll=False)
        m = razer.Razer(fake).set("razer-00db", poll=125)
        self.assertEqual((fake.poll, m.poll, m.rates), (125, 125, (125, 500, 1000)))

    def test_speed_capped_at_the_mouse_limit(self):
        fake = cobra()
        razer.Razer(fake).set("razer-00db", dpi=90000)
        self.assertEqual(fake.dpi, 26000)

    def test_asleep_says_so_in_plain_words(self):
        m = razer.Razer(cobra(asleep=True)).set("razer-00db", dpi=800)
        self.assertEqual(m.problem, razer.ASLEEP)

    def test_cable_and_receiver_are_one_mouse(self):
        fake = FakeMouse([HidInfo("rx", 0x1532, 0x00DB, 1, 2, 91),
                          HidInfo("cable", 0x1532, 0x00DA, 1, 2, 91)])
        [m] = razer.Razer(fake).find()
        self.assertEqual(m.connection, "cable")

    def test_unknown_razer_keyboard_is_not_a_mouse(self):
        fake = FakeMouse([HidInfo("kb", 0x1532, 0x0999, 1, 6, 91)])
        self.assertEqual(razer.Razer(fake).find(), [])


class Control(unittest.TestCase):
    def test_settings_validation(self):
        self.assertEqual(control.read_settings({}), {"mouse_dpi": 0, "mouse_poll": 0})
        self.assertEqual(control.read_settings({"mouse_dpi": 1600, "mouse_poll": 500}),
                         {"mouse_dpi": 1600, "mouse_poll": 500})
        with self.assertRaises(ValueError):
            control.read_settings({"mouse_poll": 333}, strict=True)
        with self.assertRaises(ValueError):
            control.read_settings({"mouse_dpi": True}, strict=True)

    def test_zero_leaves_the_mouse_alone(self):
        fake = cobra(dpi=1200)
        c = control.MouseControl(lambda: [razer.Razer(fake)])
        c.apply({"mouse_dpi": 0, "mouse_poll": 0})
        self.assertFalse([r for _p, r in fake.sent if r[7] in (0x05, 0x40)])
        self.assertEqual(fake.dpi, 1200)

    def test_apply_later_retries_until_the_mouse_wakes(self):
        fake = cobra(asleep=True)
        c = control.MouseControl(lambda: [razer.Razer(fake)])
        c.retry_every = 0.01
        done = threading.Event()
        real = c.apply

        def apply(settings):
            out = real(settings)
            if fake.dpi == 3200:
                done.set()
            fake.asleep = False          # wakes after the first try
            return out
        c.apply = apply
        c.apply_later({"mouse_dpi": 3200, "mouse_poll": 0})
        self.assertTrue(done.wait(5))


class Api(unittest.TestCase):
    def setUp(self):
        global webui
        from cs2cfg import webui   # Windows-only import chain

    def test_saves_and_sends_only_what_was_picked(self):
        prefs = {"ui": {"mouse_dpi": 800}, "accounts": {"one": {}}}
        fake = cobra(dpi=800, poll=1000)
        state = types.SimpleNamespace(mouse=control.MouseControl(lambda: [razer.Razer(fake)]))
        with (mock.patch("cs2cfg.cli.load_prefs", return_value=prefs),
              mock.patch("cs2cfg.cli.save_prefs") as save):
            fake.dpi = 1600              # changed with the button on the mouse
            out = webui._mouse_settings(state, {"mouse_poll": 500, "junk": 1})
        self.assertTrue(out["ok"])
        save.assert_called_once()
        self.assertEqual(prefs["ui"], {"mouse_dpi": 800, "mouse_poll": 500})
        self.assertEqual((fake.dpi, fake.poll), (1600, 500))
        self.assertEqual(out["mice"][0]["poll"], 500)

    def test_invalid_rejected(self):
        with (mock.patch("cs2cfg.cli.load_prefs", return_value={}),
              mock.patch("cs2cfg.cli.save_prefs") as save):
            out = webui._mouse_settings(types.SimpleNamespace(mouse=None), {"mouse_poll": 333})
        self.assertFalse(out["ok"])
        save.assert_not_called()


class SyncAndPage(unittest.TestCase):
    def test_follows_the_player_to_a_new_pc(self):
        for key in ("mouse_dpi", "mouse_poll"):
            self.assertIn(key, autosync.SYNCED_PREFS)
            self.assertTrue(profiles.is_machine(key))

    def test_mouse_tab(self):
        page = (Path(__file__).resolve().parents[1] / "cs2cfg" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-sub="mouse" role="tab"', page)
        self.assertIn('id="mouse-out"', page)
        self.assertIn('if (name === "mouse") loadMouse();', page)


if __name__ == "__main__":
    unittest.main()
