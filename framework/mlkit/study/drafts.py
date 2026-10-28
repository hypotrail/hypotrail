"""Recommendations that read the evidence (owner session 2026-10-26, lot L5).

Remarks R5, R7, R12, R13, R14 and R15 of the session notes; owner decisions D5, D6, D8, D9,
D10 and D11 (``docs/plans/OWNER-SESSION-2026-10-26-PLAN.md`` §3 L5, §4, §10).

The view layer only: this module is **not** part of any activity's code fingerprint
(``activities.MODULES``), it writes nothing, and it never changes a recorded value. It reads
current results through :class:`mlkit.study.read.Study` and drafts values that a ``propose``
action carries (``next_action.default_value``); a draft is a proposal, never a decision: the
junior adopts it, changes it, or takes the comparison option. Every draft applies only to a
structural-first study (:func:`mlkit.study.state.structural_first`, written by ``init`` since
L5); a study created before keeps its drafts.

**The preparation** (R5, D6). Drafted from the target-free results only: the quality check
(``eda.quality``, which reads the development rows without the target) and the distributions
of numeric candidates (``eda.distribution`` on one column, never the target). The rules and
their thresholds (D6, accepted by the owner on 2026-10-26):

1. rare categories: a categorical candidate with at least :data:`RARE_MIN_DISTINCT` distinct
   values whose rare categories (fewer than ``rare_rows`` rows, 30, the quality check's own
   threshold) hold at least :data:`RARE_MIN_SHARE` of the rows: group the categories with
   fewer than that many training rows. The setting is global until per-column grouping
   exists (L8), and the reason says so;
2. missing values: a candidate with at least :data:`MISSING_MIN_SHARE` missing cells: a
   missing-value indicator for it;
3. caps: a numeric candidate with values outside the range the case declares: caps at the
   training quantiles :data:`CAP_QUANTILES`;
4. signed log: a numeric candidate whose current distribution says ``numeric.skewed`` (the
   engine's own rule, ``eda._skew_bins``): ``log_transform``. The plan asks for the
   distribution of at most :data:`MAX_DISTRIBUTION_RUNS` numeric candidates, those whose
   non-negative range spans at least one order of magnitude (``(max + 1) / (min + 1) >=`` :data:`SPAN_RATIO`, read on
   the quality check's ranges), widest first (:func:`screened_columns`).

The draft is the recommended value when a rule fires; the default preparation (nothing
added) is the comparison option (``next_action.alternatives``). Its ``motivated_by`` cites the
results it read, so the engine computes ``data_contingent`` from them: false when only these
target-free results motivate it and no look at the target came before.

**The variants** (R13, D9). When the diagnostics of the linear fit flag a pattern
(``model_families.recommendation == "compare_nonlinear"``), the readable non-linear family
(EBM) is allowed and the budget has at least two trials left, the draft is the tuned penalty
and the EBM, whose question names the flags; the tuned penalty alone otherwise.

**Names and refusals** (R14, R15, D10, D11): the families in the junior's words
(:data:`JUNIOR_WORDS`, boosting named as the family of XGBoost and LightGBM), why no random
forest (:data:`NOT_OFFERED`), and the teaching refusal of a family outside the catalogue
(:func:`family_refusal`).

**Calendar years** (R12, D8): a feature the case declares ``calendar: year`` kept under a
temporal evaluation gets an advisory (:func:`calendar_advisory`).
"""
from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from . import governance
from . import state as st
from . import trials

EN, FR = 'en', 'fr'

# D6 (owner, 2026-10-26): the rules' thresholds.
RARE_MIN_DISTINCT = 20
RARE_MIN_SHARE = 0.01
MISSING_MIN_SHARE = 0.05
CAP_QUANTILES = [0.005, 0.995]
# L8 hook: a max above this multiple of the 99th percentile is an extreme tail (capped);
# a quality-check skewness at or above SKEW_LOG_MIN drafts a signed log.
EXTREME_TAIL_RATIO = 3
SKEW_LOG_MIN = 1.0
MAX_DISTRIBUTION_RUNS = 3
SPAN_RATIO = 10
QUALITY_SLOT = 'eda.quality'
DISTRIBUTION = 'eda.distribution'
USABLE = ('available_at_prediction', 'uncertain_included')
RULES = ('rare_categories', 'missing_indicator', 'cap_declared_range', 'signed_log')
REASON_KEYS = ('parameter', 'column', 'rule', 'evidence', 'text')
ALTERNATIVE_KEYS = ('value', 'label', 'why')
WORKBENCH = 'notebooks/workbench.py'


def _t(lang: str, en: str, fr: str) -> str:
    return fr if lang == FR else en


def _join(items, lang: str) -> str:
    items = [str(i) for i in items]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + _t(lang, ' and ', ' et ') + items[-1]


# --- reading current results ---------------------------------------------------------------

def current_values(study, state: Mapping, slot: str) -> tuple[str | None, dict | None]:
    """``(result_id, values)`` of the result in ``slot`` when it is current (by the rule of
    ``status``: :meth:`read.Study.currency`) and passes its integrity check, else
    ``(None, None)``."""
    rid = (state.get('current') or {}).get(slot)
    if rid is None or rid in (state.get('stale') or {}):
        return None, None
    try:
        if not study.currency(rid)['current']:
            return None, None
        values = study.result(rid)['output']['values']
    except Exception:          # noqa: BLE001 - a result that cannot be read drafts nothing
        return None, None
    return (rid, values) if isinstance(values, Mapping) else (None, None)


def _case(state: Mapping):
    from .case import CaseError, case_of
    try:
        return case_of(state)
    except (CaseError, OSError):
        return None


def candidates(state: Mapping, case) -> list[str]:
    """The candidate features the confirmed availability keeps, in the case's order; empty
    while the availability is not confirmed."""
    decision = (state.get('decisions') or {}).get('feature_availability') or {}
    if decision.get('status') != 'confirmed' or not isinstance(decision.get('value'), Mapping):
        return []
    value = decision['value']
    return [v['name'] for v in case.document['variables']
            if v['role'] == 'feature' and value.get(v['name']) in USABLE]


def _numeric(case, column: str) -> bool:
    return (case.variables.get(column) or {}).get('type') in governance.NUMERIC_TYPES


