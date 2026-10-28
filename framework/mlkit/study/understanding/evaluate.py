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

The history views (``conflicts``, ``open_reservations``, ``dimension_view`` without
``settles``) take every recorded arbitration and resolution at its word. The gate does not:
an arbitration it relies on, in any session, settles nothing unless it is admissible under
the policy the gate applies and the policy of its own session (``arbitration_checker``),
and a handover reservation resolved by a transfer the current assistance rule does not
admit stays open (review round 3, R3C-1 and R3C-4). Likewise an attempt reservation resolved
by a demonstrated decision whose assistance the stricter of the applied policy and that
decision's session policy does not admit stays open (review round 4, C4-1).

A selected decision's own problems (superseded, rubric or taskset changed, another policy,
a lost arbitration, help rectified after the review...) are computed by one function,
:func:`selected_decision_problems` (review round 4, C4-2). Since review round 5 the export
projection and the report take their whole judgement from :func:`gate` itself
(:func:`gaps_of`, :func:`judged_status`), and so does ``verify-export --study``: one
judgement, one gap list.
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


def conflicts(ext: Mapping, settles: Callable[[Mapping], bool] | None = None) -> list[dict]:
    """Unsettled conflicts: current decisions on the same actor and dimension that share an
    attempt and disagree on the status. ``settles(arbitration)`` (the gate's
    :func:`arbitration_checker`) says whether an arbitration still settles anything; without
    it every recorded arbitration does (the history)."""
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
            arbs = [settled.get(a['decision_id']), settled.get(b['decision_id'])]
            if all(x is not None and (settles is None or settles(x)) for x in arbs):
                continue
            out.append({'actor': a['reviewed_actor_id'], 'dimension_id': a['dimension_id'],
                        'decision_ids': [a['decision_id'], b['decision_id']]})
    return out


def reservation_state(ext: Mapping, r: Mapping,
                      settles: Callable[[Mapping], bool] | None = None,
                      policy_doc: Mapping | None = None,
                      session_policy_for: Callable[[Mapping], Mapping | None] | None = None
                      ) -> str | None:
    """``None`` when the reservation is closed; otherwise why it still counts: ``open``,
    ``arbitration_not_admissible`` (the arbitration that resolved it settles nothing under
    ``settles``), ``assistance_not_admissible`` (an attempt reservation resolved by a
    demonstrated decision whose assistance, as known now, the stricter of ``policy_doc`` and
    that decision's session policy does not admit, :func:`resolution_assistance_admissible`)
    or ``peer_assistance_not_admissible`` (a handover reservation resolved by a transfer whose
    peer declared AI assistance, or nothing, on a dimension ``policy_doc`` makes
    ``unaided_required``). Without ``settles`` and ``policy_doc``: the history."""
    if r['status'] == 'open':
        return 'open'
    by = r.get('resolved_by')
    a = ext['arbitrations'].get(by) if by else None
    if a is not None and settles is not None and not settles(a):
        return 'arbitration_not_admissible'
    d = ext['decisions'].get(by) if by else None
    if policy_doc is not None and d is not None and d['kind'] == 'attempt' \
            and r.get('origin') != 'transfer' \
            and not resolution_assistance_admissible(ext, d, policy_doc, session_policy_for):
        return 'assistance_not_admissible'
    if policy_doc is not None and d is not None and d['kind'] == 'transfer' \
            and r.get('origin') == 'transfer' \
            and peer_rule(policy_doc, r['dimension_id']) == 'unaided_required' \
            and not transfer_unaided(ext['transfers'].get(d['transfer_id']) or {}):
        return 'peer_assistance_not_admissible'
    return None


