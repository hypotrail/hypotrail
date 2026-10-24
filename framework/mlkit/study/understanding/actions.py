"""Revisioned actions of the understanding review (registered on import).

Every mutation goes through :meth:`StudyStore.execute` (``apply_command``): a request id,
an expected revision, a replay that returns the first receipt, a refusal without effect,
a transition validated on state reread under the writer lock. Parameters carry only
identifiers, digests and sizes; answers and documents are blobs stored before the
request. No handler reaches the network, waits for a person, runs Git, or touches a
scientific decision, partition, exposure record, result or the final test.
"""
from __future__ import annotations

from typing import Mapping

from mlkit.reliability import Handler
from mlkit.study import commands as cmd

from . import DIMENSIONS, taskset as bk, canonical, evaluate as ev, model, policy as pol, refuse
from . import service as sv

P = 'understanding.'
REGISTERED = False


def _rev(state: Mapping) -> int:
    return state['revision'] + 1


def _session(ext: Mapping, sid) -> dict:
    s = ext['sessions'].get(sid)
    if s is None:
        raise refuse('invalid_transition', 'Unknown review session.',
                     'List the sessions with `hypotrail understanding status`.',
                     session_id=sid)
    return s


def _need_status(session: Mapping, *allowed) -> None:
    if session['status'] not in allowed:
        raise refuse('invalid_transition', f'The session is {session["status"]}; this step needs '
                     f'it {" or ".join(allowed)}.', 'Check the session status.',
                     session_id=session['session_id'], status=session['status'])


def _session_taskset(store, session) -> dict:
    return sv.blob_json(store, session['taskset_blob'], 'taskset')


def _allowed_refs(store, session) -> set:
    snapdoc = sv.session_snapshot(store, session)
    out = {e['logical_key'] for e in snapdoc['local']['entries']}
    out |= {e['path'] for e in snapdoc['local']['entries'] if e.get('path')}
    out |= set(snapdoc.get('refs') or {})
    for t in _session_taskset(store, session)['tasks']:
        out |= set(t['source_refs'])
    return out


def _check_refs(refs, allowed: set, field: str) -> list:
    refs = model.str_list(refs, field)
    bad = [r for r in refs if r not in allowed]
    if bad:
        raise refuse('evidence_invalid', f'{field} names references outside the review '
                     'scope; only logical keys, mapped paths and case references resolve.',
                     'Cite the sources the task lists.', field=field, unresolved=bad[:10])
    return refs


def _unsafe(text: str) -> bool:
    lowered = text.lower()
    return any(m in lowered for m in ('file://', '$(', '`', '\nsudo ', '\nrm ', ' && '))


# --- policy -------------------------------------------------------------------------------

def _policy_set(ctx) -> Handler:
    def run(state, params):
        ext = model.require_writable(state)
        doc = pol.validate(sv.blob_json(ctx.store, params['policy_sha'], 'policy'))
        author = model.actor(params['author_declared_id'], 'author_declared_id')
        reason = model.text(params['reason'], 'reason', limit=1000)
        old = ext['policy']
        new_digest = pol.digest(doc)
        ext['policy'] = {'digest': new_digest, 'blob': params['policy_sha'],
                         'policy_id': doc['policy_id'], 'version': doc['version'],
                         'mode': doc['mode'], 'set_revision': _rev(state)}
        event = {'revision': _rev(state), 'time': sv.now(),
                 'previous_digest': old['digest'] if old else None, 'new_digest': new_digest,
                 'mode_from': old['mode'] if old else 'off', 'mode_to': doc['mode'],
                 'author_declared_id': author, 'reason': reason, 'request_id': ctx.request_id}
        ext['policy_events'].append(event)
        return {'policy_digest': new_digest, 'previous_digest': event['previous_digest'],
                'mode': doc['mode']}
    return Handler(frozenset({'policy_sha', 'author_declared_id', 'reason'}), run)


# --- sessions -----------------------------------------------------------------------------

def _start(ctx) -> Handler:
    def run(state, params):
        doc = sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        if params['policy_digest'] != pol.digest(doc):
            raise refuse('context_changed', 'The policy changed since the plan was made.',
                         'Make the plan again.')
        plan = sv.blob_json(ctx.store, params['plan_sha'], 'plan')
        taskset = sv.current_taskset(state)
        if bk.digest(taskset) != params['taskset_digest']:
            raise refuse('context_changed', 'The taskset changed since the plan was made.',
                         'Make the plan again.')
        # The capture is recomputed here, on the state reread under the lock: a source or
        # a decision that moved in between is a conflict, never a hybrid snapshot.
        frozen: dict = {}
        cap = sv.capture(state, ext, policy_digest=params['policy_digest'], taskset_doc=taskset,
                         repo=plan.get('repo'), sources=plan['sources'], frozen=frozen)
        if cap['local_snapshot_digest'] != params['local_digest'] \
                or cap['source_scope_digest'] != params['scope_digest']:
            raise refuse('context_changed', 'The study or a mapped source changed during the '
                         'capture.', 'Run start again; the capture is retried a few times.')
        stored = sv.blob_json(ctx.store, params['snapshot_sha'], 'snapshot')
        if canonical.digest(stored['local']) != cap['local_snapshot_digest']:
            raise refuse('evidence_invalid', 'The stored snapshot does not match the capture.',
                         'Run start again.')
        for data in frozen.values():               # frozen bytes of the mapped sources
            ctx.store.put_blob(data)
        actor = model.actor(plan['actor_declared_id'], 'actor_declared_id')
        dims = pol.author_dimensions(doc, plan['profile'])
        previous = plan.get('previous_session_id')
        if previous is not None and \
                _session(ext, previous)['actor_declared_id'] != plan['actor_declared_id']:
            raise refuse('evidence_invalid', 'A linked session continues a session of the same '
                         'person.', 'Link to a session of this author, or none.')
        sid = model.new_id('us', ctx.request_id)
        ext['sessions'][sid] = {
            'session_id': sid, 'status': 'active', 'actor_declared_id': actor,
            'profile': plan['profile'], 'milestone': plan['milestone'],
            'dimensions': dims, 'task_ids': list(plan['task_ids']),
            'policy_digest': params['policy_digest'], 'policy_blob': ext['policy']['blob'],
            'taskset_id': taskset['taskset_id'], 'taskset_digest': params['taskset_digest'],
            'taskset_blob': sv.put_json(ctx.store, taskset), 'taskset_qualified': bk.qualified(taskset),
            'taskset_simulated': bk.simulated_qualification(taskset),
            'plan_blob': params['plan_sha'], 'snapshot_blob': params['snapshot_sha'],
            'local_snapshot_digest': cap['local_snapshot_digest'],
            'source_scope_digest': cap['source_scope_digest'],
            'created_revision': _rev(state), 'created_at': sv.now(), 'repo_override': None,
            'previous_session_id': previous,
            'transitions': [{'to': 'active', 'revision': _rev(state), 'reason': 'started'}]}
        return {'session_id': sid, 'status': 'active', 'dimensions': dims,
                'local_snapshot_digest': cap['local_snapshot_digest'],
                'source_scope_digest': cap['source_scope_digest']}
    return Handler(frozenset({'plan_sha', 'snapshot_sha', 'local_digest', 'scope_digest',
                              'taskset_digest', 'policy_digest'}), run)


