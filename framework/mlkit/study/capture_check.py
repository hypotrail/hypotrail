"""Whether the study's captured predictor would load for the final test (round 5, review E,
R5E-2), for ``next_action`` (:mod:`mlkit.study.view`).

The check is the confirmation's own (:func:`mlkit.contracts.capture.loading_problem_of`: the
bundle verified, the installed runtime compared with the bundle's wheel, the environment, the
parity rows); it reads the bundle only and writes nothing. It imports the runtime (and so
pandas, NumPy and scikit-learn), so it is never run in a read-only process
(``HYPOTRAIL_READ_ONLY=1``, a notebook kernel): there the view keeps the action the state
gives, and the confirmation still refuses an unloadable capture.
"""
from __future__ import annotations

import os
from typing import Mapping

from . import state as st
from .errors import StudyError

CAPTURE = 'predictor.capture'
READ_ONLY_ENV = 'HYPOTRAIL_READ_ONLY'


def unloadable(study, state: Mapping) -> dict | None:
    """The ``capture_loadable`` item of the current capture when the final evaluation could
    not load it, else None (no capture, a capture not current, a read-only process, or a
    failure of the check itself, which the confirmation reports)."""
    if os.environ.get(READ_ONLY_ENV) == '1':
        return None
    rid = state['current'].get(CAPTURE)
    if rid is None or not st.is_current(state, CAPTURE):
        return None
    try:
        entry = study.result(rid)
    except StudyError:
        return None
    try:
        from mlkit.contracts import capture
        return capture.loading_problem_of(study.home, state, entry)
    except Exception:          # noqa: BLE001 - the confirmation reports what it refuses
        return None
