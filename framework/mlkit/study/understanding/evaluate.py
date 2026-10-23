"""Dimension states, conflicts, reservations, peer coverage and the milestone gate (§09–§11).

Pure computations over the ``understanding`` extension and loaders given by the caller
(blobs, the taskset, current context captures). Nothing here writes.

Axes are kept apart: a dimension has a **status** (``not_evaluated``, ``demonstrated``,
``to_consolidate``, ``needs_review``), a **freshness** (``current``, ``stale``,
``unknown``), an **assistance** summary, an **evidence availability** (``available``,
``unavailable``, ``redacted``) and an **assurance** (``human_declared``). No status is an
average; a demonstrated but stale result stays visible as history and satisfies no
current milestone.

Ordering is ``recorded_revision``, never a declared clock. Two current human decisions on
the same actor, dimension and evidence with different statuses are a **conflict** until an
arbitration settles it: the latest one does not win. A ``to_consolidate`` or
``needs_review`` decision opens a **reservation** that stays open until an explicit
resolution (a later decision naming it, with new admissible evidence on a new variant, or
an arbitration); a later positive decision that does not name it never hides it.
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable, Iterable, Mapping

from . import DIMENSIONS, canonical, policy as pol, snapshot as snap

GATE_SCHEMA = 'hypotrail.understanding-gate/1'
DECISIONS = ('not_applicable', 'allowed', 'blocked', 'allowed_by_waiver')


def _active_decisions(ext: Mapping) -> list[dict]:
    """Human review decisions on attempts (not transfer reviews), oldest first."""
    return sorted((d for d in ext['decisions'].values() if d['kind'] == 'attempt'),
                  key=lambda d: d['recorded_revision'])


def superseded_ids(ext: Mapping) -> set:
    out = set()
    for d in ext['decisions'].values():
        out.update(d.get('supersedes_ids') or [])
    return out


def arbitrated_ids(ext: Mapping) -> dict:
    """``{decision_id: arbitration}`` for every decision an arbitration settled."""
    out = {}
    for a in sorted(ext['arbitrations'].values(), key=lambda a: a['recorded_revision']):
        for did in a['conflicting_decision_ids']:
            out[did] = a
    return out


def conflicts(ext: Mapping) -> list[dict]:
    """Unsettled conflicts: current decisions on the same actor and dimension that share an
    attempt and disagree on the status."""
    gone = superseded_ids(ext)
    settled = arbitrated_ids(ext)
    current = [d for d in _active_decisions(ext) if d['decision_id'] not in gone]
    out = []
    for i, a in enumerate(current):
        for b in current[i + 1:]:
            if (a['reviewed_actor_id'], a['dimension_id']) != (b['reviewed_actor_id'],
                                                                b['dimension_id']):
                continue
            if not set(a['attempt_ids']) & set(b['attempt_ids']) or a['status'] == b['status']:
                continue
            if a['decision_id'] in settled and b['decision_id'] in settled:
                continue
            out.append({'actor': a['reviewed_actor_id'], 'dimension_id': a['dimension_id'],
                        'decision_ids': [a['decision_id'], b['decision_id']]})
    return out


def open_reservations(ext: Mapping, actor: str | None = None,
                      dimension: str | None = None) -> list[dict]:
    return [r for r in sorted(ext['reservations'].values(),
                              key=lambda r: r['opened_revision'])
            if r['status'] == 'open' and (actor is None or r['actor'] == actor)
            and (dimension is None or r['dimension_id'] == dimension)]


def effective_decision(ext: Mapping, actor: str, dimension: str) -> dict | None:
    """The decision that currently speaks for ``actor`` on ``dimension`` in the history:
    the arbitration's choice when one settled it, else the latest non-superseded one by
    recorded revision (shown as history; a gate never uses it without a selection)."""
    gone = superseded_ids(ext)
    settled = arbitrated_ids(ext)
    pool = [d for d in _active_decisions(ext) if d['reviewed_actor_id'] == actor
            and d['dimension_id'] == dimension and d['decision_id'] not in gone]
    for d in reversed(pool):
        a = settled.get(d['decision_id'])
        if a is not None:
            chosen = ext['decisions'].get(a['chosen_decision_id'])
            if chosen is not None:
                return chosen
    return pool[-1] if pool else None


def attempt_assistance(ext: Mapping, attempt_id: str) -> dict:
    """The assistance of an attempt as known now: its declaration at submission plus
    coaching and later rectifications (an aid found later re-opens dependent reviews)."""
    a = ext['attempts'][attempt_id]
    out = dict(a['assistance'])
    for ev in ext['assistance_events']:
        if ev['attempt_id'] == attempt_id and ev['kind'] == 'rectification':
            out['ai_assistance_declared'] = out['ai_assistance_declared'] or \
                ev['ai_assistance_declared']
            out['resources_used'] = sorted(set(out['resources_used']) | set(ev['resources_used']))
            out['rectified'] = True
    out['aided'] = bool(out['ai_assistance_declared'] or out['hints_seen'] or
                        out['coaching_seen'])
    return out


def dimension_view(ext: Mapping, actor: str, dimension: str) -> dict:
    """Status of ``actor`` on ``dimension`` from the history (not a gate)."""
    d = effective_decision(ext, actor, dimension)
    reservations = open_reservations(ext, actor, dimension)
    disputed = [c for c in conflicts(ext) if c['actor'] == actor
                and c['dimension_id'] == dimension]
    pending = [p for p in ext['proposals'].values()
               if p['reviewed_actor_id'] == actor and dimension in p['dimension_ids']
               and not any(set(x['attempt_ids']) & {p['attempt_id']}
                           for x in ext['decisions'].values() if x['kind'] == 'attempt')]
    rectified = d is not None and any(
        attempt_assistance(ext, a)['aided'] != aided
        for a, aided in (d.get('assistance_at_review') or {}).items() if a in ext['attempts'])
    if disputed or rectified:
        status = 'needs_review'
    elif reservations:
        status = 'to_consolidate' if any(r['kind'] == 'to_consolidate' for r in reservations) \
            else 'needs_review'
    elif d is not None:
        status = d['status']
    elif pending:
        status = 'needs_review'
    else:
        status = 'not_evaluated'
    return {'dimension_id': dimension, 'status': status,
            'decision_id': d['decision_id'] if d else None,
            'open_reservations': [r['reservation_id'] for r in reservations],
            'conflicts': disputed, 'pending_proposals': len(pending)}


def evidence_availability(ext: Mapping, attempt_ids: Iterable[str],
                          blob_ok: Callable[[str], bool]) -> str:
    state = 'available'
    for aid in attempt_ids:
        a = ext['attempts'].get(aid)
        if a is None or not blob_ok(a['response_sha256']):
            state = 'unavailable'
    return state


def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def gate(ext: Mapping, *, milestone: str, policy_doc: Mapping | None, policy_source: str,
         taskset_for: Callable[[Mapping], Mapping | None],
         captured_for: Callable[[Mapping], Mapping],
         current_for: Callable[[Mapping], Mapping],
         blob_ok: Callable[[str], bool], checked_at: str, today: str | None = None) -> dict:
    """The ``GateResult`` of ``milestone`` (SPEC §10). ``captured_for(session)`` is the
    local projection frozen when the session started; ``current_for(session)`` captures the
    current one with the same source mapping; ``taskset_for(session)`` loads the session's
    taskset as it is on disk now (``None`` when absent)."""
    reasons: list[dict] = []
    limitations = set()
    result = {'schema': GATE_SCHEMA, 'milestone': milestone, 'policy_digest': None,
              'policy_source': policy_source, 'scope_digest': None,
              'checked_context_digest': None, 'checked_at': checked_at,
              'decision': 'not_applicable', 'reasons': reasons, 'missing_dimensions': [],
              'stale_dimensions': [], 'missing_peer_dimensions': [],
              'assurance': pol.SUPPORTED_ASSURANCE, 'waiver_ref': None, 'limitations': [],
              'dimensions': {}}
    if not policy_doc or policy_doc['mode'] != 'required' \
            or milestone not in policy_doc['milestones']:
        reasons.append({'code': 'no_required_check',
                        'detail': 'off or coaching mode, or a milestone the policy does not '
                                  'name: no understanding check applies; this is not a pass'})
        result['limitations'] = sorted(pol.limitations(policy_doc or {}))
        if policy_doc:
            result['policy_digest'] = pol.digest(policy_doc)
        return result
    pdigest = pol.digest(policy_doc)
    result['policy_digest'] = pdigest
    limitations.update(pol.limitations(policy_doc))
    selection = latest_selection(ext, milestone)
    if selection is None:
        reasons.append({'code': 'no_selection', 'detail': 'no coverage selection for this '
                        'milestone; the engine never searches for an old pass'})
        return _finish(result, reasons, limitations, policy_doc, ext, milestone, today)
    result['scope_digest'] = selection['scope_digest']
    if selection['policy_digest'] != pdigest:
        reasons.append({'code': 'selection_policy_changed',
                        'detail': 'the selection was made under another policy'})
    actor = selection['actor_scope']['actor_declared_id']
    profile = selection['actor_scope']['profile']
    try:
        required = pol.author_dimensions(policy_doc, profile)
    except Exception:           # noqa: BLE001 - the profile left the policy
        reasons.append({'code': 'profile_unknown', 'detail': profile})
        return _finish(result, reasons, limitations, policy_doc, ext, milestone, today)
    critical = set(policy_doc['critical_dimensions'])
    contexts = {}
    context_digests = set()
    expired = policy_doc['expiration_rule']['kind'] == 'until' and \
        (today or _today()) > policy_doc['expiration_rule']['date']
    for dim in required:
        info = {'status': 'not_evaluated', 'freshness': 'unknown', 'assistance': None,
                'evidence_availability': None, 'decision_id': None, 'session_id': None}
        result['dimensions'][dim] = info
        did = selection['dimension_decision_map'].get(dim)
        reservations = open_reservations(ext, actor, dim)
        for r in reservations:
            reasons.append({'code': 'open_reservation', 'dimension': dim,
                            'detail': r['reservation_id']})
        for c in conflicts(ext):
            if c['actor'] == actor and c['dimension_id'] == dim:
                reasons.append({'code': 'unarbitrated_conflict', 'dimension': dim,
                                'detail': ','.join(c['decision_ids'])})
        if did is None or did not in ext['decisions']:
            result['missing_dimensions'].append(dim)
            reasons.append({'code': 'dimension_not_selected', 'dimension': dim})
            continue
        d = ext['decisions'][did]
        info.update(decision_id=did, status=d['status'], session_id=d['session_id'])
        session = ext['sessions'].get(d['session_id'])
        problems = _decision_problems(ext, d, session, actor, dim, pdigest, taskset_for)
        lost = arbitrated_ids(ext).get(did)
        if lost is not None and lost['chosen_decision_id'] != did:
            problems.append('lost_arbitration')
        if d.get('assistance_at_review') and any(
                attempt_assistance(ext, a)['aided'] != aided
                for a, aided in d['assistance_at_review'].items() if a in ext['attempts']):
            problems.append('assistance_rectified_after_review')
        for p in problems:
            reasons.append({'code': p, 'dimension': dim})
        if d['status'] != 'demonstrated' or problems:
            result['missing_dimensions'].append(dim)
        if d.get('simulated'):
            limitations.add('simulated_human_decisions')
        if dim in critical and d['reviewer_declared_id'] == actor:
            reasons.append({'code': 'reviewer_not_distinct', 'dimension': dim})
        assist = [attempt_assistance(ext, a) for a in d['attempt_ids'] if a in ext['attempts']]
        unaided = any(not a['aided'] for a in assist)
        rule = policy_doc['assistance_rule']['critical' if dim in critical else 'other']
        info['assistance'] = 'unaided' if unaided else 'aided'
        if rule == 'unaided_required' and not unaided:
            reasons.append({'code': 'assistance_not_admissible', 'dimension': dim})
        avail = evidence_availability(ext, d['attempt_ids'], blob_ok)
        info['evidence_availability'] = avail
        if avail != 'available':
            if policy_doc['evidence_requirement'] == 'payloads_available':
                reasons.append({'code': 'evidence_unavailable', 'dimension': dim})
            else:
                limitations.add('evidence_not_reauditable')
        if session is None:
            continue
        cur = contexts.get(session['session_id'])
        if cur is None:
            cur = contexts[session['session_id']] = current_for(session)
            context_digests.add(canonical.digest(cur))
        fresh = snap.freshness(captured_for(session), cur,
                               decision_dependency_keys(ext, d, taskset_for(session)))
        if expired:
            fresh = {'status': 'stale', 'changed': ['expiration_rule'], 'unknown': []}
        info['freshness'] = fresh['status']
        if fresh['status'] == 'stale':
            result['stale_dimensions'].append(dim)
            reasons.append({'code': 'stale', 'dimension': dim,
                            'detail': ','.join(fresh['changed'])})
        elif fresh['status'] == 'unknown':
            private = all(_private_key(k) for k in fresh['unknown'])
            if policy_doc['context_requirement'] == 'public_only' and private:
                limitations.add('private_context_unknown')
            else:
                reasons.append({'code': 'freshness_unknown', 'dimension': dim,
                                'detail': ','.join(fresh['unknown'])})
    for dim in policy_doc['peer_required_dimensions']:
        if dim not in required:
            continue
        cover = selected_peer_coverage(ext, actor, dim, selection, pdigest, taskset_for,
                                       captured_for, current_for)
        result['dimensions'].setdefault(dim, {})['peer'] = cover
        if cover['people'] < policy_doc['team_coverage']['minimum_people'] \
                or cover['status'] != 'current':
            result['missing_peer_dimensions'].append(dim)
            reasons.append({'code': 'peer_coverage_missing', 'dimension': dim,
                            'detail': cover['status']})
        if cover.get('simulated'):
            limitations.add('simulated_human_decisions')
    result['checked_context_digest'] = canonical.digest(sorted(context_digests))
    return _finish(result, reasons, limitations, policy_doc, ext, milestone, today)


def selected_peer_coverage(ext, author, dim, selection, pdigest, taskset_for, captured_for,
                           current_for) -> dict:
    """Peer coverage from the transfer reviews the selection names, never a search for an
    old pass: each is ``demonstrated``, by a reviewer other than the peer, on a peer other than
    the author, in a completed session, under the current policy, on the current handover
    content, and its context is still fresh for the dimension."""
    chosen = (selection or {}).get('transfer_decision_map', {}).get(dim)
    ids = [chosen] if isinstance(chosen, str) else list(chosen or [])
    peers, problems, simulated = set(), [], False
    for did in ids:
        d = ext['decisions'].get(did)
        t = ext['transfers'].get(d['transfer_id']) if d and d['kind'] == 'transfer' else None
        session = ext['sessions'].get(t['session_id']) if t else None
        if d is None or t is None or session is None or d['status'] != 'demonstrated' \
                or dim not in d['dimension_ids']:
            problems.append('not_demonstrated')
            continue
        if t['author_declared_id'] != author or t['peer_declared_id'] == author \
                or d['reviewer_declared_id'] == t['peer_declared_id']:
            problems.append('people_not_distinct')
            continue
        if session['status'] != 'completed':
            problems.append('session_not_completed')
            continue
        if d['policy_digest'] != pdigest:
            problems.append('policy_changed')
            continue
        if t['input_note_digest'] != current_handover_digest(ext, t['session_id']):
            problems.append('stale')
            continue
        taskset = taskset_for(session)
        keys = set()
        if taskset is not None:
            from . import taskset as bk
            task = bk.task(taskset, t['task_ref']['task_id'])
            r = bk.rubric_for(taskset, dim)
            keys.update(task['dependency_keys'] if task else [])
            keys.update(r['dependency_keys'] if r else [])
        fresh = snap.freshness(captured_for(session), current_for(session), keys)
        if fresh['status'] != 'current':
            problems.append(fresh['status'])
            continue
        peers.add(t['peer_declared_id'])
        simulated = simulated or bool(d.get('simulated'))
    status = 'current' if peers and not problems else (problems[0] if problems else 'missing')
    return {'people': 1 + len(peers), 'peers': sorted(peers), 'status': status,
            'problems': problems, 'simulated': simulated}


def _last_rectification(ext: Mapping, attempt_ids) -> int:
    revs = [ev['revision'] for ev in ext['assistance_events']
            if ev['attempt_id'] in attempt_ids and ev['kind'] == 'rectification']
    return max(revs or [0])


def _private_key(key: str) -> bool:
    return key.startswith(('study:', 'case:', 'data:', 'engine:'))


def _decision_problems(ext, d, session, actor, dim, pdigest, taskset_for) -> list[str]:
    out = []
    if session is None:
        return ['session_missing']
    if session['status'] != 'completed':
        out.append('session_not_completed')
    if d['reviewed_actor_id'] != actor or session['actor_declared_id'] != actor:
        out.append('actor_mismatch')
    if d['policy_digest'] != pdigest:
        out.append('decision_policy_changed')
    taskset = taskset_for(session)
    if taskset is None:
        out.append('taskset_missing')
    else:
        from . import taskset as bk
        r = bk.rubric_for(taskset, dim)
        if r is None or canonical.digest(r) != d['rubric_digest']:
            out.append('rubric_changed')
        if not bk.qualified(taskset):
            out.append('taskset_not_qualified')
        if d['taskset_digest'] != bk.digest(taskset):
            out.append('taskset_changed')
    if d['decision_id'] in superseded_ids(ext):
        out.append('decision_superseded')
    return out


def decision_dependency_keys(ext: Mapping, d: Mapping, taskset: Mapping | None) -> list[str]:
    keys = set(d.get('dependency_keys') or [])
    if taskset is not None:
        from . import taskset as bk
        r = bk.rubric_for(taskset, d['dimension_id'])
        if r is not None:
            keys.update(r['dependency_keys'])
    return sorted(keys)


def peer_coverage(ext: Mapping, author: str, dim: str, selection: Mapping | None,
                  taskset_for) -> dict:
    """Distinct declared people who can carry ``dim``: the author and every peer whose
    transfer on the current handover content was reviewed ``demonstrated`` by a human
    distinct from the peer. A transfer done on an earlier handover version is ``stale``."""
    chosen = (selection or {}).get('transfer_decision_map', {}).get(dim) if selection else None
    reviews = [d for d in ext['decisions'].values() if d['kind'] == 'transfer'
               and dim in d['dimension_ids'] and d['status'] == 'demonstrated']
    if chosen is not None:
        reviews = [d for d in reviews if d['decision_id'] == chosen]
    peers, status, simulated = set(), 'missing', False
    for d in reviews:
        t = ext['transfers'].get(d['transfer_id'])
        if t is None or t['author_declared_id'] != author or t['peer_declared_id'] == author:
            continue
        current = current_handover_digest(ext, t['session_id'])
        if t['input_note_digest'] != current:
            status = 'stale' if status == 'missing' else status
            continue
        peers.add(t['peer_declared_id'])
        simulated = simulated or bool(d.get('simulated'))
        status = 'current'
    return {'people': 1 + len(peers), 'peers': sorted(peers), 'status': status,
            'simulated': simulated}


def current_handover(ext: Mapping, session_id: str) -> dict | None:
    versions = [h for h in ext['handovers'].values() if h['session_id'] == session_id]
    return max(versions, key=lambda h: h['recorded_revision']) if versions else None


def current_handover_digest(ext: Mapping, session_id: str) -> str | None:
    h = current_handover(ext, session_id)
    return h['digest'] if h else None


def latest_selection(ext: Mapping, milestone: str) -> dict | None:
    picks = [s for s in ext['selections'].values() if s['milestone'] == milestone]
    return max(picks, key=lambda s: s['recorded_revision']) if picks else None


def _finish(result, reasons, limitations, policy_doc, ext, milestone, today) -> dict:
    result['limitations'] = sorted(limitations)
    result['missing_dimensions'] = sorted(set(result['missing_dimensions']))
    result['stale_dimensions'] = sorted(set(result['stale_dimensions']))
    result['missing_peer_dimensions'] = sorted(set(result['missing_peer_dimensions']))
    blocking = [r for r in reasons if r['code'] != 'no_required_check']
    if not blocking:
        result['decision'] = 'allowed'
        return result
    waiver = _waiver(ext, milestone, policy_doc, today)
    if waiver is not None and policy_doc['exemptions_policy']['waivers_allowed'] and \
            all(r.get('dimension') in waiver['dimensions'] for r in blocking):
        result['decision'] = 'allowed_by_waiver'
        result['waiver_ref'] = waiver['waiver_id']
        result['limitations'] = sorted(limitations | {'waived_requirements'})
        return result
    result['decision'] = 'blocked'
    if waiver is not None:
        reasons.append({'code': 'waiver_not_accepted',
                        'detail': 'the policy does not accept waivers for this milestone'
                        if not policy_doc['exemptions_policy']['waivers_allowed']
                        else 'the waiver does not cover every blocking reason'})
    return result


def _waiver(ext, milestone, policy_doc, today) -> dict | None:
    today = today or _today()
    live = [w for w in ext['waivers'].values() if w['milestone'] == milestone
            and w['policy_digest'] == pol.digest(policy_doc) and w['expires_on'] >= today]
    return max(live, key=lambda w: w['recorded_revision']) if live else None


def dimension_summary(ext: Mapping, actor: str) -> list[dict]:
    return [dimension_view(ext, actor, d) for d in DIMENSIONS]
