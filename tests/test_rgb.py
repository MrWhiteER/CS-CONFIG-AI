"""Keyboard/mouse lighting that follows the keyboard tab, without real hardware.

Each lighting API is a local server, so each is tested against a small fake
of that server: the requests are the contract.
"""

import json
import socket
import struct
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from cs2cfg import profiles
from cs2cfg.rgb import chroma, gamesense, keymaps, openrgb, palette, sync
from cs2cfg.rgb.base import Provider

BOUND = {
    "scancode26": {"script": None, "enabled": True, "is_default": True},    # W: stock
    "scancode8": {"script": "Jumpthrow", "enabled": True},                  # E: script
    "scancode10": {"script": None, "is_default": False},                    # G: changed
    "scancode20": {"script": "Old", "enabled": False},                      # Q: disabled
    "mouse1": {"script": None, "is_default": True},
    "mwheelup": {"script": None, "is_default": False},
}

W, E, G, Q, SPACE = 26, 8, 10, 20, 44


class Palette(unittest.TestCase):
    def test_kind_mirrors_keyboard_tab(self):
        self.assertEqual(palette.kind(None), "free")
        self.assertEqual(palette.kind(BOUND["scancode8"]), "script")
        self.assertEqual(palette.kind(BOUND["scancode20"]), "script_off")
        self.assertEqual(palette.kind(BOUND["scancode10"]), "custom")
        self.assertEqual(palette.kind(BOUND["scancode26"]), "bound")
        # Unknown default (game not found) stays "bound", as on the board.
        self.assertEqual(palette.kind({"script": None}), "bound")

    def test_frame_colours_keys_and_mouse(self):
        f = palette.frame(BOUND)
        self.assertEqual(f.key(W), palette.COLOURS["bound"])
        self.assertEqual(f.key(E), palette.COLOURS["script"])
        self.assertEqual(f.key(G), palette.COLOURS["custom"])
        self.assertEqual(f.key(Q), palette.COLOURS["script_off"])
        self.assertEqual(f.key(SPACE), palette.COLOURS["free"])
        self.assertEqual(f.wheel, palette.COLOURS["custom"])
        self.assertEqual(f.body, palette.COLOURS["custom"])

    def test_named_keys_and_free_off_and_brightness(self):
        f = palette.frame({"space": {"script": "x", "enabled": True}}, free="off", brightness=50)
        self.assertEqual(f.key(SPACE), (128, 22, 74))
        self.assertEqual(f.key(W), palette.OFF)

    def test_louder_spelling_wins_for_one_key(self):
        f = palette.frame({"e": {"script": None, "is_default": True},
                           "scancode8": {"script": "s", "enabled": True}})
        self.assertEqual(f.key(E), palette.COLOURS["script"])


class Keymaps(unittest.TestCase):
    def test_razer_grid_positions_are_unique_and_in_range(self):
        cells = list(keymaps.RAZER.values())
        self.assertEqual(len(cells), len(set(cells)))
        for row, col in cells:
            self.assertLess(row, keymaps.RAZER_ROWS)
            self.assertLess(col, keymaps.RAZER_COLS)
        self.assertEqual(keymaps.RAZER[W], (2, 3))
        self.assertEqual(keymaps.RAZER[41], (0, 1))
        self.assertEqual(keymaps.RAZER[SPACE], (5, 7))

    def test_every_board_key_has_a_razer_cell(self):
        from cs2cfg import keys
        missing = [c for c, u in keys._CODES.items()
                   if u not in keymaps.RAZER and c != "MetaRight"]
        self.assertEqual(missing, [])

    def test_openrgb_names(self):
        self.assertEqual(keymaps.openrgb_usage("Key: Left Shift"), 225)
        self.assertEqual(keymaps.openrgb_usage("Key: W"), W)
        self.assertEqual(keymaps.openrgb_usage("Key: Number Pad 7"), 95)
        self.assertIsNone(keymaps.openrgb_usage("Logo"))
        self.assertTrue(keymaps.is_wheel("Scroll Wheel"))


