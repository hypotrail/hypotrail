"""Evidently diagnostics profile (extra ``diagnostics``; spec L-13, L-14; AC12).

A versioned profile (``hypotrail.diagnostic_profile/1``) states, for every checked column,
its type, the method, the statistic it yields (a p-value or a distance), the threshold, the
comparison that raises an alert (``lt`` for a p-value, ``ge`` for a distance: never inferred
from the method's name), the minimum observations and how missing values are treated
(excluded from the distribution test and reported by their own data-quality check). Nothing
is chosen from the sample size. Families stay separate:

* ``data_quality``: missing-value share change, categories unseen in the reference;
* ``marginal_distribution``: one column at a time (Evidently ``ValueDrift``);
* ``relationship``: change of a declared pair's correlation (pandas), which marginal tests
  cannot see;
* ``performance``: only when labels and predictions of both populations are authorised.

P-value checks of one profile form the declared family; with ``correction: holm`` the
adjusted p-values decide the alerts, otherwise the alerts are exploratory and uncorrected.
The thresholds of :data:`DEMONSTRATION_PROFILE` are demonstration values, not business
guarantees. No alert never means "the model is still valid".

Evidently runs only on frames the caller is authorised to read
(``partition_not_authorized`` otherwise), locally (no remote service). A backend exception
makes its check ``failed`` with the cause and ``alert: null``; a check without enough
observations is ``insufficient_data``. The Evidently snapshot is kept as a versioned annex
(``raw``); the Hypotrail result (``hypotrail.diagnostic_result/1``) is the interface.
"""
from __future__ import annotations

import math
from typing import Iterable, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt

from hypotrail_runtime import canonical
from hypotrail_runtime.contracts import DiagnosticResult, parse
from hypotrail_runtime.errors import ContractError

PROFILE_SCHEMA = 'hypotrail.diagnostic_profile/1'
STATISTICS = {'ks': 'p_value', 'chisquare': 'p_value', 'z': 'p_value', 'fisher_exact': 'p_value',
              'wasserstein': 'distance', 'jensenshannon': 'distance', 'psi': 'distance',
              'kl_div': 'distance', 'hellinger': 'distance'}


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', frozen=True, allow_inf_nan=False)


class ColumnCheck(_Strict):
    kind: Literal['numerical', 'categorical']
    method: Literal['ks', 'chisquare', 'z', 'fisher_exact', 'wasserstein', 'jensenshannon',
                    'psi', 'kl_div', 'hellinger']
    statistic: Literal['p_value', 'distance']
    threshold: StrictFloat
    comparison: Literal['lt', 'le', 'gt', 'ge']
    min_observations: StrictInt = Field(ge=1)
    missing: Literal['excluded_and_reported'] = 'excluded_and_reported'


class Relationship(_Strict):
    columns: tuple[str, str]
    method: Literal['pearson', 'spearman']
    threshold: StrictFloat
    comparison: Literal['ge', 'gt'] = 'ge'


class Performance(_Strict):
    metric: Literal['mae', 'roc_auc']
    threshold: StrictFloat
    comparison: Literal['ge', 'gt'] = 'ge'


class Profile(_Strict):
    schema_version: Literal['hypotrail.diagnostic_profile/1']
    name: str
    version: StrictInt = Field(ge=1)
    columns: dict[str, ColumnCheck]
    missing_share_threshold: StrictFloat = Field(ge=0)
    unknown_category_share_threshold: StrictFloat = Field(ge=0)
    relationships: list[Relationship] = []
    performance: Optional[Performance] = None
    multiple_testing: Literal['holm', 'none_exploratory']
    demonstration_thresholds: StrictBool