# --- the preparation (R5, D6) --------------------------------------------------------------

def screened_columns(quality: Mapping, keep: list[str], case) -> list[str]:
    """The numeric candidates whose distribution the draft reads (at most
    :data:`MAX_DISTRIBUTION_RUNS`): a non-negative observed range spanning at least one order
    of magnitude, ``(max + 1) / (min + 1) >= SPAN_RATIO``, widest first, then the case's
    order. Target-free: the quality check's ranges only."""
    scored = []
    for i, item in enumerate(quality.get('ranges') or []):
        column = item.get('column')
        low, high = item.get('min'), item.get('max')
        if column not in keep or not _numeric(case, column) \
                or not isinstance(low, (int, float)) or not isinstance(high, (int, float)) \
                or isinstance(low, bool) or low < 0:
            continue
        ratio = (high + 1) / (low + 1)
        if ratio >= SPAN_RATIO:
            scored.append((-ratio, keep.index(column), column))
    return [c for _, _, c in sorted(scored)[:MAX_DISTRIBUTION_RUNS]]


def distribution_slot(column: str) -> str:
    return f'{DISTRIBUTION}:{column}'


def missing_distributions(study, state: Mapping) -> list[str]:
    """The screened columns whose distribution is not current yet (structural-first study
    whose quality check is current; empty otherwise)."""
    case = _case(state)
    if case is None or not st.structural_first(state):
        return []
    _, quality = current_values(study, state, QUALITY_SLOT)
    if quality is None:
        return []
    keep = candidates(state, case)
    # R39 (owner batch of 2026-10-28): a column the quality check's skewness drafts a log for
    # is drawn too, so the proposal shows the distribution it cites. It reads that column
    # only, and the draft does not read it back (the column is already drafted).
    def capped(item):
        q99, top = (item.get('quantiles') or {}).get('0.99'), item.get('max')
        outside = int(item.get('n_above') or 0) + int(item.get('n_below') or 0)
        return outside > 0 or (isinstance(q99, (int, float)) and isinstance(top, (int, float))
                               and q99 > 0 and top > EXTREME_TAIL_RATIO * q99)
    skewed = [item.get('column') for item in quality.get('ranges') or []
              if item.get('column') in keep and _numeric(case, item.get('column'))
              and isinstance(item.get('skewness'), (int, float))
              and item['skewness'] >= SKEW_LOG_MIN and not capped(item)]
    wanted = list(dict.fromkeys(screened_columns(quality, keep, case) + skewed))
    return [c for c in wanted
            if current_values(study, state, distribution_slot(c))[0] is None]


def distribution_run(study, state: Mapping, action: Mapping, lang: str) -> dict | None:
    """The ``run`` of the next screened distribution, before the preparation is proposed
    (structural-first study), or None. Target-free: one column, never the target."""
    missing = missing_distributions(study, state)
    if not missing:
        return None
    column = missing[0]
    from . import audience
    return {'kind': 'run', 'step': st.STRUCTURAL_EDA, 'activity': DISTRIBUTION,
            'options': {'column': column},
            'message': (f'Run eda.distribution --column {column} before proposing the '
                        'preprocessing: the draft reads whether this numeric candidate is '
                        'skewed. It reads that column only, never the target, so it is not a '
                        'look at the target.'),
            'audience': audience.AGENT,
            'junior_message': _t(
                lang, f'Before the preparation is proposed, the distribution of {column} is '
                      'read: a column whose values span a wide range may need a log '
                      'transform. Only that column is read, never the target.',
                f"Avant de proposer la préparation, on lit la distribution de {column} : une "
                "colonne dont les valeurs s'étendent sur une large plage peut demander une "
                'transformation logarithmique. Seule cette colonne est lue, jamais la cible.')}


# Owner batch of 2026-10-28 (R40, R45): the exploration step runs the case catalogue's charts
# itself, once the target summary and the special values are current: the target against
# each kept feature (``eda.mean_by`` for a regression, ``eda.rate_by`` for a binary target),
# the predictor correlation matrix (``eda.correlation``, no target), then each kept feature's
# distribution (``eda.distribution``, no target). Each target chart is a look, counted as any
# other. At most :data:`MAX_EXPLORATION_FEATURES` features (the case's order), so a wide case
# stays fast. Structural-first studies only: the preparation is decided before these looks.
MAX_EXPLORATION_FEATURES = 12
TARGET_BY = {st.BINARY: 'eda.rate_by', st.REGRESSION: 'eda.mean_by'}
CORRELATION = 'eda.correlation'


def exploration_slots(state: Mapping, case) -> list[tuple[str, str | None]]:
    """``[(activity, column or None)]`` the exploration step runs, in order (R40, R45)."""
    keep = [c for c in candidates(state, case)
            if (case.variables.get(c) or {}).get('role') == 'feature'][:MAX_EXPLORATION_FEATURES]
    by = TARGET_BY.get(st.task_of(state), 'eda.rate_by')
    out: list[tuple[str, str | None]] = [(by, c) for c in keep]
    if sum(_numeric(case, c) for c in keep) >= 2:
        out.append((CORRELATION, None))
    out += [(DISTRIBUTION, c) for c in keep]
    return out


def exploration_complete(study, state: Mapping) -> bool:
    """Lot 2026-10-28 (EN-12): every exploration chart of the plan (the step's own activities
    and :func:`exploration_slots`) is current, and no model is fitted yet."""
    case = _case(state)
    if case is None or current_values(study, state, 'fit.baseline')[0] is not None:
        return False
    fixed = next((s for s in st.derive_plan(state) if s.get('id') == 'train_eda'), {})
    slots = list(fixed.get('activities') or ()) + [
        f'{a}:{c}' if c else a for a, c in exploration_slots(state, case)]
    return all(current_values(study, state, s)[0] is not None for s in slots)


