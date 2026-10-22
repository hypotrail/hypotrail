"""Generate a synthetic binary case with planted traps and a known truth.

The case describes a fictitious library network (the Quillmere Library
Network) that sends renewal reminders to members whose membership has
expired. Nothing here comes from a public dataset, so no memorised recipe
applies: an agent that handles the traps must do so from the case
documentation and the data alone.

``make_case(out_dir, ...)`` writes three files into ``out_dir`` and nowhere
else:

* ``data.csv``: semicolon-separated data, one physical line per row;
* ``case.yaml``: the static case contract (``hypotrail.case/1``) that an agent
  under test may read;
* ``truth.json``: the generating truth. It must NEVER be shown to an agent
  under test; it exists for graders and unit tests.

The output is a pure function of ``seed`` and the options: the same inputs
give the same bytes. Randomness comes only from ``Generator.random()`` on
PCG64 streams derived from ``SeedSequence([seed, stream])``; every other
distribution is obtained by inverse transform in this module, so the bytes do
not depend on numpy's sampling algorithms for specific distributions.

Run as a script to write a case for manual inspection:

    python framework/tests/fixtures/synthetic/make_case.py OUT_DIR --seed 7
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import yaml

GENERATOR_VERSION = 1
SEP = ';'
TRAIN_FRACTION = 0.7
CASE_ID = 'synthetic-renewal-reminders'
DOMAIN = 'Quillmere Library Network'

# Generating model. Only these three columns influence the target.
COEF_SIGNAL = 1.0                       # holds_open, log-odds per unit (0/1)
COEF_VISIT_BAND = 0.4                   # visit_band, log-odds per band (0..3)
COEF_PRIOR_LAPSE = -0.6                 # 1 when the member lapsed before
P_SIGNAL = 0.35
VISIT_BAND_PROBS = (0.30, 0.35, 0.25, 0.10)
P_PRIOR_LAPSE = 0.42
# Leakage column: desk follow-ups logged after the outcome is recorded.
LEAK_MEAN_POSITIVE = 2.5                # 1 + Poisson(2.5) when renewed
LEAK_MEAN_NEGATIVE = 0.3                # Poisson(0.3) when lapsed
# Reminder stopping rule: reminders stop once the member renews.
REMINDERS_IF_POSITIVE = (0.45, 0.30, 0.15, 0.10)   # P(reminders_sent = 1..4)
P_FULL_SEQUENCE_IF_NEGATIVE = 0.85                  # else 3 (member opted out)

BRANCHES = ('Alder', 'Brook', 'Cedar', 'Dune', 'Elm')
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')
LAPSE_REASONS = ('moved', 'fees', 'no_time', 'other')
LAPSE_SENTINEL_DAYS = -1
LAPSE_SENTINEL_REASON = 'unknown'
GROUP_SIZE_PROBS = (0.5, 0.25, 0.15, 0.10)          # sizes 1..4
TIME_START = _dt.date(2023, 1, 1)
TIME_SPAN_DAYS = 731

STREAM_BASE, STREAM_GROUPS, STREAM_TIME, STREAM_DEDUP, STREAM_DUPLICATES, STREAM_SPLIT = range(6)


def _rng(seed: int, stream: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream])))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _categorical(u: float, probs) -> int:
    acc = 0.0
    for i, p in enumerate(probs):
        acc += p
        if u < acc:
            return i
    return len(probs) - 1


def _poisson_pmf(mean: float, kmax: int = 80) -> list[float]:
    return [math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1)) for k in range(kmax)]


def _poisson(u: float, mean: float) -> int:
    k, p = 0, math.exp(-mean)
    acc = p
    while u >= acc and k < 200:
        k += 1
        p *= mean / k
        acc += p
    return k


def _cells():
    """Enumerate the joint distribution of the three generating columns."""
    for s, ps in ((0, 1 - P_SIGNAL), (1, P_SIGNAL)):
        for d, pd_ in enumerate(VISIT_BAND_PROBS):
            for lapse, pl in ((0, 1 - P_PRIOR_LAPSE), (1, P_PRIOR_LAPSE)):
                yield s, d, lapse, ps * pd_ * pl


def _linear(intercept: float, s: int, d: int, lapse: int) -> float:
    return intercept + COEF_SIGNAL * s + COEF_VISIT_BAND * d + COEF_PRIOR_LAPSE * lapse


def _marginal_rate(intercept: float) -> float:
    return sum(w * _sigmoid(_linear(intercept, s, d, lapse)) for s, d, lapse, w in _cells())


def _solve_intercept(positive_rate: float) -> float:
    lo, hi = -30.0, 30.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _marginal_rate(mid) < positive_rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _conditional_rate(intercept: float, s_value: int) -> float:
    num = den = 0.0
    for s, d, lapse, w in _cells():
        if s == s_value:
            num += w * _sigmoid(_linear(intercept, s, d, lapse))
            den += w
    return num / den


def _leak_auc() -> float:
    """Exact P(L1 > L0) + P(L1 = L0) / 2 for the two class distributions."""
    p0 = _poisson_pmf(LEAK_MEAN_NEGATIVE)
    p1 = [0.0] + _poisson_pmf(LEAK_MEAN_POSITIVE)[:-1]
    auc = 0.0
    for a, pa in enumerate(p1):
        below = sum(p0[:a])
        auc += pa * (below + 0.5 * (p0[a] if a < len(p0) else 0.0))
    return auc


def _r(x: float) -> float:
    return round(float(x), 10)


def _fmt(value) -> str:
    if isinstance(value, float):
        return f'{value:.2f}'
    return str(value)


def _base_rows(seed: int, n_rows: int, intercept: float) -> list[dict]:
    rng = _rng(seed, STREAM_BASE)
    u = rng.random((n_rows, 14))
    rows = []
    for i in range(n_rows):
        r = u[i]
        s = int(r[0] < P_SIGNAL)
        d = _categorical(r[1], VISIT_BAND_PROBS)
        lapse = int(r[2] < P_PRIOR_LAPSE)
        p = _sigmoid(_linear(intercept, s, d, lapse))
        y = int(r[3] < p)
        if lapse:
            days = 30 + int(r[4] * 871)
            reason = LAPSE_REASONS[_categorical(r[5], (0.3, 0.3, 0.25, 0.15))]
        else:
            days, reason = LAPSE_SENTINEL_DAYS, LAPSE_SENTINEL_REASON
        if y:
            reminders = 1 + _categorical(r[6], REMINDERS_IF_POSITIVE)
            leak = 1 + _poisson(r[7], LEAK_MEAN_POSITIVE)
        else:
            reminders = 4 if r[6] < P_FULL_SEQUENCE_IF_NEGATIVE else 3
            leak = _poisson(r[7], LEAK_MEAN_NEGATIVE)
        fines = 0.0 if r[8] < 0.7 else round(-math.log(1.0 - r[9]) * 8.0 + 0.5, 2)
        rows.append({
            'member_age': 16 + int(r[10] * 69),
            'home_branch': BRANCHES[int(r[11] * len(BRANCHES))],
            'membership_days': 30 + int(r[12] * 9000),
            'fines_outstanding': fines,
            'desk_followups': leak,
            'holds_open': s,
            'visit_band': d,
            'days_since_last_lapse': days,
            'last_lapse_reason': reason,
            'reminders_sent': reminders,
            'last_reminder_weekday': WEEKDAYS[int(r[13] * len(WEEKDAYS))],
            'outcome': 'renewed' if y else 'lapsed',
            '_p': p,
        })
    return rows


def _assign_groups(seed: int, rows: list[dict]) -> None:
    rng = _rng(seed, STREAM_GROUPS)
    labels, gid = [], 0
    while len(labels) < len(rows):
        gid += 1
        size = 1 + _categorical(float(rng.random()), GROUP_SIZE_PROBS)
        labels.extend([gid] * size)
    labels = labels[:len(rows)]
    order = np.argsort(rng.random(len(rows)), kind='stable')
    first: dict[int, dict] = {}
    for i, idx in enumerate(order):
        row, g = rows[int(idx)], labels[i]
        row['member_ref'] = f'M{g:05d}'
        if g in first:   # repeated cycles of one member share these attributes
            row['member_age'] = first[g]['member_age']
            row['home_branch'] = first[g]['home_branch']
        else:
            first[g] = row


def _assign_time(seed: int, rows: list[dict]) -> None:
    u = _rng(seed, STREAM_TIME).random(len(rows))
    for row, v in zip(rows, u):
        row['cycle_start_date'] = (TIME_START + _dt.timedelta(days=int(v * TIME_SPAN_DAYS))).isoformat()


def _line(row: dict, columns: list[str]) -> str:
    return SEP.join(_fmt(row[c]) for c in columns)


def _remove_accidental_duplicates(seed: int, rows: list[dict], columns: list[str]) -> int:
    """Redraw the noise column membership_days until all base rows are distinct."""
    rng = _rng(seed, STREAM_DEDUP)
    seen, redraws = set(), 0
    for row in rows:
        while (text := _line(row, columns)) in seen:
            row['membership_days'] = 30 + int(float(rng.random()) * 9000)
            redraws += 1
        seen.add(text)
    return redraws


def _variable_dictionary(groups: bool, time: bool) -> list[dict]:
    def avail(value, status, source):
        return {'value': value, 'status': status, 'source': source}

    office = 'Membership office data dictionary (fictitious)'
    assumed = avail('available_at_prediction', 'scenario_assumption',
                    'Plausible for a member attribute; not stated by the membership office')
    entries = []
    if groups:
        entries.append({
            'name': 'member_ref', 'type': 'string', 'role': 'group_id',
            'description': 'Member reference. A member can appear in several renewal cycles.',
            'status': 'documented_fact', 'source': office,
            'availability': avail('available_at_prediction', 'scenario_assumption',
                                  'An identifier is known before reminders are sent; not stated'),
            'special_values': []})
    if time:
        entries.append({
            'name': 'cycle_start_date', 'type': 'date', 'format': 'YYYY-MM-DD', 'role': 'time',
            'description': 'Date on which the renewal cycle opened (membership expiry date).',
            'status': 'documented_fact', 'source': office,
            'availability': avail('available_at_prediction', 'scenario_assumption',
                                  'The cycle opens before any reminder; not stated'),
            'special_values': []})
    entries += [
        {'name': 'member_age', 'type': 'integer', 'unit': 'years', 'role': 'feature',
         'description': 'Age of the member when the renewal cycle opened.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'home_branch', 'type': 'category', 'role': 'feature',
         'description': 'Branch where the member registered.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'membership_days', 'type': 'integer', 'unit': 'days', 'role': 'feature',
         'description': 'Days between first registration and the opening of the renewal cycle.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'fines_outstanding', 'type': 'numeric', 'role': 'feature',
         'description': 'Not described by the membership office. Values are non-negative amounts '
                        'with two decimals; the unit and the date of the snapshot are not known.',
         'status': 'observed', 'source': 'Inspection of the file',
         'availability': avail('unknown', 'unknown', 'Snapshot date not documented'),
         'special_values': []},
        {'name': 'desk_followups', 'type': 'integer', 'unit': 'entries', 'role': 'feature',
         'description': 'Number of desk follow-up entries logged for the member during the 30 days '
                        'after the renewal cycle closed. The cycle closes when its outcome is '
                        'recorded, so this count is recorded after the outcome.',
         'status': 'documented_fact', 'source': office,
         'availability': avail('not_available', 'documented_fact',
                               'Recorded after the outcome, per the membership office'),
         'special_values': []},
        {'name': 'holds_open', 'type': 'binary', 'role': 'feature',
         'description': '1 if the member had at least one open hold request when the cycle opened.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'visit_band', 'type': 'ordinal', 'role': 'feature',
         'description': 'Branch visits in the 12 months before the cycle opened: '
                        '0 none, 1 one to four, 2 five to twelve, 3 thirteen or more.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'days_since_last_lapse', 'type': 'integer', 'unit': 'days', 'role': 'feature',
         'description': 'Days between the end of the previous lapsed membership and the opening '
                        'of this cycle.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': [{'value': LAPSE_SENTINEL_DAYS,
                             'meaning': 'The member never let a previous membership lapse',
                             'status': 'documented_fact', 'source': office}]},
        {'name': 'last_lapse_reason', 'type': 'category', 'role': 'feature',
         'description': 'Reason given by the member for the previous lapse.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': [{'value': LAPSE_SENTINEL_REASON,
                             'meaning': 'Not documented by the membership office',
                             'status': 'unknown', 'source': office}]},
        {'name': 'reminders_sent', 'type': 'integer', 'unit': 'reminders', 'role': 'feature',
         'description': 'Number of reminders sent during the current renewal cycle, including the '
                        'last one. The schedule has at most four reminders.',
         'status': 'documented_fact', 'source': office,
         'availability': avail('unknown', 'unknown',
                               'Depends on when the prediction is made; the prediction time is '
                               'not specified'),
         'special_values': []},
        {'name': 'last_reminder_weekday', 'type': 'category', 'role': 'feature',
         'description': 'Weekday on which the last reminder of the current cycle was sent.',
         'status': 'documented_fact', 'source': office,
         'availability': avail('unknown', 'unknown',
                               'Describes the last reminder; the prediction time is not specified'),
         'special_values': []},
        {'name': 'outcome', 'type': 'binary', 'role': 'target',
         'description': 'Renewal outcome recorded when the cycle closed: renewed or lapsed.',
         'status': 'documented_fact', 'source': office,
         'availability': avail('not_available', 'documented_fact', 'The outcome itself'),
         'special_values': []},
    ]
    return entries


def _case_document(data_sha: str, n_total: int, columns: list[str], groups: bool,
                   time: bool) -> dict:
    variables = _variable_dictionary(groups, time)
    assert [v['name'] for v in variables] == columns
    special = [{'column': v['name'], **sv} for v in variables for sv in v['special_values']]
    return {
        'schema': 'hypotrail.case/1',
        'id': CASE_ID,
        'title': f'Renewal reminders · {DOMAIN} (synthetic)',
        'description': 'Members whose library membership expired receive up to four renewal '
                       'reminders. Volunteers can phone only some of them. Which members should '
                       'be phoned first?',
        'provenance': {
            'kind': 'synthetic',
            'note': 'Generated by framework/tests/fixtures/synthetic/make_case.py; the library '
                    'network is fictitious.',
        },
        'dataset': {
            'path': 'data.csv', 'format': 'csv', 'sep': SEP, 'encoding': 'utf-8',
            'decimal': '.', 'header': True, 'sha256': data_sha, 'rows': n_total,
            'columns': len(columns),
        },
        'target': {'column': 'outcome', 'positive_label': 'renewed', 'negative_label': 'lapsed'},
        'row_key': {
            'rule': 'source_line',
            'format': 'L<line>',
            'description': 'Physical 1-based line number in data.csv; the header is line 1, so '
                           'the first data row is L2. The key is anchored to the dataset sha256.',
        },
        'facts': [
            {'id': 'observation_unit', 'value': 'One renewal cycle of one expired membership',
             'status': 'documented_fact', 'source': 'Membership office data dictionary (fictitious)'},
            {'id': 'intended_use', 'value': 'Prioritise volunteer phone calls when capacity is limited',
             'status': 'scenario_assumption', 'source': 'Case scenario'},
            {'id': 'prediction_time', 'value': 'Not specified by the membership office',
             'status': 'unknown', 'source': 'Case scenario'},
            {'id': 'causal_effect', 'value': 'The effect of a phone call on renewal is not measured',
             'status': 'unknown', 'source': 'Observational records'},
        ],
        'variables': variables,
        'special_values': special,
        'structure': {
            'row_unit': {'value': 'renewal cycle', 'status': 'documented_fact',
                         'source': 'Membership office data dictionary (fictitious)'},
            'group_column': ({'value': 'member_ref', 'status': 'documented_fact',
                              'source': 'Membership office data dictionary (fictitious)'}
                             if groups else
                             {'value': None, 'status': 'unknown',
                              'source': 'No member identifier in the extract'}),
            'time_column': ({'value': 'cycle_start_date', 'status': 'documented_fact',
                             'source': 'Membership office data dictionary (fictitious)'}
                            if time else
                            {'value': None, 'status': 'unknown',
                             'source': 'No complete date in the extract'}),
            'duplicates': {'value': None, 'status': 'unknown', 'source': 'Not documented'},
        },
        'task': 'binary',
    }


def make_case(out_dir, seed: int = 20261018, n_rows: int = 4000, positive_rate: float = 0.12,
              duplicates: int = 0, groups: bool = False, time: bool = False,
              task: str = 'binary') -> dict[str, Path]:
    """Write data.csv, case.yaml and truth.json into ``out_dir``; return their paths.

    ``n_rows`` is the number of distinct generated rows; ``duplicates`` exact copies of
    randomly chosen rows are inserted on top, so the file has ``n_rows + duplicates`` rows.
    ``positive_rate`` is the expected share of the positive label under the generating model.

    ``task='regression'`` writes the regression variant instead (:func:`make_regression_case`:
    a numeric target with known linear effects and noise); ``positive_rate`` is then unused.
    The binary output is unchanged by this option.
    """
    if task == 'regression':
        return make_regression_case(out_dir, seed=seed, n_rows=n_rows, duplicates=duplicates,
                                    groups=groups, time=time)
    if task != 'binary':
        raise ValueError('task is "binary" or "regression"')
    if not 0.0 < positive_rate < 1.0:
        raise ValueError('positive_rate must be strictly between 0 and 1')
    if n_rows < 100:
        raise ValueError('n_rows must be at least 100')
    if duplicates < 0 or duplicates > n_rows:
        raise ValueError('duplicates must be between 0 and n_rows')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    intercept = _solve_intercept(positive_rate)
    rows = _base_rows(seed, n_rows, intercept)
    if groups:
        _assign_groups(seed, rows)
    if time:
        _assign_time(seed, rows)
    columns = ((['member_ref'] if groups else []) + (['cycle_start_date'] if time else []) + [
        'member_age', 'home_branch', 'membership_days', 'fines_outstanding', 'desk_followups',
        'holds_open', 'visit_band', 'days_since_last_lapse', 'last_lapse_reason',
        'reminders_sent', 'last_reminder_weekday', 'outcome'])
    redraws = _remove_accidental_duplicates(seed, rows, columns)

    # Insert exact copies at random positions; remember which base row each copies.
    for i, row in enumerate(rows):
        row['_base'] = i
    final = list(rows)
    if duplicates:
        rng = _rng(seed, STREAM_DUPLICATES)
        sources = np.argsort(rng.random(n_rows), kind='stable')[:duplicates]
        for src in sources:
            pos = int(float(rng.random()) * (len(final) + 1))
            final.insert(pos, dict(rows[int(src)], _copy=True))

    lines = [SEP.join(columns)] + [_line(r, columns) for r in final]
    data = ('\n'.join(lines) + '\n').encode('utf-8')
    data_path = out / 'data.csv'
    data_path.write_bytes(data)
    data_sha = hashlib.sha256(data).hexdigest()
    keys = [f'L{i + 2}' for i in range(len(final))]
    n_total = len(final)

    case = _case_document(data_sha, n_total, columns, groups, time)
    case_path = out / 'case.yaml'
    case_path.write_text(yaml.safe_dump(case, sort_keys=False, allow_unicode=True, width=100),
                         encoding='utf-8')

    y = np.array([r['outcome'] == 'renewed' for r in final], dtype=int)
    split_rng = _rng(seed, STREAM_SPLIT)
    order = np.argsort(split_rng.random(n_total), kind='stable')
    n_train = int(round(TRAIN_FRACTION * n_total))
    train_idx = np.sort(order[:n_train])
    train_set = set(int(i) for i in train_idx)

    by_base: dict[int, list[str]] = {}
    for key, r in zip(keys, final):
        by_base.setdefault(r['_base'], []).append(key)
    dup_pairs = [[ks[0], k] for ks in by_base.values() if len(ks) > 1 for k in ks[1:]]
    dup_pairs.sort(key=lambda p: (int(p[0][1:]), int(p[1][1:])))
    key_index = {k: i for i, k in enumerate(keys)}
    straddle = sum((key_index[a] in train_set) != (key_index[b] in train_set) for a, b in dup_pairs)

    p1, p0 = _conditional_rate(intercept, 1), _conditional_rate(intercept, 0)
    truth = {
        'schema': 'hypotrail.synthetic-truth/1',
        'warning': 'Never expose this file to an agent under test.',
        'generator': {'module': 'framework/tests/fixtures/synthetic/make_case.py',
                      'version': GENERATOR_VERSION, 'seed': seed,
                      'options': {'n_rows': n_rows, 'positive_rate': positive_rate,
                                  'duplicates': duplicates, 'groups': groups, 'time': time}},
        'data': {'path': 'data.csv', 'sep': SEP, 'sha256': data_sha, 'rows': n_total,
                 'distinct_rows': n_rows, 'columns': columns,
                 'row_keys': {'first': keys[0], 'last': keys[-1]},
                 'accidental_duplicate_redraws': redraws},
        'target': {'column': 'outcome', 'positive_label': 'renewed',
                   'model_positive_rate': _r(_marginal_rate(intercept)),
                   'observed_positive_count': int(y.sum()),
                   'observed_positive_rate': _r(y.mean())},
        'generating_model': {
            'link': 'logit',
            'formula': 'logit P(outcome=renewed) = intercept + b_signal*holds_open '
                       '+ b_band*visit_band + b_lapse*[days_since_last_lapse != -1]',
            'intercept': _r(intercept),
            'terms': [
                {'column': 'holds_open', 'coding': '0/1', 'coefficient': COEF_SIGNAL,
                 'distribution': {'p_one': P_SIGNAL}},
                {'column': 'visit_band', 'coding': 'integer 0..3', 'coefficient': COEF_VISIT_BAND,
                 'distribution': {'probabilities': list(VISIT_BAND_PROBS)}},
                {'column': 'days_since_last_lapse',
                 'coding': '1 if the value differs from -1 (member lapsed before)',
                 'coefficient': COEF_PRIOR_LAPSE, 'distribution': {'p_one': P_PRIOR_LAPSE}},
            ],
            'independent_of_target': ['member_age', 'home_branch', 'membership_days',
                                      'fines_outstanding', 'last_reminder_weekday']
                                     + (['member_ref'] if groups else [])
                                     + (['cycle_start_date'] if time else []),
            'generating_columns_independent': True,
        },
        'signal': {
            'column': 'holds_open', 'pre_decision': True,
            'coefficient_log_odds': COEF_SIGNAL,
            'rate_if_one': _r(p1), 'rate_if_zero': _r(p0),
            'risk_difference': _r(p1 - p0),
            'marginal_odds_ratio': _r((p1 / (1 - p1)) / (p0 / (1 - p0))),
            'note': 'Exact expectations under the generating model, marginal over the other terms.',
        },
        'leakage': {
            'column': 'desk_followups', 'recorded': 'after the outcome',
            'distribution_if_positive': f'1 + Poisson({LEAK_MEAN_POSITIVE})',
            'distribution_if_negative': f'Poisson({LEAK_MEAN_NEGATIVE})',
            'exact_auc': _r(_leak_auc()),
        },
        'ambiguous_availability': {
            'last_contact_columns': ['reminders_sent', 'last_reminder_weekday'],
            'reminders_sent': {
                'depends_on_target': True,
                'mechanism': 'Reminders stop once the member renews; it includes the last reminder.',
                'if_positive': {'values': [1, 2, 3, 4], 'probabilities': list(REMINDERS_IF_POSITIVE)},
                'if_negative': {'values': [3, 4], 'probabilities':
                                [_r(1 - P_FULL_SEQUENCE_IF_NEGATIVE), P_FULL_SEQUENCE_IF_NEGATIVE]},
            },
            'last_reminder_weekday': {'depends_on_target': False},
            'fines_outstanding': {'depends_on_target': False,
                                  'note': 'Snapshot date unknown in the case; noise in truth.'},
        },
        'sentinel': {
            'columns': {'days_since_last_lapse': LAPSE_SENTINEL_DAYS,
                        'last_lapse_reason': LAPSE_SENTINEL_REASON},
            'meaning': 'The member never lapsed before; both columns carry the sentinel on '
                       'exactly the same rows.',
            'count': sum(r['days_since_last_lapse'] == LAPSE_SENTINEL_DAYS for r in final),
            'row_keys': [k for k, r in zip(keys, final)
                         if r['days_since_last_lapse'] == LAPSE_SENTINEL_DAYS],
        },
        'ties': {
            'columns': ['holds_open', 'visit_band', 'days_since_last_lapse'],
            'note': 'The true score depends only on discrete inputs, so it takes few distinct '
                    'values and many rows share each one.',
            'distinct_true_scores': len({_r(_sigmoid(_linear(intercept, s, d, lapse)))
                                         for s, d, lapse, _ in _cells()}),
            'discrete_feature': 'visit_band',
        },
        'reference_split': {
            'purpose': 'Test reference only; not a human decision.',
            'recipe': 'order = argsort(Generator(PCG64(SeedSequence([seed, 5]))).random(rows), '
                      'kind="stable"); the first round(0.7 * rows) positions of order are train, '
                      'the rest validation; positions are 0-based data rows (row key L<i+2>).',
            'seed': seed, 'stream': STREAM_SPLIT, 'train_fraction': TRAIN_FRACTION,
            'train_rows': n_train, 'validation_rows': n_total - n_train,
            'train_positive': int(y[train_idx].sum()),
            'train_target_rate': _r(y[train_idx].mean()),
            'validation_positive': int(y.sum() - y[train_idx].sum()),
            'duplicate_pairs_across_partitions': straddle,
        },
        'duplicates': {'enabled': duplicates > 0, 'count': len(dup_pairs),
                       'pairs': dup_pairs},
    }
    if groups:
        sizes: dict[str, list[str]] = {}
        for key, r in zip(keys, final):
            sizes.setdefault(r['member_ref'], []).append(key)
        hist: dict[str, int] = {}
        for ks in sizes.values():
            hist[str(len(ks))] = hist.get(str(len(ks)), 0) + 1
        truth['groups'] = {
            'enabled': True, 'column': 'member_ref', 'groups': len(sizes),
            'size_histogram': dict(sorted(hist.items(), key=lambda kv: int(kv[0]))),
            'shared_columns': ['member_age', 'home_branch'],
            'note': 'No member-level effect on the target; rows of a member are not independent '
                    'units for evaluation.',
            'members_with_repeats': {g: ks for g, ks in sorted(sizes.items()) if len(ks) > 1},
        }
    else:
        truth['groups'] = {'enabled': False}
    if time:
        dates = [r['cycle_start_date'] for r in final]
        truth['time'] = {'enabled': True, 'column': 'cycle_start_date',
                         'min': min(dates), 'max': max(dates),
                         'note': 'Rows are not ordered by date; no drift is generated.'}
    else:
        truth['time'] = {'enabled': False}

    truth_path = out / 'truth.json'
    truth_path.write_text(json.dumps(truth, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    return {'data': data_path, 'case': case_path, 'truth': truth_path}


# --- regression variant ------------------------------------------------------------------
#
# Monthly loans of the branches of the same fictitious library network. The target is a
# number with a unit; only the four generating inputs below influence it, linearly, plus
# Gaussian noise drawn by inverse transform. Traps: a leaking column recorded after the
# month, a numeric category coded with digits, a sentinel, a missing-value marker, and,
# optionally, an integer season index with a trend (an ordinal split then shows the
# extrapolation bias) and repeated sites (the group overlap).

REG_CASE_ID = 'synthetic-branch-loans'
REG_TARGET, REG_UNIT = 'monthly_loans', 'loans'
REG_INTERCEPT = 120.0
REG_COEF_AREA = 0.05            # loans per square metre of floor_area
REG_COEF_STAFF = 8.0            # loans per staff member
REG_COEF_HOURS = 2.5            # loans per weekly opening hour
REG_TYPE_EFFECTS = (0.0, 40.0, -25.0)       # branch_type codes 1, 2, 3
REG_TYPE_PROBS = (0.5, 0.3, 0.2)
REG_SEASON_TREND = 6.0          # loans per season index (time option only)
REG_SEASONS = 8                 # season index 1..8
REG_NOISE_SD = 30.0
REG_LEAK_SHARE = 0.6            # returns_logged = 0.6 * target + Normal(0, 5)
REG_LEAK_NOISE_SD = 5.0
REG_AREA_RANGE = (200.0, 2000.0)
REG_STAFF_RANGE = (2, 20)
REG_HOURS_STEPS = 101           # 20.0, 20.5, ..., 70.0
REG_P_NOT_SURVEYED = 0.35
REG_SURVEY_SENTINEL = -1
REG_P_HEATING_MISSING = 0.05
REG_MISSING = 'NA'
(STREAM_REG_BASE, STREAM_REG_GROUPS, STREAM_REG_TIME, STREAM_REG_DUPLICATES,
 STREAM_REG_SPLIT) = range(10, 15)


def _normal(u: float) -> float:
    """Standard normal quantile of ``u`` (inverse transform, deterministic)."""
    from statistics import NormalDist
    return NormalDist().inv_cdf(min(max(u, 1e-12), 1 - 1e-12))


def _reg_rows(seed: int, n_rows: int) -> list[dict]:
    rng = _rng(seed, STREAM_REG_BASE)
    u = rng.random((n_rows, 10))
    rows = []
    lo, hi = REG_AREA_RANGE
    for i in range(n_rows):
        r = u[i]
        area = round(lo + float(r[0]) * (hi - lo), 1)
        staff = REG_STAFF_RANGE[0] + int(r[1] * (REG_STAFF_RANGE[1] - REG_STAFF_RANGE[0] + 1))
        hours = 20.0 + 0.5 * int(r[2] * REG_HOURS_STEPS)
        kind = _categorical(r[3], REG_TYPE_PROBS)
        survey = (REG_SURVEY_SENTINEL if r[4] < REG_P_NOT_SURVEYED
                  else round(1.0 + 9.0 * float(r[5]), 1))
        heating = (REG_MISSING if r[6] < REG_P_HEATING_MISSING
                   else round(800.0 + 2400.0 * float(r[7]), 2))
        rows.append({'floor_area': area, 'staff_count': staff, 'opening_hours': hours,
                     'branch_type': kind + 1, 'survey_score': survey, 'heating_cost': heating,
                     '_noise_u': float(r[8]), '_leak_u': float(r[9])})
    return rows


def _reg_mean(row: dict, time: bool) -> float:
    mean = (REG_INTERCEPT + REG_COEF_AREA * row['floor_area']
            + REG_COEF_STAFF * row['staff_count'] + REG_COEF_HOURS * row['opening_hours']
            + REG_TYPE_EFFECTS[row['branch_type'] - 1])
    if time:
        mean += REG_SEASON_TREND * row['season']
    return mean


def _reg_variance(time: bool) -> dict:
    """Exact variance of each generating term (independent inputs)."""
    lo, hi = REG_AREA_RANGE
    var_area = (hi - lo) ** 2 / 12.0      # continuous uniform before rounding
    k = REG_STAFF_RANGE[1] - REG_STAFF_RANGE[0] + 1
    var_staff = (k * k - 1) / 12.0
    var_hours = 0.25 * (REG_HOURS_STEPS ** 2 - 1) / 12.0
    mean_type = sum(p * e for p, e in zip(REG_TYPE_PROBS, REG_TYPE_EFFECTS))
    var_type = sum(p * (e - mean_type) ** 2 for p, e in zip(REG_TYPE_PROBS, REG_TYPE_EFFECTS))
    terms = {'floor_area': REG_COEF_AREA ** 2 * var_area,
             'staff_count': REG_COEF_STAFF ** 2 * var_staff,
             'opening_hours': REG_COEF_HOURS ** 2 * var_hours, 'branch_type': var_type}
    if time:
        terms['season'] = REG_SEASON_TREND ** 2 * (REG_SEASONS ** 2 - 1) / 12.0
    return terms


def _reg_dictionary(groups: bool, time: bool) -> list[dict]:
    office = 'Branch statistics office data dictionary (fictitious)'

    def avail(value, status, source):
        return {'value': value, 'status': status, 'source': source}

    assumed = avail('available_at_prediction', 'scenario_assumption',
                    'A branch characteristic known before the month; not stated by the office')
    entries = []
    if groups:
        entries.append({
            'name': 'site_ref', 'type': 'string', 'role': 'group_id',
            'description': 'Site reference. One site is recorded in several seasons.',
            'status': 'documented_fact', 'source': office,
            'availability': avail('available_at_prediction', 'scenario_assumption',
                                  'An identifier is known before the month; not stated'),
            'special_values': []})
    if time:
        entries.append({
            'name': 'season', 'type': 'integer', 'unit': 'season index', 'role': 'time',
            'description': 'Index of the season the month belongs to, counted from the first '
                           'recorded season.',
            'status': 'documented_fact', 'source': office,
            'availability': avail('available_at_prediction', 'scenario_assumption',
                                  'The season is known before the month starts; not stated'),
            'special_values': []})
    entries += [
        {'name': 'floor_area', 'type': 'numeric', 'unit': 'square metres', 'role': 'feature',
         'description': 'Public floor area of the branch.', 'status': 'documented_fact',
         'source': office, 'availability': assumed, 'special_values': []},
        {'name': 'staff_count', 'type': 'integer', 'unit': 'staff', 'role': 'feature',
         'description': 'Staff members assigned to the branch for the month.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'opening_hours', 'type': 'numeric', 'unit': 'hours per week', 'role': 'feature',
         'description': 'Weekly opening hours planned for the month.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'branch_type', 'type': 'category', 'role': 'feature',
         'description': 'Branch type, coded 1, 2, or 3. The codes are labels, not quantities.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': []},
        {'name': 'survey_score', 'type': 'numeric', 'role': 'feature',
         'description': 'Satisfaction score of the last visitor survey, from 1 to 10.',
         'status': 'documented_fact', 'source': office, 'availability': assumed,
         'special_values': [{'value': REG_SURVEY_SENTINEL,
                             'meaning': 'The branch was not surveyed',
                             'status': 'documented_fact', 'source': office}]},
        {'name': 'heating_cost', 'type': 'numeric', 'role': 'feature',
         'description': 'Not described by the office. Values are positive amounts with two '
                        'decimals; the unit is not known.',
         'status': 'observed', 'source': 'Inspection of the file',
         'availability': avail('unknown', 'unknown', 'Recording date not documented'),
         'special_values': [{'value': REG_MISSING, 'meaning': 'Missing value',
                             'status': 'observed', 'source': 'Inspection of the file'}]},
        {'name': 'returns_logged', 'type': 'numeric', 'unit': 'returns', 'role': 'feature',
         'description': 'Returns logged by the branch during the month after the loans were '
                        'counted. It is recorded after the target.',
         'status': 'documented_fact', 'source': office,
         'availability': avail('not_available', 'documented_fact',
                               'Recorded after the month, per the office'),
         'special_values': []},
        {'name': REG_TARGET, 'type': 'numeric', 'unit': REG_UNIT, 'role': 'target',
         'description': 'Loans recorded by the branch during the month.',
         'status': 'documented_fact', 'source': office,
         'availability': avail('not_available', 'documented_fact', 'The target itself'),
         'special_values': []},
    ]
    return entries


def make_regression_case(out_dir, seed: int = 20261018, n_rows: int = 600,
                         duplicates: int = 0, groups: bool = False,
                         time: bool = False) -> dict[str, Path]:
    """The regression variant: data.csv, case.yaml, truth.json for a numeric target.

    ``monthly_loans = intercept + b_area * floor_area + b_staff * staff_count
    + b_hours * opening_hours + effect[branch_type] (+ b_season * season) + Normal(0, sd)``.
    ``time`` adds the integer time column ``season`` (with a trend); ``groups`` adds the
    group column ``site_ref`` (sites share their floor area and type across seasons).
    """
    if n_rows < 100:
        raise ValueError('n_rows must be at least 100')
    if duplicates < 0 or duplicates > n_rows:
        raise ValueError('duplicates must be between 0 and n_rows')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = _reg_rows(seed, n_rows)
    if groups:
        rng = _rng(seed, STREAM_REG_GROUPS)
        labels, gid = [], 0
        while len(labels) < len(rows):
            gid += 1
            labels.extend([gid] * (1 + _categorical(float(rng.random()), GROUP_SIZE_PROBS)))
        order = np.argsort(rng.random(len(rows)), kind='stable')
        first: dict[int, dict] = {}
        for i, idx in enumerate(order):
            row, g = rows[int(idx)], labels[i]
            row['site_ref'] = f'S{g:04d}'
            if g in first:      # one site keeps its floor area and type across seasons
                row['floor_area'] = first[g]['floor_area']
                row['branch_type'] = first[g]['branch_type']
            else:
                first[g] = row
    if time:
        u = _rng(seed, STREAM_REG_TIME).random(len(rows))
        for row, v in zip(rows, u):
            row['season'] = 1 + int(float(v) * REG_SEASONS)
    for row in rows:
        mean = _reg_mean(row, time)
        row[REG_TARGET] = round(mean + REG_NOISE_SD * _normal(row['_noise_u']), 1)
        leak_u = row['_leak_u']
        row['returns_logged'] = round(REG_LEAK_SHARE * row[REG_TARGET]
                                      + REG_LEAK_NOISE_SD * _normal(leak_u), 1)
        row['_mean'] = mean
    columns = ((['site_ref'] if groups else []) + (['season'] if time else []) + [
        'floor_area', 'staff_count', 'opening_hours', 'branch_type', 'survey_score',
        'heating_cost', 'returns_logged', REG_TARGET])

    def line(row):
        return SEP.join(_fmt(row[c]) if not isinstance(row[c], str) else row[c]
                        for c in columns)

    final = list(rows)
    if duplicates:
        rng = _rng(seed, STREAM_REG_DUPLICATES)
        sources = np.argsort(rng.random(n_rows), kind='stable')[:duplicates]
        for src in sources:
            pos = int(float(rng.random()) * (len(final) + 1))
            final.insert(pos, dict(rows[int(src)]))
    data = ('\n'.join([SEP.join(columns)] + [line(r) for r in final]) + '\n').encode('utf-8')
    data_path = out / 'data.csv'
    data_path.write_bytes(data)
    data_sha = hashlib.sha256(data).hexdigest()
    keys = [f'L{i + 2}' for i in range(len(final))]

    variables = _reg_dictionary(groups, time)
    assert [v['name'] for v in variables] == columns
    special = [{'column': v['name'], **sv} for v in variables for sv in v['special_values']]
    office = 'Branch statistics office data dictionary (fictitious)'
    case = {
        'schema': 'hypotrail.case/1', 'id': REG_CASE_ID,
        'title': f'Monthly loans · {DOMAIN} (synthetic)',
        'description': 'Estimate the loans a branch records in a month, to plan its staffing.',
        'provenance': {'kind': 'synthetic',
                       'note': 'Generated by framework/tests/fixtures/synthetic/make_case.py '
                               '(regression variant); the library network is fictitious.'},
        'dataset': {'path': 'data.csv', 'format': 'csv', 'sep': SEP, 'encoding': 'utf-8',
                    'decimal': '.', 'header': True, 'sha256': data_sha, 'rows': len(final),
                    'columns': len(columns), 'na_values': [REG_MISSING]},
        'target': {'column': REG_TARGET, 'positive_label': None},
        'row_key': {'rule': 'source_line', 'format': 'L<line>',
                    'description': 'Physical 1-based line number in data.csv; the header is '
                                   'line 1, so the first data row is L2. The key is anchored '
                                   'to the dataset sha256.'},
        'facts': [
            {'id': 'observation_unit', 'value': 'One branch in one month',
             'status': 'documented_fact', 'source': office},
            {'id': 'intended_use', 'value': 'Estimate the monthly loans of a branch to plan staff',
             'status': 'scenario_assumption', 'source': 'Case scenario'},
            {'id': 'prediction_time', 'value': 'Not specified by the office',
             'status': 'unknown', 'source': 'Case scenario'},
        ],
        'variables': variables,
        'special_values': special,
        'structure': {
            'row_unit': {'value': 'branch month', 'status': 'documented_fact', 'source': office},
            'group_column': ({'value': 'site_ref', 'status': 'documented_fact', 'source': office}
                             if groups else {'value': None, 'status': 'unknown',
                                             'source': 'No site identifier in the extract'}),
            'time_column': ({'value': 'season', 'status': 'documented_fact', 'source': office}
                            if time else {'value': None, 'status': 'unknown',
                                          'source': 'No season in the extract'}),
            'duplicates': {'value': None, 'status': 'unknown', 'source': 'Not documented'},
        },
        'task': 'regression',
    }
    case_path = out / 'case.yaml'
    case_path.write_text(yaml.safe_dump(case, sort_keys=False, allow_unicode=True, width=100),
                         encoding='utf-8')

    y = np.array([r[REG_TARGET] for r in final], dtype=float)
    split_rng = _rng(seed, STREAM_REG_SPLIT)
    order = np.argsort(split_rng.random(len(final)), kind='stable')
    n_train = int(round(TRAIN_FRACTION * len(final)))
    train_idx = np.sort(order[:n_train])
    terms = _reg_variance(time)
    signal_var = sum(terms.values())
    truth = {
        'schema': 'hypotrail.synthetic-truth/1',
        'warning': 'Never expose this file to an agent under test.',
        'generator': {'module': 'framework/tests/fixtures/synthetic/make_case.py',
                      'version': GENERATOR_VERSION, 'seed': seed,
                      'options': {'task': 'regression', 'n_rows': n_rows,
                                  'duplicates': duplicates, 'groups': groups, 'time': time}},
        'data': {'path': 'data.csv', 'sep': SEP, 'sha256': data_sha, 'rows': len(final),
                 'distinct_rows': n_rows, 'columns': columns,
                 'row_keys': {'first': keys[0], 'last': keys[-1]}},
        'target': {'column': REG_TARGET, 'unit': REG_UNIT,
                   'observed_mean': _r(y.mean()), 'observed_sd': _r(y.std(ddof=1))},
        'generating_model': {
            'link': 'identity',
            'formula': f'{REG_TARGET} = intercept + b_area*floor_area + b_staff*staff_count '
                       '+ b_hours*opening_hours + effect[branch_type]'
                       + (' + b_season*season' if time else '') + ' + Normal(0, noise_sd)',
            'intercept': REG_INTERCEPT,
            'coefficients': {'floor_area': REG_COEF_AREA, 'staff_count': REG_COEF_STAFF,
                             'opening_hours': REG_COEF_HOURS,
                             **({'season': REG_SEASON_TREND} if time else {})},
            'branch_type_effects': {str(i + 1): e for i, e in enumerate(REG_TYPE_EFFECTS)},
            'branch_type_probabilities': {str(i + 1): p for i, p in enumerate(REG_TYPE_PROBS)},
            'noise_sd': REG_NOISE_SD,
            'independent_of_target': ['survey_score', 'heating_cost']
                                     + (['site_ref'] if groups else []),
            'variance_by_term': {k: _r(v) for k, v in terms.items()},
            'explained_share': _r(signal_var / (signal_var + REG_NOISE_SD ** 2)),
            'true_model_mae': _r(REG_NOISE_SD * math.sqrt(2.0 / math.pi)),
            'true_model_rmse': REG_NOISE_SD,
            'note': 'MAE and RMSE of the generating mean on new rows, from the noise alone '
                    '(the target is rounded to one decimal).',
        },
        'leakage': {'column': 'returns_logged', 'recorded': 'after the month',
                    'formula': f'{REG_LEAK_SHARE} * {REG_TARGET} + Normal(0, {REG_LEAK_NOISE_SD})'},
        'categorical_codes': {'column': 'branch_type',
                              'note': 'Digits that are labels: a model must encode them as '
                                      'categories, not as a magnitude.'},
        'sentinel': {'column': 'survey_score', 'value': REG_SURVEY_SENTINEL,
                     'count': sum(r['survey_score'] == REG_SURVEY_SENTINEL for r in final)},
        'missing': {'column': 'heating_cost', 'marker': REG_MISSING,
                    'count': sum(r['heating_cost'] == REG_MISSING for r in final)},
        'reference_split': {
            'purpose': 'Test reference only; not a human decision.',
            'seed': seed, 'stream': STREAM_REG_SPLIT, 'train_fraction': TRAIN_FRACTION,
            'train_rows': n_train, 'validation_rows': len(final) - n_train,
            'train_target_mean': _r(y[train_idx].mean())},
        'duplicates': {'enabled': duplicates > 0, 'count': duplicates},
        'groups': ({'enabled': True, 'column': 'site_ref',
                    'groups': len({r['site_ref'] for r in final}),
                    'shared_columns': ['floor_area', 'branch_type']}
                   if groups else {'enabled': False}),
        'time': ({'enabled': True, 'column': 'season', 'values': [1, REG_SEASONS],
                  'trend_per_season': REG_SEASON_TREND,
                  'note': 'The target rises with the season index: a model without the season, '
                          'fitted on early seasons, predicts later seasons too low.'}
                 if time else {'enabled': False}),
    }
    truth_path = out / 'truth.json'
    truth_path.write_text(json.dumps(truth, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    return {'data': data_path, 'case': case_path, 'truth': truth_path}


def make_review_case(out_dir, *, future: bool = False, n_rows: int = 300) -> dict[str, Path]:
    """J0 fixtures: independent comparison or explicitly documented synthetic clocks.

    The future case is a contract fixture for J1, not a claim that J0 implements its
    final partition. Every clock is planted independently of the generated target.
    """
    import csv
    import io

    paths = make_case(out_dir, n_rows=n_rows)
    document = yaml.safe_load(paths['case'].read_text(encoding='utf-8'))
    timing = {'prediction_order': None, 'outcome_available_order': None, 'scale': 'ordinal'}
    if future:
        rows = list(csv.reader(io.StringIO(paths['data'].read_text(encoding='utf-8')),
                               delimiter=SEP))
        rows[0] += ['prediction_tick', 'outcome_tick']
        for tick, row in enumerate(rows[1:], start=1):
            row += [str(tick), str(tick + 2)]
        buf = io.StringIO(newline='')
        csv.writer(buf, delimiter=SEP, lineterminator='\n').writerows(rows)
        paths['data'].write_text(buf.getvalue(), encoding='utf-8')
        document['dataset']['sha256'] = hashlib.sha256(paths['data'].read_bytes()).hexdigest()
        document['dataset']['columns'] += 2
        for name in ('prediction_tick', 'outcome_tick'):
            document['variables'].append({
                'name': name, 'type': 'integer', 'role': 'identifier',
                'description': f'Planted {name} on the shared ascending ordinal scale',
                'status': 'documented_fact', 'source': 'Synthetic fixture specification',
                'availability': {'value': 'not_available', 'status': 'documented_fact',
                                 'source': 'Protocol metadata, not a predictor'},
                'special_values': [],
            })
            timing['prediction_order' if name == 'prediction_tick' else 'outcome_available_order'] = {
                'by': name, 'status': 'documented_fact', 'source': 'Synthetic fixture specification'}
    document['analysis_contract'] = {
        'schema': 'hypotrail.analysis/1',
        'scenario_id': 'synthetic-future-v1' if future else 'synthetic-independent-v1',
        'intended_use': 'future_prediction' if future else 'retrospective_comparison',
        'row_unit': 'synthetic observation', 'population': 'Generated synthetic observations',
        'prediction_statement': 'Predict using information available at the planted decision time',
        'timing': timing,
        'dependencies': {'kind': 'temporal' if future else 'independent',
                         'group_column': None, 'group_goal': None,
                         'status': 'documented_fact', 'source': 'Synthetic fixture specification'},
        'permitted_claims': ['retrospective_association'] + (
            ['future_predictive_performance'] if future else []),
    }
    paths['case'].write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                             encoding='utf-8')
    # The original generating truth still describes y, but its file hash/columns refer
    # to the base fixture. Do not expose that stale metadata for the clock variant.
    if future:
        truth = json.loads(paths['truth'].read_text(encoding='utf-8'))
        truth['data'].update(sha256=document['dataset']['sha256'], columns=rows[0])
        truth['review_clocks'] = {'prediction': 'row ordinal', 'outcome': 'row ordinal + 2'}
        paths['truth'].write_text(json.dumps(truth, indent=2) + '\n', encoding='utf-8')
    return paths


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('out_dir')
    parser.add_argument('--seed', type=int, default=20261018)
    parser.add_argument('--rows', type=int, default=4000)
    parser.add_argument('--positive-rate', type=float, default=0.12)
    parser.add_argument('--duplicates', type=int, default=0)
    parser.add_argument('--groups', action='store_true')
    parser.add_argument('--time', action='store_true')
    parser.add_argument('--task', choices=('binary', 'regression'), default='binary')
    a = parser.parse_args(argv)
    paths = make_case(a.out_dir, seed=a.seed, n_rows=a.rows, positive_rate=a.positive_rate,
                      duplicates=a.duplicates, groups=a.groups, time=a.time, task=a.task)
    print(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))


if __name__ == '__main__':
    main()