def demonstration_profile(columns: Mapping[str, str], *, relationships=(),
                          performance: str | None = None) -> Profile:
    """A profile with demonstration thresholds: KS (p < 0.05) for numerical columns,
    chi-square (p < 0.05) for categorical ones, Holm across the family; missing share and
    unknown categories at 5 %; a relationship change of 0.3; a performance loss of 0.05."""
    checks = {}
    for name, kind in columns.items():
        method = 'ks' if kind == 'numerical' else 'chisquare'
        checks[name] = {'kind': kind, 'method': method, 'statistic': 'p_value',
                        'threshold': 0.05, 'comparison': 'lt', 'min_observations': 30}
    doc = {'schema_version': PROFILE_SCHEMA, 'name': 'demonstration', 'version': 1,
           'columns': checks, 'missing_share_threshold': 0.05,
           'unknown_category_share_threshold': 0.05,
           'relationships': [{'columns': list(p), 'method': 'pearson', 'threshold': 0.3}
                             for p in relationships],
           'performance': ({'metric': performance, 'threshold': 0.05}
                           if performance else None),
           'multiple_testing': 'holm', 'demonstration_thresholds': True}
    return profile_of(doc)


def profile_of(doc) -> Profile:
    if isinstance(doc, Profile):
        return doc
    try:
        profile = Profile.model_validate(dict(doc), strict=False)
    except Exception as exc:
        raise ContractError('contract_invalid', f'Invalid diagnostic profile: {exc}',
                            path='profile', remediation='Declare every method, threshold and '
                                                        'comparison explicitly.') from None
    for name, check in profile.columns.items():
        if STATISTICS[check.method] != check.statistic:
            raise ContractError('contract_invalid', f'{check.method} yields a '
                                f'{STATISTICS[check.method]}, not a {check.statistic}.',
                                path=f'profile/columns/{name}',
                                remediation='Declare the statistic the method yields.')
    return profile


def _alert(value: float, threshold: float, comparison: str) -> bool:
    value, threshold = float(value), float(threshold)
    return {'lt': value < threshold, 'le': value <= threshold, 'gt': value > threshold,
            'ge': value >= threshold}[comparison]


