import unittest
from unittest import mock

from cs2cfg.overlay import capture


class CaptureExclusion(unittest.TestCase):
    def _user32(self):
        user = mock.MagicMock()
        return user, mock.patch.object(capture.ctypes, "WinDLL", return_value=user)

    def test_real_handle_gets_exclude_from_capture(self):
        user, patch = self._user32()
        with patch:
            capture.set_capture_exclusion(1234, True)
            capture.set_capture_exclusion(1234, False)
        calls = user.SetWindowDisplayAffinity.call_args_list
        self.assertEqual(calls, [mock.call(1234, 0x11), mock.call(1234, 0)])

    def test_non_handles_never_reach_user32(self):
        user, patch = self._user32()
        with patch:
            for bad in (None, 0, -1, True, "12", mock.MagicMock()):
                capture.set_capture_exclusion(bad, True)
            capture.configure_panel(mock.MagicMock(), True)  # stand-in window
        user.SetWindowDisplayAffinity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
