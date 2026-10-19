"""The sealed final-test partition of a study (ADR 0006, v0.2a).

At ``init``, before any look at the data, the engine sets aside a **final test**: a
share of the rows (:data:`DEFAULT_FRACTION`, 20 %) that no activity reads until it is
opened (opening is v0.2b). Every other row is a **development row**; the ``split``
decision divides the development rows into training and validation rows.

How the rows are chosen:

* the case declares an ``order`` (``CASE-CONTRACT.md``): ``temporal``, the last rows in
  that order (by file line, or by a numeric or integer column, ties broken by line);
* otherwise, a binary target: ``stratified``, the same share of each target label;
* otherwise, a regression target: ``quantile_stratified``, the same share of each of
  :data:`QUANTILE_BINS` quantile bins of the target.

A stratified assignment draws, in each stratum (in file order), a permutation from
``numpy.random.default_rng(seed)`` and keeps the first ``floor(n * fraction + 0.5)``
rows. The seed (:data:`DEFAULT_SEED`) is recorded, so the assignment is reproducible
from the dataset bytes alone.

Storage (``state.partition``, :data:`RECORD_KEYS`): counts, the method and its
parameters, and the two row-key sets as content-addressed blobs (sorted keys, one per
line; the blob name is the sha256 of that list). The development blob is what every
activity reads through :func:`mlkit.study.data.load_development`; the final-test blob is
read only to verify the partition.

The final test receives one check at ``init``, :func:`schema_check`: the declared types
parse, the target holds only allowed labels, no target is missing. It reports counts
only, never a value, a label, or a row key, and a failure refuses ``init``
(``invalid_case`` or ``unsupported_capability``) with those counts.

With ``duplicates: {policy: group}`` (v0.2b, WP-B3), identical records are one entity
group (:func:`mlkit.study.data.entity_groups`) and a group is never divided: a
stratified assignment draws whole groups (:func:`grouped_stratified`; identical records
share their target, hence their stratum), and a temporal assignment moves every copy to the
side of the group's earliest record. The record then holds ``groups`` (an optional key,
:data:`GROUPS_KEYS`); without the declaration nothing changes.

A study created before ADR 0006 has no ``partition``: it loads and runs as before,
every row is a development row, and surfaces show "no final test"
(:func:`final_test_status`). Nothing is migrated.

``status`` is ``sealed`` in v0.2a (:data:`STATUSES`). v0.2b (WP-B1) adds ``opened`` and
the optional ``opening`` record (:data:`OPENING_KEYS`): the final test is opened once, by the
``final_test`` decision in the junior's words, and the one execution of
``final_test.evaluation`` sets the status to ``opened`` when it is reserved, before any
final-test row is read, so a crash can never let it be scored twice. The other keys do not
change.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Mapping

from . import records as rec
from .case import Case, CaseError
from .errors import StudyError

SCHEMA = 'hypotrail.final-test/1'
STATE_KEY = 'partition'
STATUSES = ('sealed', 'opened')
OPENED = 'opened'
# WP-B1: the opening record, written when the one final evaluation is reserved; its
# ``result_id`` is set when that evaluation is promoted (null until then, or forever when
# the execution was interrupted: the final test is consumed either way).
OPENING_KEYS = ('revision', 'execution_id', 'proposal_id', 'user_words', 'model', 'rule',
                'time', 'result_id')
# Decisions whose confirmation after the opening makes a result "after the final test", and
# the result slots whose recomputation after it does.
AFTER_DECISIONS = ('prediction_time', 'feature_availability', 'split', 'success_criterion',
                   'preprocessing', 'model_variant', 'policy', 'model_choice')
AFTER_SLOT_PREFIXES = ('split', 'fit.', 'policy.', 'evaluate.')
STATUS_ABSENT = 'absent'
METHODS = ('stratified', 'quantile_stratified', 'temporal')
DEFAULT_FRACTION = 0.2
DEFAULT_SEED = 0
QUANTILE_BINS = 5
RECORD_KEYS = ('schema', 'status', 'method', 'fraction', 'seed', 'stratified_on', 'bins',
               'order', 'dataset_sha256', 'n_rows', 'development', 'final_test',
               'schema_check', 'created', 'implementation')
# v0.2b: ``groups`` (WP-B3) only when the case declares ``duplicates: {policy: group}``;
# ``opening`` (WP-B1) once the final test is opened.
OPTIONAL_RECORD_KEYS = ('groups', 'opening')
GROUPS_KEYS = ('policy', 'n_groups', 'n_rows', 'moved_rows')
PART_KEYS = ('n_rows', 'row_keys')
CHECK_KEYS = ('status', 'n_rows', 'checks', 'reveals')
CHECK_ITEM_KEYS = ('check', 'column', 'failing_rows')
CHECK_STATUSES = ('pass', 'fail')
ACTIVITY = 'init.final_test'
EXPOSURE_PURPOSE = 'sealed'
DEVELOPMENT = 'development'
FINAL_TEST = 'final_test'


def _round(n: int, fraction: float) -> int:
    return int(math.floor(n * fraction + 0.5))


# --- assignment (at init) ----------------------------------------------------------------

def _strata(case: Case, frame) -> list[str]:
    """One stratum label per row: the target class, or its quantile bin."""
    import pandas as pd
    target = frame[case.target_column]
    if case.task == 'binary':
        from .activities import matches
        labels = matches(target, case.positive_label).astype(int).astype(str)
        return [('missing' if pd.isna(t) else lab) for t, lab in zip(target, labels)]
    values = pd.to_numeric(target, errors='coerce')
    bins = pd.qcut(values, QUANTILE_BINS, labels=False, duplicates='drop')
    return ['missing' if pd.isna(b) else str(int(b)) for b in bins]


def _stratified(keys: list[str], strata: list[str], fraction: float, seed: int) -> list[str]:
    import numpy as np
    rng = np.random.default_rng(seed)
    final: list[str] = []
    for stratum in sorted(set(strata)):
        members = [k for k, s in zip(keys, strata) if s == stratum]
        order = rng.permutation(len(members))
        final += [members[i] for i in order[:_round(len(members), fraction)]]
    return final


def grouped_stratified(keys: list[str], strata: list[str], groups: Mapping[str, str],
                       fraction: float, seed: int) -> list[str]:
    """The rows drawn by a stratified assignment that never divides an entity group.

    In each stratum (sorted, as :func:`_stratified`), the groups are listed in order of
    their first row and permuted with ``numpy.random.default_rng(seed)``; a group is drawn
    when its rows still fit in ``floor(n * fraction + 0.5)``. When every group is one row,
    this draws exactly the rows :func:`_stratified` draws. A group's rows share one stratum
    (identical records share their target); a group spread over strata is an
    ``integrity_error``."""
    import numpy as np
    rng = np.random.default_rng(seed)
    stratum_of: dict[str, str] = {}
    members: dict[str, list[str]] = {}
    for k, s_ in zip(keys, strata):
        g = groups.get(k, k)
        if stratum_of.setdefault(g, s_) != s_:
            raise StudyError('integrity_error', 'Identical records fall in different strata.',
                             details={'group': g})
        members.setdefault(g, []).append(k)
    final: list[str] = []
    for stratum in sorted(set(strata)):
        units = [g for g in members if stratum_of[g] == stratum]
        size = sum(len(members[g]) for g in units)
        target = _round(size, fraction)
        taken = 0
        for i in rng.permutation(len(units)):
            group = members[units[i]]
            if taken + len(group) <= target:
                final += group
                taken += len(group)
    return final


def _whole_groups(keys: list[str], final: list[str], groups: Mapping[str, str]
                  ) -> tuple[list[str], int]:
    """``final`` with every divided group moved to the side of its earliest row (in
    ``keys`` order); the number of rows moved."""
    chosen = set(final)
    side: dict[str, bool] = {}
    for k in keys:
        side.setdefault(groups.get(k, k), k in chosen)
    out = [k for k in keys if side[groups.get(k, k)]]
    moved = len(set(out) ^ chosen)
    return out, moved


def _ranked_keys(case: Case, frame, keys: list[str]) -> list[str]:
    """``keys`` from the earliest to the latest in the declared order."""
    import pandas as pd
    order = case.order
    line = [int(k[1:]) for k in keys]
    if order['by'] == 'line':
        ranked = sorted(range(len(keys)), key=lambda i: line[i])
    else:
        v = pd.to_numeric(frame[order['by']], errors='coerce').to_numpy()
        ranked = sorted(range(len(keys)), key=lambda i: (v[i], line[i]))
    if order['direction'] == 'descending':
        ranked.reverse()
    return [keys[i] for i in ranked]


def _temporal(case: Case, frame, keys: list[str], fraction: float) -> tuple[list[str], dict]:
    import pandas as pd
    order = case.order
    line = [int(k[1:]) for k in keys]
    if order['by'] == 'line':
        ranked = sorted(range(len(keys)), key=lambda i: line[i])
        values = None
    else:
        values = pd.to_numeric(frame[order['by']], errors='coerce')
        if values.isna().any():
            raise CaseError('invalid_case', 'The order column must hold a number on every row.',
                            problems=[{'path': 'order.by',
                                       'problem': f'{int(values.isna().sum())} rows of '
                                                  f'{order["by"]!r} hold no number, so they '
                                                  f'cannot be placed in time.'}])
        v = values.to_numpy()
        ranked = sorted(range(len(keys)), key=lambda i: (v[i], line[i]))
    if order['direction'] == 'descending':
        ranked.reverse()
    n_final = _round(len(keys), fraction)
    final_idx = ranked[len(ranked) - n_final:] if n_final else []
    ties = 0
    if values is not None and n_final and n_final < len(ranked):
        v = values.to_numpy()
        cut = v[final_idx[0]]
        ties = int(sum(1 for i in ranked[:len(ranked) - n_final] if v[i] == cut))
    return [keys[i] for i in final_idx], {'ties_at_cut': ties}


def assign(case: Case, index, frame, *, fraction: float = DEFAULT_FRACTION,
           seed: int = DEFAULT_SEED) -> dict:
    """``{record, development, final_test}``: the partition of every row of ``frame``
    (indexed by row key, all records of ``index``). ``record`` lacks the blob digests,
    the schema check, and ``created``; :func:`seal` completes it."""
    from .data import DUPLICATES_GROUP, duplicate_summary, entity_groups
    keys = list(index.keys)
    order = case.order
    grouped = case.duplicates_policy == DUPLICATES_GROUP
    groups = entity_groups(index) if grouped else None
    moved = 0
    if order:
        ranked_keys, extra = _temporal(case, frame, keys, fraction)
        final = ranked_keys
        if grouped:
            ranked = _ranked_keys(case, frame, keys)
            final, moved = _whole_groups(ranked, final, groups)
        method, stratified_on, bins, used_seed = 'temporal', None, None, None
        order_out = {'by': order['by'], 'direction': order['direction'], **extra}
    else:
        strata = _strata(case, frame)
        final = (grouped_stratified(keys, strata, groups, fraction, seed) if grouped
                 else _stratified(keys, strata, fraction, seed))
        method = 'stratified' if case.task == 'binary' else 'quantile_stratified'
        stratified_on = case.target_column
        bins = None if case.task == 'binary' else QUANTILE_BINS
        used_seed, order_out = seed, None
    chosen = set(final)
    development = [k for k in keys if k not in chosen]
    final = [k for k in keys if k in chosen]
    if len(development) + len(final) != len(keys):
        raise StudyError('integrity_error', 'The final-test assignment lost rows.')
    implementation = ('mlkit.study.partition (last rows in the declared order)' if order else
                      'mlkit.study.partition (per-stratum permutation from '
                      'numpy.random.default_rng(seed))')
    if grouped:
        implementation += ('; identical records kept together as one entity group '
                           '(duplicates: group)')
    record = {'schema': SCHEMA, 'status': 'sealed', 'method': method, 'fraction': fraction,
              'seed': used_seed, 'stratified_on': stratified_on, 'bins': bins,
              'order': order_out, 'dataset_sha256': index.dataset_sha256, 'n_rows': len(keys),
              'implementation': implementation}
    if grouped:
        summary = duplicate_summary(case, index)
        record['groups'] = {'policy': DUPLICATES_GROUP, 'n_groups': summary['n_groups'],
                            'n_rows': summary['n_rows'], 'moved_rows': moved}
    return {'record': record, 'development': development, 'final_test': final}


# --- the final test's schema check (counts only) ----------------------------------------

def schema_check(case: Case, final_frame, development_frame) -> dict:
    """Pass/fail of the declared schema on the final-test rows, as counts only.

    Checks: every ``numeric``/``integer`` cell parses once ``na_values`` are missing
    (``numeric_cells``, one item per such variable); no target cell is missing
    (``target_missing``); a binary target holds only the case labels, or, without
    ``negative_label``, the one other label the development rows hold
    (``target_labels``). Each item gives the number of failing rows, never a value."""
    import pandas as pd
    from pandas.api.types import is_numeric_dtype
    checks = []
    for v in case.document['variables']:
        if v['type'] not in ('numeric', 'integer'):
            continue
        column = final_frame[v['name']]
        if is_numeric_dtype(column):
            bad = 0
        else:
            bad = int((column.notna() & pd.to_numeric(column, errors='coerce').isna()).sum())
        checks.append({'check': 'numeric_cells', 'column': v['name'], 'failing_rows': bad})
    target = final_frame[case.target_column]
    checks.append({'check': 'target_missing', 'column': case.target_column,
                   'failing_rows': int(target.isna().sum())})
    if case.task == 'binary':
        allowed = {str(case.positive_label)}
        negative = case.document['target'].get('negative_label')
        if negative is not None:
            allowed.add(str(negative))
        else:
            allowed |= set(development_frame[case.target_column].dropna().astype(str))
        labels = target.dropna().astype(str)
        checks.append({'check': 'target_labels', 'column': case.target_column,
                       'failing_rows': int((~labels.isin(allowed)).sum())})
    failing = any(item['failing_rows'] for item in checks)
    return {'status': 'fail' if failing else 'pass', 'n_rows': len(final_frame),
            'checks': checks, 'reveals': 'counts of failing rows only, no value'}


def _check_path(case: Case, item: Mapping) -> str:
    """The case path a failed check concerns: the variable's type, or the target."""
    if item['check'] == 'numeric_cells':
        names = case.column_names
        return f'variables[{names.index(item["column"])}].type'
    return 'target'


