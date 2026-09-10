"""Keeping the installed application up to date from GitHub releases.

Updates are published as releases on a public repository, so the check is an
ordinary unauthenticated request. No token is shipped inside the software,
nothing has to be rotated if a copy is taken apart, and a user needs no GitHub
account to receive updates. The cost is that the source is readable by anyone,
which was a deliberate trade.

Three steps, kept deliberately separate so the user decides how far to go:

* **check** -- ask what the latest release is. Cheap, and done on a timer.
* **download** -- fetch the archive into our own staging directory. May happen
  on its own if the user asked for that; nothing outside staging changes.
* **install** -- put the new files in place and restart. Never automatic, and
  never without being asked. Windows will not let a running executable be
  overwritten, so the swap is handed to a small script that waits for this
  process to exit first.

Nothing here touches the CS2 configuration folder. The only paths ever written
are the staging directory under this application's data directory and, at
install time, the directory the executables sit in.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import __version__
from .paths import (INSTALLED, PORTABLE, SOURCE, app_dir, install_kind,
                    is_frozen, user_data_dir)

# Where releases are published. Overridable so a fork, or a test, can point
# somewhere else without editing the source.
DEFAULT_REPO = "MrWhiteER/CS-CONFIG-AI"
REPO_ENV = "CS2CFG_UPDATE_REPO"

API = "https://api.github.com"
INTERVAL = 300.0          # five minutes
TIMEOUT = 15.0

# A release carries both editions. Which one this copy wants depends on how it
# was put here: a zip of the executables for a portable copy, an installer for
# a registered installation.
ASSET_FOR = {PORTABLE: "-win64.zip", INSTALLED: "-setup.exe"}


def wanted_asset(kind: str = "") -> str:
    """The tail of the asset filename this copy should be looking for."""
    return ASSET_FOR.get(kind or install_kind(), ASSET_FOR[PORTABLE])

# Unauthenticated GitHub allows 60 requests an hour, counted per address rather
# than per machine -- so several copies behind one router share one budget.
# Below this much of it left, checking slows down to fit what remains.
EASE_OFF_BELOW = 20


@dataclass
class Rate:
    """What GitHub said was left of the budget, from the response headers."""

    limit: int = -1
    remaining: int = -1
    reset: float = 0.0

    @property
    def known(self) -> bool:
        return self.remaining >= 0

    def as_dict(self) -> Dict[str, object]:
        return {"limit": self.limit, "remaining": self.remaining,
                "reset": self.reset}


def _rate_from(headers) -> Rate:
    def number(name, fallback=-1):
        try:
            return int(headers.get(name, ""))
        except (TypeError, ValueError):
            return fallback

    return Rate(limit=number("X-RateLimit-Limit"),
                remaining=number("X-RateLimit-Remaining"),
                reset=float(number("X-RateLimit-Reset", 0)))


def repo() -> str:
    return os.environ.get(REPO_ENV) or DEFAULT_REPO


def configured() -> bool:
    """False while the repository is still the placeholder in the source."""
    return not repo().startswith("REPLACE_ME")


def _user_agent() -> str:
    # GitHub rejects requests without one.
    return f"cs2-autoconfig/{__version__}"


# --------------------------------------------------------------------------
# versions

def parse_version(text: str) -> tuple:
    """Turn "v1.2.3" into (1, 2, 3) for comparison.

    Anything trailing a number in a part is dropped, so "1.2.3-rc1" reads as
    (1, 2, 3). That is imprecise, but the "latest release" endpoint already
    excludes drafts and pre-releases, so a pre-release should never reach here.
    """
    cleaned = (text or "").strip().lstrip("vV")
    parts: List[int] = []
    for chunk in cleaned.split(".")[:4]:
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def current_version() -> str:
    return __version__


def is_newer(candidate: str, than: str) -> bool:
    return parse_version(candidate) > parse_version(than)


# --------------------------------------------------------------------------
# what a release looks like to us

@dataclass
class Release:
    version: str = ""
    name: str = ""
    notes: str = ""
    page: str = ""
    published: str = ""
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    asset_sha256: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "name": self.name,
            "notes": self.notes,
            "page": self.page,
            "published": self.published,
            "asset": self.asset_name,
            "size": self.asset_size,
        }


def _get(url: str, etag: str = "") -> tuple:
    """Fetch a URL, returning (status, body, etag, rate).

    A 304 comes back with no body and the caller keeps what it already had.
    It still costs a request against the rate limit -- measured, not assumed --
    so the ETag saves bandwidth here, not budget.
    """
    request = urllib.request.Request(url, headers={
        "User-Agent": _user_agent(),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if etag:
        request.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return (response.status, response.read(),
                    response.headers.get("ETag", ""), _rate_from(response.headers))
    except urllib.error.HTTPError as exc:
        # The headers on a refusal are the useful part: they say when the
        # budget comes back.
        rate = _rate_from(getattr(exc, "headers", None) or {})
        if exc.code == 304:
            return 304, b"", etag, rate
        if exc.code in (403, 429) and rate.known and rate.remaining == 0:
            raise RateLimited(rate) from exc
        if exc.code == 404:
            raise NoReleasesYet() from exc
        raise


def parse_release(data: Dict[str, object], kind: str = "") -> Release:
    """Read GitHub's release JSON into the handful of fields we use.

    Picks the attachment matching this copy's edition. A release missing that
    attachment leaves the fields empty, and the panel then offers the release
    page rather than a download it cannot use.
    """
    tag = str(data.get("tag_name") or "")
    release = Release(
        version=tag.lstrip("vV"),
        name=str(data.get("name") or tag),
        notes=str(data.get("body") or "").strip(),
        page=str(data.get("html_url") or ""),
        published=str(data.get("published_at") or ""),
    )
    suffix = wanted_asset(kind)
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        if not name.lower().endswith(suffix):
            continue
        release.asset_name = name
        release.asset_url = str(asset.get("browser_download_url") or "")
        release.asset_size = int(asset.get("size") or 0)
        # Newer API versions publish a digest; older ones do not, and then the
        # declared size is all there is to check against.
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:"):
            release.asset_sha256 = digest.split(":", 1)[1]
        break
    return release


class NoReleasesYet(RuntimeError):
    """The repository has published nothing, or is not there at all.

    GitHub answers 404 for both, and does not distinguish them without another
    request. Neither is worth alarming anyone about: there is simply nothing
    newer than what is already running.
    """

    def __init__(self) -> None:
        super().__init__("no releases have been published yet")


class RateLimited(RuntimeError):
    """GitHub has nothing left for this address until the window resets."""

    def __init__(self, rate: Rate) -> None:
        self.rate = rate
        minutes = max(0, int((rate.reset - time.time()) / 60))
        super().__init__(
            "GitHub's hourly limit for this network is used up"
            + (f"; it resets in about {minutes} min" if minutes else ""))


def fetch_latest(etag: str = "") -> tuple:
    """The newest published release as (Release, etag, rate).

    Returns (None, etag, rate) when GitHub says nothing has changed. Uses the
    "latest" endpoint, which by definition skips drafts and pre-releases, so
    work in progress can be pushed without every user being offered it.
    """
    status, body, new_etag, rate = _get(f"{API}/repos/{repo()}/releases/latest", etag)
    if status == 304:
        return None, new_etag, rate
    return (parse_release(json.loads(body.decode("utf-8"))), new_etag, rate)


# --------------------------------------------------------------------------
# staging

def staging_dir() -> Path:
    return user_data_dir() / "updates"


def archive_path(release: Release) -> Path:
    return staging_dir() / "download" / (release.asset_name or "update.zip")


def ready_dir(release: Release) -> Path:
    return staging_dir() / "ready" / (release.version or "unknown")


def is_ready(release: Release) -> bool:
    """Has this version already been downloaded and unpacked?"""
    return (ready_dir(release) / ".complete").is_file()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(block)
    return digest.hexdigest()


def is_installer(release: Release) -> bool:
    """Whether this release's attachment is an installer rather than a zip."""
    return release.asset_name.lower().endswith(".exe")


