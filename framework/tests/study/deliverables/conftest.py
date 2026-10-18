"""Fixtures of the Phase 3 deliverable tests; the study builder lives in ``phase3_study``."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase3_study import full_study, full_study_template  # noqa: E402,F401