def refuse_failed_check(case: Case, check: Mapping) -> None:
    """Refuse ``init`` when the final test fails its schema check (counts only)."""
    if check['status'] == 'pass':
        return
    failed = [c for c in check['checks'] if c['failing_rows']]
    problems = [{'path': _check_path(case, c), 'partition': FINAL_TEST,
                 'problem': f'{c["failing_rows"]} sealed final-test rows fail the check '
                            f'{c["check"]} on {c["column"]!r}; their values are not shown, '
                            f'since the final test stays sealed.'} for c in failed]
    if all(c['check'] == 'target_missing' for c in failed):
        from .data import CAPABILITY_MISSING_TARGET
        reason = {'code': 'unsupported_capability', 'capability': CAPABILITY_MISSING_TARGET,
                  'path': 'target.column', 'column': failed[0]['column'],
                  'rows': failed[0]['failing_rows'], 'partition': FINAL_TEST,
                  'reason': f'{failed[0]["failing_rows"]} sealed final-test rows have no value '
                            f'of the target. This version neither drops nor imputes target '
                            f'rows silently.'}
        raise CaseError('unsupported_capability',
                        f'This case needs a capability that is not available yet: '
                        f'{CAPABILITY_MISSING_TARGET}', details={'reasons': [reason]})
    raise CaseError('invalid_case', 'Some sealed final-test values would silently change '
                                    'meaning.', problems=problems,
                    details={'final_test_check': dict(check)})


