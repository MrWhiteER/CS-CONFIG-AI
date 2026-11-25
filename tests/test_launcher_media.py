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
    def test_selection_and_seek_over_local_server(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "recording.webm"
            source.write_bytes(b"0123456789")
            state = SimpleNamespace(token="app-token", clip_token="media-ticket")
            with mock.patch.object(launcher_media, "user_data_dir", return_value=root), \
                 mock.patch("cs2cfg.picker.pick_gameplay_clip", return_value=str(source)), \
                 ThreadingHTTPServer(("127.0.0.1", 0), webui.make_handler(state)) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    setup = Request(base + "/api/launcher/media", data=b'{"choose":true}',
                                    headers={"X-CS2CFG-Token": state.token})
                    with urlopen(setup, timeout=3) as response:
                        media = json.load(response)
                    self.assertEqual(media["clip"], source.name)
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(base + "/launcher-clip", timeout=3)
                    self.assertEqual(denied.exception.code, 403)
                    denied.exception.close()
                    seek = Request(base + media["url"], headers={"Range": "bytes=2-4"})
                    with urlopen(seek, timeout=3) as response:
                        self.assertEqual(response.status, 206)
                        self.assertEqual(response.headers["Content-Range"], "bytes 2-4/10")
                        self.assertEqual(response.read(), b"234")
                    suffix = Request(base + media["url"], headers={"Range": "bytes=-2"})
                    with urlopen(suffix, timeout=3) as response:
                        self.assertEqual(response.read(), b"89")
                    with self.assertRaises(HTTPError) as invalid:
                        urlopen(Request(base + media["url"], headers={"Range": "bytes=11-"}), timeout=3)
                    self.assertEqual(invalid.exception.code, 416)
                    invalid.exception.close()
                    launcher_media.choose(None)
                    self.assertIsNone(launcher_media.clip())
                finally:
                    server.shutdown()
                    worker.join()
