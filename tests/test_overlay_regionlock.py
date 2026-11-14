"""Optional server adapter, driven with a fake module and manual clock."""

import builtins
import importlib
import unittest
from unittest import mock

from cs2cfg.overlay import regionlock


class RegionAdapter(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.module = mock.Mock()
        self.module.list_regions.return_value = [{"code": "dxb", "city": "Dubai", "country": "AE",
                                                   "ping_ms": 12, "loss": 0, "status": "ok"}]
        self.module.lock_status.return_value = {"busy": False, "firewall": {"status": "unlocked"}}
        self.adapter = regionlock.RegionLock(self.module, lambda: self.now)

    def test_missing_is_only_coming_soon_and_inert(self):
        adapter = regionlock.RegionLock(None)
        expected = {"available": False, "text": "Coming soon"}
        self.assertEqual(adapter.snapshot(), expected)
        self.assertEqual(adapter.open(), expected)
        self.assertEqual(adapter.poll(), expected)
        adapter.close()
        with self.assertRaises(ValueError):
            adapter.request("dxb")

    def test_import_error_is_guarded(self):
        real_import = builtins.__import__

        def missing(name, globals=None, locals=None, fromlist=(), level=0):
            if fromlist and "serverlock" in fromlist:
                raise ImportError("optional module absent")
            return real_import(name, globals, locals, fromlist, level)

        try:
            with mock.patch.object(builtins, "__import__", side_effect=missing):
                importlib.reload(regionlock)
                self.assertEqual(regionlock.RegionLock().open()["text"], "Coming soon")
        finally:
            importlib.reload(regionlock)

    def test_each_display_state(self):
        cases = [({"firewall": {"status": "locked", "city": "Dubai"}}, "Locked to Dubai"),
                 ({"pending": True}, "Applies after you quit CS2"),
                 ({"needs_setup": True}, "Finish setup in the app to enable server region lock"),
                 ({"restart_needed": True}, "Restart CS2 to apply the region change"),
                 ({"error": "Could not update"}, "Could not update"),
                 ({"busy": True}, "Updating region lock…"), ({}, "No region lock")]
        for status, expected in cases:
            with self.subTest(status=status):
                self.module.lock_status.return_value = status
                self.assertEqual(self.adapter.open()["text"], expected)

    def test_multiple_notices_are_preserved(self):
        self.assertEqual(regionlock.display({"pending": True, "restart_needed": True, "error": "Oops"}),
                         "Applies after you quit CS2. Restart CS2 to apply the region change. Oops")

    def test_construct_and_hidden_poll_never_call_module(self):
        self.adapter.snapshot()
        for _ in range(3):
            self.adapter.poll()
        self.assertEqual(self.module.mock_calls, [])

    def test_poll_only_busy_once_per_second_then_stops(self):
        self.module.lock_status.return_value = {"busy": True}
        self.assertTrue(self.adapter.open()["poll"])
        for offset in (0, .1, .5, .99):
            self.now = 10 + offset
            self.adapter.poll()
        self.module.lock_status.assert_called_once()
        self.now = 11
        self.module.lock_status.return_value = {"busy": False}
        self.assertFalse(self.adapter.poll()["poll"])
        self.now = 20
        self.adapter.poll()
        self.assertEqual(self.module.lock_status.call_count, 2)

    def test_hide_cancels_busy_poll_and_reopen_refreshes(self):
        self.module.lock_status.return_value = {"busy": True}
        self.adapter.open()
        self.adapter.close()
        self.now = 12
        self.assertFalse(self.adapter.poll()["poll"])
        self.module.lock_status.assert_called_once()
        self.adapter.open()
        self.assertEqual(self.module.lock_status.call_count, 2)

    def test_async_lock_and_unlock_wait_for_later_poll(self):
        for code in ("dxb", None):
            with self.subTest(code=code):
                self.adapter.open()
                self.module.reset_mock()
                result = self.adapter.request(code)
                self.assertTrue(result["poll"])
                self.module.lock_status.assert_not_called()
                operation = self.module.request_unlock if code is None else self.module.request_lock
                operation.assert_called_once_with(*(() if code is None else (code,)))
                self.now += 1
                self.assertFalse(self.adapter.poll()["poll"])

    def test_hidden_invalid_and_duplicate_requests_are_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter.request("dxb")
        self.adapter.open()
        with self.assertRaises(ValueError):
            self.adapter.request("unknown")
        self.adapter.request("dxb")
        with self.assertRaises(ValueError):
            self.adapter.request()
        self.module.request_lock.assert_called_once_with("dxb")
        self.module.request_unlock.assert_not_called()

    def test_status_and_operation_errors_display_without_polling(self):
        self.module.lock_status.side_effect = RuntimeError("status unavailable")
        result = self.adapter.open()
        self.assertIn("status unavailable", result["text"])
        self.assertFalse(result["poll"])
        self.module.request_lock.side_effect = RuntimeError("request failed")
        result = self.adapter.request("dxb")
        self.assertEqual(result["text"], "request failed")
        self.assertFalse(result["poll"])

    def test_snapshots_are_detached(self):
        result = self.adapter.open()
        result["regions"][0]["city"] = "Changed"
        result["status"]["busy"] = True
        self.assertEqual(self.adapter.snapshot()["regions"][0]["city"], "Dubai")
        self.assertFalse(self.adapter.snapshot()["status"]["busy"])
