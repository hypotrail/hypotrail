"""The shape of a CLI payload, for the fixture drift test (WP-I).

``key_sets(payload)`` maps every path of an object in a payload to the set of its keys. A
path names list items with ``[]``. An object that carries an ``activity``, a ``kind``, or
an ``action`` is a variant named by it (``results[]<activity=fit.logistic>``), because its
other keys depend on it; a cited segment is the variant ``<cited>``. Objects whose keys
are data (slot names, decision ids, term ids, rules, columns) are maps: their keys are not
compared, their values are, under ``{*}``.

``drift(fixture, captured)`` lists, for every path both payloads have, the keys one has
and the other lacks (see its docstring for optional keys). A ``null`` on one side compares with nothing: hand-written fixtures
carry states a capture may not reach, and the other way round.
"""
from __future__ import annotations

import re

# Paths (after the variant and map naming above) whose object keys are data: slots,
# decision ids, term and step ids, rules, fits, columns, module names, command names.
MAPS = [
    r'^decisions$', r'^results$', r'^artifacts\.items$', r'^artifacts$', r'\.rules$', r'^rules$', r'\.models$',
    r'^models$', r'\.by_partition$', r'\.by_purpose$', r'\.residuals_by$', r'\.bias_by_period$', r'^steps$',
    r'\.modules$', r'\.inputs\.results$', r'^inputs\.results$', r'\.environment$', r'^environment$',
    r'^sources$', r'^commands$', r'\.by_code$', r'\.by_reason$', r'\.coefficients$', r'^terms$',
    r'\.intervals$', r'^intervals$', r'\.deltas$', r'^deltas$', r'\.value$', r'\.params$', r'^params$',
    r'\.options$',
    # L3 (owner session 2026-10-26, D4b): the junior texts of a summary in each language by
    # their ids, an EDA result's special-value meanings, the view's case statements.
    r'^texts\.(en|fr)\.(plan|moments|choice_options|limits|artifacts|digest|goal|proposals)$',
    r'\.texts\.(en|fr)\.meanings$', r'case_texts\.(facts|special_values|groups|availability)$',
    # Contract P1 (CLI-CONTRACT §17.2): the headlines by step id, their texts, the
    # data-contingent texts by proposal id.
    r'^headlines$', r'^texts\.(en|fr)\.(headlines|data_contingent)$',
]
MAP_RE = [re.compile(p) for p in MAPS]
# Paths whose objects carry optional keys by design (a session-report timeline line has
# the keys of its own command): there only a key the engine never emits is drift.
OPTIONAL = [r'^timeline\[\]']
OPTIONAL_RE = [re.compile(p) for p in OPTIONAL]
# Keys that name the variant of an object: its other keys depend on them.
VARIANT_KEYS = ('activity', 'kind', 'action')


def _is_map(path: str) -> bool:
    return any(r.search(path) for r in MAP_RE)


def _variant(item) -> str:
    if not isinstance(item, dict):
        return ''
    for k in VARIANT_KEYS:
        if isinstance(item.get(k), str):
            return f'<{k}={item[k]}>'
    # A cited segment (CC §5) and a text segment are two shapes of one list.
    if set(item) >= {'text', 'result_id'}:
        return '<cited>'
    return ''


def _walk(value, path, union, inter):
    if isinstance(value, dict):
        if path and _is_map(path):
            for item in value.values():
                _walk(item, f'{path}.{{*}}{_variant(item)}', union, inter)
            return
        union.setdefault(path, set()).update(value)
        inter[path] = set(value) if path not in inter else inter[path] & set(value)
        for k, v in value.items():
            _walk(v, (f'{path}.{k}' if path else k) + _variant(v), union, inter)
    elif isinstance(value, list):
        for item in value:
            _walk(item, f'{path}[]{_variant(item)}', union, inter)


def key_sets(value) -> tuple[dict[str, set], dict[str, set]]:
    """``(union, intersection)``: per path, the keys of any object there, and of every one."""
    union: dict[str, set] = {}
    inter: dict[str, set] = {}
    _walk(value, '', union, inter)
    return union, inter


def drift(fixture: dict, captured: list[dict]) -> list[tuple[str, list, list]]:
    """``[(path, missing in the fixture, extra in the fixture)]`` against the captures.

    A key is missing when every captured object at the path has it and some object of the
    fixture lacks it; it is extra when no captured object at the path has it.
    """
    mine_any, mine_all = key_sets(fixture)
    theirs_any: dict[str, set] = {}
    theirs_all: dict[str, set] = {}
    for c in captured:
        any_, all_ = key_sets(c)
        for k, v in any_.items():
            theirs_any.setdefault(k, set()).update(v)
        for k, v in all_.items():
            theirs_all[k] = set(v) if k not in theirs_all else theirs_all[k] & v
    out = []
    for path in sorted(set(mine_any) & set(theirs_any)):
        optional = any(r.search(path) for r in OPTIONAL_RE)
        missing = [] if optional else sorted(theirs_all[path] - mine_all[path])
        extra = sorted(mine_any[path] - theirs_any[path])
        if missing or extra:
            out.append((path, missing, extra))
    return out
