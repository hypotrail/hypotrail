"""Snapshot capture, source manifest, digests and freshness (SPEC §12).

A capture reads one coherent revision of the study and the source files a review depends
on, and produces two projections:

* ``local``: every entry the review needs, private ones included (decision values of the
  study, the partition, the current results, the case contract, the data identity, the
  engine code, the dependency lock, the mapped repository files). Its digest is
  ``local_snapshot_digest``; it stays in the study.
* ``public``: ``hypotrail.public-source-scope/1``, only the exportable repository entries
  (relative POSIX path, SHA-256, role), the public contract digests, and the private
  entries it omits under ``opaque_private_ref`` identifiers (a stable local identity, not
  a digest of the private value, never resolvable outside the study). Its digest is
  ``source_scope_digest``; its JSON is exported whole, so a clean clone recomputes it.

Neither projection contains the review artefacts, logs, capture or render times, the
capture revision or any global revision number, the final commit or a commit receipt:
adding a review never stales its own sources, and never changes an ML result.

Freshness (:func:`freshness`) compares a captured projection with a capture of the current
context, key by key, for the dependency keys a dimension declares (logical keys, ``*``
globs, or ``role:<role>`` selectors). Equal is ``current``, different is ``stale``, absent
on either side or matching nothing is ``unknown``. Time alone never stales a review.

The mapped repository files are frozen at capture: their bytes are stored as immutable
local blobs, and rendering reads them from there, never from the live file again.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from . import canonical, refuse

SCHEMA = 'hypotrail.understanding-snapshot/1'
PUBLIC_SCHEMA = 'hypotrail.public-source-scope/1'
ROLES = ('code', 'config', 'data_contract', 'transform_recipe', 'model', 'protocol',
         'metrics', 'dependency_lock', 'security_rule', 'documentation', 'decision',
         'partition', 'result', 'case_contract', 'data_identity', 'engine_code',
         'policy', 'rubric')
REPO_ROLES = ('code', 'config', 'data_contract', 'transform_recipe', 'model', 'protocol',
              'metrics', 'dependency_lock', 'security_rule', 'documentation')
MAX_SOURCES = 200
MAX_SOURCE_BYTES = 2 * 1024 * 1024
ENGINE_DIR = Path(__file__).resolve().parents[1]           # framework/mlkit/study
LOCK_FILE = Path(__file__).resolve().parents[3] / 'uv.lock'   # framework/uv.lock
RETRIES = 3


def normalize(value: Any) -> Any:
    """``value`` in canonical JSON v1 types: floats become decimal objects (rule
    :data:`canonical.FLOAT_RULE`), tuples lists. The computation that produced the
    float is untouched."""
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return canonical.decimal(value)
    if isinstance(value, Mapping):
        return {str(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return str(value)


def safe_relative(path: str) -> str:
    """A repository path as a portable relative POSIX path, or ``path_outside_scope``."""
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise refuse('path_outside_scope', 'A source path must be a relative POSIX path.',
                     'Give paths relative to the repository root.', field='path')
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ('..', '') for part in p.parts) or str(p) != path \
            or path.startswith('./'):
        raise refuse('path_outside_scope', 'A source path is absolute, not normalised, or '
                     'leaves the repository.', 'Give normalised paths inside the repository.',
                     field='path')
    return path


def validate_sources(sources) -> list:
    """The mapped repository sources: ``{logical_key: "repo:...", path, role}`` with a
    repository role and a confined path (a plan file edited by hand is checked again)."""
    if not isinstance(sources, list):
        raise refuse('evidence_invalid', 'sources is a list.', 'Correct the plan.')
    out = []
    for s in sources:
        if not isinstance(s, Mapping) or set(s) != {'logical_key', 'path', 'role'} \
                or s['role'] not in REPO_ROLES or not isinstance(s['logical_key'], str) \
                or not s['logical_key'].startswith('repo:') or len(s['logical_key']) > 300:
            raise refuse('evidence_invalid', 'A source is {logical_key: "repo:...", path, role} '
                         'with role among ' + ', '.join(REPO_ROLES) + '.',
                         'Correct the sources.')
        safe_relative(s['path'])
        out.append(dict(s))
    return out


def read_repo_file(repo: Path, rel: str) -> bytes | None:
    """The bytes of ``repo/rel``; None when absent. A symlink that leaves the repository,
    a non-regular file or an oversized file is ``path_outside_scope``."""
    safe_relative(rel)
    path = repo / rel
    if not path.exists() and not path.is_symlink():
        return None
    real = Path(os.path.realpath(path))
    if not real.is_relative_to(Path(os.path.realpath(repo))):
        raise refuse('path_outside_scope', 'A source is a link that leaves the repository.',
                     'Map files that live inside the repository.', field='path')
    if not real.is_file():
        raise refuse('path_outside_scope', 'A source is not a regular file.',
                     'Map regular files only.', field='path')
    if real.stat().st_size > MAX_SOURCE_BYTES:
        raise refuse('path_outside_scope', 'A source is larger than the review reads.',
                     f'Map files of at most {MAX_SOURCE_BYTES} bytes.', field='path')
    return real.read_bytes()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def engine_fingerprint() -> str:
    """Digest of the engine sources a study runs (``mlkit/study`` without the review
    package itself, so the review code never stales the reviewed context)."""
    h = hashlib.sha256()
    for path in sorted(ENGINE_DIR.rglob('*.py')):
        rel = path.relative_to(ENGINE_DIR).as_posix()
        if rel.startswith('understanding/') or '__pycache__' in rel:
            continue
        h.update(rel.encode() + b'\0' + path.read_bytes() + b'\0')
    return h.hexdigest()


def opaque_ref(salt: str, logical_key: str) -> str:
    """A stable local identity of a private entry: keyed by the study's private salt and
    the entry's name, never by its value."""
    return 'opq-' + _sha(f'{salt}\0{logical_key}'.encode())[:24]


