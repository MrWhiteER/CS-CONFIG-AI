"""One Steam sign-in, shared by everything in the app that needs Steam's website.

The Steam client on the PC does not lend its session to other programs, so
the app keeps its own: Steam's login page, shown once in a window of the app.
The windows are pywebview windows that are not private, so the cookie is kept
in the app's data folder and every later window is already signed in -- the
past-match reader (:mod:`steamhistory`) uses it in a hidden window, and so can
anything else that reads a signed-in Steam page.

Setup's "Sign in with Steam" (the cloud sign-in, Steam OpenID) opens in this
window too when the app window is there, so that one sign-in covers both: the
user types their Steam login once, on Steam's own page, and the app never
sees the password.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

MARK_FILE = "steam-session.json"
COMMUNITY = "steamcommunity.com"

# Set by the desktop window (pywebview). None in a plain browser tab.
window_factory: Optional[Callable[..., Any]] = None
# Called once a sign-in finishes, e.g. to start reading match history.
on_signed_in: list = []


def available() -> bool:
    return window_factory is not None


def _mark_path():
    from .paths import user_data_dir

    return user_data_dir() / MARK_FILE


def mark(update: Optional[dict] = None) -> dict:
    """Whether this PC's app windows hold a Steam sign-in."""
    path = _mark_path()
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
        got = got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        got = {}
    if update:
        got.update(update)
        try:
            path.write_text(json.dumps(got), encoding="utf-8")
        except OSError:
            pass
    return got


def linked() -> bool:
    return bool(mark().get("linked"))


def window(url: str, hidden: bool = True, title: str = "Steam"):
    if window_factory is None:
        raise RuntimeError("Open the app's own window (not a browser tab) to use Steam.")
    return window_factory(title=title, url=url, width=900, height=760, hidden=hidden)


def current_url(win) -> str:
    try:
        return win.get_current_url() or ""
    except Exception:
        return ""


def wait_for(win, test: Callable[[str], bool], timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if test(current_url(win)):
            time.sleep(1.5)  # let the page's own scripts finish
            return True
        time.sleep(0.5)
    return False


def _signed_in_page(url: str) -> bool:
    """Back on a Steam page that is not the login form."""
    return COMMUNITY in url and "/login" not in url and "/openid/" not in url


def _left_steam(url: str) -> bool:
    """An OpenID sign-in hands back to the cloud's callback, off Steam."""
    return bool(url) and COMMUNITY not in url and "about:blank" not in url


def _finished(win, close_after: Callable[[str], bool]) -> None:
    ok = wait_for(win, close_after, 600)
    if ok:
        mark({"linked": True, "when": int(time.time())})
        for hook in list(on_signed_in):
            try:
                hook()
            except Exception:
                pass
    time.sleep(2)  # the cloud callback page needs a moment to answer
    try:
        win.destroy()
    except Exception:
        pass


def sign_in(url: Optional[str] = None) -> bool:
    """Show Steam's login (or an OpenID ``url``) once, in an app window.

    Returns at once; the window closes itself when the sign-in finishes.
    """
    if window_factory is None:
        return False
    openid = bool(url)
    win = window(url or f"https://{COMMUNITY}/login/home/?goto=my/",
                 hidden=False, title="Sign in with Steam")
    threading.Thread(target=_finished, name="steam-sign-in", daemon=True,
                     args=(win, _left_steam if openid else _signed_in_page)).start()
    return True


# Steam's OpenID page for somebody already signed in: one "Sign in" button in
# a form. Submitting it is the same click the person would make; it only
# happens for the app's own cloud, and only once they have signed in to Steam
# in the app themselves.
_OPENID_SUBMIT_JS = r"""
(function () {
  var form = document.getElementById('openidForm');
  if (!form) return 'no-form';
  var button = document.getElementById('imageLogin');
  if (button && button.click) { button.click(); return 'clicked'; }
  form.submit();
  return 'submitted';
})()
"""


def _openid_page(url: str) -> bool:
    return COMMUNITY in url and "/openid/" in url


def quiet_openid(url: str, timeout: float = 90) -> bool:
    """Finish a cloud OpenID sign-in in a hidden window, with no clicks.

    Only works when this PC's app windows already hold a Steam sign-in: then
    Steam's page is a single "Sign in" button, which this presses. Without a
    Steam session Steam shows its login form instead, and this gives up
    rather than asking -- the visible "Connect Steam" covers that case.
    Blocks; run it on a thread.
    """
    if window_factory is None or not linked():
        return False
    win = window(url, hidden=True, title="Steam")
    try:
        if not wait_for(win, _openid_page, 30):
            return False
        answer = ""
        for _ in range(10):  # the page may still be building its form
            try:
                answer = str(win.evaluate_js(_OPENID_SUBMIT_JS) or "")
            except Exception:
                answer = ""
            if answer in ("clicked", "submitted"):
                break
            time.sleep(1)
        if answer not in ("clicked", "submitted"):
            return False
        ok = wait_for(win, _left_steam, timeout)
        time.sleep(2)  # the cloud's callback page needs a moment to answer
        return ok
    finally:
        try:
            win.destroy()
        except Exception:
            pass