def _close(ctx) -> Handler:
    def run(state, params):
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        to = params['to']
        if to not in model.TRANSITIONS.get(s['status'], ()):
            raise refuse('invalid_transition', f'A {s["status"]} session cannot become {to}.',
                         'A completed or abandoned session is final; start a linked session.',
                         session_id=s['session_id'], status=s['status'], to=to)
        reason = model.text(params['reason'], 'reason', limit=1000)
        s['status'] = to
        s['transitions'].append({'to': to, 'revision': _rev(state), 'reason': reason})
        remaining = [d for d in s['dimensions']
                     if ev.dimension_view(ext, s['actor_declared_id'], d)['status']
                     != 'demonstrated']
        return {'session_id': s['session_id'], 'status': to,
                'not_demonstrated_dimensions': remaining}
    return Handler(frozenset({'session_id', 'to', 'reason'}), run)


# --- attempts and assistance ---------------------------------------------------------------

ASSISTANCE_KEYS = ('resources_used', 'ai_assistance_declared', 'independence_claim',
                   'limitations')


def _assistance(store, sha) -> dict:
    doc = sv.blob_json(store, sha, 'assistance')
    if not isinstance(doc, Mapping) or set(doc) != set(ASSISTANCE_KEYS):
        raise refuse('evidence_invalid', 'The assistance file has the keys '
                     + ', '.join(ASSISTANCE_KEYS) + '.', 'Declare the help received.',
                     field='assistance')
    if not isinstance(doc['ai_assistance_declared'], bool):
        raise refuse('evidence_invalid', 'ai_assistance_declared is true or false.',
                     'Declare whether an AI helped write the answer.', field='assistance')
    model.str_list(doc['resources_used'], 'assistance/resources_used')
    model.str_list(doc['limitations'], 'assistance/limitations')
    if doc['independence_claim'] is not None:
        model.text(doc['independence_claim'], 'assistance/independence_claim', limit=1000)
    return dict(doc)


def _reservation_variant(ext: Mapping, session: Mapping, task: Mapping | None) -> bool:
    """True when ``task`` is a new variant (same family, another variant) of a task whose
    attempt opened a reservation for the session author (SPEC §07 step 5)."""
    if task is None:
        return False
    for r in ext['reservations'].values():
        if r['status'] != 'open' or r['actor'] != session['actor_declared_id']:
            continue
        for aid in r['attempt_ids']:
            ref = ext['attempts'].get(aid, {}).get('task_ref') or {}
            if ref.get('variant_family') == task['variant_family'] \
                    and ref.get('variant_id') != task['variant_id']:
                return True
    return False


def _actor_of(ext: Mapping, session_id: str) -> str | None:
    s = ext['sessions'].get(session_id)
    return s['actor_declared_id'] if s else None


def _coached(ext: Mapping, actor: str, task_id: str) -> list:
    """Coaching the person received on this task, in any of their sessions: help carries
    over to a linked session (A04)."""
    return [e for e in ext['assistance_events'] if e['kind'] == 'coaching'
            and e['task_id'] == task_id and _actor_of(ext, e['session_id']) == actor]