def download(release: Release,
             progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None) -> Path:
    """Fetch the release archive and unpack it, ready to be installed.

    The archive is written under a temporary name and only moved into place
    once it has been verified, so a connection dropped halfway can never leave
    something that looks finished. Unpacking happens here, while the
    application is running and can report a problem, rather than during the
    swap when there is nothing left to report it to.
    """
    if not release.asset_url:
        raise RuntimeError("this release has no downloadable archive attached")

    archive = archive_path(release)
    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = archive.with_name(archive.name + ".part")

    request = urllib.request.Request(
        release.asset_url, headers={"User-Agent": _user_agent()})
    total = release.asset_size
    seen = 0
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        declared = response.headers.get("Content-Length")
        if declared and not total:
            total = int(declared)
        with partial.open("wb") as out:
            while True:
                if cancelled and cancelled():
                    partial.unlink(missing_ok=True)
                    raise RuntimeError("cancelled")
                block = response.read(1024 * 128)
                if not block:
                    break
                out.write(block)
                seen += len(block)
                if progress:
                    progress(seen, total)

    if total and seen != total:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"download was {seen} bytes, expected {total}")
    if release.asset_sha256:
        if sha256_of(partial).lower() != release.asset_sha256.lower():
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                "the downloaded file does not match its published checksum")

    partial.replace(archive)
    if is_installer(release):
        # An installer is run, not unpacked. Marking it complete here keeps
        # "have we got this version" one question with one answer for both.
        ready = ready_dir(release)
        ready.mkdir(parents=True, exist_ok=True)
        (ready / ".complete").write_text(release.version, encoding="utf-8")
    else:
        unpack(archive, release)
    return archive