def exploration_run(study, state: Mapping, action: Mapping, lang: str) -> dict | None:
    """The ``run`` of the next exploration chart of the plan (R40, R45), or None: in a
    structural-first study, before the final test is opened, once the exploration's own
    activities are current and the plan moves on to a later step."""
    case = _case(state)
    if case is None or not st.structural_first(state) or st.final_test_opened(state):
        return None
    plan = [s.get('id') for s in st.derive_plan(state)]
    if 'train_eda' not in plan:
        return None
    from . import companion_env
    step = companion_env.current_step(action, st.derive_plan(state))
    if step not in plan or plan.index(step) <= plan.index('train_eda'):
        return None
    fixed = next((s for s in st.derive_plan(state) if s.get('id') == 'train_eda'), {})
    if any(current_values(study, state, a)[0] is None for a in fixed.get('activities') or ()):
        return None
    # Only on the way from the exploration to the models: a study already past its fits (one
    # written before this rule included) is never sent back to explore.
    if current_values(study, state, 'fit.baseline')[0] is not None:
        return None
    for activity, column in exploration_slots(state, case):
        slot = f'{activity}:{column}' if column else activity
        if current_values(study, state, slot)[0] is not None:
            continue
        from . import audience
        what = audience.activity_words(activity, lang)
        reads_target = activity == TARGET_BY.get(st.task_of(state))
        named = f'{what} ({column})' if column else what
        out = {'kind': 'run', 'step': 'train_eda', 'activity': activity,
               'message': (f'Run {activity}' + (f' --column {column}' if column else '')
                           + ': the exploration step runs the case catalogue\'s charts '
                             'before the models. ' + ('It reads the target: a look, counted.'
                                                      if reads_target else
                                                      'It reads no target.')),
               'audience': audience.AGENT,
               'junior_message': _t(
                   lang, f'The exploration continues with {named}. '
                         + ('It reads the target of the development rows: one more look, '
                            'counted.' if reads_target else 'It reads no target.'),
                   f"L'exploration continue avec {named}. "
                   + ('Elle lit la cible des lignes de développement : un regard de plus, '
                      'compté.' if reads_target else 'Elle ne lit pas la cible.'))}
        if column:
            out['options'] = {'column': column}
        return out
    return None


def _reason(parameter: str, column: str | None, rule: str, rid: str, path: str,
            text: str) -> dict:
    return {'parameter': parameter, 'column': column, 'rule': rule,
            'evidence': {'result_id': rid, 'path': path}, 'text': text}


def preprocessing_draft(study, state: Mapping, lang: str) -> dict | None:
    """``{value, reasons, drafted, motivated_by}`` of a structural-first study whose quality
    check is current, else None. ``value`` carries ``motivated_by`` (the results read);
    ``drafted`` is true when at least one rule fired (the value then differs from the
    default). Each reason is ``{parameter, column, rule, evidence: {result_id, path}, text}``,
    ``path`` inside the result's values (:func:`mlkit.study.cite.resolve`)."""
    case = _case(state)
    if case is None or not st.structural_first(state):
        return None
    qid, quality = current_values(study, state, QUALITY_SLOT)
    if quality is None:
        return None
    keep = candidates(state, case)
    n = quality.get('n_rows') or 0
    value = copy.deepcopy(governance.DEFAULT_PREPROCESSING)
    reasons: list[dict] = []
    motivated = [qid]
    # 1. rare categories, per column (L8 mapping {column: min_rows}).
    rare_map = {}
    for i, item in enumerate(quality.get('cardinality') or []):
        column = item.get('column')
        if column not in keep or not n:
            continue
        rare_rows = sum(int(r.get('n_rows') or 0) for r in item.get('rare') or [])
        threshold = int(item.get('rare_rows') or 0)
        if item.get('n_distinct', 0) >= RARE_MIN_DISTINCT and threshold > 0 \
                and rare_rows / n >= RARE_MIN_SHARE:
            rare_map[column] = threshold
            reasons.append(_reason(
                'rare_category_min_rows', column, 'rare_categories', qid,
                f'cardinality.{i}.rare',
                _t(lang, f'{column} has {item["n_distinct"]} distinct values, and its '
                         f'categories with fewer than {threshold} rows hold a noticeable share '
                         'of the rows: they are grouped, in this column only.',
                   f'{column} compte {item["n_distinct"]} valeurs distinctes, et ses '
                   f'catégories de moins de {threshold} lignes regroupent une part notable des '
                   'lignes : elles sont regroupées, dans cette colonne seulement.')))
    if rare_map:
        value['rare_category_min_rows'] = rare_map
    # 2. missing values.
    indicators = {}
    for i, item in enumerate(quality.get('missing') or []):
        column = item.get('column')
        k = int(item.get('n_missing') or 0)
        if column not in keep or not n or k / n < MISSING_MIN_SHARE:
            continue
        indicators[column] = 'indicator'
        reasons.append(_reason(
            'missing', column, 'missing_indicator', qid, f'missing.{i}.n_missing',
            _t(lang, f'{column} is missing in {k} of the {n} rows: an indicator tells the '
                     'model which values were filled in.',
               f'{column} manque dans {k} des {n} lignes : un indicateur dit au modèle '
               'quelles valeurs ont été complétées.')))
    if indicators:
        value['missing'] = indicators
    # 3. caps against a declared range; 4. signed log of a skewed distribution.
    caps = {}
    for i, item in enumerate(quality.get('ranges') or []):
        column = item.get('column')
        outside = int(item.get('n_above') or 0) + int(item.get('n_below') or 0)
        if column not in keep or not _numeric(case, column):
            continue
        q99 = (item.get('quantiles') or {}).get('0.99')
        top = item.get('max')
        tail = (outside <= 0 and q99 is not None and top is not None and q99 > 0
                and top > EXTREME_TAIL_RATIO * q99)
        if outside <= 0 and not tail:
            continue
        caps[column] = list(CAP_QUANTILES)
        if tail:
            reasons.append(_reason(
                'caps', column, 'cap_extreme_tail', qid, f'ranges.{i}.max',
                _t(lang, f'{column} goes up to {top:g} while 99 % of the rows are at or below '
                         f'{q99:g}: a few extreme values are capped at the training quantiles '
                         '0.005 and 0.995.',
                   f'{column} monte jusqu\'à {top:g} alors que 99 % des lignes sont à {q99:g} '
                   'ou moins : quelques valeurs extrêmes sont plafonnées aux quantiles 0,005 et '
                   "0,995 des lignes d'entraînement.")))
            continue
        path = f'ranges.{i}.n_above' if item.get('n_above') else f'ranges.{i}.n_below'
        reasons.append(_reason(
            'caps', column, 'cap_declared_range', qid, path,
            _t(lang, f'{column} has values outside the range the case declares: capped at '
                     'the training quantiles 0.005 and 0.995.',
               f'{column} a des valeurs hors de la plage que le cas déclare : plafonnée aux '
               "quantiles 0,005 et 0,995 des lignes d'entraînement.")))
    if caps:
        value['caps'] = caps
    logs = []
    for i, item in enumerate(quality.get('ranges') or []):
        column = item.get('column')
        skew = item.get('skewness')
        if column not in keep or not _numeric(case, column) or skew is None \
                or skew < SKEW_LOG_MIN or column in caps:
            continue
        logs.append(column)
        reasons.append(_reason(
            'log_transform', column, 'signed_log', qid, f'ranges.{i}.skewness',
            _t(lang, f'The distribution of {column} is strongly skewed (a long tail of large '
                     'values): a signed log brings its scale closer to the others.',
               f'La distribution de {column} est très asymétrique (une longue traîne de grandes '
               'valeurs) : un log signé rapproche son échelle de celle des autres.')))
    for column in keep:
        if column in logs:
            continue
        if not _numeric(case, column):
            continue
        rid, dist = current_values(study, state, distribution_slot(column))
        if dist is None:
            continue
        motivated.append(rid)
        if (dist.get('numeric') or {}).get('skewed') is True:
            logs.append(column)
            reasons.append(_reason(
                'log_transform', column, 'signed_log', rid, 'numeric.skewed',
                _t(lang, f'The distribution of {column} is skewed (a long tail of large '
                         'values): a signed log brings its scale closer to the others.',
                   f'La distribution de {column} est asymétrique (une longue traîne de grandes '
                   'valeurs) : un log signé rapproche son échelle de celle des autres.')))
    if logs:
        value['log_transform'] = logs
    value['motivated_by'] = list(dict.fromkeys(motivated))
    return {'value': value, 'reasons': reasons, 'drafted': bool(reasons),
            'motivated_by': value['motivated_by']}


