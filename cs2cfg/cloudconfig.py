"""Where the cloud lives, and what is safe to say here.

Everything in this file ships inside the application, so everything in this
file is public. That is not a risk being accepted, it is a rule the file is
built around: a PyInstaller bundle unpacks with a script anyone can download,
and this project's source is on GitHub besides. A secret placed here would be
a published secret, whatever it was wrapped in.

So there is nothing secret here, and nothing secret is needed:

* the Worker's address is not a secret;
* Google's **client id** is not a secret either -- it is in the sign-in URL
  every user sees. Its matching **client secret** lives in the Worker, which
  is the only place the authorisation-code exchange happens.
* Cloudflare's own access to R2 and D1 is not a key at all. The Worker is
  given bindings, resolved by Cloudflare at runtime, so there is nothing to
  put here even if it belonged here.

The owner's administration token is the one thing that could be mistaken for
belonging here, and it is the one thing that most certainly does not. It is
read from the environment on the owner's own machine -- see :func:`admin_token`
-- so it exists on exactly one computer and is in no build, either edition.
"""

from __future__ import annotations

import os
from typing import Optional

# The Worker from worker/. Replace the host with your own after deploying it;
# until then the launcher has nowhere to sign in to and says so plainly rather
# than failing in the middle of a sign-in.
BASE_URL = "https://cs2-autoconfig-cloud.cs2tool.workers.dev"

# Google's OAuth client id, from the Google Cloud console. Public: it travels
# in the browser's address bar on every sign-in. Empty turns Google sign-in
# off, which is the right state for a launcher pointed at a Worker that has no
# Google credentials of its own.
GOOGLE_CLIENT_ID = ""

# Where the owner's token is looked for. An environment variable rather than a
# file in the application's folder, because a file in the application's folder
# is a file that gets copied into a build by accident one day.
ADMIN_TOKEN_ENV = "CS2CFG_ADMIN_TOKEN"

# The placeholder above, so the application can tell "not configured yet" from
# "configured" without guessing at the shape of a URL.
_UNCONFIGURED = "example.workers.dev"


def base_url() -> str:
    """The Worker's address, with any trailing slash removed.

    Overridable from the environment, which is how the Worker gets tested
    against a local ``wrangler dev`` without editing a shipped file.
    """
    return os.environ.get("CS2CFG_CLOUD_URL", BASE_URL).rstrip("/")


def configured() -> bool:
    """Whether there is a real Worker to talk to."""
    url = base_url()
    return bool(url) and _UNCONFIGURED not in url


def google_enabled() -> bool:
    return bool(os.environ.get("CS2CFG_GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID))


def admin_token() -> Optional[str]:
    """The owner's token, if this machine is the owner's.

    Deliberately not stored, not cached, and not written anywhere. Setting the
    variable is what makes a machine the owner's machine; nothing in the
    application marks it, and no build carries it.
    """
    found = os.environ.get(ADMIN_TOKEN_ENV, "").strip()
    return found or None


def is_owner() -> bool:
    """Whether to offer the owner's view at all.

    The honest meaning of this is "this machine has the token", not "this
    person is the owner" -- the application cannot tell the difference, and
    does not need to. The Worker checks the token on every administrative
    request, so a wrong answer here shows somebody an empty panel rather than
    anybody else's data.
    """
    return admin_token() is not None
