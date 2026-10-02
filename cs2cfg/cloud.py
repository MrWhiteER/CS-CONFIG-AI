"""Talking to the cloud: signing in, the plan, and settings that follow you.

Standard library only, like the rest of this project -- ``urllib.request`` is
what every other outward call here already uses.

The session token is the one thing worth being careful with on this side. It
is written to the user's own data directory with no other copy, kept out of
the preferences file deliberately (preferences are the thing that gets synced,
and a token is not a preference), and sent only to the one host it came from.

What this will not do is pretend to be offline-proof. Every call has a short
timeout and returns a plain answer rather than raising, because a launcher
that will not start a game because a web request was slow is a worse launcher
than one that quietly carries on without the cloud.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from . import cloudconfig

TIMEOUT = 12.0
TOKEN_FILE = "session.json"


def _user_agent() -> str:
    """Something that is not "Python-urllib".

    Cloudflare refuses the default with a 403 before the request reaches the
    Worker at all, which reads as the Worker rejecting the sign-in -- there is
    nothing in the body to say otherwise, and the Worker's own log shows
    nothing, because it was never asked. The same trap as the FACEIT calls in
    demos.py, and for the same reason: an application that does not name
    itself looks like something that does not want to be named.
    """
    from . import __version__

    return f"cs2-autoconfig/{__version__} (+https://github.com/MrWhiteER/CS-CONFIG-AI)"

# How long the launcher waits for somebody to finish in the browser, and how
# often it asks. Matched to the Worker's own window so the two agree about
# when a sign-in has gone stale.
LOGIN_WINDOW = 15 * 60
POLL_SECONDS = 2.0


class CloudError(RuntimeError):
    """A request did not work, with a message fit to show somebody."""


# --- the token on disk ------------------------------------------------------

def token_path() -> Path:
    from .paths import user_data_dir

    return user_data_dir() / TOKEN_FILE


def load_session() -> Dict[str, Any]:
    try:
        held = json.loads(token_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(held, dict) or not held.get("token"):
        return {}
    # An expired token is worth forgetting rather than sending.
    if held.get("expires_at") and float(held["expires_at"]) <= time.time():
        forget_session()
        return {}
    return held


def save_session(payload: Dict[str, Any]) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    # Readable by this account only, where the platform offers that. Best
    # effort: a failure here is not a reason to refuse to sign somebody in.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def forget_session() -> None:
    try:
        token_path().unlink()
    except OSError:
        pass


def signed_in() -> bool:
    return bool(load_session().get("token"))


# --- requests ---------------------------------------------------------------

def _call(method: str, path: str, body: Optional[Dict[str, Any]] = None,
          token: Optional[str] = None, timeout: float = TIMEOUT) -> Dict[str, Any]:
    """One request to the Worker. Raises CloudError with something readable."""
    if not cloudconfig.configured():
        raise CloudError("no cloud server is configured in this build")

    url = f"{cloudconfig.base_url()}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("accept", "application/json")
    request.add_header("user-agent", _user_agent())
    if data is not None:
        request.add_header("content-type", "application/json")
    if token:
        request.add_header("authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            raw = answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        try:
            said = json.loads(raw).get("error")
        except ValueError:
            said = None
        # The server's own wording where there is one: it knows what went
        # wrong and a status code does not.
        raise CloudError(said or f"the server said {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CloudError(f"could not reach the cloud: {exc.reason}") from exc
    except OSError as exc:
        raise CloudError(f"could not reach the cloud: {exc}") from exc

    try:
        return json.loads(raw)
    except ValueError as exc:
        raise CloudError("the cloud sent something that was not JSON") from exc


def _authed(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    session = load_session()
    if not session.get("token"):
        raise CloudError("sign in first")
    try:
        return _call(method, path, body, token=session["token"])
    except CloudError as exc:
        # A session the server no longer knows is a session worth dropping, so
        # the interface shows "signed out" rather than failing every call.
        if "sign in first" in str(exc):
            forget_session()
        raise


# --- signing in -------------------------------------------------------------

def _verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def begin_login(provider: str = "steam", link: bool = False) -> Dict[str, Any]:
    """Start a browser sign-in. Returns the state and verifier to finish with.

    ``link`` attaches the provider to the account already signed in, instead
    of signing a new one in. The browser half is identical; only the Worker
    route differs.
    """
    if provider not in ("steam", "google"):
        raise CloudError("provider must be steam or google")

    verifier = _verifier()
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    body = {"provider": provider, "challenge": challenge}

    if link:
        started = _authed("POST", "/auth/link/start", body)
    else:
        started = _call("POST", "/auth/start", body)

    if not started.get("url"):
        raise CloudError(started.get("error") or "the cloud did not offer a sign-in page")
    return {"state": started["state"], "verifier": verifier,
            "url": started["url"], "provider": provider, "link": link}


def claim_login(state: str, verifier: str) -> Dict[str, Any]:
    """Ask once whether the browser half is finished.

    ``{"waiting": True}`` means it is not, which is the usual answer and not
    an error: the person is still in the browser.
    """
    answer = _call("POST", "/auth/claim", {"state": state, "verifier": verifier})
    if answer.get("waiting"):
        return {"waiting": True}

    # A link keeps the session it was started from; a sign-in brings a new one.
    if answer.get("token"):
        save_session({
            "token": answer["token"],
            "expires_at": answer.get("expires_at"),
            "account_id": answer.get("account_id"),
            "steam_id": answer.get("steam_id"),
        })
    return {"waiting": False, **answer}


def wait_for_login(state: str, verifier: str, window: float = LOGIN_WINDOW,
                   should_stop=None) -> Dict[str, Any]:
    """Poll until the browser half finishes, or the window closes.

    Only used by the command line. The interface polls from the page instead,
    so that closing the window does not strand a sign-in half done.
    """
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            raise CloudError("sign-in stopped")
        answer = claim_login(state, verifier)
        if not answer.get("waiting"):
            return answer
        time.sleep(POLL_SECONDS)
    raise CloudError("the sign-in was not finished in time")


def register(email: str, password: str) -> Dict[str, Any]:
    answer = _call("POST", "/auth/password/register",
                   {"email": email, "password": password})
    if answer.get("token"):
        save_session({"token": answer["token"], "expires_at": answer.get("expires_at"),
                      "account_id": answer.get("account_id"),
                      "steam_id": answer.get("steam_id")})
    return answer


def sign_in(email: str, password: str) -> Dict[str, Any]:
    answer = _call("POST", "/auth/password/login",
                   {"email": email, "password": password})
    if answer.get("token"):
        save_session({"token": answer["token"], "expires_at": answer.get("expires_at"),
                      "account_id": answer.get("account_id"),
                      "steam_id": answer.get("steam_id")})
    return answer


def add_password(email: str, password: str) -> Dict[str, Any]:
    return _authed("POST", "/auth/link/password", {"email": email, "password": password})


def sign_out() -> Dict[str, Any]:
    try:
        return _authed("POST", "/auth/logout")
    except CloudError:
        # Being unable to tell the server is no reason to stay signed in here.
        return {"ok": True}
    finally:
        forget_session()


# --- the account ------------------------------------------------------------

_SEEN: Dict[str, Any] = {"at": 0.0, "me": None}
ME_TTL = 60.0


def me(refresh: bool = False) -> Dict[str, Any]:
    """Who is signed in, what plan, and what is still missing.

    Cached briefly. The page asks on every render and the answer changes about
    as often as somebody changes plan.
    """
    if not refresh and _SEEN["me"] and time.monotonic() - _SEEN["at"] < ME_TTL:
        return _SEEN["me"]
    answer = _authed("GET", "/me")
    _SEEN["at"], _SEEN["me"] = time.monotonic(), answer
    return answer


def forget_me() -> None:
    _SEEN["at"], _SEEN["me"] = 0.0, None


def status() -> Dict[str, Any]:
    """Everything the page needs, and never an exception.

    Called while drawing, so a cloud that is down has to read as "signed out"
    rather than taking the interface with it.
    """
    out: Dict[str, Any] = {
        "configured": cloudconfig.configured(),
        "google": cloudconfig.google_enabled(),
        "owner": cloudconfig.is_owner(),
        "signed_in": False,
    }
    if not out["configured"] or not signed_in():
        return out
    try:
        out.update({"signed_in": True, **me()})
    except CloudError as exc:
        out["error"] = str(exc)
        out["signed_in"] = signed_in()
    return out


def entitled(capability: str) -> bool:
    """Whether the plan includes something.

    Fails open when the cloud cannot be reached, on purpose. Somebody who paid
    and then lost their internet connection should keep the thing they paid
    for; the alternative is an application that stops working on a train. The
    enforcement that matters is the Worker refusing to do the work, not this.
    """
    if not cloudconfig.configured():
        return True
    try:
        return capability in (me().get("entitlements") or [])
    except CloudError:
        return True


# --- settings ---------------------------------------------------------------

def pull_settings() -> Dict[str, Any]:
    """Whatever is stored for this account."""
    return _authed("GET", "/settings")


def push_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Store settings for this account, replacing what is there."""
    return _authed("PUT", "/settings", settings)


def drop_settings() -> Dict[str, Any]:
    return _authed("DELETE", "/settings")