def with_final_test_counts(error: CaseError, check: Mapping) -> CaseError:
    """A refusal of the development rows, completed with the final test's counts when it
    fails too: a missing-target reason gains ``final_test_rows``, any other refusal
    ``details.final_test_check``. Never a value of the final test."""
    if check['status'] == 'pass':
        return error
    missing = next(c['failing_rows'] for c in check['checks'] if c['check'] == 'target_missing')
    from .data import CAPABILITY_MISSING_TARGET
    reasons = error.details.get('reasons') or []
    for reason in reasons:
        if reason.get('capability') == CAPABILITY_MISSING_TARGET:
            reason['final_test_rows'] = missing
    error.details['final_test_check'] = dict(check)
    return error


def seal(record: Mapping, *, development_sha: str, n_development: int, final_sha: str,
         n_final: int, check: Mapping, created: str) -> dict:
    """The complete ``state.partition`` record."""
    out = dict(record)
    out.update(development={'n_rows': n_development, 'row_keys': development_sha},
               final_test={'n_rows': n_final, 'row_keys': final_sha},
               schema_check=dict(check), created=created)
    return {k: out[k] for k in RECORD_KEYS + OPTIONAL_RECORD_KEYS if k in out}


# --- reading -----------------------------------------------------------------------------

def of(state: Mapping) -> dict | None:
    """The study's partition record, or None for a study created before ADR 0006."""
    return state.get(STATE_KEY)


