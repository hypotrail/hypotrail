"""Pure helpers for result identity and exposure arithmetic (plan §3.3, §3.5).

Both the writer modules (``registry``, ``exposure``) and the read-only modules
(``read``, ``view``) use these functions, so the read side never imports a module
that can write. This module performs no file I/O and imports neither pandas, numpy,
nor scikit-learn.

Identity (plan §3.3)::

    output.sha256 = sha256(canonical({"values": values, "blobs": blobs}))
    input_key     = sha256(canonical({"activity", "params", "inputs", "code_fingerprint"}))
    result_id     = sha256(canonical({"activity", "params", "inputs", "code_fingerprint",
                                      "output_sha256"}))

``canonical`` is JSON with sorted keys, no whitespace, and ``ensure_ascii=False``,
encoded as UTF-8. The environment (Python, platform, package versions), the
execution id, the exposure id, the revision, and the creation time are **outside**
identity: they are displayed, never compared.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .errors import StudyError

RESULT_SCHEMA = 'hypotrail.result/1'
EXPOSURE_SCHEMA = 'hypotrail.exposure/1'

# Every key of a registry entry. Identity covers only activity, params, inputs,
# code.fingerprint, and output (values and blobs).
RESULT_KEYS = ('schema', 'result_id', 'input_key', 'activity', 'params', 'inputs', 'code',
               'output', 'blobs', 'partition', 'n_rows', 'exposure_id', 'execution_id',
               'started_revision', 'environment', 'created')

EXPOSURE_PURPOSES = ('structural_inspection', 'train_eda', 'train_fit',
                     'validation_model_evaluation', 'validation_policy_selection',
                     # ADR 0006: the final-test rows sealed at init (schema check only).
                     'sealed')
# Purposes that record rows set aside rather than looked at: not counted in rows_exposed.
SEALED_PURPOSES = ('sealed',)
EXPOSURE_KEYS = ('schema', 'exposure_id', 'revision', 'activity', 'result_id', 'execution_id',
                 'purpose', 'partition', 'n_rows', 'row_keys', 'dataset_sha256', 'columns',
                 'time')
# Purposes that read the validation partition to choose something: their rows are
# no longer independent evidence.
SELECTION_PURPOSES = ('validation_model_evaluation', 'validation_policy_selection')


def canonical(obj: Any) -> bytes:
    """Canonical JSON bytes used by every identity digest."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def output_sha256(values: Any, blobs: Mapping[str, str]) -> str:
    return sha256_hex(canonical({'values': values, 'blobs': dict(blobs)}))


def input_key(activity: str, params: Mapping, inputs: Mapping, code_fingerprint: str) -> str:
    """The identity of a computation before its output: same inputs, same key."""
    return sha256_hex(canonical({'activity': activity, 'params': params, 'inputs': inputs,
                                 'code_fingerprint': code_fingerprint}))


def result_id(activity: str, params: Mapping, inputs: Mapping, code_fingerprint: str,
              out_sha256: str) -> str:
    return sha256_hex(canonical({'activity': activity, 'params': params, 'inputs': inputs,
                                 'code_fingerprint': code_fingerprint,
                                 'output_sha256': out_sha256}))


def code_digest(modules: Mapping[str, str]) -> str:
    """Fingerprint of an activity's code from ``{module name: source sha256}``."""
    return sha256_hex(canonical(dict(modules)))


# Roles of ``inputs.results`` that record history rather than an input of the
# computation: a new split names the split it replaced, to report the overlap, but its
# own currency does not depend on that (stale) split.
HISTORY_ROLES = ('previous_split',)


def upstream(entry: Mapping, *, history: bool = True) -> list[str]:
    """Result ids an entry was computed from (``inputs.results``), sorted by role.

    ``history=False`` leaves out :data:`HISTORY_ROLES`: what remains are the results the
    entry's values depend on, so it is current only while they are."""
    results = entry.get('inputs', {}).get('results', {}) or {}
    return [results[k] for k in sorted(results) if history or k not in HISTORY_ROLES]


def verify_entry(rid: str, entry: Any) -> dict:
    """Recompute the identity of a registry entry; refuse a divergent one.

    Raises ``integrity_error`` when a key is missing, when ``result_id`` or
    ``input_key`` differs from the recomputed value, or when ``output.sha256`` does
    not cover ``output.values`` and ``blobs``. Blob bytes are checked by the caller,
    which can read them.
    """
    def fail(problem: str) -> StudyError:
        return StudyError('integrity_error', f'Registry entry {rid} is not valid: {problem}.',
                          details={'result_id': rid, 'problem': problem})

    if not isinstance(entry, dict):
        raise fail('not a mapping')
    missing = [k for k in RESULT_KEYS if k not in entry]
    if missing:
        raise fail('missing ' + ', '.join(missing))
    if entry['schema'] != RESULT_SCHEMA:
        raise fail(f'schema is not {RESULT_SCHEMA}')
    code, output = entry['code'], entry['output']
    if not isinstance(code, dict) or not isinstance(output, dict) \
            or not isinstance(entry['blobs'], dict):
        raise fail('code, output, and blobs must be mappings')
    if code_digest(code.get('modules', {})) != code.get('fingerprint'):
        raise fail('code.fingerprint does not match code.modules')
    out_sha = output_sha256(output.get('values'), entry['blobs'])
    if out_sha != output.get('sha256'):
        raise fail('output.sha256 does not match the output values and blobs')
    key = input_key(entry['activity'], entry['params'], entry['inputs'], code['fingerprint'])
    if key != entry['input_key']:
        raise fail('input_key does not match activity, params, inputs, and code')
    rid_again = result_id(entry['activity'], entry['params'], entry['inputs'],
                          code['fingerprint'], out_sha)
    if rid_again != rid or entry['result_id'] != rid:
        raise fail('result_id does not match the entry content')
    return entry


