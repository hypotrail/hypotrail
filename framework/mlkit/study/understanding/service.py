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


def repository_of(store: StudyStore, session: Mapping, *, repo_override=None) -> dict:
    """Which repository the freshness of ``session`` is read from: ``preview`` (a
    ``--repo`` given to a read command), ``relocated`` (the last ``understanding relocate``)
    or ``recorded_at_start`` (the plan's). ``exists`` is false when that place is gone (its
    sources then read as unknown)."""
    if repo_override:
        path, origin = repo_override, 'preview'
    elif session.get('repo_override'):
        path, origin = session['repo_override'], 'relocated'
    else:
        path, origin = session_plan(store, session).get('repo'), 'recorded_at_start'
    return {'repository': str(path) if path else None, 'origin': origin,
            'exists': bool(path) and Path(path).is_dir(),
            'relocations': len(session.get('relocations') or [])}


def current_for(store: StudyStore, state: Mapping, ext: Mapping, *, repo_override=None):
    """A function giving the current local projection of a session (same source mapping,
    the repository given now, the relocated one or the one recorded in the plan)."""
    cache = {}

    def run(session: Mapping) -> Mapping:
        if session['session_id'] not in cache:
            plan = session_plan(store, session)
            where = repository_of(store, session, repo_override=repo_override)
            repo = where['repository'] if where['exists'] else None
            doc = capture(state, ext, policy_digest=session['policy_digest'],
                          taskset_doc=taskset_or_none(state), repo=repo, sources=plan['sources'])
            cache[session['session_id']] = doc['local']
        return cache[session['session_id']]
    return run


def gate_loaders(store: StudyStore, state: Mapping, ext: Mapping, *,
                 repo_override=None) -> dict:
    """The loaders the gate reads a session through; the export projection uses the very
    same ones for its peer coverage, so the two never disagree."""
    return {'taskset_for': lambda s: taskset_or_none(state),
            'captured_for': lambda s: session_snapshot(store, s)['local'],
            'current_for': current_for(store, state, ext, repo_override=repo_override)}


def session_policy_for(store: StudyStore):
    """The loader of the policy a session started under."""
    return lambda s: blob_json(store, s['policy_blob'], 'policy')


def arbitration_checker(store: StudyStore, ext: Mapping, policy_doc: Mapping | None):
    """:func:`evaluate.arbitration_checker` for ``policy_doc`` and the sessions' own
    policies; without a policy every recorded arbitration settles (the history)."""
    if not policy_doc:
        return None
    return ev.arbitration_checker(ext, policy_doc, session_policy_for(store))


def gate(store: StudyStore, state: Mapping, milestone: str, *, policy_override=None,
         policy_source: str = 'study', repo_override=None, today=None, actor_scope=None,
         selection=None, assess: bool = False) -> dict:
    """The engine's one gate (:func:`evaluate.gate`) on this study: ``check``, ``export
    handoff``, the export projection, the report and ``verify-export --study`` call it."""
    ext = model.of(state) or model.empty('unset')
    doc = policy_override if policy_override is not None else policy_doc(store, ext)
    return ev.gate(ext, milestone=milestone, policy_doc=doc, policy_source=policy_source,
                   **gate_loaders(store, state, ext, repo_override=repo_override),
                   blob_ok=lambda sha: blob_ok(store, sha), checked_at=now(), today=today,
                   session_policy_for=session_policy_for(store),
                   repository_for=lambda s: repository_of(store, s,
                                                          repo_override=repo_override),
                   actor_scope=actor_scope, selection=selection, assess=assess)


def applied_policy(store: StudyStore, ext: Mapping, session: Mapping) -> dict:
    """The policy the gate applies to ``session``: the study's, else (a study whose policy
    was never set) the session's."""
    return policy_doc(store, ext) or blob_json(store, session['policy_blob'], 'policy')


def scope_of(session: Mapping) -> dict:
    return {'actor_declared_id': session['actor_declared_id'], 'profile': session['profile']}


def session_judgement(store: StudyStore, state: Mapping, session: Mapping, *,
                      policy_override=None, today=None) -> dict:
    """The gate's judgement of what ``session``'s export and the report show: the gate of
    its milestone for its author and profile under the applied policy, computed in every
    mode (``assess``). With the selection of that person and profile it is ``check``'s
    result; without one, the decisions shown (the session's latest in the history) are
    judged by the same rules as a ``virtual`` selection, with ``no_selection`` (review round
    5: one judgement, one gap list)."""
    ext = model.of(state)
    doc = policy_override if policy_override is not None else \
        applied_policy(store, ext, session)
    scope = scope_of(session)
    sel = ev.selection_for(ext, session['milestone'], scope['actor_declared_id'],
                           scope['profile'])
    if sel is None:
        shown = {dim: ev.shown_decision(ext, None, scope['actor_declared_id'], dim,
                                        session['session_id'])
                 for dim in session['dimensions']}
        sel = {'milestone': session['milestone'], 'actor_scope': scope,
               'dimension_decision_map': {k: v['decision_id'] for k, v in shown.items() if v},
               'transfer_decision_map': {}, 'policy_digest': pol.digest(doc),
               'scope_digest': None, 'virtual': True}
    return gate(store, state, session['milestone'], policy_override=doc,
                policy_source='study' if policy_override is None else 'file', today=today,
                actor_scope=scope, selection=sel, assess=True)


def require_mode(store: StudyStore, state: Mapping, *, allowed=('coaching', 'required')) -> dict:
    ext = model.of(state)
    doc = policy_doc(store, ext) if ext else None
    if pol.mode(doc) not in allowed:
        raise refuse('understanding_disabled', 'The understanding review is off for this '
                     'study; nothing was recorded.', 'Apply a coaching or required policy with '
                     '`hypotrail understanding policy set` first, if the team wants it.')
    return doc