def unpack(archive: Path, release: Release) -> Path:
    """Extract the archive, refusing any entry that escapes the target.

    A zip can name an entry that climbs out of the directory it is extracted
    into. Nothing we publish does, but this arrives over the network and the
    check costs one comparison per file.
    """
    ready = ready_dir(release)
    if ready.exists():
        shutil.rmtree(ready, ignore_errors=True)
    ready.mkdir(parents=True, exist_ok=True)

    root = ready.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.namelist():
            target = (ready / entry).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(
                    f"refusing to unpack {entry!r}: it points outside the folder")
        bundle.extractall(ready)

    (ready / ".complete").write_text(release.version, encoding="utf-8")
    return ready


def clean_old(keep: str = "") -> None:
    """Drop staged versions other than the one named, so staging cannot grow."""
    base = staging_dir() / "ready"
    if not base.is_dir():
        return
    for child in base.iterdir():
        if child.is_dir() and child.name != keep:
            shutil.rmtree(child, ignore_errors=True)


# --------------------------------------------------------------------------
# installing

SWAP_SCRIPT = """@echo off
setlocal EnableDelayedExpansion
rem Written by cs2-autoconfig to finish an update. Windows will not let a
rem running executable be replaced, so this waits for the application to close
rem before copying the new files over it.
set "LOG=%~dp0swap.log"
echo [%date% %time%] waiting for pid @@PID@@ > "%LOG%"

set /a TRIES=0
:waitpid
tasklist /fi "PID eq @@PID@@" 2>nul | find "@@PID@@" >nul
if errorlevel 1 goto waitlocks
set /a TRIES+=1
if !TRIES! GTR 120 (
  echo [%date% %time%] gave up waiting for the window >> "%LOG%"
  goto copyfiles
)
ping -n 2 127.0.0.1 >nul
goto waitpid

:waitlocks
rem A second window or a console copy running out of the same folder holds a
rem lock on a file about to be overwritten. Wait for those too -- they belong
rem to the user, so they are not killed.
set /a TRIES=0
:lockloop
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t='@@TARGET@@'; $p=Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($t,'OrdinalIgnoreCase') }; if ($p) { exit 1 } exit 0"
if not errorlevel 1 goto copyfiles
set /a TRIES+=1
if !TRIES! GTR 30 (
  echo [%date% %time%] something is still running from the folder; trying anyway >> "%LOG%"
  goto copyfiles
)
echo [%date% %time%] still in use, waiting >> "%LOG%"
ping -n 3 127.0.0.1 >nul
goto lockloop

:copyfiles
echo [%date% %time%] copying >> "%LOG%"
robocopy "@@READY@@" "@@TARGET@@" /E /IS /IT /R:5 /W:2 /XF .complete >> "%LOG%" 2>&1
rem robocopy reports 0-7 for success; 8 and above mean nothing was copied.
if %ERRORLEVEL% GEQ 8 (
  echo [%date% %time%] copy failed, leaving the old version in place >> "%LOG%"
  goto done
)
echo [%date% %time%] restarting >> "%LOG%"
if not "@@RELAUNCH@@"=="" start "" "@@RELAUNCH@@"

:done
rem Remove this script now that it has finished with itself.
(goto) 2>nul & del "%~f0"
"""


