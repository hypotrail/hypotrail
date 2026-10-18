"""Immutable result registry of a study (plan §3.3).

A registry entry (``hypotrail.result/1``) records one computed result. It is written
once, under ``.hypotrail/registry/<result_id>.json``, and never changed. Large outputs
(predictions, row-key lists) are content-addressed blobs under
``.hypotrail/blobs/<sha256>``.

Identity is defined in :mod:`mlkit.study.records`: ``result_id`` covers the activity,
its parameters, its inputs, the fingerprint of the activity's own code, and the
output digest. ``input_key`` is the same digest without the output. Two entries with
the same ``input_key`` and different ``result_id`` mean the computation is not
deterministic; :func:`put` flags it and logs a ``nondeterministic_result`` event.

The environment (Python, platform, package versions) is recorded for display and is
outside identity: a changed environment does not invalidate anything (plan §9.6).
The code fingerprint covers only the modules an activity names (:func:`code_fingerprint`).

Lineage: an entry's ``inputs.results`` maps a role to the ``result_id`` it was
computed from (for example ``{"split": "<rid>"}``). :func:`lineage` walks it.

Extension point for activities (Phase 2), under the writer lock, in this order::

    code = registry.code_fingerprint(activity.modules)
    eid = exposure.new_exposure_id()
    put = registry.put(store, activity=..., params=..., inputs=..., code=code,
                       values=..., blobs={'predictions': csv_gz_bytes},
                       partition='validation', n_rows=n, exposure_id=eid,
                       execution_id=execution_id, started_revision=rev)
    exposure.record(store, exposure_id=eid, result_id=put['result_id'], ...)

Promotion (``state['current'][slot] = result_id``) is a separate state mutation made
through ``apply_command``; ``put`` never touches state.

This module imports neither pandas, numpy, nor scikit-learn.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from . import records as rec
from .errors import StudyError
from .store import BLOBS_DIR, REGISTRY_DIR, StudyStore, append_jsonl, read_jsonl

INDEX_FILE = 'registry-index.jsonl'
ENVIRONMENT_PACKAGES = ('numpy', 'pandas', 'scikit-learn', 'scipy', 'marimo')


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --- code and environment ---------------------------------------------------------------

def module_source_path(name: str) -> Path:
    """The source file of module ``name``, found without importing the module itself."""
    spec = importlib.util.find_spec(name)
    if spec is None or not spec.origin or not spec.origin.endswith('.py'):
        raise StudyError('unknown_module', f'Module {name} has no Python source file.',
                         details={'module': name})
    return Path(spec.origin)


def code_fingerprint(modules: Iterable[str]) -> dict:
    """``{"fingerprint", "modules": {name: sha256 of its source}}`` for an activity.

    Only the listed modules count. A package contributes its ``__init__.py`` only, so
    list every module whose code changes the result.
    """
    names = sorted(set(modules))
    if not names:
        raise StudyError('invalid_result', 'An activity names at least one module.')
    shas = {n: hashlib.sha256(module_source_path(n).read_bytes()).hexdigest() for n in names}
    return {'fingerprint': rec.code_digest(shas), 'modules': shas}


def environment() -> dict:
    """Displayed environment of a result (outside identity)."""
    packages = {}
    for name in ENVIRONMENT_PACKAGES:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {'python': platform.python_version(), 'implementation': sys.implementation.name,
            'platform': platform.platform(), 'packages': packages}


# --- writing ----------------------------------------------------------------------------

def _index_path(store: StudyStore) -> Path:
    return store.home / INDEX_FILE


def put(store: StudyStore, *, activity: str, params: Mapping, inputs: Mapping, code: Mapping,
        values, blobs: Mapping[str, bytes] | None = None, partition: str | None = None,
        n_rows: int | None = None, exposure_id: str | None = None,
        execution_id: str | None = None, started_revision: int | None = None,
        env: Mapping | None = None) -> dict:
    """Store one immutable result; return ``{result_id, input_key, created,
    nondeterministic, same_input_results}``.

    ``blobs`` maps a name to bytes; each is stored under its sha256. Putting the same
    result twice is a no-op (``created: False``). Call it under the writer lock.
    """
    if not isinstance(activity, str) or not activity:
        raise StudyError('invalid_result', 'activity must be a non-empty string')
    if not isinstance(params, Mapping) or not isinstance(inputs, Mapping):
        raise StudyError('invalid_result', 'params and inputs must be mappings')
    results = inputs.get('results', {})
    if not isinstance(results, Mapping) or not all(isinstance(v, str) for v in results.values()):
        raise StudyError('invalid_result', 'inputs.results maps a role to a result id')
    code = {'fingerprint': code['fingerprint'], 'modules': dict(code['modules'])}
    if rec.code_digest(code['modules']) != code['fingerprint']:
        raise StudyError('invalid_result', 'code.fingerprint does not match code.modules')
    blob_shas = {name: store.put_blob(data) for name, data in sorted((blobs or {}).items())}
    params, inputs = json.loads(rec.canonical(params)), json.loads(rec.canonical(inputs))
    values = json.loads(rec.canonical(values))
    out_sha = rec.output_sha256(values, blob_shas)
    key = rec.input_key(activity, params, inputs, code['fingerprint'])
    rid = rec.result_id(activity, params, inputs, code['fingerprint'], out_sha)
    entry = {'schema': rec.RESULT_SCHEMA, 'result_id': rid, 'input_key': key,
             'activity': activity, 'params': params, 'inputs': inputs, 'code': code,
             'output': {'sha256': out_sha, 'values': values}, 'blobs': blob_shas,
             'partition': partition, 'n_rows': n_rows, 'exposure_id': exposure_id,
             'execution_id': execution_id, 'started_revision': started_revision,
             'environment': dict(env) if env is not None else environment(),
             'created': _now()}
    rec.verify_entry(rid, entry)
    same = sorted({row['result_id'] for row in read_jsonl(_index_path(store))
                   if row.get('input_key') == key and row.get('result_id') != rid})
    path = store.home / REGISTRY_DIR / f'{rid}.json'
    created = not path.exists()
    if created:
        store.put_registry(rid, entry)
    if created or not any(r.get('result_id') == rid for r in read_jsonl(_index_path(store))):
        append_jsonl(_index_path(store), {'input_key': key, 'result_id': rid,
                                          'activity': activity})
    if same and created:
        store.event('nondeterministic_result', activity=activity, input_key=key,
                    result_id=rid, others=same)
    return {'result_id': rid, 'input_key': key, 'created': created,
            'nondeterministic': bool(same), 'same_input_results': same}


# --- reading ----------------------------------------------------------------------------

def get(store: StudyStore, rid: str) -> dict:
    """The verified entry ``rid``: identity and every blob digest are recomputed.

    Refusals: ``unknown_result`` (absent) and ``integrity_error`` (divergent).
    """
    path = store.home / REGISTRY_DIR / f'{rid}.json'
    if not rid or '/' in rid or rid.startswith('.') or not path.is_file():
        raise StudyError('unknown_result', f'No result {rid} in the registry.',
                         details={'result_id': rid})
    try:
        entry = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise StudyError('integrity_error', f'Registry entry {rid} is not valid JSON.',
                         details={'result_id': rid}) from exc
    rec.verify_entry(rid, entry)
    for name, sha in entry['blobs'].items():
        blob = store.home / BLOBS_DIR / sha
        if not blob.is_file():
            raise StudyError('integrity_error', f'Blob {name} of result {rid} is missing.',
                             details={'result_id': rid, 'blob': name, 'sha256': sha})
        store.read_blob(sha)
    return entry


def entries(store: StudyStore) -> Iterator[dict]:
    """Every registry entry, unverified, in file-name order (for scans)."""
    folder = store.home / REGISTRY_DIR
    if not folder.is_dir():
        return
    for path in sorted(folder.glob('*.json')):
        yield json.loads(path.read_text(encoding='utf-8'))


def by_input_key(store: StudyStore, key: str) -> list[str]:
    """Result ids recorded for ``input_key`` (more than one: nondeterministic)."""
    return sorted({r['result_id'] for r in read_jsonl(_index_path(store))
                   if r.get('input_key') == key})


def lineage(store: StudyStore, rid: str) -> list[str]:
    """Every ancestor of ``rid`` (through ``inputs.results``), nearest first."""
    seen: list[str] = []
    frontier = rec.upstream(get(store, rid))
    while frontier:
        nxt = []
        for parent in frontier:
            if parent in seen:
                continue
            seen.append(parent)
            nxt += rec.upstream(get(store, parent))
        frontier = nxt
    return seen


def is_current(state: Mapping, rid: str) -> bool:
    """True if ``rid`` is promoted in some slot of ``state['current']`` and not stale."""
    return rid in set(state['current'].values()) and rid not in state['stale']