# Owner batch of 2026-10-28 (R40, R41): the quality check's verdict for every column, the
# transformed ones and those left unchanged, with the threshold that decided it, as data the
# panel and the report draw (CLI-CONTRACT §17.6). The thresholds are the draft's own rules.
VERDICT_KEYS = ('column', 'kept', 'changed', 'parameters', 'checks', 'text')
PARAMETER_WORDS = {
    'log_transform': {EN: 'a signed log', FR: 'un log signé'},
    'caps': {EN: 'caps at the training quantiles', FR: "des plafonds aux quantiles d'entraînement"},
    'missing': {EN: 'a missing-value indicator column',
                FR: 'une colonne indicatrice de valeur manquante'},
    'rare_category_min_rows': {EN: 'its rare categories grouped',
                               FR: 'ses catégories rares regroupées'}}
CHECK_KEYS = ('rule', 'value', 'threshold', 'exceeds', 'path', 'words')


def _num(x, lang: str, digits: int = 2) -> str:
    text = f'{x:.{digits}f}'.rstrip('0').rstrip('.') if isinstance(x, float) else f'{x}'
    return text.replace('.', ',') if lang == FR else text


def quality_verdicts(study, state: Mapping, lang: str, draft: Mapping | None = None
                     ) -> dict | None:
    """``{result_id, columns: [...]}`` (:data:`VERDICT_KEYS`) of a structural-first study
    whose quality check is current, else None. Each column of the quality check states what
    each rule measured against its threshold (:data:`CHECK_KEYS`: the skewness against
    :data:`SKEW_LOG_MIN`, the maximum against :data:`EXTREME_TAIL_RATIO` times the 99th
    percentile, the share of missing cells against :data:`MISSING_MIN_SHARE`, the categories
    with fewer than the check's ``rare_rows`` rows), the parameters the draft gives it
    (``changed``), and one sentence in the study language; the changed columns come first.
    A "no change" is backed by the same figures as a change."""
    case = _case(state)
    if case is None or not st.structural_first(state):
        return None
    qid, quality = current_values(study, state, QUALITY_SLOT)
    if quality is None:
        return None
    draft = draft if draft is not None else preprocessing_draft(study, state, lang)
    keep = candidates(state, case)
    params: dict[str, list[str]] = {}
    for reason in (draft or {}).get('reasons') or []:
        params.setdefault(reason.get('column'), []).append(reason.get('parameter'))
    n = quality.get('n_rows') or 0
    found: dict[str, list[dict]] = {}
    order: list[str] = []

    def add(column, check):
        if column not in found:
            found[column] = []
            order.append(column)
        found[column].append(check)
    for i, item in enumerate(quality.get('missing') or []):
        k = int(item.get('n_missing') or 0)
        share = k / n if n else 0.0
        add(item.get('column'), {
            'rule': 'missing_indicator', 'value': share, 'threshold': MISSING_MIN_SHARE,
            'exceeds': bool(n) and share >= MISSING_MIN_SHARE, 'path': f'missing.{i}.n_missing',
            'words': _t(lang, f'{k} missing of {n} ({_num(100 * share, lang, 1)}%) '
                              f'{"≥" if share >= MISSING_MIN_SHARE else "<"} 5%',
                        f'{k} manquantes sur {n} ({_num(100 * share, lang, 1)} %) '
                        f'{"≥" if share >= MISSING_MIN_SHARE else "<"} 5 %')})
    for i, item in enumerate(quality.get('ranges') or []):
        column = item.get('column')
        skew = item.get('skewness')
        if isinstance(skew, (int, float)):
            add(column, {'rule': 'signed_log', 'value': skew, 'threshold': SKEW_LOG_MIN,
                         'exceeds': skew >= SKEW_LOG_MIN, 'path': f'ranges.{i}.skewness',
                         'words': _t(lang, f'skewness {_num(float(skew), lang)} '
                                           f'{"≥" if skew >= SKEW_LOG_MIN else "<"} 1',
                                     f'asymétrie {_num(float(skew), lang)} '
                                     f'{"≥" if skew >= SKEW_LOG_MIN else "<"} 1')})
        q99 = (item.get('quantiles') or {}).get('0.99')
        top = item.get('max')
        if isinstance(q99, (int, float)) and isinstance(top, (int, float)) and q99 > 0:
            bound = EXTREME_TAIL_RATIO * q99
            add(column, {'rule': 'cap_extreme_tail', 'value': top, 'threshold': bound,
                         'exceeds': top > bound, 'path': f'ranges.{i}.max',
                         'words': _t(lang, f'max {_num(float(top), lang)} '
                                           f'{">" if top > bound else "≤"} 3 × q99 '
                                           f'({_num(float(bound), lang)})',
                                     f'max {_num(float(top), lang)} '
                                     f'{">" if top > bound else "≤"} 3 × q99 '
                                     f'({_num(float(bound), lang)})')})
        outside = int(item.get('n_above') or 0) + int(item.get('n_below') or 0)
        if item.get('declared') is not None:
            add(column, {'rule': 'cap_declared_range', 'value': outside, 'threshold': 0,
                         'exceeds': outside > 0, 'path': f'ranges.{i}.n_above',
                         'words': _t(lang, f'{outside} values outside the declared range',
                                     f'{outside} valeurs hors de la plage déclarée')})
    for i, item in enumerate(quality.get('cardinality') or []):
        threshold = int(item.get('rare_rows') or 0)
        rare = item.get('rare') or []
        count = len(rare)
        add(item.get('column'), {
            'rule': 'rare_categories', 'value': count, 'threshold': threshold,
            'exceeds': count > 0, 'path': f'cardinality.{i}.rare',
            'words': _t(lang, (f'{count} categories under {threshold} rows' if count else
                               f'no category under {threshold} rows'),
                        (f'{count} catégories sous {threshold} lignes' if count else
                         f'aucune catégorie sous {threshold} lignes'))})
    none_words = _t(lang, 'no change', 'pas de changement')
    columns = []
    for column in order:
        given = list(dict.fromkeys(params.get(column) or []))
        checks = found[column]
        words = (', ' if lang != FR else ', ').join(c['words'] for c in checks)
        named = [PARAMETER_WORDS.get(p, {}).get(lang, p) for p in given]
        outcome = (_t(lang, 'drafted: ', 'proposé : ') + ', '.join(named)) if given \
            else none_words
        columns.append({'column': column, 'kept': column in keep, 'changed': bool(given),
                        'parameters': given, 'checks': checks,
                        'text': f'{column}{_t(lang, ": ", " : ")}{words}{_t(lang, ": ", " : ")}'
                                f'{outcome}.'})
    columns.sort(key=lambda c: (not c['changed'], not c['kept']))
    return {'result_id': qid, 'columns': columns}


