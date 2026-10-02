"""The sign-in panel's side of the cloud.

The browser half of a sign-in is a round trip through Steam or Google, and
these are the endpoints the page drives it with. The thing worth guarding is
what does *not* travel: the verifier is what proves this launcher started the
sign-in, and it stays on this side of the wire -- the page has no use for it
and the server holds it, so a sign-in cannot be claimed by anything that
merely saw the browser's address bar.

Nothing here reaches the network: the cloud client is stubbed throughout.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cloud, webui  # noqa: E402


def _state():
    return types.SimpleNamespace(refresh=lambda *a, **k: None)


class Status(unittest.TestCase):
    def test_it_never_raises_while_the_page_is_drawing(self):
        """A cloud that is down has to read as signed out rather than taking
        the panel with it."""
        with mock.patch.object(cloud, "status",
                               return_value={"configured": True, "signed_in": False,
                                             "error": "could not reach the cloud"}):
            out = webui._cloud(_state(), {})
        self.assertTrue(out["ok"])
        self.assertFalse(out["signed_in"])


class StartingASignIn(unittest.TestCase):
    def test_the_verifier_never_reaches_the_page(self):
        """The one thing in the exchange that must travel no further than it
        has to. The state goes through the browser's address bar; the verifier
        is what stops a copied URL being enough to take the session."""
        state = _state()
        started = {"state": "S", "verifier": "V", "url": "https://steam/login"}
        with mock.patch.object(cloud, "begin_login", return_value=started), \
             mock.patch.object(webui, "_open_in_default_browser", return_value=True):
            out = webui._cloud_login(state, {"provider": "steam"})
        self.assertTrue(out["ok"])
        self.assertNotIn("verifier", out)
        self.assertNotIn("state", out)
        # ...and it is held here instead, for the poll to use.
        self.assertEqual(state._login["verifier"], "V")

    def test_a_browser_that_will_not_open_hands_back_the_address(self):
        """Better than a dead end: the sign-in is still startable by hand."""
        started = {"state": "S", "verifier": "V", "url": "https://steam/login"}
        with mock.patch.object(cloud, "begin_login", return_value=started), \
             mock.patch.object(webui, "_open_in_default_browser", return_value=False):
            out = webui._cloud_login(_state(), {"provider": "steam"})
        self.assertTrue(out["ok"])
        self.assertFalse(out["opened"])
        self.assertEqual(out["url"], "https://steam/login")

    def test_a_refusal_is_reported_not_raised(self):
        with mock.patch.object(cloud, "begin_login",
                               side_effect=cloud.CloudError("no cloud server is configured")):
            out = webui._cloud_login(_state(), {"provider": "steam"})
        self.assertFalse(out["ok"])
        self.assertIn("configured", out["error"])


class WaitingOnTheBrowser(unittest.TestCase):
    def test_waiting_is_not_an_error(self):
        """The usual answer while somebody is still in the browser."""
        state = _state()
        state._login = {"state": "S", "verifier": "V"}
        with mock.patch.object(cloud, "claim_login", return_value={"waiting": True}):
            out = webui._cloud_poll(state, {})
        self.assertTrue(out["ok"])
        self.assertTrue(out["waiting"])
        self.assertIsNotNone(state._login, "the sign-in is still in progress")

    def test_a_finished_sign_in_clears_the_pending_one(self):
        state = _state()
        state._login = {"state": "S", "verifier": "V"}
        with mock.patch.object(cloud, "claim_login",
                               return_value={"waiting": False, "token": "t"}), \
             mock.patch.object(cloud, "forget_me") as fresh:
            out = webui._cloud_poll(state, {})
        self.assertFalse(out["waiting"])
        self.assertIsNone(state._login)
        fresh.assert_called_once()

    def test_polling_with_nothing_in_progress_says_so(self):
        """The page polls on a timer; it has to be able to stop."""
        out = webui._cloud_poll(_state(), {})
        self.assertTrue(out["nothing"])

    def test_a_failed_claim_does_not_leave_it_pending_forever(self):
        state = _state()
        state._login = {"state": "S", "verifier": "V"}
        with mock.patch.object(cloud, "claim_login",
                               side_effect=cloud.CloudError("that sign-in expired")):
            out = webui._cloud_poll(state, {})
        self.assertFalse(out["ok"])
        self.assertIsNone(state._login)

    def test_it_can_be_given_up_on(self):
        state = _state()
        state._login = {"state": "S", "verifier": "V"}
        webui._cloud_cancel(state, {})
        self.assertIsNone(state._login)


class WithAnAddressAndAPassword(unittest.TestCase):
    def _call(self, mode, fn):
        with mock.patch.object(cloud, fn, return_value={"ok": True, "token": "t"}) as called, \
             mock.patch.object(cloud, "forget_me"):
            out = webui._cloud_password(
                _state(), {"mode": mode, "email": " Me@Example.COM ", "password": "x" * 12})
        return out, called

    def test_signing_in(self):
        out, called = self._call("login", "sign_in")
        self.assertTrue(out["ok"])
        called.assert_called_once()

    def test_opening_an_account(self):
        out, called = self._call("register", "register")
        self.assertTrue(out["ok"])
        called.assert_called_once()

    def test_attaching_one_to_an_account_signed_in_another_way(self):
        out, called = self._call("link", "add_password")
        self.assertTrue(out["ok"])
        called.assert_called_once()

    def test_the_servers_own_wording_is_what_gets_shown(self):
        """A status code tells somebody nothing; the server knows what went
        wrong and said so."""
        with mock.patch.object(cloud, "sign_in",
                               side_effect=cloud.CloudError(
                                   "that email address and password do not match")):
            out = webui._cloud_password(_state(), {"email": "a@b.c", "password": "no"})
        self.assertFalse(out["ok"])
        self.assertIn("do not match", out["error"])


class SigningOut(unittest.TestCase):
    def test_it_drops_any_sign_in_still_in_progress(self):
        state = _state()
        state._login = {"state": "S", "verifier": "V"}
        with mock.patch.object(cloud, "sign_out", return_value={"ok": True}):
            webui._cloud_logout(state, {})
        self.assertIsNone(state._login)


class ThePanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cs2cfg import paths

        cls.page = (paths.bundle_root() / "web" / "index.html").read_text(
            encoding="utf-8", errors="replace")

    def test_it_has_its_own_place_rather_than_being_wedged_in(self):
        self.assertIn('data-sub="account"', self.page)
        self.assertIn('id="account-card"', self.page)

    def test_all_three_ways_in_are_offered(self):
        for way in ('cloudWay("steam"', 'cloudWay("google"', 'cloudWay("mail"'):
            self.assertIn(way, self.page)

    def test_an_unconfigured_build_says_so_rather_than_failing(self):
        self.assertIn("no cloud server set", self.page)

    def test_steam_is_shown_as_the_end_of_every_road(self):
        """An account without one is signed in but incomplete, and the panel
        has to say so rather than let somebody finish and wonder why nothing
        applies to them."""
        self.assertIn("needs_steam", self.page)
        self.assertIn("Attach Steam to finish", self.page)

    def test_the_browser_half_is_polled_not_waited_on(self):
        """So closing this window does not strand a sign-in half done."""
        self.assertIn("function watchCloudLogin()", self.page)
        self.assertIn('/api/cloud/poll', self.page)


if __name__ == "__main__":
    unittest.main()