def _value_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return ', '.join(f'{k}: {_value_text(v)}' for k, v in value.items())
    if isinstance(value, list):
        return ', '.join(_value_text(v) for v in value)
    return canonical.dumps(normalize(value)).decode()


def _study_entries(state: Mapping, case_file: Path | None) -> tuple[list, dict]:
    entries, refs = [], {}
    for did, d in sorted((state.get('decisions') or {}).items()):
        if not isinstance(d, Mapping) or d.get('status') != 'confirmed':
            continue
        entries.append({'logical_key': f'study:decision:{did}', 'origin': 'study',
                        'path': None, 'role': 'decision',
                        'sha256': canonical.digest(normalize({'value': d.get('value')}))})
        refs[f'decision:{did}'] = _value_text(d.get('value'))
    if state.get('partition') is not None:
        entries.append({'logical_key': 'study:partition', 'origin': 'study', 'path': None,
                        'role': 'partition',
                        'sha256': canonical.digest(normalize(state['partition']))})
    for slot, rid in sorted((state.get('current') or {}).items()):
        if isinstance(rid, str):
            entries.append({'logical_key': f'study:result:{slot}', 'origin': 'study',
                            'path': None, 'role': 'result',
                            'sha256': _sha(rid.encode())})
            # A prerequisite only (never placed in a prompt): the result exists.
            refs[f'result:{slot}'] = 'available'
    case = state.get('case') or {}
    if case_file is not None and case_file.is_file():
        entries.append({'logical_key': 'case:contract', 'origin': 'case', 'path': None,
                        'role': 'case_contract', 'sha256': _sha(case_file.read_bytes())})
    dataset = state.get('dataset') or {}
    if isinstance(dataset.get('sha256'), str):
        entries.append({'logical_key': 'data:dataset', 'origin': 'case', 'path': None,
                        'role': 'data_identity', 'sha256': dataset['sha256']})
    refs['case:id'] = str(case.get('id', ''))
    return entries, refs


def _case_refs(case_file: Path | None) -> dict:
    if case_file is None or not case_file.is_file():
        return {}
    import yaml
    doc = yaml.safe_load(case_file.read_text(encoding='utf-8')) or {}
    refs = {}
    for fact in doc.get('facts') or []:
        if isinstance(fact, Mapping) and isinstance(fact.get('id'), str):
            refs[f'fact:{fact["id"]}'] = _value_text(fact.get('value'))
    target = doc.get('target') or {}
    if isinstance(target.get('column'), str):
        refs['case:target'] = target['column']
    if isinstance(doc.get('task'), str):
        refs['case:task'] = doc['task']
    return refs


def case_file_of(state: Mapping) -> Path | None:
    path = (state.get('case') or {}).get('path')
    return Path(path) if isinstance(path, str) and os.path.isabs(path) else None