PIPELINE_SENTENCE = {
    EN: 'In every case, the model replaces a missing value by the median or the most frequent '
        'category, puts the numbers on the same scale and codes each category as a 0/1 '
        'column.',
    FR: 'Dans tous les cas, le modèle remplace une valeur manquante par la médiane ou la '
        'catégorie la plus fréquente, met les nombres à la même échelle et code chaque '
        'catégorie en colonne 0/1.'}


def _summary(reasons: list, lang: str) -> str:
    """The drafted parameters in a few words, by rule, naming their columns."""
    by_rule: dict = {}
    for r in reasons:
        by_rule.setdefault(r['rule'], []).append(r['column'])
    parts = []
    for rule in RULES:
        columns = _join(dict.fromkeys(by_rule.get(rule) or []), lang)
        if not columns:
            continue
        parts.append({
            'rare_categories': _t(lang, f'rare categories grouped ({columns}; the setting '
                                        'applies to every categorical column)',
                                  f'catégories rares regroupées ({columns} ; le réglage vaut '
                                  'pour toutes les colonnes catégorielles)'),
            'missing_indicator': _t(lang, f'a missing-value indicator for {columns}',
                                    f'un indicateur de valeur manquante pour {columns}'),
            'cap_declared_range': _t(lang, f'caps on {columns}', f'des plafonds sur {columns}'),
            'signed_log': _t(lang, f'a signed log of {columns}', f'un log signé de {columns}'),
        }[rule])
    return '; '.join(parts) if lang != FR else ' ; '.join(parts)


def preprocessing_recommended(draft: Mapping, lang: str) -> dict:
    """``recommended`` of a drafted preparation: ``{value, why, reasons}``; ``why`` names
    the drafted parameters, each reason's ``text`` says what the check found."""
    if draft['drafted']:
        why = _t(lang, 'Drafted from the data quality check, which does not read the target: '
                       f'{_summary(draft["reasons"], lang)}. The default (nothing added) stays '
                       'the comparison option.',
                 "Établie d'après le contrôle de qualité des données, qui ne lit pas la "
                 f'cible : {_summary(draft["reasons"], lang)}. La préparation par défaut '
                 "(rien d'ajouté) reste l'option de comparaison.")
    else:
        why = _t(lang, 'The data quality check, which does not read the target, finds nothing '
                       'the rules act on (many rare categories, many missing cells, values '
                       'outside a declared range, a skewed distribution): nothing is added.',
                 "Le contrôle de qualité des données, qui ne lit pas la cible, ne trouve rien "
                 'sur quoi les règles agissent (beaucoup de catégories rares, beaucoup de '
                 'cellules manquantes, des valeurs hors d\'une plage déclarée, une distribution '
                 "asymétrique) : rien n'est ajouté.")
    return {'value': copy.deepcopy(draft['value']), 'why': why,
            'reasons': copy.deepcopy(draft['reasons'])}


def preprocessing_alternatives(draft: Mapping, lang: str) -> list[dict]:
    """The comparison option of a drafted preparation: the default, nothing added."""
    value = copy.deepcopy(governance.DEFAULT_PREPROCESSING)
    value['motivated_by'] = list(draft['motivated_by'])
    return [{'value': value,
             'label': _t(lang, 'Without transformation', 'Sans transformation'),
             'why': _t(lang, 'Nothing is added, to compare: the model keeps only the fixed '
                             'preparation.',
                       "Rien n'est ajouté, pour comparer : le modèle garde seulement la "
                       'préparation fixe.')}]


