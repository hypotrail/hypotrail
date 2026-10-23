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


def _same(a: dict, b: dict) -> bool:
    keys = ('decision', 'policy_digest', 'scope_digest', 'checked_context_digest')
    return all(a.get(k) == b.get(k) for k in keys)


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
    cmd.after_commit(Path(study_dir), {'ok': True})       # the report at the reserved revision
    gate_before = sv.gate(store, sv.load_state(study_dir), 'handoff')
    study, view, files, included = ce.build(study_dir)
    if view['revision'] != reserved_revision:
        return _abandon(study_dir, rid, None, 'the study changed while the pack was built')
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
    for hook in BEFORE_FINALIZE:           # tests only: a concurrent change at this point
        hook(study_dir)
    with store.writing() as fresh:
        current = sv.gate(store, fresh, 'handoff')
        same = fresh['revision'] == reserved_revision and _same(current, gate_before) and \
            current['decision'] in ('allowed', 'allowed_by_waiver')
        if same:
            if target.exists() and target.is_dir() and not any(target.iterdir()):
                target.rmdir()
            try:
                ex.rename_noreplace(tmp, target)
            except FileExistsError:
                same = False
        if not same:
            candidate = target.parent / f'{target.name}.candidate-{token}'
            os.rename(tmp, candidate)
    if not same:
        return _abandon(study_dir, rid, str(candidate),
                        'the policy, the selection, a source or the study changed between '
                        'the reservation and the publication')
    actions.apply(study_dir, 'milestone_record', {
        'reservation_id': rid, 'outcome': 'published',
        'files': {f['path']: f['sha256'] for f in listed}},
        request_id=f'handoff-record-{token}',
        expected_revision=sv.load_state(study_dir)['revision'])
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


def _abandon(study_dir, rid, candidate, why):
    actions.apply(study_dir, 'milestone_record', {
        'reservation_id': rid, 'outcome': 'candidate_not_current',
        'files': {'candidate': os.path.basename(candidate) if candidate else ''}},
        request_id=f'handoff-abandon-{rid}',
        expected_revision=sv.load_state(study_dir)['revision'])
    raise refuse('context_changed', f'The handoff was not published: {why}. The written '
                 'folder, if any, stays as a candidate and is never a handoff.',
                 'Run understanding check, then export handoff again.',
                 candidate=os.path.basename(candidate) if candidate else None)