class _Chroma(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *a):
        pass

    def _reply(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(n)) if n else None
        type(self).calls.append((self.command, self.path, data))

    def do_GET(self):
        self._record()
        self._reply({"core": "3.40.00", "version": "3.40.02"})

    def do_POST(self):
        self._record()
        port = self.server.server_address[1]
        self._reply({"sessionid": 1, "uri": f"http://127.0.0.1:{port}/chromasdk"})

    def do_PUT(self):
        self._record()
        self._reply({"result": 0})

    def do_DELETE(self):
        self._record()
        self._reply({"result": 0})


class Chroma(unittest.TestCase):
    def setUp(self):
        _Chroma.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Chroma)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        port = self.server.server_address[1]
        self.p = chroma.ChromaProvider(f"http://127.0.0.1:{port}/razer/chromasdk", settle=0)

    def test_session_paints_keeps_alive_and_hands_back(self):
        self.assertTrue(self.p.probe())
        self.p.start()
        self.p.apply(palette.frame(BOUND))
        self.p.keepalive()
        self.p.stop()
        verbs = [(c[0], c[1]) for c in _Chroma.calls]
        self.assertEqual(verbs, [
            ("GET", "/razer/chromasdk"), ("POST", "/razer/chromasdk"),
            ("PUT", "/chromasdk/keyboard"), ("PUT", "/chromasdk/mouse"),
            ("PUT", "/chromasdk/heartbeat"), ("DELETE", "/chromasdk")])
        self.assertEqual(_Chroma.calls[1][2]["category"], "application")
        kb = _Chroma.calls[2][2]
        self.assertEqual(kb["effect"], "CHROMA_CUSTOM")
        self.assertEqual(kb["param"][2][3], chroma.bgr(palette.COLOURS["bound"]))   # W
        self.assertEqual(kb["param"][2][4], chroma.bgr(palette.COLOURS["script"]))  # E
        mouse = _Chroma.calls[3][2]
        self.assertEqual(mouse["effect"], "CHROMA_CUSTOM2")
        self.assertEqual(len(mouse["param"]), 9)
        self.assertFalse(self.p.active)

    def test_bgr(self):
        self.assertEqual(chroma.bgr((0x11, 0x22, 0x33)), 0x332211)

    def test_probe_fails_quietly_without_synapse(self):
        p = chroma.ChromaProvider("http://127.0.0.1:9/razer/chromasdk")
        self.assertFalse(p.probe())
        self.assertIn("not running", p.why)


class GameSense(unittest.TestCase):
    def test_groups_cover_every_key_once(self):
        groups = gamesense.groups(palette.frame(BOUND))
        keys = [k for _c, ks in groups for k in ks]
        self.assertEqual(sorted(keys), sorted(gamesense.ALL_KEYS))
        self.assertLessEqual(len(groups), len(gamesense._EVENTS))

    def test_probe_without_gg(self):
        with tempfile.TemporaryDirectory() as tmp:
            props = Path(tmp) / "coreProps.json"
            props.write_text(json.dumps({"address": "127.0.0.1:9"}))
            p = gamesense.GameSenseProvider(props)
            self.assertFalse(p.probe())


def _text(s):
    raw = s.encode() + b"\0"
    return struct.pack("<H", len(raw)) + raw


def _controller_blob(kind, name, leds, colours, modes=("Wave", "Direct"), active=0):
    body = struct.pack("<i", kind) + _text(name)
    body += b"".join(_text(x) for x in ("desc", "1.0", "serial", "usb"))
    body += struct.pack("<H", len(modes)) + struct.pack("<i", active)
    for i, m in enumerate(modes):
        body += _text(m) + struct.pack("<i", i) + b"\0" * 32 + struct.pack("<H", 1) + b"\1\2\3\0"
    body += struct.pack("<H", 1) + _text("Keys") + b"\0" * 16 + struct.pack("<H", 0)
    body += struct.pack("<H", len(leds)) + b"".join(_text(l) + b"\0" * 4 for l in leds)
    body += struct.pack("<H", len(colours)) + b"".join(bytes((*c, 0)) for c in colours)
    return struct.pack("<I", 4 + len(body)) + body


