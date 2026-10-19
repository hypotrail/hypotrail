"""EDA governance and the two WP-A4 decisions (v0.2a; review synthesis §3).

Pure: no file, no pandas, numpy, or scikit-learn. Shared by ``decide`` (value checks),
the fits (``fit.py`` reads :func:`effective_preprocessing`), the view (the success
criterion assessment and the ledger of target-involving looks), and ``check`` (the
``verdict_contradicts_criterion`` warning).

**Preprocessing** (decision ``preprocessing``, class b of the synthesis): proposed in the
junior's words, its parameters learnt on training rows only and applied to validation rows
(and later to every fold). Its value is::

    {"missing": "none" | "indicator" | {column: "none" | "indicator"},
     "rare_category_min_rows": k,          # >= 0 training rows; 0 keeps every category
     "caps": {column: [q_low, q_high]},     # training quantiles, 0 <= q_low < q_high <= 1
     "log_transform": [column, ...],        # signed log, sign(x) * log(1 + |x|)
     "motivated_by": [result_id, ...],      # optional when proposed: the analyses behind it
     "data_contingent": true | false,       # set by the engine
     "target_looks_before": n}              # set by the engine (WP-A9, M1)

:data:`DEFAULT_PREPROCESSING` is what the models did before the decision existed (no
missing-value indicator, every category kept, no cap, no transform), so results stay
comparable. ``data_contingent`` is computed by the engine when the value is proposed: true
when any result named in ``motivated_by`` read the target (:func:`uses_target`), or (WP-A9,
M1) when the study had any target-involving look on training rows before the proposal,
named or not: ``target_looks_before`` records how many (:func:`ledger`). A decision
motivated by a look at the target is still allowed; it is stamped so.

**Success criterion** (decision ``success_criterion``): fixed after the split decision and
before any model is fitted. A binary study states a minimum precision gain over the
baseline at the adopted rule, in percentage points: ``{"metric": "precision_gain",
"min_points": p}``; a regression study a minimum relative reduction of the validation
mean absolute error of the mean baseline: ``{"metric": "mae_reduction", "min_share": f}``.
:func:`assess` compares it with the current evaluation.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Iterable, Mapping

PREPROCESSING_KEYS = ('missing', 'rare_category_min_rows', 'caps', 'log_transform')
PREPROCESSING_OPTIONAL_KEYS = ('motivated_by', 'data_contingent', 'target_looks_before')
MISSING_STRATEGIES = ('none', 'indicator')
DEFAULT_PREPROCESSING = {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {},
                         'log_transform': []}
# The parameters that change a model (``motivated_by`` and ``data_contingent`` do not).
PARAMETER_KEYS = PREPROCESSING_KEYS
NUMERIC_TYPES = ('numeric', 'integer')
RARE_GROUP = '(rare)'

CRITERION_METRICS = {'binary': 'precision_gain', 'regression': 'mae_reduction'}
CRITERION_KEYS = {'binary': ('metric', 'min_points'), 'regression': ('metric', 'min_share')}
ADOPT_VERDICTS = ('adopt_policy', 'adopt_model')
CRITERION_STATUSES = ('met', 'not_met', 'uncertain', 'not_assessed')

# Activities that read the target. ``eda.distribution`` reads it only when its column is
# the target; ``split`` only when it is stratified.
TARGET_ACTIVITIES = ('eda.target_rate', 'eda.target_summary', 'eda.special_values',
                     'eda.rate_by', 'eda.mean_by', 'eda.single_feature_signal',
                     'fit.baseline', 'fit.logistic', 'fit.linear', 'policy.evaluation',
                     'evaluate.regression')
EDA_PREFIX = 'eda.'


class ValueProblem(ValueError):
    """A value that does not fit a decision; ``details`` go into ``invalid_value``."""

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


# --- target use and the ledger of looks -----------------------------------------------

def uses_target(entry: Mapping, target: str | None = None) -> bool:
    """Whether the registry entry ``entry`` read the target column ``target`` (the study's
    target; a distribution records no target in its inputs, so it is needed there)."""
    activity = entry.get('activity')
    inputs = entry.get('inputs') or {}
    params = entry.get('params') or {}
    if activity in TARGET_ACTIVITIES:
        return True
    if activity == 'eda.distribution':
        target = target or (inputs.get('target') or {}).get('column')
        return target is not None and params.get('column') == target
    if activity == 'split':
        decision = inputs.get('decision') or {}
        return decision.get('method') == 'stratified_random'
    return False


def ledger(records: Iterable[Mapping], target: str | None) -> dict:
    """The ledger of target-involving looks (synthesis §3, honest multiplicity): every
    exploration of the training rows that read the target, as recorded in the exposure
    ledger. It is a disclosure, not a correction: ``looks`` counts each run (a run that
    replaced an earlier one is a second look), ``results`` lists their result ids in order,
    ``by_activity`` counts them per activity."""
    looks, results, by_activity = 0, [], {}
    for r in records:
        if r.get('purpose') != 'train_eda' or not str(r.get('activity', '')).startswith(EDA_PREFIX):
            continue
        if target is None or target not in (r.get('columns') or []):
            continue
        looks += 1
        activity = r['activity']
        by_activity[activity] = by_activity.get(activity, 0) + 1
        rid = r.get('result_id')
        if rid and rid not in results:
            results.append(rid)
    return {'target_looks': looks, 'results': results, 'by_activity': dict(sorted(by_activity.items())),
            'note': 'Each exploration that read the target on training rows is a look. The '
                    'count is a disclosure: the more looks, the more a pattern found among '
                    'them can be chance. Validation and final-test rows are never explored.'}


# --- preprocessing -------------------------------------------------------------------------

def _features(case) -> dict[str, dict]:
    return {v['name']: v for v in case.document['variables'] if v['role'] == 'feature'}


def check_preprocessing(value: Any, case) -> None:
    """Refuse a preprocessing value that does not fit the case (:class:`ValueProblem`)."""
    features = _features(case)
    numeric = sorted(n for n, v in features.items() if v['type'] in NUMERIC_TYPES)
    if not isinstance(value, Mapping):
        raise ValueProblem('preprocessing is {"missing", "rare_category_min_rows", "caps", '
                           '"log_transform"} (and optionally "motivated_by").',
                           keys=list(PREPROCESSING_KEYS), default=DEFAULT_PREPROCESSING)
    missing = [k for k in PREPROCESSING_KEYS if k not in value]
    unknown = [k for k in value if k not in PREPROCESSING_KEYS + PREPROCESSING_OPTIONAL_KEYS]
    if missing or unknown:
        raise ValueProblem('preprocessing needs exactly its four parameters, and optionally '
                           'motivated_by.', missing=missing, unknown=unknown,
                           keys=list(PREPROCESSING_KEYS), default=DEFAULT_PREPROCESSING)
    strategy = value['missing']
    if isinstance(strategy, Mapping):
        bad = sorted(k for k in strategy if k not in features)
        wrong = sorted(k for k, v in strategy.items() if v not in MISSING_STRATEGIES)
        if bad or wrong:
            raise ValueProblem('missing maps candidate features to "none" or "indicator".',
                               field='missing', not_features=bad, invalid=wrong,
                               strategies=list(MISSING_STRATEGIES))
    elif strategy not in MISSING_STRATEGIES:
        raise ValueProblem('missing is "none", "indicator", or a mapping of features to one of '
                           'them.', field='missing', strategies=list(MISSING_STRATEGIES))
    k = value['rare_category_min_rows']
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueProblem('rare_category_min_rows is a whole number of training rows (0 keeps '
                           'every category).', field='rare_category_min_rows')
    caps = value['caps']
    if not isinstance(caps, Mapping):
        raise ValueProblem('caps maps numeric features to [q_low, q_high].', field='caps',
                           numeric_features=numeric)
    for column, bounds in caps.items():
        if column not in numeric:
            raise ValueProblem(f'caps names {column!r}, which is not a numeric feature.',
                               field='caps', column=column, numeric_features=numeric)
        ok = isinstance(bounds, (list, tuple)) and len(bounds) == 2 and all(
            isinstance(q, (int, float)) and not isinstance(q, bool) for q in bounds)
        if not ok or not 0 <= bounds[0] < bounds[1] <= 1:
            raise ValueProblem(f'caps.{column} is [q_low, q_high] with 0 <= q_low < q_high <= 1 '
                               f'(training quantiles).', field=f'caps.{column}')
    logs = value['log_transform']
    if not isinstance(logs, list) or not all(isinstance(c, str) for c in logs) \
            or len(set(logs)) != len(logs):
        raise ValueProblem('log_transform is a list of distinct numeric features.',
                           field='log_transform', numeric_features=numeric)
    bad = sorted(c for c in logs if c not in numeric)
    if bad:
        raise ValueProblem('log_transform names features that are not numeric.',
                           field='log_transform', columns=bad, numeric_features=numeric)
    if 'motivated_by' in value:
        m = value['motivated_by']
        if not isinstance(m, list) or not all(isinstance(r, str) and r for r in m):
            raise ValueProblem('motivated_by is a list of result ids.', field='motivated_by')
    if 'data_contingent' in value and not isinstance(value['data_contingent'], bool):
        raise ValueProblem('data_contingent is set by the engine (true or false).',
                           field='data_contingent')
    looks = value.get('target_looks_before', 0)
    if isinstance(looks, bool) or not isinstance(looks, int) or looks < 0:
        raise ValueProblem('target_looks_before is set by the engine (a count of looks).',
                           field='target_looks_before')


def normalize_preprocessing(value: Mapping, lookup: Callable[[str], Mapping | None],
                            target: str | None = None, looks_before: int = 0) -> dict:
    """The value recorded for a proposal: ``motivated_by`` (``[]`` when absent, in the given
    order), ``data_contingent`` computed from the motivating results and from the
    target-involving looks the study had before the proposal (``looks_before``, WP-A9 M1),
    and ``target_looks_before``. ``lookup(rid)`` returns the registry entry of a result id,
    or None when the study has no such result (:class:`ValueProblem`,
    ``unknown_results``)."""
    out = {k: copy.deepcopy(value[k]) for k in PREPROCESSING_KEYS}
    motivated = list(dict.fromkeys(value.get('motivated_by') or []))
    entries, unknown = [], []
    for rid in motivated:
        entry = lookup(rid)
        (entries if entry is not None else unknown).append(entry if entry is not None else rid)
    if unknown:
        raise ValueProblem('motivated_by names results this study does not have.',
                           field='motivated_by', unknown_results=unknown)
    contingent = any(uses_target(e, target) for e in entries) or looks_before > 0
    if 'data_contingent' in value and value['data_contingent'] != contingent:
        raise ValueProblem('data_contingent is computed by the engine from motivated_by and '
                           f'the looks at the target before the proposal: '
                           f'{str(contingent).lower()} here.', field='data_contingent',
                           computed=contingent)
    if 'target_looks_before' in value and value['target_looks_before'] != looks_before:
        raise ValueProblem('target_looks_before is counted by the engine: '
                           f'{looks_before} here.', field='target_looks_before',
                           computed=looks_before)
    out['motivated_by'] = motivated
    out['data_contingent'] = contingent
    out['target_looks_before'] = looks_before
    return out


def parameters(value: Any) -> dict | None:
    """The model parameters of a preprocessing value (``None`` when it is not a mapping)."""
    if not isinstance(value, Mapping):
        return None
    return {k: copy.deepcopy(value.get(k)) for k in PARAMETER_KEYS}


def effective_preprocessing(state: Mapping) -> dict | None:
    """The preprocessing a fit applies: the confirmed value's parameters in a study with the
    decision, ``None`` in a study created before it (the fits then keep their identities)."""
    decision = (state.get('decisions') or {}).get('preprocessing')
    if decision is None:
        return None
    return parameters(decision['value']) if decision['value'] is not None else \
        copy.deepcopy(DEFAULT_PREPROCESSING)


def is_default(value: Any) -> bool:
    return parameters(value) == DEFAULT_PREPROCESSING


def missing_strategy(value: Mapping, column: str) -> str:
    strategy = value.get('missing', 'none')
    if isinstance(strategy, Mapping):
        return strategy.get(column, 'none')
    return strategy


# --- success criterion ---------------------------------------------------------------------

def check_criterion(value: Any, task: str) -> None:
    keys = CRITERION_KEYS[task]
    metric = CRITERION_METRICS[task]
    if not isinstance(value, Mapping) or set(value) != set(keys) or value['metric'] != metric:
        if task == 'binary':
            raise ValueProblem('success_criterion is {"metric": "precision_gain", "min_points": '
                               'p}: the minimum gain in precision over the baseline at the '
                               'adopted rule, in percentage points.', keys=list(keys),
                               metric=metric)
        raise ValueProblem('success_criterion is {"metric": "mae_reduction", "min_share": f}: '
                           'the minimum relative reduction of the mean baseline\'s validation '
                           'mean absolute error (0.1 is ten percent).', keys=list(keys),
                           metric=metric)
    amount = value[keys[1]]
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueProblem(f'{keys[1]} is a number.', field=keys[1])
    if task == 'binary' and not 0 <= amount <= 100:
        raise ValueProblem('min_points is between 0 and 100 percentage points.', field=keys[1])
    if task == 'regression' and not 0 <= amount < 1:
        raise ValueProblem('min_share is a share of the baseline error, from 0 to below 1.',
                           field=keys[1])


def _citable(item) -> bool:
    return bool(item) and item.get('current') and item.get('integrity') == 'ok' \
        and isinstance(item.get('values'), Mapping)


def _rule(decisions: Mapping, proposals: list, evaluated: list[str],
          canonical: Callable[[str], str]) -> str | None:
    policy = decisions.get('policy') or {}
    candidates = []
    if policy.get('status') in ('confirmed', 'reconfirm_required'):
        candidates.append(policy.get('value'))
    candidates += [p['value'] for p in proposals if p.get('decision_id') == 'policy']
    for c in candidates:
        if isinstance(c, str) and canonical(c) in evaluated:
            return canonical(c)
    return None


def assess(view: Mapping, canonical: Callable[[str], str] = lambda r: r) -> dict | None:
    """The success criterion against the current evaluation (``view.criterion``), or None in
    a study without the decision.

    ``status``: ``met`` (the gain reaches the minimum and the paired interval excludes 0),
    ``uncertain`` (the point gain reaches it but the interval includes 0), ``not_met``, or
    ``not_assessed`` (no confirmed criterion, or no current evaluation of the adopted
    rule, the open policy proposal, or the models). ``contradicts_verdict`` is true when the
    conclusion (confirmed, to confirm again, or proposed) adopts while the status is
    ``not_met`` or ``uncertain``: ``check`` then warns ``verdict_contradicts_criterion``.
    """
    decisions = view.get('decisions') or {}
    decision = decisions.get('success_criterion')
    if decision is None:
        return None
    task = view.get('task') or 'binary'
    value = decision.get('value') if decision.get('status') in (
        'confirmed', 'reconfirm_required') else None
    out = {'decision_status': decision.get('status'), 'value': copy.deepcopy(value),
           'metric': CRITERION_METRICS[task], 'status': 'not_assessed', 'result_id': None,
           'rule': None, 'model': None, 'gain': None, 'low': None, 'high': None,
           'minimum': None, 'unit': 'percentage points' if task == 'binary' else 'share',
           'interval_includes_zero': None, 'verdict': None, 'contradicts_verdict': False}
    conclusion = decisions.get('conclusion') or {}
    verdict = conclusion.get('value', {}).get('verdict') \
        if isinstance(conclusion.get('value'), Mapping) else None
    out['verdict'] = verdict
    results = view.get('results') or {}
    if isinstance(value, Mapping):
        if task == 'binary':
            item = results.get('policy.evaluation')
            if _citable(item):
                rules = item['values'].get('rules') or {}
                evaluated = {canonical(r): r for r in rules}
                rule = _rule(decisions, view.get('open_proposals') or [], list(evaluated),
                             canonical)
                delta = (((rules.get(evaluated.get(rule)) or {}).get('deltas') or {})
                         .get('fit.logistic') or {}).get('precision') if rule else None
                if isinstance(delta, Mapping) and isinstance(delta.get('point'), (int, float)):
                    out.update(result_id=item['result_id'], rule=rule, model='fit.logistic',
                               gain=100 * delta['point'], minimum=value['min_points'],
                               low=100 * delta['low'] if delta.get('low') is not None else None,
                               high=100 * delta['high'] if delta.get('high') is not None else None)
        else:
            item = results.get('evaluate.regression')
            if _citable(item):
                vals = item['values']
                base = ((vals.get('models') or {}).get('fit.baseline') or {}).get('mae')
                delta = ((vals.get('deltas') or {}).get('fit.linear') or {}).get('mae')
                if isinstance(base, (int, float)) and base > 0 and isinstance(delta, Mapping) \
                        and isinstance(delta.get('point'), (int, float)):
                    out.update(result_id=item['result_id'], model='fit.linear',
                               gain=-delta['point'] / base, minimum=value['min_share'],
                               low=-delta['high'] / base, high=-delta['low'] / base)
        if out['gain'] is not None:
            includes = (out['low'] is not None and out['high'] is not None
                        and out['low'] <= 0 <= out['high'])
            out['interval_includes_zero'] = includes
            reached = out['gain'] >= out['minimum'] - 1e-12
            out['status'] = 'not_met' if not reached else ('uncertain' if includes else 'met')
    out['contradicts_verdict'] = verdict in ADOPT_VERDICTS and out['status'] in ('not_met',
                                                                                 'uncertain')
    return out
