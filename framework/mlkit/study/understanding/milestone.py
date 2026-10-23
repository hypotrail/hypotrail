"""The protected milestone ``handoff`` under a required policy (SPEC §10, A25).

``export handoff`` keeps its contract when the review is off or coaching: it changes
nothing in the study. When the study's policy is ``required`` and names ``handoff``, the
export runs this protocol instead, so no direct call bypasses the review and no earlier
``understanding check`` is reused as an authorisation:

1. **reserve**, under the writer lock, on the state reread there: the policy, the
   selection, the identities of the context (a fresh capture of every session's sources)
   and the gate are computed again; a blocked gate refuses with ``milestone_blocked`` and
   writes nothing; otherwise the reservation records the policy, scope and context digests
   (one revision);
2. **render** the pack out of the lock, only from the study at the reserved revision
   (``cmd_export.build``) into a temporary sibling folder of the target;
3. **revalidate** under the writer lock: the revision is still the reserved one and the
   gate, recomputed again, has the same decision, policy, scope and context digests. Only
   then is the folder renamed onto the target (never a replacement). Any relevant change in
   between leaves the folder as a ``.candidate`` next to the target, records
   ``candidate_not_current`` and refuses with ``context_changed``: it is never a handoff;
4. **record** the publication (one revision) and re-render the deliverables.
"""
from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path

from mlkit.study import commands as cmd

from . import actions, export as ex, model, policy as pol, refuse, service as sv


def required(study_dir, milestone: str) -> bool:
    """True when the study's policy is required and names ``milestone``."""
    state = sv.load_state(study_dir)
    ext = model.of(state)
    if not ext:
        return False
    try:
        doc = sv.policy_doc(sv.open_store(study_dir), ext)
    except Exception:            # noqa: BLE001 - an unreadable policy blocks, never skips
        return True
    return bool(doc) and doc['mode'] == 'required' and milestone in doc['milestones']


def _same(current: dict, reserved: dict) -> bool:
    """The gate computed now has the reserved decision and identities."""
    return current['decision'] in ('allowed', 'allowed_by_waiver') and all(
        current.get(k) == reserved.get(k)
        for k in ('policy_digest', 'scope_digest', 'checked_context_digest'))


def _record_locked(store, state, rid, outcome, files, request_id):
    """Record the outcome inside the writer lock already held (same transaction protocol as
    every command: request id, revision, receipt)."""
    from mlkit import reliability
    actions.register()
    request = {'request_id': request_id, 'expected_revision': state['revision'],
               'action': actions.P + 'milestone_record',
               'params': {'reservation_id': rid, 'outcome': outcome, 'files': files}}
    return reliability.apply_command(store, state, request,
                                     cmd.handlers(cmd.Context(store, request_id)))


# In-process test hooks run between the rendering and the revalidation (A25).
BEFORE_FINALIZE: list = []


def export_handoff_gated(study_dir, *, out=None, expected_revision=None):
    from mlkit.study import cmd_export as ce

    state = sv.load_state(study_dir)
    store = sv.open_store(study_dir)
    if expected_revision is not None and expected_revision != state['revision']:
        raise refuse('stale_revision', f'The study is at revision {state["revision"]}, not '
                     f'{expected_revision}; nothing was written.', 'Read the study again.',
                     expected_revision=expected_revision, current_revision=state['revision'])
    token = uuid.uuid4().hex[:12]
    reserved = actions.apply(study_dir, 'milestone_reserve', {'milestone': 'handoff'},
                             request_id=f'handoff-reserve-{token}',
                             expected_revision=state['revision'])
    rid = reserved['result']['reservation_id']
    reserved_revision = reserved['revision']
    tmp = None
    try:
        cmd.after_commit(Path(study_dir), {'ok': True})   # the report at the reserved revision
        study, view, files, included = ce.build(study_dir)
        if view['revision'] != reserved_revision:
            raise refuse('context_changed', 'The study changed while the pack was built.',
                         'Run export handoff again.')
        target = ce._target(study.study_dir, out, view['revision'])
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.parent / f'.{target.name}.tmp-{secrets.token_hex(4)}'
        tmp.mkdir()
        listed = []
        for name in ce.FILES:
            if name not in files:
                continue
            with open(tmp / name, 'xb') as handle:
                handle.write(files[name])
                handle.flush()
                os.fsync(handle.fileno())
            listed.append({'path': name, 'sha256': ce._sha(files[name]),
                           'bytes': len(files[name])})
        for hook in BEFORE_FINALIZE:       # tests only: a concurrent change at this point
            hook(study_dir)
    except BaseException:
        if tmp is not None and tmp.exists():
            for p in tmp.iterdir():
                p.unlink()
            tmp.rmdir()
        _release(study_dir, rid, token)
        raise
    with store.writing() as fresh:
        record = fresh['understanding']['milestones'][rid]
        current = sv.gate(store, fresh, 'handoff')
        same = fresh['revision'] == reserved_revision and _same(current, record)
        if same:
            if target.exists() and target.is_dir() and not any(target.iterdir()):
                target.rmdir()
            try:
                ex.rename_noreplace(tmp, target)
            except FileExistsError:
                same = False
        if same:
            # Published and recorded under the same lock: no published-but-unrecorded pack.
            _record_locked(store, fresh, rid, 'published',
                           {f['path']: f['sha256'] for f in listed},
                           f'handoff-record-{token}')
        else:
            candidate = target.parent / f'{target.name}.candidate-{token}'
            os.rename(tmp, candidate)
            _record_locked(store, fresh, rid, 'candidate_not_current',
                           {'candidate': candidate.name}, f'handoff-record-{token}')
    if not same:
        raise refuse('context_changed', 'The handoff was not published: the policy, the '
                     'selection, a source or the study changed between the reservation and the '
                     'publication. The written folder stays as a candidate and is never a '
                     'handoff.', 'Run understanding check, then export handoff again.',
                     candidate=candidate.name)
    cmd.after_commit(Path(study_dir), {'ok': True})
    payload = {'schema': ce.SCHEMA, 'ok': True, 'study': str(study.study_dir),
               'revision': view['revision'], 'kind': 'handoff', 'out': str(target),
               'files': listed, 'included_report': included,
               'warnings': ce._warnings(view, included)}
    payload = {k: payload[k] for k in ce.PAYLOAD_KEYS}
    payload['understanding'] = {'milestone': 'handoff', 'decision': current['decision'],
                                'reservation_id': rid, 'assurance': pol.SUPPORTED_ASSURANCE,
                                'limitations': current['limitations']}
    return payload, cmd.EXIT_OK if included else cmd.EXIT_ARTIFACT_STALE


def _release(study_dir, rid, token):
    """A failure after the reservation closes it as not published (never left reserved)."""
    try:
        actions.apply(study_dir, 'milestone_record', {
            'reservation_id': rid, 'outcome': 'candidate_not_current', 'files': {}},
            request_id=f'handoff-release-{token}',
            expected_revision=sv.load_state(study_dir)['revision'])
    except Exception:          # noqa: BLE001 - the original failure is what the user sees
        pass