def _fill(pid: int, ready: str, target: str, relaunch: str) -> str:
    """Fill the template by token, not by format.

    The script contains PowerShell, and PowerShell is mostly braces. str.format
    would need every one of them doubled, and one missed pair produces a script
    that runs and does the wrong thing.
    """
    out = SWAP_SCRIPT
    for token, value in (("@@PID@@", str(pid)), ("@@READY@@", ready),
                         ("@@TARGET@@", target), ("@@RELAUNCH@@", relaunch)):
        out = out.replace(token, value)
    return out


def install(release: Release, relaunch: bool = True) -> Path:
    """Put the new version in place and return the script doing it.

    The caller is expected to exit promptly afterwards -- the script is already
    waiting for this process to disappear.

    An installed copy runs the next Setup.exe, so its Add/Remove Programs
    entry, shortcuts and uninstaller keep describing what is actually there. A
    portable copy copies files over its own folder. Either way a failure leaves
    the working version exactly where it was.
    """
    if not is_frozen():
        raise RuntimeError(
            "this copy runs from source, so there is nothing to replace; "
            "update it with git instead")
    ready = ready_dir(release)
    if not (ready / ".complete").is_file():
        raise RuntimeError("that version has not finished downloading yet")

    if is_installer(release):
        return _run_installer(release, relaunch)

    script = staging_dir() / "swap.cmd"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_fill(
        pid=os.getpid(),
        ready=str(ready),
        target=str(app_dir()),
        relaunch=str(Path(sys.executable)) if relaunch else "",
    ), encoding="utf-8")

    _spawn(script)
    return script


INSTALL_SCRIPT = """@echo off
setlocal EnableDelayedExpansion
rem Written by cs2-autoconfig to finish an update on an installed copy. The
rem installer refuses to replace files that are still locked, and under silent
rem flags it does so without saying anything -- so this waits first.
set "LOG=%~dp0swap.log"
echo [%date% %time%] waiting for pid @@PID@@ > "%LOG%"

set /a TRIES=0
:waitpid
tasklist /fi "PID eq @@PID@@" 2>nul | find "@@PID@@" >nul
if errorlevel 1 goto waitlocks
set /a TRIES+=1
if !TRIES! GTR 120 goto runsetup
ping -n 2 127.0.0.1 >nul
goto waitpid

:waitlocks
set /a TRIES=0
:lockloop
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t='@@TARGET@@'; $p=Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($t,'OrdinalIgnoreCase') }; if ($p) { exit 1 } exit 0"
if not errorlevel 1 goto runsetup
set /a TRIES+=1
if !TRIES! GTR 30 (
  echo [%date% %time%] still in use; running the installer anyway >> "%LOG%"
  goto runsetup
)
ping -n 3 127.0.0.1 >nul
goto lockloop

:runsetup
rem /SILENT, not /VERYSILENT: a large copy with nothing on screen reads as a
rem hang. /DIR is pinned rather than left to a registry lookup, so this cannot
rem install somewhere other than where it is replacing.
echo [%date% %time%] running the installer >> "%LOG%"
start "" /wait "@@SETUP@@" /SILENT /SP- /NOCANCEL /NORESTART /DIR="@@TARGET@@" /LOG="%~dp0setup.log"
if errorlevel 1 (
  echo [%date% %time%] installer returned %ERRORLEVEL%; the old version is still installed >> "%LOG%"
  goto done
)
echo [%date% %time%] restarting >> "%LOG%"
if not "@@RELAUNCH@@"=="" start "" "@@RELAUNCH@@"

:done
(goto) 2>nul & del "%~f0"
"""


