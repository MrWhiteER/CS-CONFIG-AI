"""Publish a release. Run only when a release is actually wanted.

This is the one script here that reaches outside the machine: it pushes to
GitHub and publishes a release that every installed copy will be offered
within five minutes. Nothing else in the project does that, and nothing calls
this automatically -- it exists to be run deliberately, by hand.

    py tools/release.py                        # next patch, notes from the commits
    py tools/release.py minor                  # or major, or an explicit 1.4.0
    py tools/release.py --dry-run              # say what would happen, do none of it
    py tools/release.py --notes "..."          # override the generated notes

With no arguments it steps the last number up by one and writes the notes from
the commit subjects since the previous tag, so publishing needs nothing typed
but the command itself.

The order matters. Tests run before the version is touched, the build runs
before anything is pushed, and the tag is only pushed once there is an
archive to attach to it -- so a failure at any step leaves nothing published
and nothing half-tagged.

The repository the built application checks for updates is not typed in
anywhere: it is read from the `origin` remote and written into the source
before building, so a build can never point somewhere its own repository does
not.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "cs2cfg" / "__init__.py"
UPDATES = ROOT / "cs2cfg" / "updates.py"
DIST = ROOT / "dist"
BINARIES = ("CS2 Launcher.exe", "cs2cfg.exe")


class Stop(SystemExit):
    """A refusal with a reason, printed without a traceback."""

    def __init__(self, message: str) -> None:
        super().__init__(f"\n  stopped: {message}\n")


def run(command, capture: bool = False, check: bool = True) -> str:
    printed = command if isinstance(command, str) else " ".join(command)
    print(f"    $ {printed}")
    result = subprocess.run(
        command, cwd=ROOT, shell=isinstance(command, str),
        capture_output=capture, text=True)
    if check and result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr.strip())
        raise Stop(f"`{printed}` failed with exit code {result.returncode}")
    return (result.stdout or "").strip() if capture else ""


# --------------------------------------------------------------------------
# where this is published

def origin_repo() -> str:
    """owner/name for the `origin` remote, in whichever form it is written."""
    url = run(["git", "remote", "get-url", "origin"], capture=True, check=False)
    if not url:
        raise Stop(
            "there is no `origin` remote yet, so there is nowhere to publish.\n"
            "  Create the repository on GitHub, then:\n"
            "    git remote add origin https://github.com/<you>/cs2-autoconfig.git")
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not match:
        raise Stop(f"could not read an owner/name out of the origin remote: {url}")
    return f"{match.group(1)}/{match.group(2)}"


def point_updater_at(repo: str) -> bool:
    """Write the repository into the source the build will be made from."""
    text = UPDATES.read_text(encoding="utf-8")
    new = re.sub(r'^DEFAULT_REPO = ".*"$', f'DEFAULT_REPO = "{repo}"',
                 text, count=1, flags=re.M)
    if new == text:
        return False
    UPDATES.write_text(new, encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# version

def read_version() -> str:
    match = re.search(r'^__version__ = "(.+?)"$', INIT.read_text(encoding="utf-8"), re.M)
    if not match:
        raise Stop("could not find __version__ in cs2cfg/__init__.py")
    return match.group(1)


def write_version(version: str) -> None:
    text = INIT.read_text(encoding="utf-8")
    INIT.write_text(
        re.sub(r'^__version__ = ".+?"$', f'__version__ = "{version}"',
               text, count=1, flags=re.M),
        encoding="utf-8")


def as_numbers(version: str) -> tuple:
    parts = [int(p) for p in re.findall(r"\d+", version)[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def resolve_version(asked: str, current: str) -> str:
    """Work out the version to publish.

    "patch", "minor", "major" step up from what is there now; anything else is
    taken as an explicit version and checked below. Defaulting to a patch bump
    is what makes a release a single word -- the common case is a handful of
    fixes, and that is exactly what the last number is for.
    """
    major, minor, patch = as_numbers(current)
    step = (asked or "patch").strip().lower()
    if step == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if step == "minor":
        return f"{major}.{minor + 1}.0"
    if step == "major":
        return f"{major + 1}.0.0"
    return step.lstrip("vV")


def last_tag() -> str:
    """The most recent release tag, or "" before the first one."""
    return run(["git", "describe", "--tags", "--abbrev=0"],
               capture=True, check=False)


def notes_from_git(since: str) -> str:
    """The commit subjects since the last release, as the notes.

    Written once, in the commit, and read back here -- rather than written
    again by hand at release time and slowly drifting away from the truth.
    """
    span = f"{since}..HEAD" if since else "HEAD"
    subjects = run(["git", "log", span, "--no-merges", "--pretty=format:%s"],
                   capture=True, check=False)
    lines = [s.strip() for s in subjects.splitlines() if s.strip()]
    if not lines:
        return ""
    return "\n".join("- " + line for line in lines)


# --------------------------------------------------------------------------
# the archive

def build_archive(version: str) -> Path:
    missing = [name for name in BINARIES if not (DIST / name).is_file()]
    if missing:
        raise Stop("the build did not produce: " + ", ".join(missing))

    archive = DIST / f"cs2-autoconfig-{version}-win64.zip"
    archive.unlink(missing_ok=True)
    # Stored at the root of the zip, because the updater copies the unpacked
    # contents straight over the folder the executables live in.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in BINARIES:
            bundle.write(DIST / name, arcname=name)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    size = archive.stat().st_size / (1024 * 1024)
    print(f"    {archive.name}  {size:.1f} MB")
    print(f"    sha256 {digest}")
    return archive


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a release to GitHub.")
    parser.add_argument("version", nargs="?", default="patch",
                        help='"patch" (the default), "minor", "major", '
                             'or an explicit version like "1.4.0"')
    parser.add_argument("--notes", default="",
                        help="release notes; shown in the update centre")
    parser.add_argument("--notes-file", default="",
                        help="read the release notes from a file instead")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would happen and change nothing")
    parser.add_argument("--skip-tests", action="store_true",
                        help="do not run the suite first (not recommended)")
    args = parser.parse_args()

    previous = read_version()
    version = resolve_version(args.version, previous)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise Stop(f"{version!r} is not a three-part version like 1.2.0")

    if as_numbers(version) <= as_numbers(previous):
        raise Stop(
            f"{version} is not newer than the current {previous}. "
            "Installed copies compare version numbers, so they would never "
            "be offered it.")

    notes = args.notes
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8")
    if not notes.strip():
        notes = notes_from_git(last_tag())
    if not notes.strip():
        notes = f"Version {version}."

    repo = origin_repo()
    has_gh = bool(shutil.which("gh"))

    print(f"\n  releasing {previous} -> {version}   to {repo}")
    if args.dry_run:
        # A dry run is for checking the plan, so it reports a missing `gh`
        # rather than refusing over it -- there is nothing to publish with yet.
        print("\n  --dry-run: nothing below will actually be done\n")
        for step in (f"point the updater at {repo}",
                     "run the test suite",
                     f"set __version__ to {version}",
                     "build both executables",
                     f"zip them as cs2-autoconfig-{version}-win64.zip",
                     f"commit, tag v{version}, push to {repo}",
                     "publish the release with the zip attached"):
            print(f"    - {step}")
        print(f"\n  gh: {'found' if has_gh else 'NOT INSTALLED -- publishing would stop here'}")
        print("\n  notes it would publish:")
        for line in notes.splitlines()[:12]:
            print(f"    {line}")
        print()
        return 0

    if not has_gh:
        raise Stop(
            "the GitHub CLI (`gh`) is not installed, so this cannot publish.\n"
            "    winget install --id GitHub.cli\n"
            "  then sign in once with:  gh auth login")

    dirty = run(["git", "status", "--porcelain"], capture=True)
    if dirty:
        raise Stop("the working tree has uncommitted changes. Commit them "
                   "first, so the release matches what is in the repository:\n"
                   + "\n".join("    " + line for line in dirty.splitlines()))

    print("\n  [1/6] pointing the updater at the release repository")
    if point_updater_at(repo):
        print(f"    DEFAULT_REPO = {repo!r}")
    else:
        print(f"    already {repo!r}")

    if not args.skip_tests:
        print("\n  [2/6] running the tests")
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    else:
        print("\n  [2/6] tests skipped")

    print(f"\n  [3/6] setting the version to {version}")
    write_version(version)

    print("\n  [4/6] building")
    run(str(ROOT / "dev.bat") + " build")

    print("\n  [5/6] packaging")
    archive = build_archive(version)

    print("\n  [6/6] publishing")
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"Release {version}"])
    run(["git", "tag", "-a", f"v{version}", "-m", f"Release {version}"])
    run(["git", "push", "origin", "HEAD"])
    run(["git", "push", "origin", f"v{version}"])
    run(["gh", "release", "create", f"v{version}", str(archive),
         "--title", f"{version}", "--notes", notes])

    print(f"\n  published: https://github.com/{repo}/releases/tag/v{version}")
    print("  Installed copies will be offered it within five minutes.\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Stop as stop:
        print(stop.args[0] if stop.args else "stopped")
        raise SystemExit(1)