def holm(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (monotone, capped at 1)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def _check(**fields) -> dict:
    base = {'reference_partition': None, 'n_reference': None, 'statistic_name': None,
            'statistic_value': None, 'p_value': None, 'adjusted_p_value': None,
            'effect_size': None, 'threshold': None, 'comparison': None, 'alert': None,
            'reason': None}
    return {**base, **fields}


def _versions() -> dict:
    import evidently
    return {'distribution': 'evidently', 'version': evidently.__version__}


def run(profile, reference, current, *, reference_partition: str, current_partition: str,
        authorized: Iterable[str], labels: Mapping | None = None) -> dict:
    """``{result: DiagnosticResult, raw}`` comparing ``current`` with ``reference``.

    ``labels`` (optional, only when both populations' labels are authorised):
    ``{'reference': (y, prediction), 'current': (y, prediction)}``."""
    profile = profile_of(profile)
    allowed = set(authorized)
    for part in (reference_partition, current_partition):
        if part not in allowed:
            raise ContractError('partition_not_authorized',
                                f'Diagnostics may not read the {part} rows here.',
                                path='partition', remediation='Diagnose authorised '
                                'populations only; the final test is never read here.',
                                details={'partition': part, 'authorized': sorted(allowed)})
    try:
        backend = _versions()
        from evidently import DataDefinition, Dataset, Report
        from evidently.metrics import ValueDrift
    except ImportError as exc:
        raise ContractError('optional_dependency_missing', 'Evidently is not installed.',
                            remediation='Install the diagnostics extra; the base workflow '
                                        'does not need it.', details={'error': str(exc)}) \
            from None
    import numpy as np
    checks: list[dict] = []
    raw: dict = {'evidently_version': backend['version'], 'metrics': {}}
    common = {'reference_partition': reference_partition, 'current_partition': current_partition}
    n_ref_rows, n_cur_rows = int(len(reference)), int(len(current))
    for name, spec in profile.columns.items():
        ref_col, cur_col = reference[name], current[name]
        # data quality: the missing share (reported separately from the distribution test)
        miss_ref, miss_cur = float(ref_col.isna().mean()) if n_ref_rows else None, \
            float(cur_col.isna().mean()) if n_cur_rows else None
        if miss_ref is None or miss_cur is None:
            checks.append(_check(id=f'missing_share:{name}', family='data_quality',
                                 column_or_pair=[name], **common, n_reference=n_ref_rows,
                                 n_current=n_cur_rows, status='insufficient_data',
                                 reason='an empty population'))
        else:
            diff = abs(miss_cur - miss_ref)
            checks.append(_check(id=f'missing_share:{name}', family='data_quality',
                                 column_or_pair=[name], **common, n_reference=n_ref_rows,
                                 n_current=n_cur_rows, statistic_name='abs_missing_share_change',
                                 statistic_value=diff, effect_size=miss_cur - miss_ref,
                                 threshold=profile.missing_share_threshold, comparison='ge',
                                 alert=_alert(diff, profile.missing_share_threshold, 'ge'),
                                 status='ok'))
        if spec.kind == 'categorical':
            seen = set(ref_col.dropna().astype(str))
            cur_text = cur_col.dropna().astype(str)
            if len(cur_text):
                share = float((~cur_text.isin(seen)).mean())
                checks.append(_check(
                    id=f'unknown_categories:{name}', family='data_quality',
                    column_or_pair=[name], **common, n_reference=int(ref_col.notna().sum()),
                    n_current=int(len(cur_text)), statistic_name='unknown_category_share',
                    statistic_value=share, threshold=profile.unknown_category_share_threshold,
                    comparison='ge',
                    alert=_alert(share, profile.unknown_category_share_threshold, 'ge'),
                    status='ok'))
        # marginal distribution (missing values excluded, minimum observations enforced)
        n_ref, n_cur = int(ref_col.notna().sum()), int(cur_col.notna().sum())
        check_id = f'{spec.method}:{name}'
        base = dict(id=check_id, family='marginal_distribution', column_or_pair=[name],
                    **common, n_reference=n_ref, n_current=n_cur,
                    statistic_name=f'{spec.method}_{spec.statistic}',
                    threshold=spec.threshold, comparison=spec.comparison)
        if min(n_ref, n_cur) < spec.min_observations:
            checks.append(_check(**base, status='insufficient_data',
                                 reason=f'fewer than {spec.min_observations} non-missing '
                                        'observations in a population'))
            continue
        definition = DataDefinition(numerical_columns=[name] if spec.kind == 'numerical' else [],
                                    categorical_columns=[name] if spec.kind == 'categorical'
                                    else [])
        try:
            snapshot = Report([ValueDrift(column=name, method=spec.method,
                                          threshold=spec.threshold)]).run(
                Dataset.from_pandas(current[[name]], data_definition=definition),
                Dataset.from_pandas(reference[[name]], data_definition=definition))
            payload = snapshot.dict()
            value = payload['metrics'][0]['value']
            raw['metrics'][check_id] = payload['metrics'][0]
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f'non-finite statistic {value!r}')
        except Exception as exc:          # noqa: BLE001 - the cause is the result
            checks.append(_check(**base, status='failed',
                                 reason=f'backend_failed: {type(exc).__name__}: {exc}'[:300]))
            continue
        item = _check(**base, status='ok', statistic_value=value)
        if spec.statistic == 'p_value':
            item['p_value'] = value
        item['alert'] = _alert(value, spec.threshold, spec.comparison)
        checks.append(item)
    # relationships between declared pairs
    for rel in profile.relationships:
        a, b = rel.columns
        pair_ref, pair_cur = reference[[a, b]].dropna(), current[[a, b]].dropna()
        base = dict(id=f'{rel.method}:{a}~{b}', family='relationship', column_or_pair=[a, b],
                    **common, n_reference=int(len(pair_ref)), n_current=int(len(pair_cur)),
                    statistic_name=f'abs_{rel.method}_change', threshold=rel.threshold,
                    comparison=rel.comparison)
        if min(len(pair_ref), len(pair_cur)) < 3:
            checks.append(_check(**base, status='insufficient_data', reason='fewer than 3 pairs'))
            continue
        r_ref = pair_ref[a].corr(pair_ref[b], method=rel.method)
        r_cur = pair_cur[a].corr(pair_cur[b], method=rel.method)
        if not (math.isfinite(r_ref) and math.isfinite(r_cur)):
            checks.append(_check(**base, status='insufficient_data',
                                 reason='a correlation is undefined (constant column)'))
            continue
        diff = abs(r_cur - r_ref)
        checks.append(_check(**base, status='ok', statistic_value=float(diff),
                             effect_size=float(r_cur - r_ref),
                             alert=_alert(diff, rel.threshold, rel.comparison)))
    # performance on labelled rows, only when authorised
    if profile.performance is not None:
        perf = profile.performance
        base = dict(id=f'performance:{perf.metric}', family='performance', column_or_pair=[],
                    **common, statistic_name=f'{perf.metric}_degradation',
                    threshold=perf.threshold, comparison=perf.comparison)
        if not labels:
            checks.append(_check(**base, n_current=n_cur_rows, status='not_applicable',
                                 reason='labels of both populations are not authorised here'))
        else:
            from mlkit.study import metrics
            values = {}
            for side in ('reference', 'current'):
                y, pred = (np.asarray(v, dtype=float) for v in labels[side])
                if perf.metric == 'mae':
                    values[side] = float(np.mean(np.abs(y - pred))) if len(y) else None
                else:
                    values[side] = metrics.roc_auc(y.astype(int), pred)
            if None in values.values():
                checks.append(_check(**base, n_current=len(labels['current'][0]),
                                     status='insufficient_data',
                                     reason='the metric is undefined in a population'))
            else:
                loss = (values['current'] - values['reference'] if perf.metric == 'mae'
                        else values['reference'] - values['current'])
                checks.append(_check(**base, n_reference=len(labels['reference'][0]),
                                     n_current=len(labels['current'][0]), status='ok',
                                     statistic_value=float(loss), effect_size=float(loss),
                                     alert=_alert(loss, perf.threshold, perf.comparison)))
    # the declared multiple-testing family: p-value checks of the marginal family
    family = [c for c in checks if c['p_value'] is not None and c['status'] == 'ok']
    warnings = []
    if profile.multiple_testing == 'holm' and family:
        for c, adj in zip(family, holm([c['p_value'] for c in family])):
            c['adjusted_p_value'] = adj
            c['alert'] = _alert(adj, c['threshold'], c['comparison'])
    elif family:
        warnings.append('Alerts are exploratory: p-values are not corrected for multiplicity.')
    if profile.demonstration_thresholds:
        warnings.append('Thresholds are demonstration values, not business guarantees.')
    warnings.append('No alert does not mean the model is still valid; a marginal test does '
                    'not see relationships it does not measure.')
    computed = [c for c in checks if c['status'] == 'ok']
    if not checks or (checks and all(c['status'] == 'failed' for c in checks)):
        status, reason = 'failed', 'every check failed in the backend'
    elif not computed:
        status, reason = 'insufficient_data', 'no check could be computed'
    else:
        status, reason = 'ok', None
    if any(c['alert'] for c in computed):
        alert = True
    elif any(c['status'] != 'ok' for c in checks if c['status'] != 'not_applicable'):
        alert = None
    else:
        alert = False
    doc = {'schema_version': 'hypotrail.diagnostic_result/1', 'result_id': '0' * 64,
           'status': status, 'reason': reason, 'context': None, 'backend': backend,
           'method': {'name': 'hypotrail.diagnostics.evidently', 'version': '1',
                      'parameters': profile.model_dump(mode='json')},
           'warnings': warnings, 'artifact_refs': ['evidently_snapshot'], 'checks': checks,
           'alert': alert, 'extensions': {'hypotrail.rows': {'reference': n_ref_rows,
                                                            'current': n_cur_rows}}}
    doc['result_id'] = canonical.artifact_id(doc, exclude=('result_id',))
    return {'result': parse(DiagnosticResult, doc), 'raw': raw}
