"""Make the helpers importable however the suite is started.

``unittest discover -s tests`` puts this directory on ``sys.path`` and imports
each module top-level, so ``from sandbox import ...`` just works. Running one
module as ``python -m tests.test_starter`` imports this package instead and
does not, so the same path is added here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