def with_preprocessing_draft(study, state: Mapping, action: dict, lang: str) -> dict:
    """The ``propose`` of the preparation with the drafted value (structural-first study
    with a current quality check); ``action`` unchanged otherwise."""
    draft = preprocessing_draft(study, state, lang)
    if draft is None:
        return action
    out = dict(action)
    out['default_value'] = copy.deepcopy(draft['value'])
    out['recommended'] = preprocessing_recommended(draft, lang)
    # R40, R41: every column's verdict and the threshold that decided it (additive, last).
    out['recommended']['verdicts'] = (quality_verdicts(study, state, lang, draft) or {}).get(
        'columns')
    if draft['drafted']:
        out['alternatives'] = preprocessing_alternatives(draft, lang)
    return out


# --- the stamp, in the junior's words (R7) -----------------------------------------------

def contingency_text(looks: int, by_activity: Mapping, motivating: int, lang: str) -> str:
    """``data_contingent_reason.junior_text``: why a preparation is stamped, in the study
    language, the term "look at the target" first, then this study's looks."""
    from . import audience
    named = _join([audience.activity_words(a, lang) for a in sorted(by_activity)], lang)
    parts = []
    if looks:
        parts.append(_t(lang, f'This preparation is proposed after {looks} look(s) at the '
                              f'target ({named}).',
                        f'Cette préparation est proposée après {looks} regard(s) sur la cible '
                        f'({named}).'))
    if motivating:
        parts.append(_t(lang, f'{motivating} of the analyses that motivate it read the '
                              'target.',
                        f"{motivating} des analyses qui la motivent ont lu la cible."))
    parts.append(_t(lang, 'A look at the target is an analysis that read the variable to '
                          'predict. This is not a mistake: it is recorded because a choice '
                          'guided by the target can make the development figures slightly '
                          'optimistic.',
                    "Un regard sur la cible est une analyse qui a lu la variable à prédire. "
                    "Ce n'est pas une erreur : c'est noté parce qu'un choix guidé par la cible "
                    'peut rendre les chiffres de développement un peu optimistes.'))
    return ' '.join(parts)


def variant_contingency_text(families: list, lang: str) -> str:
    """``junior_text`` of a variant proposal stamped data-contingent."""
    words = _join([family_words(f, lang) for f in families if f], lang) or _t(
        lang, 'this variant', 'cette variante')
    return _t(lang, f'{words[:1].upper() + words[1:]} is proposed after the diagnostics of the '
                    'linear model showed a pattern it does not follow: a trial chosen after '
                    'seeing these rows, so its comparison is recorded as data-contingent.',
              f'{words[:1].upper() + words[1:]} est proposée après que les diagnostics du '
              'modèle linéaire ont montré une forme qu\'il ne suit pas : un essai choisi après '
              'avoir vu ces lignes, dont la comparaison est notée comme dépendante des données.')


# --- the variants (R13, D9) ----------------------------------------------------------------

def _flag_words(flags: list, lang: str) -> tuple[list[str], list[str], bool]:
    nonlinear = [f['feature'] for f in flags if f.get('check') == 'nonlinearity'
                 and f.get('feature')][:3]
    interaction = [f['feature'] for f in flags if f.get('check') == 'interaction'
                   and f.get('feature')][:3]
    calibration = any(f.get('check') == 'calibration_slope' for f in flags)
    return nonlinear, interaction, calibration


def signal_words(flags: list, lang: str) -> str:
    """The diagnostics' flags in words: "the shape of lead_time and the effect of
    arrival_date_month"."""
    nonlinear, interaction, calibration = _flag_words(flags, lang)
    parts = []
    if nonlinear:
        parts.append(_t(lang, 'the shape of ' + _join(nonlinear, lang),
                        'la forme de ' + _join(nonlinear, lang)))
    if interaction:
        parts.append(_t(lang, 'an effect that varies with ' + _join(interaction, lang),
                        'un effet qui varie selon ' + _join(interaction, lang)))
    if calibration:
        parts.append(_t(lang, 'the spread of its scores (their calibration)',
                        "l'étalement de ses scores (leur calibration)"))
    return _join(parts, lang)


def ebm_question(flags: list, task: str, lang: str) -> str:
    """The EBM variant's question in the study language, naming the flags."""
    signal = signal_words(flags, lang) or _t(lang, 'the pattern the diagnostics show',
                                             'la forme que montrent les diagnostics')
    if task == st.REGRESSION:
        text = _t(lang, 'Does a readable non-linear model predict with a smaller error by '
                        f'following what the linear model misses: {signal}?',
                  'Un modèle non linéaire lisible prédit-il avec une erreur plus petite en '
                  f'suivant ce que le modèle linéaire manque : {signal} ?')
    else:
        text = _t(lang, 'Does a readable non-linear model rank the rows better by following '
                        f'what the linear model misses: {signal}?',
                  'Un modèle non linéaire lisible classe-t-il mieux les lignes en suivant ce '
                  f'que le modèle linéaire manque : {signal} ?')
    return text[:trials.MAX_QUESTION]


def variant_draft(study, state: Mapping, lang: str) -> dict | None:
    """``{value, flags, diagnostic}`` of the drafted variants when the diagnostics flag a
    pattern, the EBM is allowed and at least two trials are left (structural-first study);
    None otherwise (the state's draft, the tuned penalty alone, stays)."""
    if not st.structural_first(state):
        return None
    case = _case(state)
    task = st.task_of(state)
    rid, diag = current_values(study, state, st.DIAG_SLOT[task])
    if diag is None or case is None:
        return None
    families = trials.shortlist(case.document, diag, task, lang, rid)
    if families.get('recommendation') != 'compare_nonlinear':
        return None
    ebm = next((f for f in families['families'] if f['family'] == 'ebm'), None)
    if ebm is None or not ebm.get('allowed') or trials.budget(state)['remaining'] < 2:
        return None
    flags = list(families['evidence']['flags'])
    value = st.default_variant(state)
    variant = {'kind': 'family', 'family': 'ebm',
               trials.QUESTION_KEY: ebm_question(flags, task, lang)}
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        variant.update({trials.ORIGIN_KEY: 'diagnostic_informed',
                        trials.DIAGNOSTIC_RESULT_KEY: rid})
    value[trials.LIST_KEY].append(variant)
    if len(trials.used_specs(state, value)) > trials.MAX_VARIANTS:
        return None
    return {'value': value, 'flags': flags, 'diagnostic': rid}


