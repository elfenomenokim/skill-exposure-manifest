"""Import the package from ``src/`` when it is not installed.

CI installs the package first and tests the installed copy; a plain checkout runs
the same suite without an install step.
"""

import sys
from pathlib import Path

try:
    import skill_exposure_manifest  # noqa: F401
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
