"""Helpers of the library-integration tests: a study taken to its fits, its frames and plans."""
from __future__ import annotations

from pathlib import Path

import flowkit as fk
from flowkit import Flow
from mlkit.study import activities as act, case as c, data as dt, read, store as sto

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'


def study_at_fits(tmp_path: Path, task: str = 'binary', n_rows: int = 500,
                  case_dir: Path | None = None, preprocessing=None) -> Flow:
    if case_dir is None:
        case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions(preprocessing=preprocessing)
    flow.run('split')
    return flow


def development(flow: Flow):
    case = c.load_case(flow.case_dir)
    keys = fk.partition_keys(flow.study, 'development')
    return case, dt.load_development(case, keys).frame


def candidate_plan(flow: Flow):
    """``(inputs, params)`` of the candidate fit as the engine would plan it now."""
    s = read.open(flow.study)
    case = c.load_case(flow.case_dir)
    slot = act.LINEAR if s.state['task'] == 'regression' else act.LOGISTIC
    return act.model_plan(s.state, case, slot)


def folds(flow: Flow) -> dict:
    s = read.open(flow.study)
    store = sto.StudyStore(flow.study)
    return act.fold_assignment(store, s.state['current'][act.SPLIT])
