"""The reviewed export ``hypotrail.understanding-review/1`` (SPEC §14, §16).

Three layers, each with a fixed list of fields (no free "generated fields" rule):

* the **approval projection** (:func:`projection`): what every contributor approves, the
  same complete object for all of them. It holds every public contribution, alias, status
  and rationale, the handover content, the public source scope and the gaps. It excludes
  ``review_id`` (derived from its digest), ``created_at``, ``renderer_version``,
  ``provenance.base_commit``, ``privacy_review``, the export manifest and the publication
  receipt, so it never contains its own digest and approving it changes nothing in it;
* the **review** (:func:`review`): the projection plus ``review_id``, ``created_at``,
  ``renderer_version``, ``provenance.base_commit`` and ``privacy_review``;
* the **files**: ``understanding-review.json`` (canonical JSON v1), ``understanding-review.md``
  (a deterministic rendering of the same object, :func:`markdown`) and
  ``export-manifest.json`` (the digests of both and the renderer version, not its own).

Answers stay local: the export carries opaque attempt references, never an answer, a
transcript, a local path, a secret or a full name. Contributions of a person (alias,
rationale, peer difficulties) need that person's approval of the exact projection; a
change of the projection invalidates every approval.

Publication is an immutable generation ``docs/understanding/<review_id>/`` in the target
repository: an intent reserved in the study, the three files written and synced in a
sibling temporary folder, the set validated, then renamed onto a destination that must not
exist (``renameat2(RENAME_NOREPLACE)``; never a replacement), then a receipt in the study.
An existing destination with the same bytes is the idempotent result; different bytes are
refused. ``latest.json`` is an index updated atomically and separately, never an authority.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import secrets
import sys
from pathlib import Path
from typing import Mapping

from . import DIMENSIONS, DIMENSION_TITLES, taskset as bk, canonical, evaluate as ev, model, policy as pol
from . import refuse, service as sv, snapshot as snap

SCHEMA = 'hypotrail.understanding-review/1'
MANIFEST_SCHEMA = 'hypotrail.understanding-export-manifest/1'
INDEX_SCHEMA = 'hypotrail.understanding-latest/1'
RENDERER_VERSION = 'hypotrail.understanding-render/1'
EXPORT_DIR = 'docs/understanding'
JSON_FILE = 'understanding-review.json'
MD_FILE = 'understanding-review.md'
MANIFEST_FILE = 'export-manifest.json'
FILES = (JSON_FILE, MD_FILE, MANIFEST_FILE)
LATEST = 'latest.json'
APPROVAL_FIELDS = ('schema', 'study_public_id', 'session_ref', 'author_alias',
                   'public_source_scope',
                   'policy', 'policy_digest', 'tasks', 'rubrics', 'source_manifest',
                   'source_scope_digest', 'handover_content', 'handover_digest',
                   'coverage_selection', 'dimensions', 'peer_coverage', 'decisions_summary',
                   'reservation_resolutions', 'known_gaps', 'limitations', 'safe_evidence',
                   'assurance', 'provenance')
REVIEW_FIELDS = ('review_id', 'created_at', 'renderer_version', 'privacy_review') + \
    APPROVAL_FIELDS
DIMENSION_FIELDS = ('id', 'title', 'required', 'critical', 'status', 'freshness_at_export',
                    'criteria', 'task_refs', 'attempt_refs', 'assistance_summary',
                    'reviewer_alias', 'human_review_ref', 'rationale', 'safe_evidence_refs',
                    'dependency_keys', 'evidence_availability', 'next_step')
PROVENANCE_FIELDS = ('engine', 'canonical', 'float_rule', 'taskset_id', 'taskset_version',
                     'taskset_qualification', 'policy_id', 'policy_version', 'base_commit')
STATUSES = model.DIMENSION_STATUSES
FRESHNESS = ('current', 'stale', 'unknown')
AVAILABILITY = ('available', 'unavailable', 'redacted', 'not_applicable')
ASSISTANCE = ('unaided', 'aided', 'none')


def _opaque(ext: Mapping, kind: str, value: str) -> str:
    return snap.opaque_ref(ext['salt'], f'{kind}:{value}')


def study_public_id(ext: Mapping) -> str:
    return 'study-' + canonical.sha256_hex(f'{ext["salt"]}\0study'.encode())[:16]


def _public_refs(refs, scope: Mapping) -> list:
    public = {e['path'] for e in scope['entries'] if e['path']} | \
        {e['logical_key'] for e in scope['entries']}
    return sorted(r for r in refs if r in public)


def _session_decisions(ext, session) -> list:
    return sorted((d for d in ext['decisions'].values()
                   if d['session_id'] == session['session_id']),
                  key=lambda d: d['recorded_revision'])


def projection(store, state: Mapping, session: Mapping) -> dict:
    """The approval projection of ``session`` (see the module docstring)."""
    ext = model.of(state)
    doc = sv.blob_json(store, session['policy_blob'], 'policy')
    taskset = sv.blob_json(store, session['taskset_blob'], 'taskset')
    snapdoc = sv.session_snapshot(store, session)
    scope = snapdoc['public']
    loaders = sv.gate_loaders(store, state, ext)
    current = loaders['current_for'](session)
    actor = session['actor_declared_id']
    critical = set(doc['critical_dimensions'])
    dims, gaps, safe, used_tasks = [], [], set(), {}
    for dim in session['dimensions']:
        view = ev.dimension_view(ext, actor, dim)
        d = ext['decisions'].get(view['decision_id']) if view['decision_id'] else None
        if d is not None and d['session_id'] != session['session_id']:
            d = None
        r = bk.rubric_for(taskset, dim)
        fresh = snap.freshness(snapdoc['local'], current,
                               ev.decision_dependency_keys(ext, d, taskset) if d else
                               (r['dependency_keys'] if r else []))
        attempts = d['attempt_ids'] if d else []
        for aid in attempts:
            t = ext['attempts'][aid]['task_ref']
            used_tasks[t['task_id']] = t
        evidence = _public_refs(d['evidence_refs'], scope) if d else []
        safe.update(evidence)
        status = view['status'] if d is not None or view['status'] != 'demonstrated' \
            else 'not_evaluated'
        entry = {
            'id': dim, 'title': DIMENSION_TITLES[dim], 'required': True,
            'critical': dim in critical, 'status': status,
            'freshness_at_export': fresh['status'] if d else 'unknown',
            'criteria': [{'criterion_id': c['criterion_id'], 'result': c['result']}
                         for c in (d['criterion_results'] if d else [])],
            'task_refs': sorted({ext['attempts'][a]['task_ref']['task_id'] for a in attempts}),
            'attempt_refs': [_opaque(ext, 'attempt', a) for a in attempts],
            'assistance_summary': ev.assistance_summary(ext, attempts),
            'reviewer_alias': d['reviewer_declared_id'] if d else None,
            'human_review_ref': d['decision_id'] if d else None,
            'rationale': d['rationale'] if d else None,
            'safe_evidence_refs': evidence,
            'dependency_keys': ev.decision_dependency_keys(ext, d, taskset) if d
            else sorted(r['dependency_keys'] if r else []),
            'evidence_availability': (ev.evidence_availability(
                ext, attempts, lambda sha: sv.blob_ok(store, sha)) if attempts
                else 'not_applicable'),
            'next_step': _next_step(status, fresh['status'] if d else 'unknown',
                                    view['open_reservations'])}
        dims.append(entry)
        if entry['status'] != 'demonstrated':
            gaps.append({'kind': 'dimension_not_demonstrated', 'ref': dim})
        elif entry['freshness_at_export'] != 'current':
            gaps.append({'kind': f'dimension_{entry["freshness_at_export"]}', 'ref': dim})
        for rid in view['open_reservations']:
            gaps.append({'kind': 'open_reservation', 'ref': rid})
    peers = []
    handover = ev.current_handover(ext, session['session_id'])
    # The same selection-based coverage as the gate (same function, same loaders), for this
    # session's author and profile; without such a selection it is missing, never a search
    # for any demonstrated transfer (round 2, C2-3).
    selection = ev.latest_selection(ext, session['milestone'])
    scope_sel = selection if selection is not None and \
        selection['actor_scope'] == {'actor_declared_id': actor,
                                     'profile': session['profile']} else None
    gate_policy = sv.policy_doc(store, ext) or doc
    for dim in doc['peer_required_dimensions']:
        if dim not in session['dimensions']:
            continue
        cover = ev.selected_peer_coverage(ext, actor, dim, scope_sel, pol.digest(gate_policy),
                                          loaders['taskset_for'], loaders['captured_for'],
                                          loaders['current_for'], policy_doc=gate_policy)
        reviews = [x for x in ext['decisions'].values() if x['kind'] == 'transfer'
                   and dim in x['dimension_ids'] and x['session_id'] == session['session_id']]
        transfers = []
        for x in sorted(reviews, key=lambda x: x['recorded_revision']):
            t = ext['transfers'][x['transfer_id']]
            transfers.append({
                'transfer_ref': _opaque(ext, 'transfer', t['transfer_id']),
                'peer_alias': t['peer_declared_id'], 'task_ref': t['task_ref']['task_id'],
                'input_note_digest': t['input_note_digest'],
                'on_current_handover': t['input_note_digest'] == (handover or {}).get('digest'),
                'evidence_refs': _public_refs(t['evidence_refs'], scope),
                'difficulty_or_blockers': list(t['difficulty_or_blockers']),
                'reviewer_alias': x['reviewer_declared_id'], 'status': x['status'],
                'rationale': x['rationale'], 'human_review_ref': x['decision_id']})
        peers.append({'dimension_id': dim, 'people': cover['people'], 'status': cover['status'],
                      'transfers': transfers})
        if cover['status'] != 'current' or \
                cover['people'] < doc['team_coverage']['minimum_people']:
            gaps.append({'kind': 'peer_coverage_missing', 'ref': dim})
    for key in snapdoc['local'].get('unreadable_sources') or []:
        gaps.append({'kind': 'source_unreadable', 'ref': key})
    if any(snap.is_external_source(e) for e in snapdoc['local']['entries']):
        gaps.append({'kind': 'external_unverified',
                     'ref': 'case contract, data identity and engine are local, not in Git'})
    decisions = []
    gone = ev.superseded_ids(ext)
    for d in _session_decisions(ext, session):
        decisions.append({'decision_ref': d['decision_id'], 'kind': d['kind'],
                          'dimensions': [d['dimension_id']] if d['kind'] == 'attempt'
                          else list(d['dimension_ids']),
                          'status': d['status'], 'reviewer_alias': d['reviewer_declared_id'],
                          'superseded': d['decision_id'] in gone,
                          'simulated': bool(d.get('simulated')),
                          'assurance': pol.SUPPORTED_ASSURANCE})
    reservations = [{'reservation_ref': r['reservation_id'], 'dimension_id': r['dimension_id'],
                     'kind': r['kind'], 'status': r['status'], 'resolved_by': r['resolved_by']}
                    for r in sorted(ext['reservations'].values(),
                                    key=lambda r: r['opened_revision'])
                    if r['actor'] == actor and r['dimension_id'] in session['dimensions']]
    limitations = set(pol.limitations(doc))
    if any(x['simulated'] for x in decisions):
        limitations.add('simulated_human_decisions')
    if not session['taskset_qualified']:
        limitations.add('taskset_not_qualified')
    if session['taskset_simulated']:
        limitations.add('taskset_qualification_simulated')
    if scope['omitted_private']:
        limitations.add('private_context_opaque')
    proj = {
        'schema': SCHEMA, 'study_public_id': study_public_id(ext),
        'session_ref': _opaque(ext, 'session', session['session_id']),
        'author_alias': session['actor_declared_id'], 'public_source_scope': scope, 'policy': doc, 'policy_digest': pol.digest(doc),
        'tasks': [_task_public(taskset, t) for _, t in sorted(used_tasks.items())],
        'rubrics': [{'dimension_id': r['dimension_id'], 'rubric_id': r['rubric_id'],
                     'version': r['version'], 'digest': canonical.digest(r),
                     'criteria': [{'criterion_id': c['criterion_id'], 'text': c['text'],
                                   'mandatory': c['mandatory']} for c in r['criteria']]}
                    for r in taskset['rubrics'] if r['dimension_id'] in session['dimensions']],
        'source_manifest': [e for e in scope['entries'] if e['path']],
        'source_scope_digest': canonical.digest(scope),
        'handover_content': sv.blob_json(store, handover['blob'], 'handover')
        if handover else None,
        'handover_digest': handover['digest'] if handover else None,
        'coverage_selection': _selection_public(selection, session),
        'dimensions': dims, 'peer_coverage': peers, 'decisions_summary': decisions,
        'reservation_resolutions': reservations, 'known_gaps': gaps,
        'limitations': sorted(limitations), 'safe_evidence': sorted(safe),
        'assurance': pol.SUPPORTED_ASSURANCE,
        'provenance': {'engine': 'hypotrail', 'canonical': canonical.VERSION,
                       'float_rule': canonical.FLOAT_RULE, 'taskset_id': taskset['taskset_id'],
                       'taskset_version': taskset['taskset_version'],
                       'taskset_qualification': taskset['qualification']['status'],
                       'policy_id': doc['policy_id'], 'policy_version': doc['version']}}
    return {k: proj[k] for k in APPROVAL_FIELDS}


def _task_public(taskset, ref) -> dict:
    t = bk.task(taskset, ref['task_id'])
    return bk.public_task(t) if t else {k: ref[k] for k in ('task_id', 'task_version')}


def _selection_public(selection, session) -> dict | None:
    """The milestone selection about this session's author only (another person's
    selection is not theirs to publish)."""
    if selection is None or \
            selection['actor_scope']['actor_declared_id'] != session['actor_declared_id']:
        return None
    return {'milestone': selection['milestone'], 'scope_digest': selection['scope_digest'],
            'actor_alias': selection['actor_scope']['actor_declared_id'],
            'profile': selection['actor_scope']['profile'],
            'dimension_decision_map': selection['dimension_decision_map'],
            'transfer_decision_map': selection['transfer_decision_map']}


def _next_step(status: str, freshness: str, reservations) -> str:
    if reservations:
        return 'resolve the open reservation with a new variant of the task'
    if status == 'not_evaluated':
        return 'answer a task of this dimension and have it reviewed'
    if status == 'to_consolidate':
        return 'study the difficulty, then answer a new variant'
    if status == 'needs_review':
        return 'a person reviews the evidence or arbitrates'
    if freshness == 'stale':
        return 'a source changed: review this dimension again'
    if freshness == 'unknown':
        return 'make the sources readable, then check again'
    return 'none until a relevant source changes'


def required_contributors(proj: Mapping) -> list:
    """Every declared person whose alias, rationale or contribution the projection
    publishes, the author included; each approves the same complete projection. The verifier
    recomputes this list from the published content (it never trusts the stored one)."""
    people = {proj['author_alias']} if proj.get('author_alias') else set()
    sel = proj.get('coverage_selection')
    if sel:
        people.add(sel['actor_alias'])
    for d in proj['dimensions']:
        if d['reviewer_alias']:
            people.add(d['reviewer_alias'])
    for p in proj['peer_coverage']:
        for t in p['transfers']:
            people.add(t['peer_alias'])
            people.add(t['reviewer_alias'])
    for d in proj['decisions_summary']:
        people.add(d['reviewer_alias'])
    return sorted(people)


def missing_approvals(ext: Mapping, session: Mapping, proj: Mapping) -> list:
    digest = canonical.digest(proj)
    approved = {a['approver_declared_id'] for a in ext['approvals'].values()
                if a['session_id'] == session['session_id'] and a['content_digest'] == digest}
    need = set(required_contributors(proj)) | {session['actor_declared_id']}
    return sorted(need - approved)


def review_id(proj: Mapping) -> str:
    return 'rv-' + canonical.digest(proj)[:20]


def review(ext: Mapping, session: Mapping, proj: Mapping, *, created_at: str,
           base_commit: str | None) -> dict:
    digest = canonical.digest(proj)
    first = {}
    for a in sorted(ext['approvals'].values(), key=lambda a: a['recorded_revision']):
        if a['session_id'] == session['session_id'] and a['content_digest'] == digest:
            first.setdefault(a['approver_declared_id'], a)     # one approval per person
    approvals = [{'approver_alias': who, 'approved_at': a['approved_at'],
                  'content_digest': a['content_digest']} for who, a in sorted(first.items())]
    need = sorted(set(required_contributors(proj)) | {session['actor_declared_id']})
    done = {a['approver_alias'] for a in approvals}
    out = dict(proj)
    out['provenance'] = {**proj['provenance'], 'base_commit': base_commit}
    out.update(review_id=review_id(proj), created_at=created_at,
               renderer_version=RENDERER_VERSION,
               privacy_review={'status': 'approved' if set(need) <= done else 'pending',
                               'required_contributors': need, 'approvals': approvals})
    return {k: out[k] for k in REVIEW_FIELDS}


def approval_projection(review_doc: Mapping) -> dict:
    """The approval projection of an exported review (for the verifier)."""
    out = {k: review_doc[k] for k in APPROVAL_FIELDS}
    out['provenance'] = {k: v for k, v in review_doc['provenance'].items()
                         if k != 'base_commit'}
    return out


# --- rendering ----------------------------------------------------------------------------

def _md(text) -> str:
    """Plain text for Markdown: markup characters escaped, links never rendered."""
    if text is None:
        return '—'
    out = ''.join(' ' if (ord(ch) < 0x20 or ch in '\x7f\x85\u2028\u2029') else ch
                  for ch in str(text))          # no line break, carriage return or control
    out = out.strip().replace('\\', '\\\\')
    for ch in '`*_{}[]()#+-.!|<>=~:&$':       # & entities, $ math
        out = out.replace(ch, '\\' + ch)
    # GFM links an e-mail address after escapes are resolved: '@' as its own code span
    # splits the text, so no address forms (the rendered text still reads, and copies, '@').
    return out.replace('@', '`@`')


def markdown(doc: Mapping) -> str:
    """The deterministic Markdown rendering of a review (one input, one byte output)."""
    L = [f'# Understanding and handover review {_md(doc["review_id"])}', '',
         'This note records what the team can explain and take over about this study at the '
         'time of export. It is not a grade, it certifies neither general competence, nor '
         'security, nor the scientific validity of the study, and its assurance is '
         f'**{_md(doc["assurance"])}** (attributed by local declarations, not authenticated).',
         '', f'Exported context: created {_md(doc["created_at"])}, policy '
         f'{_md(doc["policy"]["policy_id"])} v{_md(doc["policy"]["version"])} '
         f'({_md(doc["policy"]["mode"])}), source scope `{doc["source_scope_digest"]}`. '
         'It describes this context, never the current state of the work.', '']
    h = doc['handover_content']
    L += ['## Work and scope', '']
    if h:
        L += [_md(h['purpose']), '', '## Main decisions and reasons', '']
        L += [f'- {_md(x)}' for x in h['decisions_with_reasons']] or ['- none recorded']
        L += ['', '## What can and cannot be concluded', '', _md(h['result_interpretation']), '']
        L += ['## Limits', ''] + ([f'- {_md(x)}' for x in h['limits']] or ['- none recorded'])
        L += ['', '## Reproduce and change', '', _md(h['environment_and_reproduction']), '']
        L += [f'- change here: {_md(x)}' for x in h['change_locations']]
        L += [f'- safety rule: {_md(x)}' for x in h['safety_rules']]
        L += ['']
    else:
        L += ['No handover content was recorded.', '']
    L += ['## What the author can explain', '',
          '| Dimension | Status | Freshness at export | Help | Reviewer | Evidence |',
          '|---|---|---|---|---|---|']
    for d in doc['dimensions']:
        L.append(f'| {_md(d["id"])} {_md(d["title"])}{" (critical)" if d["critical"] else ""}'
                 f' | {_md(d["status"])} | {_md(d["freshness_at_export"])} | '
                 f'{_md(d["assistance_summary"])} | {_md(d["reviewer_alias"])} | '
                 f'{_md(d["evidence_availability"])} |')
    L.append('')
    for d in doc['dimensions']:
        if d['rationale']:
            L.append(f'- {_md(d["id"])}, reviewer\'s rationale: {_md(d["rationale"])}')
    L += ['', '## What a colleague could take over', '']
    if not doc['peer_coverage']:
        L.append('No handover task was required.')
    for p in doc['peer_coverage']:
        L.append(f'- {_md(p["dimension_id"])}: {_md(p["people"])} declared people, '
                 f'{_md(p["status"])}')
        for t in p['transfers']:
            L.append(f'  - {_md(t["peer_alias"])}: {_md(t["status"])}, reviewed by '
                     f'{_md(t["reviewer_alias"])}'
                     + ('' if t['on_current_handover'] else
                        ', on an earlier version of the handover content'))
            for b in t['difficulty_or_blockers']:
                L.append(f'    - difficulty: {_md(b)}')
    L += ['', '## Gaps and next actions', '']
    L += [f'- {_md(g["kind"])}: {_md(g["ref"])}' for g in doc['known_gaps']] or ['- none']
    if h:
        L += [f'- next: {_md(x)}' for x in h['next_actions']]
    L += ['', '## Help received, staleness and limits', '',
          'A dimension marked *aided* rests only on answers given after hints or with declared '
          'AI help. A relevant change of a listed source makes a dimension stale; time alone '
          'does not.', '']
    L += [f'- {_md(x)}' for x in doc['limitations']]
    L += ['', '## Approvals', '',
          f'Privacy review: {_md(doc["privacy_review"]["status"])}; required contributors: '
          + ', '.join(_md(x) for x in doc['privacy_review']['required_contributors']) + '.', '']
    L += [f'- {_md(a["approver_alias"])} approved `{a["content_digest"]}`'
          for a in doc['privacy_review']['approvals']]
    L += ['', f'Rendered by {_md(doc["renderer_version"])} from {_md(JSON_FILE)}.', '']
    return '\n'.join(L)


def files_of(doc: Mapping) -> dict:
    data_json = canonical.dumps(doc)
    data_md = markdown(doc).encode('utf-8')
    manifest = {'schema': MANIFEST_SCHEMA, 'review_id': doc['review_id'],
                'renderer_version': RENDERER_VERSION,
                'files': {JSON_FILE: {'sha256': canonical.sha256_hex(data_json),
                                      'bytes': len(data_json)},
                          MD_FILE: {'sha256': canonical.sha256_hex(data_md),
                                    'bytes': len(data_md)}}}
    return {JSON_FILE: data_json, MD_FILE: data_md, MANIFEST_FILE: canonical.dumps(manifest)}


# --- validation (shared with the verifier) ---------------------------------------------------

def _is_code(value) -> bool:
    """A status code of the engine (peer coverage statuses are its problem codes)."""
    return isinstance(value, str) and 0 < len(value) <= 40 and all(
        c in 'abcdefghijklmnopqrstuvwxyz_' for c in value)


def _is_digest(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in '0123456789abcdef' for c in value)


def validate_review(doc) -> list[str]:
    """Problems of a review document against the closed schema (empty when valid)."""
    p = []
    if not isinstance(doc, dict) or set(doc) != set(REVIEW_FIELDS):
        return ['review: missing or unknown fields']
    if doc['schema'] != SCHEMA:
        p.append('schema')
    if doc['assurance'] != pol.SUPPORTED_ASSURANCE:
        p.append('assurance')
    if doc['renderer_version'] != RENDERER_VERSION:
        p.append('renderer_version')
    for key in ('source_scope_digest', 'policy_digest'):
        if not _is_digest(doc[key]):
            p.append(key)
    try:
        pol.validate(doc['policy'])
    except Exception:          # noqa: BLE001 - any refusal of the embedded policy
        p.append('policy')
    if not isinstance(doc['dimensions'], list):
        return p + ['dimensions']
    ids = [d.get('id') for d in doc['dimensions'] if isinstance(d, dict)]
    if len(ids) != len(set(ids)):
        p.append('duplicate dimension ids')
    for d in doc['dimensions']:
        if not isinstance(d, dict) or set(d) != set(DIMENSION_FIELDS):
            p.append('dimension fields')
            continue
        if d['id'] not in DIMENSIONS:
            p.append('dimension id')
        if d['status'] not in STATUSES or d['freshness_at_export'] not in FRESHNESS \
                or d['evidence_availability'] not in AVAILABILITY \
                or d['assistance_summary'] not in ASSISTANCE:
            p.append(f'dimension {d.get("id")} enum')
        if d['status'] == 'demonstrated' and not d['human_review_ref']:
            p.append(f'dimension {d.get("id")} demonstrated without a human review')
    if not isinstance(doc['provenance'], dict) or set(doc['provenance']) != \
            set(PROVENANCE_FIELDS):
        p.append('provenance')
    peers = doc['peer_coverage']
    if not isinstance(peers, list) or not all(
            isinstance(c, dict) and c.get('dimension_id') in DIMENSIONS
            and type(c.get('people')) is int and c['people'] >= 1
            and _is_code(c.get('status')) for c in peers):
        p.append('peer_coverage')
    pr = doc['privacy_review']
    if not isinstance(pr, dict) or set(pr) != {'status', 'required_contributors', 'approvals'} \
            or pr['status'] not in ('pending', 'approved'):
        p.append('privacy_review')
    elif not isinstance(pr['approvals'], list) or not all(
            isinstance(a, dict) and _is_digest(a.get('content_digest'))
            for a in pr['approvals']):
        p.append('privacy_review approvals')
    scope = doc['public_source_scope']
    if not isinstance(scope, dict) or scope.get('schema') != snap.PUBLIC_SCHEMA:
        p.append('public_source_scope')
    else:
        try:
            for e in scope['entries']:
                if e['path'] is not None:
                    snap.safe_relative(e['path'])
                if e['ref'] != 'public_ref':
                    p.append('public entry ref')
            for o in scope['omitted_private']:
                if not str(o['opaque_private_ref']).startswith('opq-'):
                    p.append('opaque ref')
        except Exception:      # noqa: BLE001
            p.append('public_source_scope entries')
    if not str(doc['review_id']).startswith('rv-'):
        p.append('review_id')
    return p


# --- publication -----------------------------------------------------------------------------

_RENAME_NOREPLACE = 1


def rename_noreplace(src: Path, dst: Path) -> None:
    """Rename ``src`` onto ``dst`` only if ``dst`` does not exist (atomic, never a
    replacement). ``FileExistsError`` when it exists; ``OSError`` when the platform has no
    such primitive (the publication is then refused, never emulated with a race)."""
    libc = ctypes.CDLL(ctypes.util.find_library('c') or None, use_errno=True)
    if sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        AT_FDCWD = -100
        res = libc.renameat2(AT_FDCWD, os.fsencode(src), AT_FDCWD, os.fsencode(dst),
                             _RENAME_NOREPLACE)
    elif sys.platform == 'darwin' and hasattr(libc, 'renamex_np'):
        res = libc.renamex_np(os.fsencode(src), os.fsencode(dst), 0x00000004)   # RENAME_EXCL
    else:
        raise OSError(errno.ENOSYS, 'no atomic rename without replacement on this platform')
    if res != 0:
        err = ctypes.get_errno()
        if err == errno.EEXIST or err == errno.ENOTEMPTY:
            raise FileExistsError(err, os.strerror(err), str(dst))
        raise OSError(err, os.strerror(err), str(dst))


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _same(dest: Path, files: Mapping[str, bytes]) -> bool:
    if not dest.is_dir() or dest.is_symlink():
        return False
    names = sorted(p.name for p in dest.iterdir())
    if names != sorted(files):
        return False
    return all((dest / n).read_bytes() == data for n, data in files.items())


def publish(repo: Path, review_id_: str, files: Mapping[str, bytes], *, fault=None) -> str:
    """Publish one generation; ``'published'`` or ``'already_published'`` (same bytes)."""
    parent = Path(repo) / EXPORT_DIR
    real_repo = Path(os.path.realpath(repo))
    if not Path(os.path.realpath(parent)).is_relative_to(real_repo):
        raise refuse('path_outside_scope', 'docs/understanding leaves the repository.',
                     'Remove the link.')
    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / review_id_
    if dest.exists() or dest.is_symlink():
        if _same(dest, files):
            return 'already_published'
        raise refuse('export_stale', 'This generation already exists with other content; it '
                     'is never replaced.', 'Export a new generation.', review_id=review_id_)
    tmp = parent / f'.{review_id_}.tmp-{secrets.token_hex(4)}'
    tmp.mkdir()
    try:
        for name in FILES:
            with open(tmp / name, 'xb') as handle:
                handle.write(files[name])
                handle.flush()
                os.fsync(handle.fileno())
            if fault == f'after_{name}':
                raise RuntimeError(f'injected fault after {name}')
        _fsync_dir(tmp)
        if not _same(tmp, files):
            raise refuse('evidence_invalid', 'The written generation does not match.',
                         'Export again.')
        if fault == 'before_rename':
            raise RuntimeError('injected fault before rename')
        try:
            rename_noreplace(tmp, dest)
        except FileExistsError:
            if _same(dest, files):
                return 'already_published'
            raise refuse('export_stale', 'Another export published this review id first with '
                         'other content.', 'Export a new generation.') from None
        except OSError as exc:       # no rename without replacement here: never emulated
            raise refuse('unsupported_capability', 'This filesystem or platform has no atomic '
                         'rename without replacement, so the generation was not published '
                         f'({exc.strerror or exc}).', 'Export into a repository on a local '
                         'Linux or macOS filesystem; a retry there reconciles the same '
                         'export.') from None
        _fsync_dir(parent)
    finally:
        if tmp.exists():
            for p in tmp.iterdir():
                p.unlink()
            tmp.rmdir()
    if fault == 'after_rename':
        raise RuntimeError('injected fault after rename')
    return 'published'


def write_latest(repo: Path, review_id_: str) -> None:
    """Update the optional index atomically; it is never an authority."""
    from mlkit.study.store import atomic_write
    atomic_write(Path(repo) / EXPORT_DIR / LATEST,
                 canonical.dumps({'schema': INDEX_SCHEMA, 'review_id': review_id_,
                                  'authority': False}))