def inputs(state: Mapping) -> dict | None:
    """What an activity's identity records about the rows it may read:
    ``{"row_keys": <development blob sha256>, "n_rows": n}``, or None for a legacy study
    (whose identities then stay exactly as before)."""
    part = of(state)
    if part is None:
        return None
    return {'row_keys': part['development']['row_keys'],
            'n_rows': part['development']['n_rows']}


def development_keys(read_blob: Callable[[str], bytes], development: Mapping | None):
    """The development row keys named by ``development`` (from :func:`inputs`), verified
    against their count; None when there is no partition (every row is a development
    row)."""
    if development is None:
        return None
    keys = rec.parse_row_keys(read_blob(development['row_keys']))
    if len(keys) != development['n_rows']:
        raise StudyError('integrity_error', 'The development rows blob does not hold the '
                                            'recorded number of rows.',
                         details={'expected': development['n_rows'], 'actual': len(keys)})
    return keys


STATUS_VIEW_KEYS = ('status', 'rows', 'method', 'fraction', 'development_rows', 'schema_check',
                    # WP-B1: the opening, and what changed after it.
                    'opening', 'post_final_test', 'changed_after')
OPENING_VIEW_KEYS = ('revision', 'model', 'rule', 'result_id', 'user_words')


def changed_after(state: Mapping, started: Mapping | None = None) -> list[str]:
    """What changed after the final test was opened (WP-B1): the decisions of
    :data:`AFTER_DECISIONS` confirmed again (or waiting to be) at a later revision, and the
    current results of :data:`AFTER_SLOT_PREFIXES` computed later (``started``:
    ``{slot: started_revision}`` of the current results, given by the view). Empty while
    the final test is sealed."""
    part = of(state)
    opening = (part or {}).get('opening')
    if not opening:
        return []
    since = opening['revision']
    out = []
    for d in AFTER_DECISIONS:
        dec = (state.get('decisions') or {}).get(d)
        if not dec:
            continue
        conf = dec.get('confirmation') or {}
        later = isinstance(conf.get('revision'), int) and conf['revision'] > since
        if dec.get('status') == 'reconfirm_required' or (dec.get('status') == 'confirmed'
                                                          and later):
            out.append(d)
    for slot, revision in sorted((started or {}).items()):
        if slot.startswith(AFTER_SLOT_PREFIXES) and isinstance(revision, int) \
                and revision > since:
            out.append(slot)
    return out


