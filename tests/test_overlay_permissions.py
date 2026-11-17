"""Permission checks and wizard hints never request or change permissions."""

import builtins
import sys
import types
import unittest
from unittest import mock

from cs2cfg.overlay import permissions


class FrameCapturePermissions(unittest.TestCase):
    def test_elevated_admin_token_is_ready(self):
        with mock.patch.object(permissions, "_token_has_sid", return_value=True) as check:
            self.assertTrue(permissions.frame_capture_ready())
        check.assert_called_once_with("S-1-5-32-544")

    def test_performance_group_token_is_ready(self):
        with mock.patch.object(permissions, "_token_has_sid", side_effect=[False, True]) as check:
            self.assertTrue(permissions.frame_capture_ready())
        self.assertEqual(check.call_args_list, [mock.call("S-1-5-32-544"), mock.call("S-1-5-32-559")])

    def test_token_without_enabled_membership_is_not_ready(self):
        with mock.patch.object(permissions, "_token_has_sid", return_value=False):
            self.assertFalse(permissions.frame_capture_ready())

    def test_ctypes_membership_uses_sid_and_frees_it_even_if_check_fails(self):
        for succeeded, member, expected in ((True, True, True), (True, False, False),
                                             (False, True, False)):
            with self.subTest(succeeded=succeeded, member=member):
                security, kernel = mock.Mock(), mock.Mock()

                def convert(sid, pointer):
                    pointer._obj.value = 123
                    return True

                def check(token, sid, pointer):
                    self.assertIsNone(token)
                    self.assertEqual(sid.value, 123)
                    pointer._obj.value = member
                    return succeeded

                security.ConvertStringSidToSidW.side_effect = convert
                security.CheckTokenMembership.side_effect = check
                with mock.patch.object(permissions.ctypes, "WinDLL", side_effect=[security, kernel],
                                       create=True):
                    self.assertEqual(permissions._token_has_sid("S-1-5-32-559"), expected)
                self.assertEqual(security.ConvertStringSidToSidW.call_args.args[0], "S-1-5-32-559")
                kernel.LocalFree.assert_called_once()
                self.assertEqual(kernel.LocalFree.call_args.args[0].value, 123)

    def test_unavailable_token_api_is_not_ready(self):
        with mock.patch.object(permissions.ctypes, "WinDLL", side_effect=OSError, create=True):
            self.assertFalse(permissions.frame_capture_ready())

    def test_request_is_inert_and_owned_by_setup(self):
        with (mock.patch.object(permissions.ctypes, "WinDLL", create=True) as native,
              mock.patch.object(builtins, "__import__") as imports):
            self.assertEqual(permissions.request_frame_capture(), "handled by setup wizard")
        native.assert_not_called()
        imports.assert_not_called()


class SetupHints(unittest.TestCase):
    def helper(self, installed):
        helper = types.ModuleType("cs2cfg.elevated")
        helper.ready, helper.run = mock.Mock(return_value=installed), mock.Mock()
        return helper

    def test_missing_helper_import_points_to_setup(self):
        real_import = builtins.__import__

        def without_helper(name, globals=None, locals=None, fromlist=(), level=0):
            if fromlist and "elevated" in fromlist:
                raise ImportError("setup helper is on another branch")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch.object(builtins, "__import__", side_effect=without_helper):
            self.assertEqual(permissions.frame_capture_hint(ready=False), permissions.SETUP_HINT)

    def test_helper_not_installed_points_to_setup_even_after_dismissal(self):
        helper = self.helper(False)
        with (mock.patch.dict(sys.modules, {"cs2cfg.elevated": helper}),
              mock.patch("cs2cfg.elevated", helper, create=True)):
            hint = permissions.frame_capture_hint({permissions.DISMISSED_KEY: True}, ready=False)
        self.assertEqual(hint, permissions.SETUP_HINT)
        helper.ready.assert_called_once_with()
        helper.run.assert_not_called()

    def test_installed_helper_shows_sign_out_until_dismissed(self):
        helper = self.helper(True)
        with (mock.patch.dict(sys.modules, {"cs2cfg.elevated": helper}),
              mock.patch("cs2cfg.elevated", helper, create=True)):
            self.assertEqual(permissions.frame_capture_hint(ready=False), permissions.SIGN_OUT_HINT)
            for _ in range(2):
                self.assertEqual(permissions.frame_capture_hint(
                    {permissions.DISMISSED_KEY: True}, ready=False), "")
        helper.run.assert_not_called()

    def test_ready_capture_has_no_hint_and_does_not_query_helper(self):
        helper = self.helper(True)
        with (mock.patch.dict(sys.modules, {"cs2cfg.elevated": helper}),
              mock.patch("cs2cfg.elevated", helper, create=True),
              mock.patch.object(permissions, "frame_capture_ready", return_value=True)):
            self.assertEqual(permissions.frame_capture_hint(), "")
        helper.ready.assert_not_called()
        helper.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