class OpenRGB(unittest.TestCase):
    def test_parse_controller_keeps_active_mode_and_colours(self):
        blob = _controller_blob(5, "Corsair K70", ["Key: W", "Key: Space"], [(1, 2, 3), (4, 5, 6)])
        c = openrgb.parse_controller(0, blob)
        self.assertEqual(c.name, "Corsair K70")
        self.assertEqual(c.leds, ["Key: W", "Key: Space"])
        self.assertEqual(c.colours, [(1, 2, 3), (4, 5, 6)])
        self.assertTrue(c.mode_block.startswith(_text("Wave")))

    def test_paint(self):
        f = palette.frame(BOUND)
        kb = openrgb.Controller(0, 5, "kb", 0, b"", ["Key: W", "Key: E", "Logo"])
        self.assertEqual(openrgb.paint(kb, f), [f.key(W), f.key(E), f.base])
        mouse = openrgb.Controller(1, 6, "m", 0, b"", ["Scroll Wheel", "Logo"])
        self.assertEqual(openrgb.paint(mouse, f), [f.wheel, f.body])
        strip = openrgb.Controller(2, 4, "strip", 0, b"", ["LED 1"])
        self.assertIsNone(openrgb.paint(strip, f))

    def test_session_against_fake_server_skips_owned_vendor_and_restores(self):
        blobs = [_controller_blob(5, "Corsair K70", ["Key: W"], [(9, 9, 9)]),
                 _controller_blob(6, "Razer Cobra", ["Logo"], [(1, 1, 1)]),
                 _controller_blob(4, "Strip", ["LED"], [(0, 0, 0)])]
        got = []
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(2)
        self.addCleanup(srv.close)

        def serve():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                with conn:
                    while True:
                        head = b""
                        while len(head) < 16:
                            chunk = conn.recv(16 - len(head))
                            if not chunk:
                                break
                            head += chunk
                        if len(head) < 16:
                            break
                        dev, pkt, size = struct.unpack("<III", head[4:])
                        payload = b""
                        while len(payload) < size:
                            payload += conn.recv(size - len(payload))
                        got.append((dev, pkt, payload))
                        if pkt == openrgb.REQUEST_CONTROLLER_COUNT:
                            reply = struct.pack("<I", len(blobs))
                        elif pkt == openrgb.REQUEST_CONTROLLER_DATA:
                            reply = blobs[dev]
                        else:
                            continue
                        conn.sendall(b"ORGB" + struct.pack("<III", dev, pkt, len(reply)) + reply)

        threading.Thread(target=serve, daemon=True).start()
        p = openrgb.OpenRGBProvider(port=srv.getsockname()[1])
        p.skip_vendors = {"razer"}
        self.assertTrue(p.probe())
        p.start()
        self.assertEqual(p.devices, ["Corsair K70"])
        p.apply(palette.frame(BOUND))
        p.stop()
        for _ in range(50):
            if any(g[1] == openrgb.UPDATELEDS and g[2].endswith(bytes((9, 9, 9, 0))) for g in got):
                break
            time.sleep(0.02)
        packets = [(d, k) for d, k, _ in got if k not in (0, 1, 50)]
        self.assertEqual(packets, [(0, openrgb.SETCUSTOMMODE), (0, openrgb.UPDATELEDS),
                                   (0, openrgb.UPDATEMODE), (0, openrgb.UPDATELEDS)])
        painted = [g for g in got if g[1] == openrgb.UPDATELEDS][0][2]
        self.assertEqual(painted[6:9], bytes(palette.COLOURS["bound"]))   # W
        mode = [g for g in got if g[1] == openrgb.UPDATEMODE][0][2]
        self.assertEqual(struct.unpack("<i", mode[4:8])[0], 0)


class FakeProvider(Provider):
    id = name = "fake"
    vendors = ("fake",)

    def __init__(self, there=True):
        super().__init__()
        self.there, self.log = there, []

    def probe(self):
        return self.there

    def start(self):
        self.log.append("start")
        self.active = True

    def apply(self, frame):
        self.log.append(("apply", frame.key(E)))

    def keepalive(self):
        self.log.append("keepalive")

    def stop(self):
        self.log.append("stop")
        self.active = False


