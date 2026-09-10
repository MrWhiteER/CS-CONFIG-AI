"""Entry point for ``python -m cs2cfg``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