def _run_installer(release: Release, relaunch: bool) -> Path:
    """Hand the downloaded Setup.exe to a script that waits, then runs it."""
    setup = archive_path(release)
    if not setup.is_file():
        raise RuntimeError("the installer for that version is not on disk")

    script = staging_dir() / "swap.cmd"
    script.parent.mkdir(parents=True, exist_ok=True)
    out = INSTALL_SCRIPT
    for token, value in (("@@PID@@", str(os.getpid())),
                         ("@@SETUP@@", str(setup)),
                         ("@@TARGET@@", str(app_dir())),
                         ("@@RELAUNCH@@",
                          str(Path(sys.executable)) if relaunch else "")):
        out = out.replace(token, value)
    script.write_text(out, encoding="utf-8")
    _spawn(script)
    return script


def _spawn(script: Path) -> None:
    """Start a finishing script detached, so it outlives this process."""
    detached = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        detached = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    subprocess.Popen(["cmd", "/c", str(script)], cwd=str(staging_dir()),
                     creationflags=detached, close_fds=True)


# --------------------------------------------------------------------------
# the timer

# What the page can be told, and what each one means:
IDLE = "idle"                 # nothing known yet, or already up to date
CHECKING = "checking"
AVAILABLE = "available"       # a newer release exists, not fetched
DOWNLOADING = "downloading"
READY = "ready"               # fetched and unpacked, waiting to be installed
ERROR = "error"