def variant_recommended(draft: Mapping, lang: str) -> dict:
    signal = signal_words(draft['flags'], lang)
    why = _t(lang, f'The diagnostics of the linear model flag {signal}: the Explainable '
                   'Boosting Machine (EBM), a readable non-linear model, is drafted beside the '
                   'penalty chosen by nested cross-validation to test it. Each variant spends '
                   'one trial of the budget of three and adds a little selection optimism; the '
                   'EBM, chosen after the diagnostics, is recorded as data-contingent.',
             f'Les diagnostics du modèle linéaire signalent {signal} : l\'Explainable Boosting '
             'Machine (EBM), un modèle non linéaire lisible, est proposée à côté de la pénalité '
             'choisie par validation croisée imbriquée pour le vérifier. Chaque variante '
             "dépense un essai du budget de trois et ajoute un peu d'optimisme de sélection ; "
             "l'EBM, choisie après les diagnostics, est notée comme dépendante des données.")
    return {'value': copy.deepcopy(draft['value']), 'why': why}


def with_variant_draft(study, state: Mapping, action: dict, lang: str) -> dict:
    draft = variant_draft(study, state, lang)
    if draft is None:
        return action
    out = dict(action)
    out['default_value'] = copy.deepcopy(draft['value'])
    out['recommended'] = variant_recommended(draft, lang)
    return out


# --- the families in the junior's words (R14, D10) -----------------------------------------

JUNIOR_WORDS = {
    EN: {'linear': 'the linear model',
         'ebm': 'an Explainable Boosting Machine (EBM), a readable model with one curve per '
                'variable',
         'hgb': 'tree boosting (the same family as XGBoost and LightGBM)'},
    FR: {'linear': 'le modèle linéaire',
         'ebm': 'une Explainable Boosting Machine (EBM), un modèle lisible avec une courbe par '
                'variable',
         'hgb': "boosting d'arbres (même famille que XGBoost et LightGBM)"},
}
NOT_OFFERED_KEYS = ('name', 'words', 'why')
NOT_OFFERED = [
    {'name': 'random forest',
     'words': {EN: 'a random forest', FR: 'une forêt aléatoire'},
     'why': {EN: 'A random forest usually does less well than a tuned boosting on tabular '
                 'data, and a variant of the same kind would spend a trial for little new '
                 'information.',
             FR: 'Une forêt aléatoire fait en général moins bien qu\'un boosting réglé sur des '
                 'données tabulaires, et une variante de même nature dépenserait un essai pour '
                 "peu d'information nouvelle."}}]


def family_words(family: str, lang: str) -> str:
    return JUNIOR_WORDS[FR if lang == FR else EN].get(family, str(family))


def with_junior_words(families: Mapping | None, lang: str) -> Mapping | None:
    """``model_families`` with ``families[].junior_words`` and ``not_offered`` (additive)."""
    if not isinstance(families, Mapping):
        return families
    out = dict(families)
    out['families'] = [{**f, 'junior_words': family_words(f.get('family'), lang)}
                       for f in families.get('families') or []]
    lang_key = FR if lang == FR else EN
    out['not_offered'] = [{'name': n['name'], 'words': n['words'][lang_key],
                           'why': n['why'][lang_key]} for n in NOT_OFFERED]
    return out


def families_sentence(lang: str) -> str:
    """One sentence for the variant digest: boosting named as the junior knows it, and why no
    random forest."""
    return _t(lang, 'Boosting here is tree boosting, the same family as XGBoost and LightGBM. '
                    'A random forest is not offered: ' + NOT_OFFERED[0]['why'][EN][:1].lower()
              + NOT_OFFERED[0]['why'][EN][1:],
              "Le boosting est ici le boosting d'arbres, la même famille que XGBoost et "
              'LightGBM. Une forêt aléatoire n\'est pas proposée : '
              + NOT_OFFERED[0]['why'][FR][:1].lower() + NOT_OFFERED[0]['why'][FR][1:])


# --- a model outside the catalogue (R15, D11) -----------------------------------------------

def _norm(name: Any) -> str:
    return re.sub(r'[^a-z0-9]', '', str(name or '').lower())


# The asked names whose closest family is tree boosting (D11); anything else is closest to
# the readable non-linear family.
BOOSTING_LIKE = ('randomforest', 'rf', 'forest', 'foretaleatoire', 'xgboost', 'xgb', 'lightgbm',
                 'lgbm', 'lgb', 'catboost', 'gradientboosting', 'gbm', 'gbdt', 'gbt',
                 'adaboost', 'extratrees', 'boosting')
ASKED_WORDS = {
    'svm': ('an SVM (support vector machine)', 'un SVM (machine à vecteurs de support)'),
    'svc': ('an SVM (support vector machine)', 'un SVM (machine à vecteurs de support)'),
    'supportvectormachine': ('an SVM (support vector machine)',
                             'un SVM (machine à vecteurs de support)'),
    'knn': ('k-nearest neighbours (k-NN)', 'les k plus proches voisins (k-NN)'),
    'kneighbors': ('k-nearest neighbours (k-NN)', 'les k plus proches voisins (k-NN)'),
    'neuralnetwork': ('a neural network', 'un réseau de neurones'),
    'mlp': ('a neural network', 'un réseau de neurones'),
    'nn': ('a neural network', 'un réseau de neurones'),
    'gam': ('a GAM (generalised additive model)', 'un GAM (modèle additif généralisé)'),
    'randomforest': ('a random forest', 'une forêt aléatoire'),
    'rf': ('a random forest', 'une forêt aléatoire'),
    'xgboost': ('XGBoost', 'XGBoost'), 'xgb': ('XGBoost', 'XGBoost'),
    'lightgbm': ('LightGBM', 'LightGBM'), 'lgbm': ('LightGBM', 'LightGBM'),
    'catboost': ('CatBoost', 'CatBoost'),
}


def closest_family(asked: Any) -> str:
    return 'hgb' if _norm(asked) in BOOSTING_LIKE else 'ebm'


def unknown_family(value: Any) -> str | None:
    """The family a ``model_variant`` value asks for that is outside the catalogue (a
    ``family`` variant naming another family, or a kind that is a known model name), else
    None."""
    if not isinstance(value, Mapping):
        return None
    items = value.get(trials.LIST_KEY) if trials.LIST_KEY in value else [value]
    for v in items if isinstance(items, (list, tuple)) else []:
        if not isinstance(v, Mapping):
            continue
        kind = v.get('kind')
        if kind == 'family' and v.get('family') not in trials.FAMILIES:
            return str(v.get('family'))
        if kind not in trials.KINDS and (_norm(kind) in ASKED_WORDS
                                         or _norm(kind) in BOOSTING_LIKE):
            return str(kind)
    return None