def resolution_assistance_admissible(ext: Mapping, d: Mapping, policy_doc: Mapping | None,
                                     session_policy_for: Callable[[Mapping], Mapping | None]
                                     | None = None) -> bool:
    """Whether the demonstrated decision ``d`` may resolve a reservation on its dimension as
    far as help goes (review round 4, C4-1): when ``policy_doc`` (the policy applied) or the
    policy ``d``'s session started under makes the dimension ``unaided_required`` (the
    stricter wins), every attempt ``d`` rests on is unaided as known now (a rectification
    counts). A session policy that cannot be read is taken as ``unaided_required``."""
    dim = d['dimension_id']
    strict = policy_doc is not None and peer_rule(policy_doc, dim) == 'unaided_required'
    if not strict and session_policy_for is not None:
        owner = ext['sessions'].get(d['session_id'])
        try:
            spol = session_policy_for(owner) if owner is not None else None
            strict = spol is None or peer_rule(spol, dim) == 'unaided_required'
        except Exception:           # noqa: BLE001 - an unreadable session policy: the strictest
            strict = True
    return not strict or assistance_summary(ext, d['attempt_ids']) == 'unaided'


def open_reservations(ext: Mapping, actor: str | None = None,
                      dimension: str | None = None, *,
                      settles: Callable[[Mapping], bool] | None = None,
                      policy_doc: Mapping | None = None,
                      session_policy_for: Callable[[Mapping], Mapping | None] | None = None
                      ) -> list[dict]:
    """The reservations that still count (:func:`reservation_state`), oldest first."""
    return [r for r in sorted(ext['reservations'].values(),
                              key=lambda r: r['opened_revision'])
            if (actor is None or r['actor'] == actor)
            and (dimension is None or r['dimension_id'] == dimension)
            and reservation_state(ext, r, settles, policy_doc, session_policy_for) is not None]


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


_HISTORY = object()


def shown_decision(ext: Mapping, selection: Mapping | None, actor: str, dimension: str,
                   session_id: str | None = None) -> dict | None:
    """The decision a session's export and the report show for ``actor`` on ``dimension``:
    with a selection for that person and profile, the decision it maps (the one the gate
    reads, in whatever session; ``None`` when it maps none); without one, the history's
    effective decision, restricted to ``session_id`` when given (review round 3, R3C-2)."""
    if selection is not None:
        did = selection['dimension_decision_map'].get(dimension)
        d = ext['decisions'].get(did) if did else None
        return d if d is not None and d['kind'] == 'attempt' else None
    d = effective_decision(ext, actor, dimension)
    if d is not None and session_id is not None and d['session_id'] != session_id:
        return None
    return d


def selection_for(ext: Mapping, milestone: str, actor: str, profile: str) -> dict | None:
    """The latest selection of ``milestone`` when it is about ``actor`` and ``profile``
    (the one the gate would read for them), else ``None``."""
    sel = latest_selection(ext, milestone)
    if sel is None or sel['actor_scope'] != {'actor_declared_id': actor, 'profile': profile}:
        return None
    return sel


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


def assistance_summary(ext: Mapping, attempt_ids) -> str:
    """``unaided`` only when every attempt a decision rests on is unaided: an unaided weak
    answer next to a coached one never makes the demonstration unaided (A04). ``none``
    without attempts."""
    assist = [attempt_assistance(ext, a) for a in attempt_ids if a in ext['attempts']]
    if not assist:
        return 'none'
    return 'unaided' if all(not a['aided'] for a in assist) else 'aided'


