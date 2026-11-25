"""Atomic file replacement and optimistic revision checks for local edits."""
from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
from pathlib import Path

# Also protects a check/backup/write transaction made by callers in this process.
LOCK = threading.RLock()


class RevisionConflict(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def revision(path: Path) -> str:
    try:
        return digest(Path(path).read_bytes())
    except FileNotFoundError:
        return "missing"


def write_bytes(path: Path, data: bytes, *, expected: str | None = None) -> str:
    """Replace only after a complete write; preserve the original on failure.

    The caller must encode text before calling. A revision is optional for
    generated files and required by interactive editors. Temporary files live
    on the destination volume, so os.replace does not become a partial copy.
    """
    path = Path(path)
    with LOCK:
        if expected is not None and revision(path) != expected:
            raise RevisionConflict("The file changed since you opened it. Review the current version before saving.")
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if mode is not None:
                os.chmod(temporary, mode)
            if expected is not None and revision(path) != expected:
                raise RevisionConflict("The file changed while saving. Your draft is still open.")
            os.replace(temporary, path)
        finally:
            try:
                if os.path.exists(temporary):
                    os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return digest(data)


def write_text(path: Path, text: str, encoding: str = "utf-8", *, expected: str | None = None) -> str:
    return write_bytes(path, text.encode(encoding), expected=expected)
