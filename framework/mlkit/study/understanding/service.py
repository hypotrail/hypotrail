"""Reading side of the review: one study, its blobs, its taskset, its current context.

Used by the CLI and by the action handlers (which call it on the state they hold under
the writer lock). It never writes the state; :func:`put_json` and :func:`put_bytes` only
add immutable content-addressed blobs, which a refused command leaves unused and harmless.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Mapping

from mlkit.study import read
from mlkit.study.store import StudyStore

from . import taskset as bk, canonical, evaluate as ev, model, policy as pol, refuse
from . import snapshot as snap


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')


def open_store(study_dir) -> StudyStore:
    store = StudyStore(study_dir)
    if not store.exists():
        from mlkit.study.errors import StudyError
        raise StudyError('study_missing', f'No study here: {store.state_path} does not exist.',
                         details={'study': str(store.study_dir)})
    return store


def load_state(study_dir) -> dict:
    return read.load_state(study_dir)


def put_bytes(store: StudyStore, data: bytes) -> str:
    return store.put_blob(data)


def put_json(store: StudyStore, obj: Any) -> str:
    return store.put_blob(canonical.dumps(obj))


def blob_ok(store: StudyStore, sha: str) -> bool:
    try:
        store.read_blob(sha)
        return True
    except (OSError, ValueError):
        return False


def blob_json(store: StudyStore, sha: str, field: str = 'blob') -> Any:
    try:
        return canonical.loads(store.read_blob(sha))
    except FileNotFoundError:
        raise refuse('evidence_unavailable', f'The stored {field} is no longer available '
                     'locally.', 'Its historical judgement stays; a new review needs the '
                     'evidence again.', field=field) from None
    except (OSError, ValueError) as exc:
        raise refuse('evidence_invalid', f'The stored {field} cannot be read '
                     f'({exc.__class__.__name__}).', 'Store it again.', field=field) from None


def blob_text(store: StudyStore, sha: str) -> str | None:
    try:
        return store.read_blob(sha).decode('utf-8')
    except (OSError, ValueError):
        return None


def policy_doc(store: StudyStore, ext: Mapping | None) -> dict | None:
    if not ext or not ext.get('policy'):
        return None
    return blob_json(store, ext['policy']['blob'], 'policy')


def mode(store: StudyStore, state: Mapping) -> str:
    ext = model.of(state)
    return pol.mode(policy_doc(store, ext)) if ext else 'off'


def case_dir(state: Mapping) -> Path | None:
    f = snap.case_file_of(state)
    return f.parent if f is not None else None


def current_taskset(state: Mapping) -> dict:
    d = case_dir(state)
    if d is None:
        raise refuse('unsupported_case', 'The case directory of this study cannot be located.',
                     'Keep the case at the path the study was created from.')
    return bk.load(d, case_id=(state.get('case') or {}).get('id'))


def taskset_or_none(state: Mapping) -> dict | None:
    try:
        return current_taskset(state)
    except Exception:            # noqa: BLE001 - a missing or broken taskset reads as absent
        return None


def session_plan(store: StudyStore, session: Mapping) -> dict:
    return blob_json(store, session['plan_blob'], 'plan')


def session_snapshot(store: StudyStore, session: Mapping) -> dict:
    return blob_json(store, session['snapshot_blob'], 'snapshot')


def capture(state: Mapping, ext: Mapping | None, *, policy_digest: str | None,
            taskset_doc: Mapping | None, repo, sources, frozen: dict | None = None) -> dict:
    salt = ext['salt'] if ext else 'unset'
    return snap.capture_context(state, policy_digest=policy_digest, taskset_doc=taskset_doc,
                                repo=Path(repo).resolve() if repo else None, sources=sources,
                                salt=salt, frozen=frozen)


def current_for(store: StudyStore, state: Mapping, ext: Mapping, *, repo_override=None):
    """A function giving the current local projection of a session (same source mapping,
    the repository given now or the one recorded in the plan)."""
    cache = {}

    def run(session: Mapping) -> Mapping:
        if session['session_id'] not in cache:
            plan = session_plan(store, session)
            repo = repo_override or plan.get('repo')
            if repo and not Path(repo).is_dir():
                repo = None
            doc = capture(state, ext, policy_digest=session['policy_digest'],
                          taskset_doc=taskset_or_none(state), repo=repo, sources=plan['sources'])
            cache[session['session_id']] = doc['local']
        return cache[session['session_id']]
    return run


def gate(store: StudyStore, state: Mapping, milestone: str, *, policy_override=None,
         policy_source: str = 'study', repo_override=None, today=None) -> dict:
    ext = model.of(state) or model.empty('unset')
    doc = policy_override if policy_override is not None else policy_doc(store, ext)
    return ev.gate(ext, milestone=milestone, policy_doc=doc, policy_source=policy_source,
                   taskset_for=lambda s: taskset_or_none(state),
                   captured_for=lambda s: session_snapshot(store, s)['local'],
                   current_for=current_for(store, state, ext, repo_override=repo_override),
                   blob_ok=lambda sha: blob_ok(store, sha), checked_at=now(), today=today)


def require_mode(store: StudyStore, state: Mapping, *, allowed=('coaching', 'required')) -> dict:
    ext = model.of(state)
    doc = policy_doc(store, ext) if ext else None
    if pol.mode(doc) not in allowed:
        raise refuse('understanding_disabled', 'The understanding review is off for this '
                     'study; nothing was recorded.', 'Apply a coaching or required policy with '
                     '`hypotrail understanding policy set` first, if the team wants it.')
    return doc