def dimension_view(ext: Mapping, actor: str, dimension: str, *, decision=_HISTORY,
                   settles: Callable[[Mapping], bool] | None = None,
                   policy_doc: Mapping | None = None,
                   session_policy_for: Callable[[Mapping], Mapping | None] | None = None
                   ) -> dict:
    """Status of ``actor`` on ``dimension`` (not a gate): from the history, or from
    ``decision`` (the selected one, :func:`shown_decision`) with the reservations and
    conflicts as the gate counts them under ``settles``, ``policy_doc`` and
    ``session_policy_for``."""
    d = effective_decision(ext, actor, dimension) if decision is _HISTORY else decision
    reservations = open_reservations(ext, actor, dimension, settles=settles,
                                     policy_doc=policy_doc,
                                     session_policy_for=session_policy_for)
    disputed = [c for c in conflicts(ext, settles) if c['actor'] == actor
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
         blob_ok: Callable[[str], bool], checked_at: str, today: str | None = None,
         session_policy_for: Callable[[Mapping], Mapping | None] | None = None,
         repository_for: Callable[[Mapping], Mapping] | None = None,
         actor_scope: Mapping | None = None, selection=None, assess: bool = False) -> dict:
    """The ``GateResult`` of ``milestone`` (SPEC §10). ``captured_for(session)`` is the
    local projection frozen when the session started; ``current_for(session)`` captures the
    current one with the same source mapping; ``taskset_for(session)`` loads the session's
    taskset as it is on disk now (``None`` when absent); ``session_policy_for(session)``
    loads the policy the session started under (arbitrations are re-checked against it and
    the current one); ``repository_for(session)`` says which repository the session's
    freshness is read from (reported in ``repositories``).

    The one judgement of the review (review round 5): ``check``, ``export handoff``, the
    export projection, the report section and ``verify-export --study`` all call it.
    ``actor_scope`` (``{actor_declared_id, profile}``) judges that person and profile only:
    the latest selection of the milestone counts when it is about them, else
    ``no_selection``. ``selection`` replaces the latest selection by an explicit one; a
    ``virtual`` one (the decisions an export without a selection shows) is judged by the
    same rules and adds ``no_selection``. ``assess`` computes every reason even when the
    policy does not require the milestone (coaching): the decision stays
    ``not_applicable`` and ``no_required_check`` comes first; the export and the report
    take their gaps from these reasons."""
    seen_repos: dict = {}
    read_current = current_for

    def current_for(session):         # noqa: F811 - the same loader, which also records
        if repository_for is not None and session['session_id'] not in seen_repos:
            seen_repos[session['session_id']] = dict(repository_for(session))
        return read_current(session)

    reasons: list[dict] = []
    limitations = set()
    result = {'schema': GATE_SCHEMA, 'milestone': milestone, 'policy_digest': None,
              'policy_source': policy_source, 'scope_digest': None,
              'checked_context_digest': None, 'checked_at': checked_at,
              'decision': 'not_applicable', 'reasons': reasons, 'missing_dimensions': [],
              'stale_dimensions': [], 'missing_peer_dimensions': [],
              'assurance': pol.SUPPORTED_ASSURANCE, 'waiver_ref': None, 'limitations': [],
              'dimensions': {}, 'repositories': []}
    applicable = bool(policy_doc) and policy_doc['mode'] == 'required' \
        and milestone in policy_doc['milestones']
    if not applicable and not (assess and policy_doc):
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
    if selection is None:
        selection = latest_selection(ext, milestone)
        if selection is not None and actor_scope is not None \
                and selection['actor_scope'] != dict(actor_scope):
            reasons.append({'code': 'no_selection', 'detail': 'the latest coverage selection '
                            'of this milestone is about another person or profile'})
            return _finish(result, reasons, limitations, policy_doc, ext, milestone, today,
                           None, applicable)
    if selection is None:
        reasons.append({'code': 'no_selection', 'detail': 'no coverage selection for this '
                        'milestone; the engine never searches for an old pass'})
        return _finish(result, reasons, limitations, policy_doc, ext, milestone, today,
                       None, applicable)
    if selection.get('virtual'):
        reasons.append({'code': 'no_selection', 'detail': 'no coverage selection for this '
                        'person and profile: the decisions shown are judged, nothing is '
                        'selected'})
    else:
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
        return _finish(result, reasons, limitations, policy_doc, ext, milestone, today,
                       selection, applicable)
    critical = set(policy_doc['critical_dimensions'])
    contexts = {}
    context_digests = set()
    expired = policy_doc['expiration_rule']['kind'] == 'until' and \
        (today or _today()) > policy_doc['expiration_rule']['date']
    settles = arbitration_checker(ext, policy_doc, session_policy_for)
    gate_conflicts = conflicts(ext, settles)
    history_conflicts = {tuple(c['decision_ids']) for c in conflicts(ext)}
    for dim in required:
        info = {'status': 'not_evaluated', 'freshness': 'unknown', 'assistance': None,
                'evidence_availability': None, 'decision_id': None, 'session_id': None}
        result['dimensions'][dim] = info
        did = selection['dimension_decision_map'].get(dim)
        # Every reservation and conflict of the person on the dimension counts, in any
        # session; an arbitration that closed one of them is relied on and settles it only
        # when admissible now (R3C-1). One the gate does not rely on never blocks (C2-2).
        not_admissible = False
        for r in open_reservations(ext, actor, dim, settles=settles, policy_doc=policy_doc,
                                   session_policy_for=session_policy_for):
            reasons.append({'code': 'open_reservation', 'dimension': dim,
                            'detail': r['reservation_id']})
            why = reservation_state(ext, r, settles, policy_doc, session_policy_for)
            if why == 'arbitration_not_admissible':
                not_admissible = True
            elif why in ('peer_assistance_not_admissible', 'assistance_not_admissible'):
                # A resolution whose help the applied rule does not admit (R3C-4, C4-1).
                reasons.append({'code': why, 'dimension': dim,
                                'detail': r['reservation_id']})
        for c in gate_conflicts:
            if c['actor'] == actor and c['dimension_id'] == dim:
                reasons.append({'code': 'unarbitrated_conflict', 'dimension': dim,
                                'detail': ','.join(c['decision_ids'])})
                if tuple(c['decision_ids']) not in history_conflicts:
                    not_admissible = True
        if not_admissible:
            reasons.append({'code': 'arbitration_not_admissible', 'dimension': dim})
            result['missing_dimensions'].append(dim)
        if did is None or did not in ext['decisions']:
            result['missing_dimensions'].append(dim)
            reasons.append({'code': 'dimension_not_selected', 'dimension': dim})
            continue
        d = ext['decisions'][did]
        info.update(decision_id=did, status=d['status'], session_id=d['session_id'])
        session = ext['sessions'].get(d['session_id'])
        problems = selected_decision_problems(ext, d, actor, dim, pdigest, taskset_for,
                                              settles)
        for p in problems:
            reasons.append({'code': p, 'dimension': dim})
        if d['status'] != 'demonstrated' or problems:
            # Not demonstrated now: a selected decision recorded with another status (its
            # reservation may be resolved by another one) or with a problem (round 5: the
            # reason is always given, so a missing dimension never passes silently).
            result['missing_dimensions'].append(dim)
            reasons.append({'code': 'dimension_not_demonstrated', 'dimension': dim})
        if d.get('simulated'):
            limitations.add('simulated_human_decisions')
        if dim in critical and d['reviewer_declared_id'] == actor:
            reasons.append({'code': 'reviewer_not_distinct', 'dimension': dim})
        summary = assistance_summary(ext, d['attempt_ids'])
        rule = policy_doc['assistance_rule']['critical' if dim in critical else 'other']
        info['assistance'] = summary
        if rule == 'unaided_required' and summary != 'unaided':
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
                info['freshness_limitation'] = 'private_context_unknown'
            else:
                reasons.append({'code': 'freshness_unknown', 'dimension': dim,
                                'detail': ','.join(fresh['unknown'])})
    for dim in policy_doc['peer_required_dimensions']:
        if dim not in required:
            continue
        cover = selected_peer_coverage(ext, actor, dim, selection, pdigest, taskset_for,
                                       captured_for, current_for, policy_doc=policy_doc,
                                       blob_ok=blob_ok)
        result['dimensions'].setdefault(dim, {})['peer'] = cover
        if peer_gap(cover, policy_doc):
            result['missing_peer_dimensions'].append(dim)
            reasons.append({'code': 'peer_coverage_missing', 'dimension': dim,
                            'detail': cover['status']})
        if cover.get('simulated'):
            limitations.add('simulated_human_decisions')
        if cover.get('evidence_availability') == 'unavailable':
            limitations.add('evidence_not_reauditable')
    result['checked_context_digest'] = canonical.digest(sorted(context_digests))
    result['repositories'] = [{'session_id': k, **v} for k, v in sorted(seen_repos.items())]
    return _finish(result, reasons, limitations, policy_doc, ext, milestone, today, selection,
                   applicable)