# --- exposure arithmetic ----------------------------------------------------------------

def row_keys_bytes(row_keys: Iterable[str]) -> bytes:
    """Canonical blob of a set of row keys: sorted, unique, one per line."""
    keys = sorted(set(row_keys))
    for key in keys:
        if not isinstance(key, str) or not key or '\n' in key:
            raise StudyError('invalid_exposure', 'Row keys must be non-empty strings without '
                                                 'newlines.')
    return ''.join(k + '\n' for k in keys).encode('utf-8')


def parse_row_keys(data: bytes) -> list[str]:
    return [line for line in data.decode('utf-8').splitlines() if line]


def summarize(records: list[dict], rows_of: Mapping[str, list[str]],
              prior_exposure: list | None = None) -> dict:
    """Exposure summary from records and their row keys (``{exposure_id: keys}``).

    Counts are distinct row keys. ``prior_exposure`` is the study's exposure before
    any recorded activity (plan §3.5): it is always surfaced, never subtracted.
    """
    by_purpose: dict[str, set] = {}
    by_partition: dict[str, dict[str, set]] = {}
    for rec in records:
        keys = set(rows_of.get(rec['exposure_id'], ()))
        by_purpose.setdefault(rec['purpose'], set()).update(keys)
        part = by_partition.setdefault(rec.get('partition') or 'all', {})
        part.setdefault(rec['purpose'], set()).update(keys)
    looked = [keys for p, keys in by_purpose.items() if p not in SEALED_PURPOSES]
    every = set().union(*looked) if looked else set()
    selection = set().union(*(by_purpose.get(p, set()) for p in SELECTION_PURPOSES))
    return {
        'records': len(records),
        'rows_exposed': len(every),
        'by_purpose': {p: len(by_purpose[p]) for p in sorted(by_purpose)},
        'by_partition': {part: {p: len(v) for p, v in sorted(purposes.items())}
                         for part, purposes in sorted(by_partition.items())},
        'validation_rows_used_for_selection': len(selection),
        'prior_exposure': list(prior_exposure or []),
    }


def split_assignment(split: Mapping) -> dict[str, str]:
    """``{row_key: partition}`` from ``{partition: [row keys]}`` or from itself."""
    if all(isinstance(v, str) for v in split.values()):
        return dict(split)
    out: dict[str, str] = {}
    for part, keys in split.items():
        for key in keys:
            out[key] = part
    return out


def overlap(old_split: Mapping, new_split: Mapping,
            exposed: Mapping[str, set] | None = None) -> dict:
    """How a new split relates to an old one, and what its partitions already saw.

    ``old_split`` and ``new_split`` are ``{partition: [row keys]}`` (or
    ``{row_key: partition}``). ``exposed`` maps each exposure purpose to the set of
    row keys exposed under it. Changing a split never makes explored rows unseen: for
    every new partition the result lists how many of its rows were already exposed,
    by purpose.
    """
    old, new = split_assignment(old_split), split_assignment(new_split)
    transitions: dict[str, dict[str, int]] = {}
    for key, part in new.items():
        row = transitions.setdefault(part, {})
        before = old.get(key, 'absent')
        row[before] = row.get(before, 0) + 1
    previously: dict[str, dict[str, int]] = {}
    for part in sorted(set(new.values())):
        keys = {k for k, p in new.items() if p == part}
        previously[part] = {purpose: len(keys & rows)
                            for purpose, rows in sorted((exposed or {}).items())
                            if keys & rows}
    return {
        'rows_in_new': len(new),
        'rows_in_old': len(old),
        'moved': sum(1 for k, p in new.items() if k in old and old[k] != p),
        'transitions': {p: dict(sorted(t.items())) for p, t in sorted(transitions.items())},
        'previously_exposed': previously,
        'note': 'Changing the split does not make previously explored rows unseen.',
    }


# --- policy rules (review fix L2) ------------------------------------------------------------

_CAPACITY = re.compile(r'[0-9]+', re.ASCII)
_THRESHOLD = re.compile(r'[0-9]+(?:\.[0-9]+)?', re.ASCII)


def canonical_rule(rule: Any) -> str | None:
    """The one spelling of a policy rule, or None when ``rule`` is not one.

    ``threshold:t`` with ``0 <= t <= 1`` written in plain decimal digits, trailing zeros
    dropped (``threshold:0.30`` and ``threshold:0.3`` are one rule, ``threshold:1.0`` is
    ``threshold:1``); ``capacity:k`` with ``k >= 1`` written in plain digits, leading
    zeros dropped. Spaces around the parts are ignored. Signs, exponents, underscores
    (``capacity:1_000``), non-ASCII digits, ``nan``, and ``inf`` are refused. Every
    comparison, identity, and stored value of a rule uses this spelling.
    """
    if not isinstance(rule, str) or rule.count(':') != 1:
        return None
    kind, _, number = rule.partition(':')
    kind, number = kind.strip(), number.strip()
    if kind == 'capacity' and _CAPACITY.fullmatch(number):
        k = int(number)
        return f'capacity:{k}' if k >= 1 else None
    if kind == 'threshold' and _THRESHOLD.fullmatch(number):
        t = Decimal(number)
        if not 0 <= t <= 1:
            return None
        text = format(t.normalize(), 'f')
        return f'threshold:{text}'
    return None


def parse_rule(rule: Any) -> tuple[str, float | int] | None:
    """``("threshold", t)`` or ``("capacity", k)`` of a rule (:func:`canonical_rule`)."""
    canonical = canonical_rule(rule)
    if canonical is None:
        return None
    kind, _, number = canonical.partition(':')
    return (kind, int(number)) if kind == 'capacity' else (kind, float(number))