def capture_context(state: Mapping, *, policy_digest: str | None, bank_doc: Mapping | None,
                    repo: Path | None, sources: Iterable[Mapping], salt: str,
                    frozen: dict | None = None) -> dict:
    """The snapshot document of ``state`` (one revision) and the mapped sources.

    ``frozen`` receives ``{sha256: bytes}`` of every repository source read, so the
    caller stores them as immutable blobs. A mapped source that is absent or unreadable
    gets no entry (its dependency is ``unknown``)."""
    case_file = case_file_of(state)
    entries, refs = _study_entries(state, case_file)
    refs.update(_case_refs(case_file))
    entries.append({'logical_key': 'engine:code', 'origin': 'engine', 'path': None,
                    'role': 'engine_code', 'sha256': engine_fingerprint()})
    if LOCK_FILE.is_file():
        entries.append({'logical_key': 'engine:dependency_lock', 'origin': 'engine',
                        'path': None, 'role': 'dependency_lock',
                        'sha256': _sha(LOCK_FILE.read_bytes())})
    if policy_digest:
        entries.append({'logical_key': 'contract:policy', 'origin': 'contract', 'path': None,
                        'role': 'policy', 'sha256': policy_digest})
    if bank_doc is not None:
        for r in bank_doc['rubrics']:
            entries.append({'logical_key': f'contract:rubric:{r["dimension_id"]}',
                            'origin': 'contract', 'path': None, 'role': 'rubric',
                            'sha256': canonical.digest(r)})
    missing = []
    sources = validate_sources(sources)
    if len(sources) > MAX_SOURCES:
        raise refuse('path_outside_scope', f'At most {MAX_SOURCES} sources are mapped.',
                     'Map fewer files.', field='sources')
    for s in sources:
        rel = safe_relative(s['path'])
        data = read_repo_file(repo, rel) if repo is not None else None
        if data is None:
            missing.append(s['logical_key'])
            continue
        sha = _sha(data)
        if frozen is not None:
            frozen[sha] = data
        entries.append({'logical_key': s['logical_key'], 'origin': 'repo', 'path': rel,
                        'role': s['role'], 'sha256': sha})
    keys = [e['logical_key'] for e in entries]
    if len(set(keys)) != len(keys):
        raise refuse('policy_invalid', 'Two sources share a logical key.',
                     'Give every mapped source its own logical_key.', field='sources')
    entries = canonical.sorted_set(entries, 'logical_key')
    local = {'schema': SCHEMA, 'study_id': str((state.get('case') or {}).get('id', '')),
             'entries': entries, 'unreadable_sources': sorted(missing)}
    public = public_scope(local, salt)
    return {'local': local, 'public': public, 'refs': refs,
            'local_snapshot_digest': canonical.digest(local),
            'source_scope_digest': canonical.digest(public)}


def public_scope(local: Mapping, salt: str) -> dict:
    """The public projection of a local snapshot (see the module docstring)."""
    public, omitted = [], []
    for e in local['entries']:
        if e['origin'] == 'repo':
            public.append({'logical_key': e['logical_key'], 'path': e['path'],
                           'role': e['role'], 'sha256': e['sha256'], 'ref': 'public_ref'})
        elif e['origin'] == 'contract':
            public.append({'logical_key': e['logical_key'], 'path': None, 'role': e['role'],
                           'sha256': e['sha256'], 'ref': 'public_ref'})
        else:
            omitted.append({'opaque_private_ref': opaque_ref(salt, e['logical_key']),
                            'role': e['role']})
    return {'schema': PUBLIC_SCHEMA, 'entries': canonical.sorted_set(public, 'logical_key'),
            'omitted_private': canonical.sorted_set(omitted, 'opaque_private_ref'),
            'unreadable_sources': list(local.get('unreadable_sources') or [])}


def _matches(pattern: str, entry: Mapping) -> bool:
    if pattern.startswith('role:'):
        return entry['role'] == pattern[5:]
    return fnmatch.fnmatchcase(entry['logical_key'], pattern)


def freshness(captured: Mapping, current: Mapping, keys: Iterable[str]) -> dict:
    """``{status, changed, unknown}`` of ``keys`` between two local projections."""
    before = {e['logical_key']: e for e in captured['entries']}
    after = {e['logical_key']: e for e in current['entries']}
    changed, unknown = [], []
    for pattern in sorted(set(keys)):
        names = {k for k, e in before.items() if _matches(pattern, e)} | \
                {k for k, e in after.items() if _matches(pattern, e)}
        unreadable = [k for k in list(captured.get('unreadable_sources') or [])
                      + list(current.get('unreadable_sources') or [])
                      if fnmatch.fnmatchcase(k, pattern)]
        if not names or unreadable:
            unknown.append(pattern)
            continue
        for name in sorted(names):
            if name not in before or name not in after:
                unknown.append(name)
            elif before[name]['sha256'] != after[name]['sha256']:
                changed.append(name)
    status = 'stale' if changed else ('unknown' if unknown else 'current')
    return {'status': status, 'changed': sorted(set(changed)),
            'unknown': sorted(set(unknown))}


def public_freshness(scope: Mapping, read_path) -> dict:
    """Freshness of a public scope against a tree (``read_path(rel) -> bytes | None``):
    every public repository entry must be present with the same bytes."""
    changed, missing = [], []
    for e in scope['entries']:
        if e['path'] is None:
            continue
        data = read_path(e['path'])
        if data is None:
            missing.append(e['path'])
        elif _sha(data) != e['sha256']:
            changed.append(e['path'])
    if scope.get('unreadable_sources'):
        missing += list(scope['unreadable_sources'])
    status = 'stale' if changed else ('unknown' if missing else 'current')
    return {'status': status, 'changed': changed, 'missing': missing}


def is_external_source(entry: Mapping) -> bool:
    return entry['origin'] in ('case', 'engine')