# Reasons of a dimension that do not change its status: freshness and peer coverage are
# their own axes (``freshness_at_export``, ``peer_coverage``).
FRESHNESS_CODES = ('stale', 'freshness_unknown')
STATUS_NEUTRAL_CODES = FRESHNESS_CODES + ('peer_coverage_missing',)
# Gaps that say what the gate counted as a limitation, not a blocking reason.
LIMITATION_GAPS = ('private_context_unknown',)


def judged_status(status: str, result: Mapping, dim: str) -> str:
    """The status an export or the report shows for ``dim``: a ``demonstrated`` dimension
    with a blocking reason of the gate ``result`` (other than freshness and peer coverage) is
    ``needs_review`` (review round 5: one judgement, C4-2 generalised)."""
    codes = {r['code'] for r in result['reasons'] if r.get('dimension') == dim}
    if status == 'demonstrated' and codes - set(STATUS_NEUTRAL_CODES):
        return 'needs_review'
    return status


def gaps_of(result: Mapping, milestone: str) -> list[dict]:
    """The gaps of a gate ``result``: one ``{kind, ref}`` per reason (``kind`` the gate's
    code, ``ref`` its dimension, else the milestone), in the gate's order and without
    duplicates, then one ``private_context_unknown`` per dimension whose unknown freshness
    the gate counted as that limitation (``public_only``)."""
    out: list[dict] = []
    for r in result['reasons']:
        if r['code'] == 'no_required_check':
            continue
        g = {'kind': r['code'], 'ref': r.get('dimension') or milestone}
        if g not in out:
            out.append(g)
    for dim, info in sorted(result['dimensions'].items()):
        if info.get('freshness_limitation') in LIMITATION_GAPS:
            g = {'kind': info['freshness_limitation'], 'ref': dim}
            if g not in out:
                out.append(g)
    return out


