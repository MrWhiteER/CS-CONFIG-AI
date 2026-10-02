"""The cloud client: sessions, entitlements, and what must never ship.

The first class is the one that matters most. The launcher's source is public
and its bundle unpacks with a script anyone can download, so anything placed
in it is placed in public. These check that nothing secret ever is -- not by
reviewing the file, which is a thing people stop doing, but by failing the
build if a secret turns up in it.

No test here reaches the network: every request is a stub.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cs2cfg import cloud, cloudconfig  # noqa: E402


class NothingSecretIsShipped(unittest.TestCase):
    """The rule the whole design rests on."""

    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1]
                       / "cs2cfg" / "cloudconfig.py").read_text(encoding="utf-8")

    def test_there_is_no_admin_token_in_the_build(self):
        """It is read from the environment of the owner's own machine, so it
        exists on one computer and in no build of either edition."""
        self.assertIsNone(getattr(cloudconfig, "ADMIN_TOKEN", None))
        self.assertIn("environ", self.source)

    def test_no_google_client_secret_anywhere(self):
        """The client id is public and ships; the secret is the Worker's and
        never leaves it. Confusing the two is the mistake this catches."""
        self.assertFalse(hasattr(cloudconfig, "GOOGLE_CLIENT_SECRET"))
        lowered = self.source.lower()
        for phrase in ("client_secret", "clientsecret"):
            # Allowed in prose explaining why it is absent, never as a value.
            for line in lowered.splitlines():
                if phrase in line and "=" in line.split(phrase)[0] + phrase:
                    self.assertTrue(line.lstrip().startswith(("#", "*", '"')),
                                    f"a secret looks assigned here: {line.strip()}")

    def test_no_cloudflare_credentials(self):
        """R2 and D1 reach the Worker as bindings, not keys, so there is
        nothing of Cloudflare's to put here even by accident."""
        for word in ("R2_ACCESS", "SECRET_ACCESS_KEY", "CLOUDFLARE_API_TOKEN",
                     "ACCOUNT_ID"):
            self.assertNotIn(word, self.source)

    def test_the_owner_token_is_not_cached_to_disk(self):
        with mock.patch.dict("os.environ", {cloudconfig.ADMIN_TOKEN_ENV: "s3cret"}):
            self.assertEqual(cloudconfig.admin_token(), "s3cret")
            self.assertTrue(cloudconfig.is_owner())
        # Gone the moment it is out of the environment: nothing kept it.
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(cloudconfig.admin_token())
            self.assertFalse(cloudconfig.is_owner())

    def test_an_unconfigured_build_knows_it(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(cloudconfig, "BASE_URL",
                                   "https://x.example.workers.dev"):
                self.assertFalse(cloudconfig.configured())
            with mock.patch.object(cloudconfig, "BASE_URL", "https://cloud.real.dev"):
                self.assertTrue(cloudconfig.configured())


class _Answer(io.BytesIO):
    """Stands in for what urlopen hands back."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _replies(payload, status=200):
    """A urlopen that answers once with this payload."""
    if status >= 400:
        def raiser(request, timeout=None):
            raise urllib.error.HTTPError(
                "u", status, "no", {}, io.BytesIO(json.dumps(payload).encode()))
        return raiser
    return lambda request, timeout=None: _Answer(json.dumps(payload).encode())


class _Session(unittest.TestCase):
    """A throwaway data directory, so no real session is touched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(cloud, "token_path",
                                  return_value=Path(self.tmp.name) / "session.json")
        patch.start()
        self.addCleanup(patch.stop)
        cloud.forget_me()
        live = mock.patch.object(cloudconfig, "BASE_URL", "https://cloud.test")
        live.start()
        self.addCleanup(live.stop)


class TheSessionOnDisk(_Session):
    def test_it_keeps_a_token_and_reads_it_back(self):
        cloud.save_session({"token": "abc", "expires_at": 2 ** 40})
        self.assertTrue(cloud.signed_in())
        self.assertEqual(cloud.load_session()["token"], "abc")

    def test_an_expired_token_is_dropped_rather_than_sent(self):
        cloud.save_session({"token": "abc", "expires_at": 1})
        self.assertEqual(cloud.load_session(), {})
        self.assertFalse(cloud.token_path().exists(), "it should clean up after itself")

    def test_rubbish_on_disk_is_not_a_session(self):
        cloud.token_path().write_text("{ not json", encoding="utf-8")
        self.assertFalse(cloud.signed_in())

    def test_a_token_is_not_kept_in_the_preferences(self):
        """Preferences are the thing that gets synced to the cloud. A session
        token in there would be a session token uploaded to a server and handed
        back to every other machine on the account."""
        cloud.save_session({"token": "abc", "expires_at": 2 ** 40})
        self.assertNotEqual(cloud.token_path().name, "config.json")
        self.assertIn("session", cloud.token_path().name)

    def test_signing_out_forgets_it_even_when_the_server_cannot_be_told(self):
        cloud.save_session({"token": "abc", "expires_at": 2 ** 40})
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("down")):
            self.assertTrue(cloud.sign_out()["ok"])
        self.assertFalse(cloud.signed_in())


