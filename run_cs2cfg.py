"""Frozen-build entry point.

``cs2cfg/__main__.py`` uses a relative import, which is correct for
``python -m cs2cfg`` but fails under PyInstaller: the bootloader runs the
script as a top level module with no parent package. This file does the same
job with an absolute import so both paths work.

When frozen and started with no arguments, open the desktop window. Someone
double-clicking an application expects an application, not a terminal or a
browser tab. Every command is still available by passing arguments.
"""

import sys

from cs2cfg.console import prepare_streams
from cs2cfg.paths import is_frozen

# Before anything else: a GUI-subsystem build starts with no standard streams,
# so this either attaches to the launching console or points them at the null
# device. Importing cli first would risk a print on a None stream.
prepare_streams()

from cs2cfg.cli import main  # noqa: E402

def _default_command() -> list:
    """What running the binary with no arguments should do.

    The windowed build is the application: it opens. The console build is the
    command line tool: with nothing to do it prints its help rather than
    silently launching a window from a terminal.
    """
    from pathlib import Path

    if not is_frozen():
        return []
    name = Path(sys.executable).stem.lower()
    return ["desktop"] if "launcher" in name else ["--help"]


if __name__ == "__main__":
    argv = sys.argv[1:] or _default_command()
    sys.exit(main(argv))