def peer_gap(cover: Mapping, policy_doc: Mapping) -> bool:
    """The one rule of a missing peer coverage, for the gate, the export projection and the
    report: fewer declared people than ``team_coverage.minimum_people``, or a coverage that is
    not ``current`` (review round 3, R3C-3)."""
    return cover['people'] < policy_doc['team_coverage']['minimum_people'] \
        or cover['status'] != 'current'


def selected_peer_coverage(ext, author, dim, selection, pdigest, taskset_for, captured_for,
                           current_for, *, policy_doc: Mapping | None = None,
                           blob_ok: Callable[[str], bool] | None = None) -> dict:
    """Peer coverage from the transfer reviews the selection names, never a search for an
    old pass: each is ``demonstrated``, by a reviewer other than the peer, on a peer other than
    the author, in a completed session, under the current policy, on the current handover
    content, and its context is still fresh for the dimension. Without a selection (or one
    naming no transfer for ``dim``) the coverage is ``missing``.

    Integrator default awaiting the owner's decision (round 2, C2-7): when ``policy_doc``
    requires ``unaided_required`` for ``dim``, a transfer whose peer declared AI assistance
    (or declared nothing) does not count (``peer_assistance_not_admissible``). The export
    projection calls this same function with the same inputs as the gate.

    The peer's answer follows the attempts' payload rule (review round 3, R3C-6, A28): when
    its blob is gone and ``policy_doc`` requires ``payloads_available``, the transfer does not
    count (``evidence_unavailable``); under ``recorded_decisions`` it counts and
    ``evidence_availability`` says ``unavailable`` (the gate adds
    ``evidence_not_reauditable``)."""
    chosen = (selection or {}).get('transfer_decision_map', {}).get(dim)
    ids = [chosen] if isinstance(chosen, str) else list(chosen or [])
    peers, problems, simulated = set(), [], False
    availability = 'available'
    payloads = policy_doc is not None and \
        policy_doc.get('evidence_requirement') == 'payloads_available'
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
        if policy_doc is not None and peer_rule(policy_doc, dim) == 'unaided_required' \
                and not transfer_unaided(t):
            problems.append('peer_assistance_not_admissible')
            continue
        if blob_ok is not None and not (t.get('response_ref') and blob_ok(t['response_ref'])):
            if payloads:
                problems.append('evidence_unavailable')
                continue
            availability = 'unavailable'
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
            'problems': problems, 'simulated': simulated,
            'evidence_availability': availability if peers else None}