def _submit(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        _need_status(s, 'active')
        tid = params['task_id']
        taskset = _session_taskset(ctx.store, s)
        task = bk.task(taskset, tid)
        if tid not in s['task_ids'] and not _reservation_variant(ext, s, task):
            raise refuse('invalid_transition', 'This task is neither in the session plan nor a '
                         'new variant for an open reservation.',
                         'Ask for the next task with `understanding task`.', task_id=tid)
        refs = sv.session_snapshot(ctx.store, s).get('refs') or {}
        _, missing = bk.resolve(task['prompt_template'], refs, task['required_refs'])
        if missing:
            raise refuse('prerequisite_missing', 'The task cites a study element that does not '
                         'exist yet.', 'Take the study further first, or pick another task.',
                         missing=missing)
        if not sv.blob_ok(ctx.store, params['response_sha']):
            raise refuse('evidence_invalid', 'The answer was not stored.', 'Submit again.')
        assistance = _assistance(ctx.store, params['assistance_sha'])
        cited = _check_refs(params['cited_refs'], _allowed_refs(ctx.store, s), 'cited_refs')
        actor_ = s['actor_declared_id']
        # The first attempt of a person on a task is first across all their sessions.
        prior = [a for a in ext['attempts'].values() if a['task_ref']['task_id'] == tid
                 and a['declared_actor'] == actor_]
        previous = params['previous_attempt_id']
        if previous is not None and previous not in {a['attempt_id'] for a in prior}:
            raise refuse('evidence_invalid', 'previous_attempt_id is not an attempt of this '
                         'task in this session.', 'Name the attempt the new one corrects.')
        coached = _coached(ext, actor_, tid)
        assistance.update(hints_seen=sorted({h for e in coached for h in e['hints']}),
                          coaching_seen=bool(coached))
        family = task['variant_family']
        assistance['coaching_seen_on_family'] = any(
            e['variant_family'] == family for e in ext['assistance_events']
            if e['kind'] == 'coaching' and _actor_of(ext, e['session_id']) == actor_)
        aid = model.new_id('ua', ctx.request_id)
        ext['attempts'][aid] = {
            'attempt_id': aid, 'session_id': s['session_id'],
            'task_ref': {'task_id': tid, 'task_version': task['task_version'],
                         'variant_family': family, 'variant_id': task['variant_id'],
                         'rubric_id': task['rubric_id']},
            'dimension_ids': list(task['dimension_ids']),
            'started_at': None, 'submitted_at': sv.now(),
            'response_sha256': params['response_sha'], 'response_bytes': params['response_bytes'],
            'response_digest': params['response_sha'], 'cited_refs': cited,
            'assistance': assistance, 'previous_attempt_id': previous,
            'declared_actor': s['actor_declared_id'], 'first_attempt': not prior,
            'recorded_revision': _rev(state)}
        return {'attempt_id': aid, 'first_attempt': not prior,
                'aided': bool(assistance['ai_assistance_declared'] or coached)}
    return Handler(frozenset({'session_id', 'task_id', 'response_sha', 'response_bytes',
                              'assistance_sha', 'cited_refs', 'previous_attempt_id'}), run)


def _coach(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        a = ext['attempts'].get(params['attempt_id'])
        if a is None:
            raise refuse('invalid_transition', 'Coaching opens after a first attempt.',
                         'Submit a first answer, then ask for coaching.')
        s = _session(ext, a['session_id'])
        _need_status(s, 'active', 'awaiting_review')
        taskset = _session_taskset(ctx.store, s)
        r = bk.rubric(taskset, a['task_ref']['rubric_id'])
        hints = [f'{r["rubric_id"]}#hint{i}' for i in range(len(r['hints']))]
        ext['assistance_events'].append({
            'kind': 'coaching', 'attempt_id': a['attempt_id'], 'session_id': s['session_id'],
            'task_id': a['task_ref']['task_id'], 'variant_family': a['task_ref']['variant_family'],
            'hints': hints, 'revision': _rev(state)})
        return {'attempt_id': a['attempt_id'], 'rubric_id': r['rubric_id'],
                'hint_count': len(hints)}
    return Handler(frozenset({'attempt_id'}), run)


def _rectify(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        a = ext['attempts'].get(params['attempt_id'])
        if a is None:
            raise refuse('invalid_transition', 'Unknown attempt.', 'Check the attempt id.')
        doc = _assistance(ctx.store, params['assistance_sha'])
        ext['assistance_events'].append({
            'kind': 'rectification', 'attempt_id': a['attempt_id'],
            'session_id': a['session_id'], 'task_id': a['task_ref']['task_id'],
            'ai_assistance_declared': doc['ai_assistance_declared'],
            'resources_used': doc['resources_used'], 'hints': [], 'revision': _rev(state)})
        dependent = [d['decision_id'] for d in ext['decisions'].values()
                     if a['attempt_id'] in d.get('attempt_ids', [])]
        return {'attempt_id': a['attempt_id'], 'decisions_to_review': sorted(dependent)}
    return Handler(frozenset({'attempt_id', 'assistance_sha'}), run)


# --- proposals, human reviews, arbitration ------------------------------------------------

PROPOSAL_KEYS = ('attempt_id', 'rubric_digest', 'author', 'criteria', 'uncertainties')


def _propose(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        _need_status(s, 'active', 'awaiting_review')
        doc = sv.blob_json(ctx.store, params['proposal_sha'], 'proposal')
        if not isinstance(doc, Mapping) or set(doc) != set(PROPOSAL_KEYS):
            raise refuse('evidence_invalid', 'A proposal has the keys '
                         + ', '.join(PROPOSAL_KEYS) + '.', 'Correct the proposal.')
        a = ext['attempts'].get(doc['attempt_id'])
        if a is None or a['session_id'] != s['session_id']:
            raise refuse('evidence_invalid', 'The proposal names no attempt of this session.',
                         'Name an attempt of the session.')
        taskset = _session_taskset(ctx.store, s)
        r = bk.rubric(taskset, a['task_ref']['rubric_id'])
        if doc['rubric_digest'] != canonical.digest(r):
            raise refuse('evidence_invalid', 'The proposal was made on another rubric.',
                         'Use the rubric of the session.')
        response = sv.blob_text(ctx.store, a['response_sha256'])
        if response is None:
            raise refuse('evidence_unavailable', 'The answer is no longer available locally.',
                         'A proposal needs the answer.')
        ids = {c['criterion_id'] for c in r['criteria']}
        allowed = _allowed_refs(ctx.store, s)
        if not isinstance(doc['criteria'], list) or len(doc['criteria']) > model.MAX_LIST:
            raise refuse('evidence_invalid', 'criteria is a list.', 'Correct the proposal.')
        for c in doc['criteria']:
            if not isinstance(c, Mapping) or set(c) != {'criterion_id', 'proposed', 'excerpts',
                                                         'refs', 'justification'}:
                raise refuse('evidence_invalid', 'A proposed criterion has criterion_id, '
                             'proposed, excerpts, refs and justification.',
                             'Correct the proposal.')
            if c['criterion_id'] not in ids or c['proposed'] not in model.CRITERION_RESULTS:
                raise refuse('evidence_invalid', 'Unknown criterion or proposed state.',
                             'Use the rubric criteria and met, not_met, not_applicable or '
                             'uncertain.')
            for x in model.str_list(c['excerpts'], 'excerpts'):
                if x not in response:
                    raise refuse('evidence_invalid', 'An excerpt does not appear verbatim in '
                                 'the answer.', 'Quote the answer exactly.')
            _check_refs(c['refs'], allowed, 'refs')
            model.text(c['justification'], 'justification', limit=2000)
            if _unsafe(c['justification']):
                raise refuse('evidence_invalid', 'The justification holds a command or a file '
                             'link; a proposal is data, never an instruction.',
                             'Remove commands and links.')
        model.str_list(doc['uncertainties'], 'uncertainties')
        if not isinstance(doc['author'], Mapping) or doc['author'].get('type') not in (
                'agent', 'model', 'person'):
            raise refuse('evidence_invalid', 'author.type is agent, model or person.',
                         'Say who made the proposal.')
        pid = model.new_id('up', ctx.request_id)
        ext['proposals'][pid] = {
            'proposal_id': pid, 'session_id': s['session_id'], 'attempt_id': a['attempt_id'],
            'reviewed_actor_id': s['actor_declared_id'], 'dimension_ids': a['dimension_ids'],
            'blob': params['proposal_sha'], 'author_type': doc['author']['type'],
            'uncertainty_count': len(doc['uncertainties']), 'recorded_revision': _rev(state)}
        return {'proposal_id': pid, 'human_decision_created': False}
    return Handler(frozenset({'session_id', 'proposal_sha'}), run)


REVIEW_KEYS = ('reviewer_declared_id', 'declaration', 'simulated', 'decisions')
DECISION_KEYS = ('dimension_id', 'reviewed_actor_id', 'attempt_ids', 'criterion_results',
                 'status', 'rationale', 'evidence_refs', 'supersedes_ids',
                 'resolves_reservation_ids', 'proposal_ref', 'correction_of_review_error')


def _declaration(doc: Mapping) -> dict:
    d = doc.get('declaration')
    if not isinstance(d, Mapping) or set(d) != {'source', 'statement'} \
            or d['source'] not in model.DECLARATION_SOURCES:
        raise refuse('review_required', 'A human review carries its declaration: source '
                     '(reviewer_cli, reviewer_file or chat_relay) and the reviewer\'s statement.',
                     'Collect the decision from the reviewer; an agent never fills this act '
                     'in their name.')
    model.text(d['statement'], 'declaration/statement', limit=2000)
    if not isinstance(doc.get('simulated'), bool):
        raise refuse('review_required', 'simulated is true (a test fixture) or false.',
                     'State whether the reviewer is simulated.')
    return dict(d)


def _criteria(results, rubric: Mapping) -> list:
    known = {c['criterion_id']: c for c in rubric['criteria']}
    if not isinstance(results, list) or len(results) != len(known) or \
            {r.get('criterion_id') for r in results if isinstance(r, Mapping)} != set(known):
        raise refuse('evidence_invalid', 'criterion_results gives one result per criterion of '
                     'the rubric.', 'Fill every criterion.')
    out = []
    for r in results:
        if set(r) != {'criterion_id', 'result', 'note'} or r['result'] not in \
                model.CRITERION_RESULTS:
            raise refuse('evidence_invalid', 'A criterion result has criterion_id, result '
                         '(met, not_met, not_applicable, uncertain) and note.',
                         'Correct the result.')
        if r['result'] == 'not_applicable' and (not known[r['criterion_id']][
                'not_applicable_allowed'] or not isinstance(r['note'], str)
                or not r['note'].strip()):
            raise refuse('evidence_invalid', 'not_applicable is allowed only where the rubric '
                         'provides it, with a justification.', 'Justify or evaluate it.')
        if r['note'] is not None:
            model.text(r['note'], 'note', limit=2000, empty_ok=True)
        out.append(dict(r))
    return sorted(out, key=lambda r: r['criterion_id'])


def _status_consistent(status: str, results: list, rubric: Mapping) -> None:
    mandatory = {c['criterion_id'] for c in rubric['criteria'] if c['mandatory']}
    by_id = {r['criterion_id']: r['result'] for r in results}
    if status == 'demonstrated':
        if any(by_id[c] not in ('met', 'not_applicable') for c in mandatory) \
                or 'uncertain' in by_id.values():
            raise refuse('evidence_invalid', 'demonstrated needs every mandatory criterion met '
                         'by admissible evidence and no uncertain criterion.',
                         'Record to_consolidate or needs_review instead.')
    elif status == 'to_consolidate' and 'not_met' not in by_id.values():
        raise refuse('evidence_invalid', 'to_consolidate names at least one criterion not met.',
                     'Mark the difficulty, or use needs_review.')
    elif status not in ('demonstrated', 'to_consolidate', 'needs_review'):
        raise refuse('evidence_invalid', 'status is demonstrated, to_consolidate or '
                     'needs_review.', 'Correct the status.')


def _review(ctx) -> Handler:
    def run(state, params):
        doc_policy = sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        _need_status(s, 'active', 'awaiting_review')
        doc = sv.blob_json(ctx.store, params['decisions_sha'], 'review')
        if not isinstance(doc, Mapping) or set(doc) != set(REVIEW_KEYS):
            raise refuse('review_required', 'A review file has the keys '
                         + ', '.join(REVIEW_KEYS) + '.', 'Collect the human review.')
        reviewer = model.actor(doc['reviewer_declared_id'], 'reviewer_declared_id')
        declaration = _declaration(doc)
        if not isinstance(doc['decisions'], list) or not doc['decisions'] \
                or len(doc['decisions']) > len(DIMENSIONS) * 2:
            raise refuse('evidence_invalid', 'decisions lists one to sixteen decisions.',
                         'Correct the review file.')
        taskset = _session_taskset(ctx.store, s)
        allowed = _allowed_refs(ctx.store, s)
        created = []
        for i, d in enumerate(doc['decisions']):
            if not isinstance(d, Mapping) or set(d) != set(DECISION_KEYS):
                raise refuse('evidence_invalid', 'A decision has the keys '
                             + ', '.join(DECISION_KEYS) + '.', 'Correct the review file.',
                             index=i)
            dim = d['dimension_id']
            if dim not in s['dimensions']:
                raise refuse('evidence_invalid', 'The dimension is outside the session scope.',
                             'Review the dimensions the session covers.', dimension=dim)
            actor = model.actor(d['reviewed_actor_id'], 'reviewed_actor_id')
            if actor != s['actor_declared_id']:
                raise refuse('evidence_invalid', 'The reviewed person is not the session '
                             'author.', 'Review the session author.')
            if reviewer == actor and doc_policy['mode'] == 'required' \
                    and dim in doc_policy['critical_dimensions']:
                raise refuse('review_required', 'On a critical dimension the reviewer is '
                             'another declared person than the author.',
                             'Ask a colleague to review this dimension.', dimension=dim)
            attempts = model.str_list(d['attempt_ids'], 'attempt_ids')
            if not attempts:
                raise refuse('evidence_invalid', 'A decision rests on at least one attempt.',
                             'Name the attempts reviewed.')
            for aid in attempts:
                a = ext['attempts'].get(aid)
                if a is None or a['session_id'] != s['session_id'] or dim not in a['dimension_ids']:
                    raise refuse('evidence_invalid', 'An attempt is not of this session and '
                                 'dimension.', 'Name attempts of this session.', attempt_id=aid)
                if not sv.blob_ok(ctx.store, a['response_sha256']):
                    raise refuse('evidence_unavailable', 'An answer is no longer available '
                                 'locally; a new review cannot rest on it.',
                                 'Its historical judgement stays; collect a new answer.',
                                 attempt_id=aid)
            rubric = bk.rubric_for(taskset, dim)
            results = _criteria(d['criterion_results'], rubric)
            _status_consistent(d['status'], results, rubric)
            rationale = model.text(d['rationale'], 'rationale', limit=4000)
            evidence = _check_refs(d['evidence_refs'], allowed, 'evidence_refs')
            supersedes = model.str_list(d['supersedes_ids'], 'supersedes_ids')
            for old in supersedes:
                o = ext['decisions'].get(old)
                if o is None or o['kind'] != 'attempt' or o['reviewed_actor_id'] != actor \
                        or o['dimension_id'] != dim:
                    raise refuse('evidence_invalid', 'supersedes_ids names a decision on '
                                 'another person or dimension.', 'Name decisions it replaces.')
                if o['reviewer_declared_id'] != reviewer:
                    raise refuse('review_required', 'Only its own reviewer replaces a decision; '
                                 'a disagreement between reviewers is settled by arbitration.',
                                 'Record your own decision and ask for an arbitration.')
                if any(o['decision_id'] in c['decision_ids'] for c in ev.conflicts(ext)):
                    raise refuse('review_required', 'This decision is in a conflict; only an '
                                 'arbitration settles it.', 'Ask for an arbitration.')
                if not (set(attempts) - set(o['attempt_ids'])) and not \
                        d['correction_of_review_error']:
                    raise refuse('evidence_invalid', 'Replacing a decision needs new admissible '
                                 'evidence or a stated correction of a review error.',
                                 'Add a new attempt or set correction_of_review_error.')
            resolves = model.str_list(d['resolves_reservation_ids'], 'resolves_reservation_ids')
            for rid in resolves:
                r = ext['reservations'].get(rid)
                if r is None or r['status'] != 'open' or r['actor'] != actor \
                        or r['dimension_id'] != dim or r.get('origin') == 'transfer':
                    raise refuse('evidence_invalid', 'resolves_reservation_ids names no open '
                                 'reservation of this person and dimension.',
                                 'Name the open reservation.')
                old_variants = {ext['attempts'][x]['task_ref']['variant_id']
                                for x in r['attempt_ids'] if x in ext['attempts']}
                fresh = [x for x in attempts if x not in r['attempt_ids']
                         and ext['attempts'][x]['task_ref']['variant_id'] not in old_variants]
                own = ext['decisions'][r['decision_id']]['reviewer_declared_id'] == reviewer
                if d['status'] != 'demonstrated' or (not fresh and not (
                        d['correction_of_review_error'] and own)):
                    raise refuse('evidence_invalid', 'A reservation is resolved by a '
                                 'demonstrated decision on a new attempt of a new variant (the '
                                 'same question again does not demonstrate anew), or by a '
                                 'correction of a review error by the same reviewer.',
                                 'Ask a new variant of the task, or arbitrate.')
            if not isinstance(d['correction_of_review_error'], bool):
                raise refuse('evidence_invalid', 'correction_of_review_error is a boolean.',
                             'Correct the field.')
            if d['proposal_ref'] is not None and d['proposal_ref'] not in ext['proposals']:
                raise refuse('evidence_invalid', 'proposal_ref names no stored proposal.',
                             'Name the proposal or null.')
            did = model.new_id('ud', ctx.request_id, str(i))
            task_keys = sorted({k for x in attempts for k in bk.task(
                taskset, ext['attempts'][x]['task_ref']['task_id'])['dependency_keys']})
            ext['decisions'][did] = {
                'kind': 'attempt', 'decision_id': did, 'session_id': s['session_id'],
                'reviewer_declared_id': reviewer, 'reviewed_actor_id': actor,
                'reviewed_at': sv.now(), 'recorded_revision': _rev(state),
                'attempt_ids': attempts, 'dimension_id': dim, 'criterion_results': results,
                'status': d['status'], 'rationale': rationale, 'evidence_refs': evidence,
                'snapshot_digest': s['local_snapshot_digest'],
                'source_scope_digest': s['source_scope_digest'],
                'policy_digest': s['policy_digest'],
                'rubric_digest': canonical.digest(rubric), 'taskset_digest': s['taskset_digest'],
                'supersedes_ids': supersedes, 'resolves_reservation_ids': resolves,
                'assurance': pol.SUPPORTED_ASSURANCE, 'proposal_ref': d['proposal_ref'],
                'declaration': declaration, 'simulated': doc['simulated'],
                'correction_of_review_error': d['correction_of_review_error'],
                'dependency_keys': task_keys,
                'assistance_at_review': {x: ev.attempt_assistance(ext, x)['aided']
                                         for x in attempts}}
            for rid in resolves:
                r = ext['reservations'][rid]
                r.update(status='resolved', resolved_by=did, resolved_revision=_rev(state))
            if d['status'] in ('to_consolidate', 'needs_review'):
                rid = model.new_id('ur', ctx.request_id, str(i))
                ext['reservations'][rid] = {
                    'reservation_id': rid, 'decision_id': did, 'actor': actor,
                    'dimension_id': dim, 'kind': d['status'], 'attempt_ids': attempts,
                    'criteria': [r['criterion_id'] for r in results
                                 if r['result'] in ('not_met', 'uncertain')],
                    'status': 'open', 'opened_revision': _rev(state), 'resolved_by': None}
            created.append({'decision_id': did, 'dimension_id': dim, 'status': d['status']})
        return {'decisions': created, 'assurance': pol.SUPPORTED_ASSURANCE,
                'simulated': doc['simulated']}
    return Handler(frozenset({'session_id', 'decisions_sha'}), run)


ARBITRATION_KEYS = ('arbiter_declared_id', 'declaration', 'simulated',
                    'conflicting_decision_ids', 'reservation_ids', 'chosen_decision_id',
                    'rationale', 'evidence_refs')


def _arbitrate(ctx) -> Handler:
    def run(state, params):
        doc_policy = sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        _need_status(s, 'active', 'awaiting_review', 'completed')
        doc = sv.blob_json(ctx.store, params['arbitration_sha'], 'arbitration')
        if not isinstance(doc, Mapping) or set(doc) != set(ARBITRATION_KEYS):
            raise refuse('review_required', 'An arbitration has the keys '
                         + ', '.join(ARBITRATION_KEYS) + '.', 'Collect the arbitration.')
        arbiter = model.actor(doc['arbiter_declared_id'], 'arbiter_declared_id')
        declaration = _declaration(doc)
        allowed_arbiters = doc_policy['role_policy']['arbiters']
        if allowed_arbiters != 'any_declared' and arbiter not in allowed_arbiters:
            raise refuse('review_required', 'The policy does not name this arbiter.',
                         'Ask an arbiter the policy names.')
        ids = model.str_list(doc['conflicting_decision_ids'], 'conflicting_decision_ids')
        decisions = [ext['decisions'].get(x) for x in ids]
        if any(d is None or d['session_id'] != s['session_id'] for d in decisions):
            raise refuse('evidence_invalid', 'The arbitration names decisions outside this '
                         'session.', 'Name the decisions in conflict.')
        reservations = model.str_list(doc['reservation_ids'], 'reservation_ids')
        for rid in reservations:
            r = ext['reservations'].get(rid)
            if r is None or r['status'] != 'open':
                raise refuse('evidence_invalid', 'A reservation is unknown or closed.',
                             'Name open reservations.')
        if not ids and not reservations:
            raise refuse('evidence_invalid', 'An arbitration settles decisions or '
                         'reservations.', 'Name them.')
        chosen = doc['chosen_decision_id']
        if (ids and chosen not in ids) or (not ids and chosen is not None):
            raise refuse('evidence_invalid', 'chosen_decision_id is one of the conflicting '
                         'decisions (null when only reservations are settled).',
                         'Choose among the decisions in conflict.')
        for rid in reservations:
            r = ext['reservations'][rid]
            if ext['decisions'][r['decision_id']]['session_id'] != s['session_id']:
                raise refuse('evidence_invalid', 'A reservation of another session is settled '
                             'in that session.', 'Arbitrate in the session of the reservation.')
        actors = {d['reviewed_actor_id'] for d in decisions} | \
            {ext['reservations'][r]['actor'] for r in reservations}
        dims = {d['dimension_id'] for d in decisions} | \
            {ext['reservations'][r]['dimension_id'] for r in reservations}
        if len(actors) > 1 or len(dims) > 1:
            raise refuse('evidence_invalid', 'One arbitration settles one person and one '
                         'dimension.', 'Split the arbitration.')
        # The session's own policy and the current one both apply (the stricter wins): a
        # policy toggled in between never relaxes who may arbitrate.
        session_policy = sv.blob_json(ctx.store, s['policy_blob'], 'policy')
        critical = set(doc_policy['critical_dimensions']) | \
            set(session_policy['critical_dimensions'])
        if arbiter in actors and dims & critical:
            raise refuse('review_required', 'On a critical dimension the arbiter is not the '
                         'person reviewed.', 'Ask another declared person.')
        parties = {d['reviewer_declared_id'] for d in decisions}
        if arbiter in parties:
            raise refuse('review_required', 'A reviewer whose decision is in the conflict does '
                         'not arbitrate it.', 'Ask a third declared person.')
        evidence = _check_refs(doc['evidence_refs'], _allowed_refs(ctx.store, s),
                               'evidence_refs')
        if reservations and not ids and not evidence:
            raise refuse('evidence_invalid', 'Settling a reservation without a conflict rests '
                         'on identified evidence (spec §09).', 'Cite the evidence.')
        aid = model.new_id('uarb', ctx.request_id)
        ext['arbitrations'][aid] = {
            'arbitration_id': aid, 'session_id': s['session_id'],
            'conflicting_decision_ids': ids, 'reservation_ids': reservations,
            'chosen_decision_id': chosen, 'arbiter_declared_id': arbiter,
            'rationale': model.text(doc['rationale'], 'rationale', limit=4000),
            'evidence_refs': evidence,
            'policy_digest': s['policy_digest'], 'snapshot_digest': s['local_snapshot_digest'],
            'declaration': declaration, 'simulated': doc['simulated'],
            'recorded_revision': _rev(state)}
        for rid in reservations:
            ext['reservations'][rid].update(status='resolved', resolved_by=aid,
                                            resolved_revision=_rev(state))
        return {'arbitration_id': aid}
    return Handler(frozenset({'session_id', 'arbitration_sha'}), run)


# --- selection, waivers -------------------------------------------------------------------

SELECTION_KEYS = ('milestone', 'actor_scope', 'dimension_decision_map',
                  'transfer_decision_map', 'reservation_resolution_refs')


def _selected(ext, field, kind, dim, did, actor) -> None:
    d = ext['decisions'].get(did)
    if d is None or d['kind'] != kind:
        raise refuse('evidence_invalid', f'{field} names an unknown decision.',
                     'Name recorded decisions.', dimension=dim)
    session = ext['sessions'].get(d['session_id'])
    if session is None or session['status'] != 'completed':
        raise refuse('invalid_transition', 'Only decisions of completed sessions can be '
                     'selected; an active or awaiting session satisfies no required milestone.',
                     'Close the session first.', dimension=dim)
    if kind == 'attempt' and (d['reviewed_actor_id'] != actor or d['dimension_id'] != dim):
        raise refuse('evidence_invalid', 'A selected decision is about another person or '
                     'dimension.', 'Correct the map.', dimension=dim)
    if kind == 'transfer' and dim not in d['dimension_ids']:
        raise refuse('evidence_invalid', 'A selected transfer review does not cover this '
                     'dimension.', 'Correct the map.', dimension=dim)


def _select(ctx) -> Handler:
    def run(state, params):
        doc_policy = sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        doc = sv.blob_json(ctx.store, params['selection_sha'], 'selection')
        if not isinstance(doc, Mapping) or set(doc) != set(SELECTION_KEYS):
            raise refuse('evidence_invalid', 'A coverage selection has the keys '
                         + ', '.join(SELECTION_KEYS) + '.', 'Correct the selection.')
        if doc['milestone'] not in doc_policy['milestones']:
            raise refuse('policy_invalid', 'The policy names no such milestone.',
                         'Select for a milestone of the policy.')
        scope = doc['actor_scope']
        if not isinstance(scope, Mapping) or set(scope) != {'actor_declared_id', 'profile'}:
            raise refuse('evidence_invalid', 'actor_scope has actor_declared_id and profile.',
                         'Correct the scope.')
        actor = model.actor(scope['actor_declared_id'], 'actor_scope/actor_declared_id')
        pol.author_dimensions(doc_policy, scope['profile'])
        for field in ('dimension_decision_map', 'transfer_decision_map'):
            m = doc[field]
            if not isinstance(m, Mapping) or any(k not in DIMENSIONS for k in m):
                raise refuse('evidence_invalid', f'{field} maps dimension ids to decision ids.',
                             'Correct the map.')
            for dim, value in m.items():
                kind = 'attempt' if field == 'dimension_decision_map' else 'transfer'
                ids_ = [value] if isinstance(value, str) or kind == 'attempt' else value
                if not isinstance(ids_, list) or not ids_ or \
                        not all(isinstance(x, str) for x in ids_) or len(set(ids_)) != len(ids_):
                    raise refuse('evidence_invalid', f'{field} maps a dimension to a decision '
                                 'id (a list of distinct ids for transfers).',
                                 'Correct the map.', dimension=dim)
                for did in ids_:
                    _selected(ext, field, kind, dim, did, actor)
        model.str_list(doc['reservation_resolution_refs'], 'reservation_resolution_refs')
        sid = model.new_id('usel', ctx.request_id)
        record = {'selection_id': sid, 'milestone': doc['milestone'],
                  'policy_digest': pol.digest(doc_policy), 'actor_scope': dict(scope),
                  'dimension_decision_map': dict(doc['dimension_decision_map']),
                  'transfer_decision_map': dict(doc['transfer_decision_map']),
                  'reservation_resolution_refs': list(doc['reservation_resolution_refs']),
                  'recorded_revision': _rev(state)}
        record['scope_digest'] = canonical.digest({k: record[k] for k in (
            'milestone', 'policy_digest', 'actor_scope', 'dimension_decision_map',
            'transfer_decision_map')})
        ext['selections'][sid] = record
        open_ = ev.open_reservations(ext, actor)
        return {'selection_id': sid, 'scope_digest': record['scope_digest'],
                'open_reservations_in_scope': [r['reservation_id'] for r in open_]}
    return Handler(frozenset({'selection_sha'}), run)


WAIVER_KEYS = ('milestone', 'dimensions', 'reason', 'scope', 'approver_declared_id',
               'expires_on', 'unmet_requirements')


def _waive(ctx) -> Handler:
    def run(state, params):
        doc_policy = sv.require_mode(ctx.store, state, allowed=('required',))
        ext = model.require_writable(state)
        doc = sv.blob_json(ctx.store, params['waiver_sha'], 'waiver')
        if not isinstance(doc, Mapping) or set(doc) != set(WAIVER_KEYS):
            raise refuse('evidence_invalid', 'A waiver has the keys ' + ', '.join(WAIVER_KEYS)
                         + '.', 'Correct the waiver.')
        if doc['milestone'] not in doc_policy['milestones']:
            raise refuse('policy_invalid', 'The policy names no such milestone.',
                         'Waive a milestone of the policy.')
        dims = model.str_list(doc['dimensions'], 'dimensions')
        if any(d not in DIMENSIONS for d in dims):
            raise refuse('evidence_invalid', 'dimensions lists dimension ids.', 'Correct it.')
        if not isinstance(doc['expires_on'], str) or not pol.DATE.fullmatch(doc['expires_on']):
            raise refuse('evidence_invalid', 'expires_on is a date YYYY-MM-DD.', 'Set a date.')
        wid = model.new_id('uw', ctx.request_id)
        ext['waivers'][wid] = {
            'waiver_id': wid, 'milestone': doc['milestone'], 'dimensions': dims,
            'reason': model.text(doc['reason'], 'reason', limit=2000),
            'scope': model.text(doc['scope'], 'scope', limit=1000),
            'approver_declared_id': model.actor(doc['approver_declared_id'],
                                                'approver_declared_id'),
            'expires_on': doc['expires_on'],
            'unmet_requirements': model.str_list(doc['unmet_requirements'],
                                                 'unmet_requirements'),
            'policy_digest': pol.digest(doc_policy), 'status': 'waived',
            'recorded_revision': _rev(state)}
        return {'waiver_id': wid, 'status': 'waived',
                'accepted_by_policy': doc_policy['exemptions_policy']['waivers_allowed']}
    return Handler(frozenset({'waiver_sha'}), run)


# --- handover and transfer ----------------------------------------------------------------

HANDOVER_KEYS = ('purpose', 'decisions_with_reasons', 'result_interpretation', 'limits',
                 'source_refs', 'environment_and_reproduction', 'change_locations',
                 'safety_rules', 'next_actions')


def handover_content(doc) -> dict:
    if not isinstance(doc, Mapping) or set(doc) != set(HANDOVER_KEYS):
        raise refuse('evidence_invalid', 'HandoverContent has the keys '
                     + ', '.join(HANDOVER_KEYS) + '.', 'Correct the handover content.')
    for k in ('purpose', 'result_interpretation', 'environment_and_reproduction'):
        model.text(doc[k], k, limit=4000)
    for k in ('decisions_with_reasons', 'limits', 'source_refs', 'change_locations',
              'safety_rules', 'next_actions'):
        model.str_list(doc[k], k)
    return dict(doc)


def _handover(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        _need_status(s, 'active', 'awaiting_review')
        doc = handover_content(sv.blob_json(ctx.store, params['content_sha'], 'handover'))
        _check_refs(doc['source_refs'], _allowed_refs(ctx.store, s), 'source_refs')
        hid = model.new_id('uh', ctx.request_id)
        previous = ev.current_handover_digest(ext, s['session_id'])
        ext['handovers'][hid] = {'handover_id': hid, 'session_id': s['session_id'],
                                 'blob': params['content_sha'], 'digest': canonical.digest(doc),
                                 'author_declared_id': s['actor_declared_id'],
                                 'recorded_revision': _rev(state)}
        stale = [t['transfer_id'] for t in ext['transfers'].values()
                 if t['author_declared_id'] == s['actor_declared_id']
                 and t['input_note_digest'] != canonical.digest(doc)]
        return {'handover_id': hid, 'digest': canonical.digest(doc),
                'previous_digest': previous, 'transfers_now_stale': sorted(stale)}
    return Handler(frozenset({'session_id', 'content_sha'}), run)


def _transfer_start(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        _need_status(s, 'active', 'awaiting_review')
        peer = model.actor(params['peer_declared_id'], 'peer_declared_id')
        if peer == s['actor_declared_id']:
            raise refuse('evidence_invalid', 'The peer and the author have the same declared id; '
                         'a two-person coverage needs two distinct declared people (a '
                         'distinction that does not authenticate either of them).',
                         'Name another colleague as peer.')
        task = bk.task(_session_taskset(ctx.store, s), params['task_id'])
        if task is None or task['kind'] != 'transfer':
            raise refuse('evidence_invalid', 'A handover task is a taskset task of kind transfer.',
                         'Pick a transfer task.')
        note = ev.current_handover_digest(ext, s['session_id'])
        if note is None:
            raise refuse('prerequisite_missing', 'There is no handover content to take over.',
                         'Record it with `understanding handover set` first.')
        tid = model.new_id('ut', ctx.request_id)
        ext['transfers'][tid] = {
            'transfer_id': tid, 'session_id': s['session_id'], 'peer_declared_id': peer,
            'author_declared_id': s['actor_declared_id'], 'task_ref': bk.public_task(task),
            'dimension_ids': list(task['dimension_ids']), 'input_note_digest': note,
            'snapshot_digest': s['local_snapshot_digest'], 'status': 'started',
            'performed_at': None, 'response_ref': None, 'evidence_refs': [],
            'difficulty_or_blockers': [], 'assistance': None, 'human_review_ref': None,
            'recorded_revision': _rev(state)}
        return {'transfer_id': tid, 'input_note_digest': note}
    return Handler(frozenset({'session_id', 'peer_declared_id', 'task_id'}), run)


def _transfer_submit(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        t = ext['transfers'].get(params['transfer_id'])
        if t is None or t['status'] != 'started':
            raise refuse('invalid_transition', 'The handover task is unknown or already '
                         'answered.', 'Start a new handover task.')
        s = _session(ext, t['session_id'])
        _need_status(s, 'active', 'awaiting_review')
        if not sv.blob_ok(ctx.store, params['response_sha']):
            raise refuse('evidence_invalid', 'The answer was not stored.', 'Submit again.')
        doc = sv.blob_json(ctx.store, params['evidence_sha'], 'evidence')
        if not isinstance(doc, Mapping) or set(doc) != {'evidence_refs',
                                                        'difficulty_or_blockers'}:
            raise refuse('evidence_invalid', 'The evidence file has evidence_refs and '
                         'difficulty_or_blockers.', 'Correct it.')
        refs = _check_refs(doc['evidence_refs'], _allowed_refs(ctx.store, s), 'evidence_refs')
        if not refs:
            raise refuse('evidence_invalid', 'The peer cites their own references; reading or '
                         'approving the note is not a handover.',
                         'Find the elements in the repository and cite them.')
        assistance = _assistance(ctx.store, params['assistance_sha'])
        t.update(status='answered', performed_at=sv.now(), response_ref=params['response_sha'],
                 response_bytes=params['response_bytes'], evidence_refs=refs,
                 difficulty_or_blockers=model.str_list(doc['difficulty_or_blockers'],
                                                       'difficulty_or_blockers'),
                 assistance=assistance, answered_revision=_rev(state))
        return {'transfer_id': t['transfer_id'], 'status': 'answered'}
    return Handler(frozenset({'transfer_id', 'response_sha', 'response_bytes', 'assistance_sha',
                              'evidence_sha'}), run)


TRANSFER_REVIEW_KEYS = ('reviewer_declared_id', 'declaration', 'simulated', 'dimension_ids',
                        'status', 'rationale')
TRANSFER_STATUSES = ('demonstrated', 'to_consolidate', 'needs_review', 'not_reproducible')


def _transfer_review(ctx) -> Handler:
    def run(state, params):
        doc_policy = sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        t = ext['transfers'].get(params['transfer_id'])
        if t is None or t['status'] != 'answered':
            raise refuse('invalid_transition', 'A handover task is reviewed once answered.',
                         'Wait for the peer\'s answer.')
        _need_status(_session(ext, t['session_id']), 'active', 'awaiting_review')
        doc = sv.blob_json(ctx.store, params['review_sha'], 'transfer review')
        if isinstance(doc, Mapping) and 'resolves_reservation_ids' not in doc:
            doc = {**doc, 'resolves_reservation_ids': []}
        if not isinstance(doc, Mapping) or set(doc) != set(TRANSFER_REVIEW_KEYS) | {
                'resolves_reservation_ids'}:
            raise refuse('review_required', 'A handover review has the keys '
                         + ', '.join(TRANSFER_REVIEW_KEYS) + '.', 'Collect the human review.')
        reviewer = model.actor(doc['reviewer_declared_id'], 'reviewer_declared_id')
        declaration = _declaration(doc)
        if reviewer == t['peer_declared_id']:
            raise refuse('review_required', 'The peer does not review their own handover.',
                         'Ask the author or another person.')
        dims = model.str_list(doc['dimension_ids'], 'dimension_ids')
        if not dims or any(d not in t['dimension_ids'] for d in dims):
            raise refuse('evidence_invalid', 'The review covers dimensions of the task.',
                         'Correct dimension_ids.')
        if doc['status'] not in TRANSFER_STATUSES:
            raise refuse('evidence_invalid', 'status is ' + ', '.join(TRANSFER_STATUSES) + '.',
                         'Correct the status.')
        resolves = model.str_list(doc['resolves_reservation_ids'], 'resolves_reservation_ids')
        for rid in resolves:
            r = ext['reservations'].get(rid)
            if r is None or r['status'] != 'open' or r.get('origin') != 'transfer' \
                    or r['actor'] != t['author_declared_id'] or r['dimension_id'] not in dims \
                    or r.get('transfer_id') == t['transfer_id'] \
                    or doc['status'] != 'demonstrated':
                raise refuse('evidence_invalid', 'A handover reservation is resolved by a '
                             'demonstrated review of another, later handover task on the same '
                             'dimension.', 'Run a new handover task.')
        did = model.new_id('udt', ctx.request_id)
        s = _session(ext, t['session_id'])
        ext['decisions'][did] = {
            'kind': 'transfer', 'decision_id': did, 'transfer_id': t['transfer_id'],
            'session_id': t['session_id'], 'reviewer_declared_id': reviewer,
            'reviewed_actor_id': t['peer_declared_id'], 'dimension_ids': dims,
            'status': doc['status'], 'rationale': model.text(doc['rationale'], 'rationale'),
            'input_note_digest': t['input_note_digest'], 'policy_digest': pol.digest(doc_policy),
            'snapshot_digest': s['local_snapshot_digest'], 'declaration': declaration,
            'simulated': doc['simulated'], 'assurance': pol.SUPPORTED_ASSURANCE,
            'recorded_revision': _rev(state), 'reviewed_at': sv.now()}
        t.update(human_review_ref=did, status='reviewed')
        for rid in resolves:
            ext['reservations'][rid].update(status='resolved', resolved_by=did,
                                            resolved_revision=_rev(state))
        opened = []
        if doc['status'] != 'demonstrated':
            # A handover that did not succeed is a reservation on the author's dimension: a
            # later positive handover never hides it (spec §09-§10).
            for i, dim in enumerate(dims):
                rid = model.new_id('urt', ctx.request_id, str(i))
                ext['reservations'][rid] = {
                    'reservation_id': rid, 'decision_id': did, 'actor': t['author_declared_id'],
                    'dimension_id': dim, 'kind': 'needs_review' if doc['status'] ==
                    'needs_review' else 'to_consolidate', 'attempt_ids': [],
                    'criteria': [], 'status': 'open', 'opened_revision': _rev(state),
                    'resolved_by': None, 'origin': 'transfer', 'transfer_id': t['transfer_id']}
                opened.append(rid)
        return {'decision_id': did, 'status': doc['status'], 'reservations': opened}
    return Handler(frozenset({'transfer_id', 'review_sha'}), run)


# --- export approvals and publication -----------------------------------------------------

def _approve(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        who = model.actor(params['contributor'], 'contributor')
        from . import export as ex
        projection = ex.projection(ctx.store, state, s)
        digest = canonical.digest(projection)
        if params['content_digest'] != digest:
            raise refuse('privacy_approval_required', 'The content changed since it was shown; '
                         'an approval covers exactly the projection reviewed.',
                         'Run export preview again and approve its digest.',
                         current_digest=digest)
        if who not in ex.required_contributors(projection) and who != s['actor_declared_id']:
            raise refuse('privacy_approval_required', 'This person contributes nothing to the '
                         'exported content.', 'Approvals come from the contributors listed '
                         'by export preview.')
        aid = model.new_id('uap', ctx.request_id)
        ext['approvals'][aid] = {'approval_id': aid, 'session_id': s['session_id'],
                                 'approver_declared_id': who, 'content_digest': digest,
                                 'approved_at': sv.now(), 'recorded_revision': _rev(state)}
        return {'approval_id': aid, 'content_digest': digest}
    return Handler(frozenset({'session_id', 'contributor', 'content_digest'}), run)


def _export_intent(ctx) -> Handler:
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        from . import export as ex
        projection = ex.projection(ctx.store, state, s)
        digest = canonical.digest(projection)
        if digest != params['projection_digest']:
            raise refuse('export_stale', 'The exportable content changed since it was '
                         'prepared.', 'Preview, approve and write again.')
        missing = ex.missing_approvals(ext, s, projection)
        if missing:
            raise refuse('privacy_approval_required', 'Every contributor approves the exact '
                         'content before export.', 'Collect the missing approvals.',
                         missing=missing)
        rid = params['review_id']
        for intent in ext['exports'].values():
            if intent['review_id'] == rid:
                if intent['files'] != params['files']:
                    raise refuse('export_stale', 'This review id already holds other content; '
                                 'a generation is never replaced.', 'Export a new generation.')
                # Same generation again (a retry after an unknown outcome): the existing
                # intent is reused, no second one is reserved.
                return {'intent_id': intent['intent_id'], 'review_id': rid, 'reused': True}
        iid = model.new_id('ux', ctx.request_id)
        ext['exports'][iid] = {
            'intent_id': iid, 'session_id': s['session_id'], 'review_id': rid,
            'projection_digest': digest, 'destination': params['destination'],
            'files': dict(params['files']), 'status': 'reserved',
            'snapshot_digest': s['local_snapshot_digest'],
            'source_scope_digest': s['source_scope_digest'],
            'policy_digest': s['policy_digest'], 'recorded_revision': _rev(state),
            'created_at': params['created_at'], 'base_commit': params['base_commit'],
            'receipt': None}
        return {'intent_id': iid, 'review_id': rid}
    return Handler(frozenset({'session_id', 'review_id', 'projection_digest', 'destination',
                              'files', 'created_at', 'base_commit'}), run)


def _export_receipt(ctx) -> Handler:
    def run(state, params):
        ext = model.require_writable(state)
        intent = ext['exports'].get(params['intent_id'])
        if intent is None:
            raise refuse('invalid_transition', 'Unknown export intent.', 'Check the id.')
        if intent['status'] != 'reserved':
            return {'intent_id': intent['intent_id'], 'status': intent['status'],
                    'final': True}
        if dict(params['verified_files']) != intent['files']:
            raise refuse('export_stale', 'The published files are not the bytes the intent '
                         'announced.', 'Inspect docs/understanding before any new attempt.')
        # Revalidated here, under the writer lock: a new policy or context means the
        # generation exists as history but is not declared current.
        from . import export as ex
        s = _session(ext, intent['session_id'])
        current = canonical.digest(ex.projection(ctx.store, state, s))
        doc_policy = sv.policy_doc(ctx.store, ext)
        same_policy = doc_policy is not None and pol.digest(doc_policy) == intent['policy_digest']
        outcome = 'published' if current == intent['projection_digest'] and same_policy \
            else 'not_current'
        intent['status'] = outcome
        intent['receipt'] = {'verified_files': dict(params['verified_files']),
                             'recorded_revision': _rev(state), 'recorded_at': sv.now()}
        return {'intent_id': intent['intent_id'], 'status': outcome}
    return Handler(frozenset({'intent_id', 'verified_files'}), run)


def _git_receipt(ctx) -> Handler:
    def run(state, params):
        ext = model.require_writable(state)
        rid = model.new_id('ug', ctx.request_id)
        ext['receipts'][rid] = {'receipt_id': rid, 'review_id': params['review_id'],
                                'commit': params['commit'], 'tree': params['tree'],
                                'paths': dict(params['paths']),
                                'recorded_revision': _rev(state)}
        return {'receipt_id': rid}
    return Handler(frozenset({'review_id', 'commit', 'tree', 'paths'}), run)


# --- milestone protocol (export handoff in required mode) ---------------------------------

def _milestone_reserve(ctx) -> Handler:
    def run(state, params):
        ext = model.require_writable(state)
        # The gate is computed again here, on the state reread under the writer lock: an
        # earlier ``check`` is never an authorisation.
        result = sv.gate(ctx.store, state, params['milestone'])
        if result['decision'] not in ('allowed', 'allowed_by_waiver'):
            raise refuse('milestone_blocked', 'The understanding review does not allow this '
                         'milestone now.', 'Run `hypotrail understanding check --milestone '
                         f'{params["milestone"]}` to see the reasons.',
                         reasons=result['reasons'][:20])
        mid = model.new_id('um', ctx.request_id)
        ext['milestones'][mid] = {
            'reservation_id': mid, 'milestone': params['milestone'],
            'decision': result['decision'], 'policy_digest': result['policy_digest'],
            'scope_digest': result['scope_digest'],
            'checked_context_digest': result['checked_context_digest'],
            'waiver_ref': result['waiver_ref'], 'status': 'reserved',
            'reserved_revision': _rev(state), 'outcome': None}
        return {'reservation_id': mid, 'decision': result['decision'],
                'checked_context_digest': result['checked_context_digest']}
    return Handler(frozenset({'milestone'}), run)


def _milestone_record(ctx) -> Handler:
    def run(state, params):
        ext = model.require_writable(state)
        m = ext['milestones'].get(params['reservation_id'])
        if m is None or m['status'] != 'reserved':
            raise refuse('invalid_transition', 'Unknown or finished milestone reservation.',
                         'Run the protected action again.')
        if params['outcome'] not in ('published', 'candidate_not_current'):
            raise refuse('invalid_transition', 'outcome is published or candidate_not_current.',
                         'Correct the outcome.')
        m.update(status=params['outcome'], outcome={'files': dict(params['files']),
                                                    'revision': _rev(state)})
        return {'reservation_id': m['reservation_id'], 'status': m['status']}
    return Handler(frozenset({'reservation_id', 'outcome', 'files'}), run)


def _relocate(ctx) -> Handler:
    """The repository of a session moved: record its new local path (the source digests
    are relative and unchanged; freshness is then read from the new place)."""
    def run(state, params):
        sv.require_mode(ctx.store, state)
        ext = model.require_writable(state)
        s = _session(ext, params['session_id'])
        repo = params['repo']
        if not isinstance(repo, str) or not repo.startswith('/') or len(repo) > 4000:
            raise refuse('path_outside_scope', 'repo is an absolute path.', 'Give --repo.')
        s['repo_override'] = repo
        return {'session_id': s['session_id'], 'repo_recorded': True}
    return Handler(frozenset({'session_id', 'repo'}), run)


FACTORIES = {
    'policy_set': _policy_set, 'start': _start, 'close': _close, 'submit': _submit,
    'coach': _coach, 'rectify': _rectify, 'propose': _propose, 'review': _review,
    'arbitrate': _arbitrate, 'select': _select, 'waive': _waive, 'handover': _handover,
    'transfer_start': _transfer_start, 'transfer_submit': _transfer_submit,
    'transfer_review': _transfer_review, 'approve': _approve,
    'export_intent': _export_intent, 'export_receipt': _export_receipt,
    'git_receipt': _git_receipt, 'milestone_reserve': _milestone_reserve,
    'relocate': _relocate,
    'milestone_record': _milestone_record}


def _guarded(factory):
    """A malformed input document (a wrong type deep inside a file) is a refusal without
    effect, never an internal error; the input itself is not echoed."""
    def make(ctx):
        handler = factory(ctx)

        def run(state, params):
            try:
                return handler.run(state, params)
            except (TypeError, KeyError, AttributeError, IndexError) as exc:
                raise refuse('evidence_invalid', 'An input document has a field of the wrong '
                             f'shape ({exc.__class__.__name__}).',
                             'Correct the file against the documented format.') from None
        return Handler(handler.params, run, handler.check)
    return make


def register() -> None:
    global REGISTERED
    if REGISTERED:
        return
    for name, factory in FACTORIES.items():
        if P + name not in cmd.ACTIONS:
            cmd.register_action(P + name, _guarded(factory))
    REGISTERED = True


def apply(study_dir, action: str, params: dict, *, request_id: str,
          expected_revision: int) -> dict:
    """Apply one understanding action; the receipt (``{result, revision, replayed}``)."""
    register()
    store = sv.open_store(study_dir)
    request = {'request_id': request_id, 'expected_revision': expected_revision,
               'action': P + action, 'params': params}
    return store.execute(request, cmd.handlers(cmd.Context(store, request_id)))