class ItNamesItself(_Session):
    """Cloudflare refuses "Python-urllib" with a 403 before the request ever
    reaches the Worker. That reads as the Worker rejecting the sign-in -- the
    body is empty and the Worker's own log shows nothing, because it was never
    asked. Found on a live deployment, where /auth/start returned 403 from
    this client and 200 from everything else."""

    def test_every_request_carries_a_user_agent(self):
        sent = {}

        def capture(request, timeout=None):
            sent.update({k.lower(): v for k, v in request.header_items()})
            return _Answer(b'{"ok":true}')

        with mock.patch.object(cloud.urllib.request, "urlopen", side_effect=capture):
            cloud._call("GET", "/health")
        self.assertIn("user-agent", sent)
        self.assertNotIn("python-urllib", sent["user-agent"].lower())

    def test_it_says_which_application_and_which_version(self):
        from cs2cfg import __version__

        self.assertIn("cs2-autoconfig", cloud._user_agent())
        self.assertIn(__version__, cloud._user_agent())


class SigningIn(_Session):
    def test_it_sends_a_hash_and_keeps_the_secret(self):
        """The state goes through the browser's address bar; the verifier
        never does. Sending the verifier up front would make a copied URL
        enough to take the session."""
        sent = {}

        def capture(request, timeout=None):
            sent["body"] = json.loads(request.data.decode())
            return _Answer(json.dumps(
                {"ok": True, "state": "S", "url": "https://steam/login"}).encode())

        with mock.patch.object(cloud.urllib.request, "urlopen", side_effect=capture):
            started = cloud.begin_login("steam")

        self.assertNotIn("verifier", sent["body"])
        self.assertRegex(sent["body"]["challenge"], r"^[0-9a-f]{64}$")
        import hashlib
        self.assertEqual(
            hashlib.sha256(started["verifier"].encode()).hexdigest(),
            sent["body"]["challenge"])

    def test_waiting_is_not_an_error(self):
        """The usual answer while somebody is still in the browser."""
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=_replies({"ok": True, "waiting": True})):
            self.assertTrue(cloud.claim_login("S", "V")["waiting"])
        self.assertFalse(cloud.signed_in())

    def test_a_claimed_session_is_saved(self):
        payload = {"ok": True, "waiting": False, "token": "tok",
                   "expires_at": 2 ** 40, "steam_id": "7656", "account_id": "a1"}
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=_replies(payload)):
            cloud.claim_login("S", "V")
        self.assertEqual(cloud.load_session()["token"], "tok")

    def test_an_unknown_provider_is_refused_before_any_request(self):
        with mock.patch.object(cloud.urllib.request, "urlopen") as called:
            with self.assertRaises(cloud.CloudError):
                cloud.begin_login("facebook")
        called.assert_not_called()

    def test_the_server_s_own_wording_is_what_gets_shown(self):
        """A status code tells somebody nothing; the server knows what went
        wrong."""
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=_replies(
                                   {"error": "that email address and password do not match"},
                                   status=401)):
            with self.assertRaises(cloud.CloudError) as caught:
                cloud.sign_in("a@b.c", "nope")
        self.assertIn("do not match", str(caught.exception))


class TheAccount(_Session):
    def test_a_session_the_server_has_forgotten_is_dropped_here_too(self):
        """Otherwise every call fails and the interface still says signed in."""
        cloud.save_session({"token": "stale", "expires_at": 2 ** 40})
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=_replies({"error": "sign in first"}, status=401)):
            with self.assertRaises(cloud.CloudError):
                cloud.me(refresh=True)
        self.assertFalse(cloud.signed_in())

    def test_status_never_raises(self):
        """It is called while drawing the page. A cloud that is down has to
        read as signed out, not take the interface with it."""
        cloud.save_session({"token": "t", "expires_at": 2 ** 40})
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("no route")):
            answer = cloud.status()
        self.assertIn("error", answer)
        self.assertTrue(answer["configured"])

    def test_steam_is_the_end_of_every_road(self):
        """Whichever way somebody came in, the account is incomplete until a
        Steam id is attached -- a CS2 configuration without one is a
        configuration for nobody."""
        cloud.save_session({"token": "t", "expires_at": 2 ** 40})
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=_replies({"ok": True, "steam_id": None,
                                                     "needs_steam": True,
                                                     "entitlements": ["sync"]})):
            self.assertTrue(cloud.me(refresh=True)["needs_steam"])


class Entitlements(_Session):
    def test_it_reads_the_plan_the_server_issued(self):
        cloud.save_session({"token": "t", "expires_at": 2 ** 40})
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=_replies({"ok": True, "tier": "pro",
                                                     "entitlements": ["configure", "sync"]})):
            cloud.me(refresh=True)
            self.assertTrue(cloud.entitled("sync"))
            self.assertFalse(cloud.entitled("demos"))

    def test_it_fails_open_when_the_cloud_cannot_be_reached(self):
        """Somebody who paid and then lost their connection keeps what they
        paid for. An application that stops working on a train is worse than
        one that is occasionally generous, and the enforcement that counts is
        the server refusing to do the work."""
        cloud.save_session({"token": "t", "expires_at": 2 ** 40})
        cloud.forget_me()
        with mock.patch.object(cloud.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("down")):
            self.assertTrue(cloud.entitled("sync"))

    def test_an_unconfigured_build_gates_nothing(self):
        with mock.patch.object(cloudconfig, "BASE_URL",
                               "https://x.example.workers.dev"):
            self.assertTrue(cloud.entitled("anything at all"))


if __name__ == "__main__":
    unittest.main()