def final_test_status(state: Mapping, started: Mapping | None = None) -> dict:
    """``{status, rows, method, fraction, development_rows, schema_check, opening,
    post_final_test, changed_after}`` for surfaces; ``status`` is ``absent`` (and the counts
    null) for a study without a final test. ``opening`` is null while the final test is
    sealed; ``post_final_test`` says that something changed after the opening
    (:func:`changed_after`), so the final test is no longer independent evidence of what the
    study now holds."""
    part = of(state)
    if part is None:
        return {'status': STATUS_ABSENT, 'rows': None, 'method': None, 'fraction': None,
                'development_rows': None, 'schema_check': None, 'opening': None,
                'post_final_test': False, 'changed_after': []}
    opening = part.get('opening')
    after = changed_after(state, started)
    return {'status': part['status'], 'rows': part['final_test']['n_rows'],
            'method': part['method'], 'fraction': part['fraction'],
            'development_rows': part['development']['n_rows'],
            'schema_check': part['schema_check']['status'],
            'opening': ({k: opening.get(k) for k in OPENING_VIEW_KEYS} if opening else None),
            'post_final_test': bool(after), 'changed_after': after}


def open_record(*, revision: int, execution_id: str, proposal_id: str | None,
                user_words: str | None, model: str, rule: str | None, time: str) -> dict:
    """The ``opening`` record (WP-B1), its ``result_id`` null until the promotion."""
    return {'revision': revision, 'execution_id': execution_id, 'proposal_id': proposal_id,
            'user_words': user_words, 'model': model, 'rule': rule, 'time': time,
            'result_id': None}


