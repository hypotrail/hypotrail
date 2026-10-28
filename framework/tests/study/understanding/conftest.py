"""Understanding review tests (ADR 0008). Studies, repositories and banks live in tmp_path.

Every "human" in these tests is a simulated declaration of a test fixture (``simulated:
true``); no test establishes that a real person understood anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
