"""Enable the test safety kernel before pytest can collect project imports."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def _is_pytest_bootstrap() -> bool:
    argv0 = Path(sys.argv[0]).name.lower()
    return "pytest" in argv0


if os.environ.get("NIA_TEST_MODE") == "1" or _is_pytest_bootstrap():
    from app.testing.safety_kernel import activate

    activate()