def peer_rule(policy_doc: Mapping, dim: str) -> str:
    critical = dim in policy_doc['critical_dimensions']
    return policy_doc['assistance_rule']['critical' if critical else 'other']


def transfer_unaided(t: Mapping) -> bool:
    """The peer declared their handover answer without AI assistance (a transfer has no
    hints or coaching; an answer without a declaration is not unaided)."""
    a = t.get('assistance')
    return isinstance(a, Mapping) and a.get('ai_assistance_declared') is False


def arbitration_subject(ext: Mapping, a: Mapping) -> tuple:
    """``(actor, dimension)`` an arbitration settles (one person and one dimension, checked
    when it was recorded); ``(None, None)`` when nothing it names is known."""
    for x in a['conflicting_decision_ids']:
        d = ext['decisions'].get(x)
        if d is not None:
            return d['reviewed_actor_id'], d['dimension_id']
    for x in a['reservation_ids']:
        r = ext['reservations'].get(x)
        if r is not None:
            return r['actor'], r['dimension_id']
    return None, None


def arbitration_checker(ext: Mapping, policy_doc: Mapping,
                        session_policy_for: Callable[[Mapping], Mapping | None] | None = None
                        ) -> Callable[[Mapping], bool]:
    """``settles(arbitration)``: whether a recorded arbitration still settles what it names
    for the gate, i.e. it is admissible under ``policy_doc`` (the policy the gate applies)
    **and** under the policy of the session it was recorded in (:func:`arbitration_admissible`).

    Applied to every arbitration the gate relies on, in any session (review round 3,
    R3C-1): the gate counts the person's reservations and conflicts in every session, so an
    arbitration of a session the selection does not use (an author's self-arbitration under
    a relaxed policy, a then-listed arbiter) is relied on as soon as it closes one of them,
    and is no longer read as history. An arbitration nothing relies on (its conflict no
    longer exists, its reservation was resolved again, another person or dimension) is never
    asked, so it never blocks (round 2, C2-2). A non-admissible one settles nothing: the
    reservation or the conflict counts again (``arbitration_not_admissible``), and it can be
    settled again (a new admissible arbitration, or a demonstrated decision on a new
    variant)."""
    cache: dict = {}

    def settles(a: Mapping) -> bool:
        aid = a['arbitration_id']
        if aid not in cache:
            actor, dim = arbitration_subject(ext, a)
            try:
                owner = ext['sessions'].get(a['session_id'])
                spol = session_policy_for(owner) if session_policy_for and owner else None
                cache[aid] = actor is not None and arbitration_admissible(
                    a, actor, dim, policy_doc, ext, session_policy=spol)
            except Exception:       # noqa: BLE001 - an unreadable session policy never admits
                cache[aid] = False
        return cache[aid]
    return settles


def arbitration_admissible(a: Mapping, actor: str, dim: str, policy_doc: Mapping,
                           ext: Mapping, *, session_policy: Mapping | None = None) -> bool:
    """Checked again by the gate under the policy it applies and the policy the session
    started under (spec §09; the stricter wins): the arbiter is a declared person both
    allow, not the person reviewed on a dimension either makes critical, and not one of the
    reviewers whose decisions are in conflict."""
    docs = [policy_doc] + ([session_policy] if session_policy else [])
    for doc in docs:
        arbiters = doc['role_policy']['arbiters']
        if arbiters != 'any_declared' and a['arbiter_declared_id'] not in arbiters:
            return False
        if dim in doc['critical_dimensions'] and a['arbiter_declared_id'] == actor:
            return False
    parties = {ext['decisions'][x]['reviewer_declared_id']
               for x in a['conflicting_decision_ids'] if x in ext['decisions']}
    return a['arbiter_declared_id'] not in parties


