"""The three pauses as preconditions of the decision graph (plan §4).

* Pause 1: ``feature_availability`` needs ``prediction_time``; the split decision needs
  both.
* Pause 2: the ``split`` activity needs the split decision, and every EDA and fit
  needs a current split result.
* Pause 3: confirming ``policy`` needs a current policy evaluation of that rule;
  the conclusion needs an adopted policy, or the ``keep_baseline`` verdict.

``missing_for_decision`` and ``missing_for_activity`` return the unmet requirements
(empty when met); the ``require_*`` functions raise
:class:`mlkit.reliability.CommandRefused` with code ``precondition_missing``. Phase 2
activities call :func:`require_activity` before reserving an execution, and again
when promoting a result.

Pure: only state is read, plus, when ``store`` is given, the registry entry of the
current policy evaluation (to check that it evaluated the proposed rule).
"""
from __future__ import annotations

from typing import Any, Mapping

from mlkit.reliability import CommandRefused

from . import records as rec
from . import state as st

POLICY_EVALUATION = 'policy.evaluation'
SPLIT_SLOT = 'split'
CONCLUSION_VERDICTS = ('adopt_policy', 'keep_baseline', 'inconclusive')

DECISION_REQUIRES = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': ('prediction_time', 'feature_availability'),
    'policy': ('prediction_time', 'feature_availability', 'split'),
    'conclusion': ('prediction_time', 'feature_availability', 'split'),
}


def _confirmed(state: Mapping, decision_id: str) -> bool:
    return state['decisions'][decision_id]['status'] == 'confirmed'


def _need_decision(state: Mapping, decision_id: str) -> dict:
    return {'requirement': 'decision_confirmed', 'decision': decision_id,
            'status': state['decisions'][decision_id]['status']}


def evaluated_rules(entry: Mapping) -> list[str]:
    """Rules a policy evaluation entry covers: ``params.rules`` or ``params.rule``."""
    params = entry.get('params', {})
    if isinstance(params.get('rules'), list):
        rules = [str(r) for r in params['rules']]
    else:
        rules = [str(params['rule'])] if params.get('rule') is not None else []
    return [rec.canonical_rule(r) or r for r in rules]


def missing_for_decision(state: Mapping, decision_id: str, value: Any = None, *,
                         store=None) -> list[dict]:
    """Unmet requirements to confirm ``decision_id`` with ``value``."""
    missing = [_need_decision(state, d) for d in DECISION_REQUIRES[decision_id]
               if not _confirmed(state, d)]
    if decision_id == 'policy':
        if not st.is_current(state, POLICY_EVALUATION):
            missing.append({'requirement': 'result_current', 'slot': POLICY_EVALUATION,
                            'detail': 'Evaluate the policy before adopting it.'})
        elif store is not None:
            from . import registry   # read of one entry; registry is a writer-side module
            entry = registry.get(store, state['current'][POLICY_EVALUATION])
            if value is not None and (rec.canonical_rule(value) or str(value)) \
                    not in evaluated_rules(entry):
                missing.append({'requirement': 'result_current', 'slot': POLICY_EVALUATION,
                                'rule': value, 'evaluated': evaluated_rules(entry),
                                'detail': 'The current evaluation did not evaluate this rule.'})
    if decision_id == 'conclusion':
        verdict = value.get('verdict') if isinstance(value, Mapping) else None
        if verdict != 'keep_baseline' and not _confirmed(state, 'policy'):
            missing.append({**_need_decision(state, 'policy'),
                            'detail': 'Adopt a policy first, or conclude keep_baseline.'})
    return missing


ACTIVITY_DECISIONS = ('prediction_time', 'feature_availability', 'split')


def missing_for_activity(state: Mapping, activity: str) -> list[dict]:
    """Unmet requirements to run ``activity`` (a slot name such as ``fit.logistic``)."""
    missing = [_need_decision(state, d) for d in ACTIVITY_DECISIONS if not _confirmed(state, d)]
    if activity == SPLIT_SLOT:
        return missing
    if not st.is_current(state, SPLIT_SLOT):
        missing.append({'requirement': 'result_current', 'slot': SPLIT_SLOT,
                        'detail': 'Split the data before exploring or fitting it.'})
    if activity.startswith('policy.'):
        for slot in ('fit.baseline', 'fit.logistic'):
            if not st.is_current(state, slot):
                missing.append({'requirement': 'result_current', 'slot': slot})
    return missing


def _refuse(missing: list[dict], subject: str) -> None:
    if missing:
        raise CommandRefused('precondition_missing', f'{subject} is not possible yet.',
                             details={'missing': missing})


def require_decision(state: Mapping, decision_id: str, value: Any = None, *, store=None) -> None:
    _refuse(missing_for_decision(state, decision_id, value, store=store),
            f'Confirming {decision_id}')


def require_activity(state: Mapping, activity: str) -> None:
    _refuse(missing_for_activity(state, activity), f'Running {activity}')