def family_refusal(asked: str, lang: str) -> dict:
    """The details a refusal of a family outside the catalogue adds (D11): ``reason``,
    ``asked``, ``closest_family``, ``workbench`` and ``junior_message`` in the study
    language (why the catalogue is closed, the closest family and why, the workbench for a
    personal exploration that is not study evidence)."""
    closest = closest_family(asked)
    pair = ASKED_WORDS.get(_norm(asked))
    asked_words = (pair[1] if lang == FR else pair[0]) if pair else f'« {asked} »' \
        if lang == FR else f'"{asked}"'
    catalogue = _t(lang, 'the linear model, the Explainable Boosting Machine (EBM) and tree '
                         'boosting (the same family as XGBoost and LightGBM)',
                   "le modèle linéaire, l'Explainable Boosting Machine (EBM) et le boosting "
                   "d'arbres (même famille que XGBoost et LightGBM)")
    if closest == 'hgb':
        why = _t(lang, 'Tree boosting is the closest family: it adds trees one after another, '
                       'each correcting the previous ones, as XGBoost and LightGBM do.',
                 "Le boosting d'arbres est la famille la plus proche : il ajoute des arbres "
                 "l'un après l'autre, chacun corrigeant les précédents, comme XGBoost et "
                 'LightGBM.')
        if _norm(asked) in ('randomforest', 'rf', 'forest', 'foretaleatoire'):
            why += ' ' + NOT_OFFERED[0]['why'][FR if lang == FR else EN]
    else:
        why = _t(lang, 'The closest family is the EBM: a non-linear model that stays readable, '
                       'with one curve per variable and a few interactions.',
                 "La famille la plus proche est l'EBM : un modèle non linéaire qui reste "
                 'lisible, avec une courbe par variable et quelques interactions.')
    message = _t(
        lang,
        f'{asked_words[:1].upper() + asked_words[1:]} is not in the study\'s catalogue, which '
        f'holds {catalogue}. The catalogue is closed on purpose: each family needs a fixed '
        'tuning grid, a trial of the budget of three, an evaluation on the final test, and '
        f'notebook cells that compute it again. {why} Nothing was recorded and no trial was '
        f'spent. To try it anyway, use the workbench ({WORKBENCH}), on the development '
        'training rows: a personal exploration that is not study evidence (not compared, not '
        'chosen, not tested on the final test, not reported as a result).',
        f"{asked_words[:1].upper() + asked_words[1:]} n'est pas dans le catalogue de "
        f"l'étude, qui contient {catalogue}. Le catalogue est fermé exprès : chaque famille "
        "demande une grille de réglage fixe, un essai du budget de trois, une évaluation sur "
        "le test final et des cellules du notebook qui la recalculent. "
        f"{why} Rien n'a été enregistré et aucun essai n'a été dépensé. Pour l'essayer quand "
        f"même, utilisez votre établi ({WORKBENCH}), sur les lignes d'entraînement de "
        "l'échantillon de développement : une exploration personnelle qui n'est pas une "
        "preuve de l'étude (ni comparée, ni choisie, ni testée sur le test final, ni "
        'présentée comme un résultat).')
    return {'reason': 'family_not_in_catalogue', 'asked': asked, 'closest_family': closest,
            'workbench': WORKBENCH, 'junior_message': message}


# --- calendar years under a temporal evaluation (R12, D8) ------------------------------------

TEMPORAL_METHODS = ('temporal_folds', 'forward_chaining', 'ordered_retrospective',
                    'ordinal_cutoff')


def temporal_evaluation(state: Mapping) -> bool:
    """Whether the study evaluates (or will, by the draft) along time: its split decision, an
    open split proposal, else the drafted scheme (``state.cv_method``)."""
    value = ((state.get('decisions') or {}).get('split') or {}).get('value')
    if not (isinstance(value, Mapping) and value.get('method')):
        value = next((p['value'] for p in (state.get('proposals') or {}).values()
                      if p.get('decision_id') == 'split' and p.get('status') == 'open'
                      and isinstance(p.get('value'), Mapping)), None)
    if isinstance(value, Mapping) and value.get('method'):
        return value['method'] in TEMPORAL_METHODS
    return st.has_wp_b1_decisions(state) and st.cv_method(state) in TEMPORAL_METHODS


def calendar_years(case, availability: Mapping | None) -> list[str]:
    """The features the case declares ``calendar: year`` that ``availability`` keeps."""
    if case is None or not isinstance(availability, Mapping):
        return []
    return [v['name'] for v in case.document['variables']
            if v.get('calendar') == 'year' and v['role'] == 'feature'
            and availability.get(v['name']) in USABLE]


def calendar_advisory(case, state: Mapping, availability: Mapping | None,
                      lang: str) -> str | None:
    """The advisory on calendar-year features kept under a temporal evaluation (D8 a), or
    None: "keep the month and the week; the year can only extrapolate"."""
    years = calendar_years(case, availability)
    if not years or not temporal_evaluation(state):
        return None
    named = _join(years, lang)
    return _t(lang, f'{named} holds a calendar year and the evaluation follows time: the '
                    'validation years come after the training years, so a year term can only '
                    'extrapolate a trend the future may not follow. Keep the month and the '
                    'week; question the year.',
              f"{named} contient une année civile et l'évaluation suit le temps : les années "
              "de validation viennent après celles d'entraînement, donc un terme d'année ne "
              "peut qu'extrapoler une tendance que l'avenir peut ne pas suivre. Gardez le mois "
              "et la semaine ; interrogez l'année.")


__all__ = ['preprocessing_draft', 'with_preprocessing_draft', 'distribution_run',
           'missing_distributions', 'screened_columns', 'variant_draft', 'with_variant_draft',
           'with_junior_words', 'family_words', 'family_refusal', 'unknown_family',
           'closest_family', 'contingency_text', 'variant_contingency_text',
           'calendar_advisory', 'calendar_years', 'temporal_evaluation', 'PIPELINE_SENTENCE']
