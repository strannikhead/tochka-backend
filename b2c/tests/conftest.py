from __future__ import annotations

import sys
from pathlib import Path

PROJECT_PATH = Path(__file__).resolve().parents[1]  # b2c/
SRC_PATH = PROJECT_PATH / "src"  # b2c/src/

for _path in (str(SRC_PATH), str(PROJECT_PATH)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