def validate(part: Any) -> list[dict]:
    """Schema problems of a ``state.partition`` record (empty when valid)."""
    path = STATE_KEY
    if not isinstance(part, dict):
        return [{'path': path, 'problem': 'must be a mapping'}]
    problems = []
    missing = [k for k in RECORD_KEYS if k not in part]
    extra = [k for k in part if k not in RECORD_KEYS + OPTIONAL_RECORD_KEYS]
    problems += [{'path': f'{path}.{k}', 'problem': 'is required'} for k in missing]
    problems += [{'path': f'{path}.{k}', 'problem': 'is not part of the schema'} for k in extra]
    if missing:
        return problems
    if part['schema'] != SCHEMA:
        problems.append({'path': f'{path}.schema', 'problem': f'must be "{SCHEMA}"'})
    if part['status'] not in STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(STATUSES)}'})
    if part['method'] not in METHODS:
        problems.append({'path': f'{path}.method',
                         'problem': f'must be one of {", ".join(METHODS)}'})
    for name in (DEVELOPMENT, FINAL_TEST):
        sub = part[name]
        if not isinstance(sub, dict) or set(sub) != set(PART_KEYS) \
                or type(sub.get('n_rows')) is not int or not isinstance(sub.get('row_keys'), str):
            problems.append({'path': f'{path}.{name}',
                             'problem': 'must be {n_rows: integer, row_keys: blob sha256}'})
    if not problems and part['development']['n_rows'] + part['final_test']['n_rows'] \
            != part['n_rows']:
        problems.append({'path': f'{path}.n_rows',
                         'problem': 'must equal the development and final-test rows'})
    opening = part.get('opening')
    if part['status'] == OPENED and (not isinstance(opening, dict)
                                     or set(opening) != set(OPENING_KEYS)):
        problems.append({'path': f'{path}.opening',
                         'problem': 'an opened final test has its opening record '
                                    '{' + ', '.join(OPENING_KEYS) + '}'})
    if part['status'] != OPENED and opening is not None:
        problems.append({'path': f'{path}.opening', 'problem': 'a sealed final test has none'})
    if 'groups' in part and (not isinstance(part['groups'], dict)
                             or set(part['groups']) != set(GROUPS_KEYS)):
        problems.append({'path': f'{path}.groups',
                         'problem': 'must be {policy, n_groups, n_rows, moved_rows}'})
    check = part['schema_check']
    if not isinstance(check, dict) or set(check) != set(CHECK_KEYS) \
            or check.get('status') not in CHECK_STATUSES:
        problems.append({'path': f'{path}.schema_check',
                         'problem': 'must be {status: pass|fail, n_rows, checks, reveals}'})
    return problems