def _wait(cond, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Sync(unittest.TestCase):
    def setUp(self):
        self.fake = FakeProvider()
        self.missing = FakeProvider(there=False)
        self.s = sync.RgbSync(lambda: [self.fake, self.missing])
        self.addCleanup(self.s.stop)

    def test_off_by_default_and_inert(self):
        self.assertFalse(self.s.status()["enabled"])
        self.s.update(BOUND)
        self.assertIsNone(self.s._thread)
        self.assertEqual(self.fake.log, [])

    def test_waits_for_a_board_then_paints_and_hands_back(self):
        self.s.configure({"rgb_enabled": True})
        time.sleep(0.2)
        self.assertNotIn("start", self.fake.log)       # nothing to show yet
        self.s.update(BOUND)
        self.assertTrue(_wait(lambda: ("apply", palette.COLOURS["script"]) in self.fake.log))
        self.assertEqual(self.missing.log, [])
        self.s.configure({"rgb_enabled": False})
        self.assertEqual(self.fake.log[-1], "stop")
        self.assertFalse(self.s.status()["running"])

    def test_rebind_repaints(self):
        self.s.update(BOUND)
        self.s.configure({"rgb_enabled": True})
        self.assertTrue(_wait(lambda: any(isinstance(x, tuple) for x in self.fake.log)))
        changed = dict(BOUND, scancode8={"script": None, "is_default": True})
        self.s.update(changed)
        self.assertTrue(_wait(lambda: ("apply", palette.COLOURS["bound"]) in self.fake.log))

    def test_failing_provider_is_dropped_with_reason(self):
        self.fake.apply = mock.Mock(side_effect=OSError("unplugged"))
        self.s.update(BOUND)
        self.s.configure({"rgb_enabled": True})
        self.assertTrue(_wait(lambda: "unplugged" in self.fake.why))
        self.assertFalse(self.fake.active)

    def test_settings_validation(self):
        self.assertEqual(sync.read_settings({"rgb_free": "bogus"}), sync.DEFAULTS)
        with self.assertRaises(ValueError):
            sync.read_settings({"rgb_brightness": 101}, strict=True)
        with self.assertRaises(ValueError):
            sync.read_settings({"rgb_enabled": "yes"}, strict=True)

    def test_cache_written_only_while_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "rgb-board.json"
            s = sync.RgbSync(lambda: [], cache=cache)
            s.update(BOUND)
            self.assertFalse(cache.exists())
            s.configure({"rgb_enabled": True})
            s.stop()
            saved = json.loads(cache.read_text())
            self.assertEqual(saved["scancode8"], {"script": "Jumpthrow", "enabled": True})
            self.assertTrue(sync.RgbSync(lambda: [], cache=cache).status()["has_board"])


class Api(unittest.TestCase):
    def setUp(self):
        global webui
        from cs2cfg import webui   # Windows-only import chain

    def test_settings_are_machine_wide_and_applied(self):
        prefs = {"ui": {}, "accounts": {"one": {}}}
        rgb = mock.Mock()
        rgb.status.return_value = {"has_board": True, "enabled": True}
        state = types.SimpleNamespace(rgb=rgb)
        with (mock.patch("cs2cfg.cli.load_prefs", return_value=prefs),
              mock.patch("cs2cfg.cli.save_prefs") as save):
            out = webui._rgb_settings(state, {"rgb_enabled": True, "junk": 1})
        self.assertTrue(out["ok"])
        save.assert_called_once()
        self.assertTrue(prefs["ui"]["rgb_enabled"])
        self.assertNotIn("junk", prefs["ui"])
        rgb.configure.assert_called_once()
        self.assertTrue(profiles.is_machine("rgb_brightness"))

    def test_invalid_settings_rejected(self):
        rgb = mock.Mock()
        with (mock.patch("cs2cfg.cli.load_prefs", return_value={}),
              mock.patch("cs2cfg.cli.save_prefs") as save):
            out = webui._rgb_settings(types.SimpleNamespace(rgb=rgb), {"rgb_free": "rainbow"})
        self.assertFalse(out["ok"])
        save.assert_not_called()
        rgb.configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