class Checker:
    """Ask GitHub what the latest release is, every few minutes.

    Downloading may follow a check on its own, if the user has asked for that.
    Installing never does: replacing the program someone is in the middle of
    using is their decision and nobody else's, so it stops at READY and waits.

    A check that fails is not an event worth interrupting anyone over -- the
    network comes and goes -- so the error is recorded for the update panel to
    show and the timer carries on.
    """

    def __init__(self, current: str = "", interval: float = INTERVAL,
                 auto_download: bool = False, skip: str = "") -> None:
        self.current = current or current_version()
        self.interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._etag = ""
        self._latest: Optional[Release] = None
        self._state = IDLE
        self._error = ""
        self._checked = 0.0
        self._done = 0
        self._total = 0
        self._auto = bool(auto_download)
        self._skip = skip or ""
        self._want = False
        self._rate = Rate()

    # -- what the server reads --------------------------------------------
    def summary(self) -> Dict[str, object]:
        with self._lock:
            latest = self._latest
            newer = bool(latest and is_newer(latest.version, self.current))
            out: Dict[str, object] = {
                "current": self.current,
                "state": self._state,
                "error": self._error,
                "checked": self._checked,
                "interval": self.interval,
                "auto_download": self._auto,
                "skipped": self._skip,
                "repo": repo(),
                "configured": configured(),
                "frozen": is_frozen(),
                "edition": install_kind(),
                "running": bool(self._thread and self._thread.is_alive()),
                "available": newer,
                "done": self._done,
                "total": self._total,
                "rate": self._rate.as_dict(),
                "next_in": round(self._delay(), 1),
            }
            out["latest"] = latest.as_dict() if latest else None
            # The popup should appear for a new version the user has not
            # already waved away, and never for one they are already running.
            out["notify"] = bool(
                newer and latest and latest.version != self._skip
                and self._state in (AVAILABLE, DOWNLOADING, READY))
        return out

    def set_auto_download(self, on: bool) -> None:
        with self._lock:
            self._auto = bool(on)
        if on:
            self._wake.set()

    def skip_version(self, version: str) -> None:
        """Stop offering this particular version; a later one still counts."""
        with self._lock:
            self._skip = version or ""

    def check_soon(self) -> None:
        self._wake.set()

    def want_download(self) -> None:
        with self._lock:
            self._want = True
        self._wake.set()

    # -- the loop ----------------------------------------------------------
    def _set(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(self, "_" + key, value)

    def check_once(self) -> None:
        """One round trip. Safe to call from the loop or a request."""
        if not configured():
            self._set(state=IDLE, error="no update repository is configured yet")
            return
        self._set(state=CHECKING, error="")
        try:
            found, etag, rate = fetch_latest(self._etag)
        except NoReleasesYet as exc:
            # Nothing published: up to date by definition, and the panel says
            # so rather than showing a bare status code.
            self._set(state=IDLE, error=str(exc), checked=time.time())
            return
        except RateLimited as exc:
            # Not a failure worth alarming anyone about: the timer below will
            # simply wait for the window to come back.
            with self._lock:
                self._rate = exc.rate
                self._checked = time.time()
            self._set(state=IDLE if self._latest is None else self._state,
                      error=str(exc))
            return
        except Exception as exc:                      # network, DNS, refusal
            self._set(state=ERROR, error=str(exc), checked=time.time())
            return

        with self._lock:
            self._etag = etag
            self._rate = rate
            self._checked = time.time()
            if found is not None:
                self._latest = found
            latest = self._latest
            self._error = ""

        if latest is None or not is_newer(latest.version, self.current):
            self._set(state=IDLE)
            return
        self._set(state=READY if is_ready(latest) else AVAILABLE)

    def download_once(self) -> None:
        with self._lock:
            latest = self._latest
            self._want = False
        if latest is None or not is_newer(latest.version, self.current):
            return
        if is_ready(latest):
            self._set(state=READY)
            return

        self._set(state=DOWNLOADING, error="", done=0, total=latest.asset_size)

        def progress(done: int, total: int) -> None:
            self._set(done=done, total=total)

        try:
            download(latest, progress=progress, cancelled=self._stop.is_set)
        except Exception as exc:
            self._set(state=ERROR, error=str(exc))
            return
        clean_old(keep=latest.version)
        self._set(state=READY)

    def _delay(self) -> float:
        """How long to wait before asking again.

        The configured interval is a floor, never a ceiling. When the budget
        for this address is running low, whatever is left is spread over the
        time until it resets -- so several copies behind one router slow each
        other down rather than locking each other out.

        Deliberately does not take the lock: summary() calls this while already
        holding it, and the lock is not reentrant. One attribute read is atomic
        here, and choosing a delay from a slightly stale budget is harmless.
        """
        rate = self._rate
        if not rate.known or rate.remaining > EASE_OFF_BELOW:
            return self.interval
        left = max(1.0, rate.reset - time.time())
        if rate.remaining <= 0:
            return max(self.interval, left + 5)
        return max(self.interval, left / rate.remaining)

    def _run(self) -> None:
        # A first check shortly after start, so a user who opens the window and
        # closes it a minute later still finds out. Then on the interval.
        delay = 5.0
        while not self._stop.is_set():
            self._wake.wait(delay)
            if self._stop.is_set():
                return
            self._wake.clear()
            delay = self._delay()

            self.check_once()
            with self._lock:
                asked = self._want
                auto = self._auto
                state = self._state
            if state == AVAILABLE and (asked or auto):
                self.download_once()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="cs2cfg-update-check")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
