import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cs2cfg import launcher_media, webui


class LauncherMedia(unittest.TestCase):
    def test_screenshot_selection_and_serving_over_local_server(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "gameplay.png"
            source.write_bytes(b"0123456789")
            agents = root / "launcher-agents"
            agents.mkdir()
            (agents / "ct.png").write_bytes(b"unspecified agent")
            state = SimpleNamespace(token="app-token", scene_token="media-ticket")
            with mock.patch.object(launcher_media, "user_data_dir", return_value=root), \
                 mock.patch("cs2cfg.picker.pick_gameplay_screenshot", return_value=str(source)), \
                 ThreadingHTTPServer(("127.0.0.1", 0), webui.make_handler(state)) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    setup = Request(base + "/api/launcher/media", data=b'{"choose":true}',
                                    headers={"X-CS2CFG-Token": state.token})
                    with urlopen(setup, timeout=3) as response:
                        media = json.load(response)
                    self.assertEqual(media["screenshot"], source.name)
                    self.assertEqual(media["agents"], {})
                    (agents / "ct-default.png").write_bytes(b"stock CT sheet")
                    with urlopen(base + "/launcher-agent/ct?ticket=" + state.scene_token, timeout=3) as response:
                        self.assertEqual(response.read(), b"stock CT sheet")
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(base + "/launcher-screenshot", timeout=3)
                    self.assertEqual(denied.exception.code, 403)
                    denied.exception.close()
                    with urlopen(base + media["url"], timeout=3) as response:
                        self.assertEqual(response.headers["Content-Type"], "image/png")
                        self.assertEqual(response.read(), b"0123456789")
                    clear = Request(base + "/api/launcher/media", data=b'{"clear":true}',
                                    headers={"X-CS2CFG-Token": state.token})
                    with urlopen(clear, timeout=3) as response:
                        self.assertEqual(json.load(response)["url"], "")
                    self.assertIsNone(launcher_media.screenshot())
                finally:
                    server.shutdown()
                    worker.join()