def _last_rectification(ext: Mapping, attempt_ids) -> int:
    revs = [ev['revision'] for ev in ext['assistance_events']
            if ev['attempt_id'] in attempt_ids and ev['kind'] == 'rectification']
    return max(revs or [0])


def _private_key(key: str) -> bool:
    return key.startswith(('study:', 'case:', 'data:', 'engine:'))


def selected_decision_problems(ext: Mapping, d: Mapping, actor: str, dim: str, pdigest: str,
                               taskset_for: Callable[[Mapping], Mapping | None],
                               settles: Callable[[Mapping], bool] | None) -> list[str]:
    """The problems of a selected decision ``d`` for ``actor`` on ``dim`` under the policy of
    digest ``pdigest``: the gate's own list (each makes the dimension missing), also used by
    the export projection and the report so that they never show as demonstrated and current
    a decision the gate refuses (review round 4, C4-2). ``session_missing``,
    ``session_not_completed``, ``actor_mismatch``, ``decision_policy_changed``,
    ``taskset_missing``, ``rubric_changed``, ``taskset_not_qualified``, ``taskset_changed``,
    ``decision_superseded``, ``lost_arbitration`` (an arbitration admissible under
    ``settles`` chose another decision) and ``assistance_rectified_after_review``."""
    session = ext['sessions'].get(d['session_id'])
    problems = _decision_problems(ext, d, session, actor, dim, pdigest, taskset_for)
    lost = arbitrated_ids(ext).get(d['decision_id'])
    if lost is not None and lost['chosen_decision_id'] != d['decision_id'] \
            and (settles is None or settles(lost)):
        problems.append('lost_arbitration')
    if d.get('assistance_at_review') and any(
            attempt_assistance(ext, a)['aided'] != aided
            for a, aided in d['assistance_at_review'].items() if a in ext['attempts']):
        problems.append('assistance_rectified_after_review')
    return problems


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
    """The latest handover content of the author of ``session_id``, in any of their
    sessions: a newer note in a linked session makes a transfer on the older one stale."""
    s = ext['sessions'].get(session_id)
    author = s['actor_declared_id'] if s else None
    versions = [h for h in ext['handovers'].values()
                if (ext['sessions'].get(h['session_id']) or {}).get('actor_declared_id')
                == author] if author else []
    return max(versions, key=lambda h: h['recorded_revision']) if versions else None


def current_handover_digest(ext: Mapping, session_id: str) -> str | None:
    h = current_handover(ext, session_id)
    return h['digest'] if h else None


def latest_selection(ext: Mapping, milestone: str) -> dict | None:
    picks = [s for s in ext['selections'].values() if s['milestone'] == milestone]
    return max(picks, key=lambda s: s['recorded_revision']) if picks else None


def _finish(result, reasons, limitations, policy_doc, ext, milestone, today, selection,
            applicable=True) -> dict:
    result['limitations'] = sorted(limitations)
    result['missing_dimensions'] = sorted(set(result['missing_dimensions']))
    result['stale_dimensions'] = sorted(set(result['stale_dimensions']))
    result['missing_peer_dimensions'] = sorted(set(result['missing_peer_dimensions']))
    if not applicable:                 # ``assess``: every reason, but this is not a pass
        reasons.insert(0, {'code': 'no_required_check',
                           'detail': 'off or coaching mode, or a milestone the policy does '
                                     'not name: the reasons say what a required check would '
                                     'find; this is not a pass'})
        result['decision'] = 'not_applicable'
        return result
    blocking = [r for r in reasons if r['code'] != 'no_required_check']
    if not blocking:
        result['decision'] = 'allowed'
        return result
    waiver = _waiver(ext, milestone, policy_doc, today)
    actor = (selection or {}).get('actor_scope', {}).get('actor_declared_id')
    if waiver is not None and waiver['approver_declared_id'] == actor:
        reasons.append({'code': 'waiver_approved_by_the_author'})
        waiver = None
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
