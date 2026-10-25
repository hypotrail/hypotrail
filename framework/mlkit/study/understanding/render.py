"""The report section "Understanding and handover" (SPEC §14).

A separate section of the offline HTML report, shown only when the study holds the
``understanding`` extension: mode, coverage, dimensions, help received, assurance,
freshness, links and gaps. It says that it is not the scientific verdict. Every entered
text is escaped; identifiers and digests are recorded literals (``data-literal``), so the
report's number check does not read them as figures. It reads blobs, never a live source
after its capture, and never the content of an answer.
"""
from __future__ import annotations

import html
from typing import Mapping

from . import DIMENSION_TITLES, DIMENSIONS, STATE_SCHEMA, evaluate as ev, model, policy as pol
from . import service as sv

e = html.escape
WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven',
         8: 'eight', 9: 'nine', 10: 'ten'}


def _lit(text) -> str:
    return f'<code data-literal="identifier">{e(str(text))}</code>'


def _word(n: int) -> str:
    return WORDS.get(n, 'many')


def _peer_gap_text(cover: Mapping | None, doc: Mapping | None) -> str:
    if not cover:
        return 'missing'
    if cover.get('status') == 'current' and doc:
        need = doc['team_coverage']['minimum_people']
        return (f'{_word(cover["people"])} declared people, the policy asks for '
                f'{_word(need)}')
    return str(cover.get('status'))


def section(study_dir, state: Mapping) -> str:
    """The HTML of the section, or ``''`` when the study never enabled the review.

    Rows and gaps are the gate's judgement of each session (review round 5,
    :func:`service.session_judgement`), the one the export projection publishes: a gap per
    reason with the gate's code. When the policy's stored payload cannot be read, the mode is
    the one the state recorded and the section says the policy is unavailable (no
    judgement)."""
    ext = model.of(state)
    if not ext or ext.get('schema') != STATE_SCHEMA:
        return ''
    store = sv.open_store(study_dir)
    recorded = ext.get('policy') or {}
    policy_available = True
    try:
        doc = sv.policy_doc(store, ext)
    except Exception:          # noqa: BLE001 - the report still renders
        doc, policy_available = None, False
    mode = pol.mode(doc) if policy_available else recorded.get('mode', 'off')
    rows, gaps = [], []
    sessions = sorted(ext['sessions'].values(), key=lambda s: s['created_revision'])
    try:
        settles = sv.arbitration_checker(store, ext, doc)
    except Exception:              # noqa: BLE001 - the report still renders
        settles = None

    def gap(text: str) -> None:
        if text not in gaps:
            gaps.append(text)
    if not policy_available:
        gap(f'{_lit("policy_unavailable")}: the stored policy cannot be read, so nothing is '
            'judged; the mode shown is the one the state recorded')
    for s in sessions[-3:]:
        actor = s['actor_declared_id']
        judged = None
        if policy_available:
            try:
                judged = sv.session_judgement(store, state, s)
            except Exception:      # noqa: BLE001 - the report still renders
                judged = None
                gap(f'{_lit("judgement_unavailable")} for {_lit(actor)}: a stored payload of '
                    'this session cannot be read')
        selection = ev.selection_for(ext, s['milestone'], actor, s['profile'])
        for dim in s['dimensions']:
            # The rule of the export projection (R3C-2): with the selection of this person
            # and profile, a dimension shows the decision it maps; without one, the
            # history's latest decision of the session.
            d = ev.shown_decision(ext, selection, actor, dim, s['session_id'])
            try:
                v = ev.dimension_view(ext, actor, dim, decision=d, settles=settles,
                                      policy_doc=doc,
                                      session_policy_for=sv.session_policy_for(store))
            except Exception:      # noqa: BLE001 - the report still renders
                v = ev.dimension_view(ext, actor, dim, decision=d)
            status = v['status'] if d is not None or v['status'] != 'demonstrated' \
                else 'not_evaluated'
            fresh = 'unknown'
            if judged is not None:
                status = ev.judged_status(status, judged, dim)
                info = judged['dimensions'].get(dim) or {}
                if d is not None and info.get('decision_id') == d['decision_id']:
                    fresh = info['freshness']
            assist = ev.assistance_summary(ext, d['attempt_ids']) if d else 'none'
            rows.append(
                f'<tr><td>{_lit(dim)} {e(DIMENSION_TITLES[dim])}</td><td>{_lit(actor)}</td>'
                f'<td>{e(status.replace("_", " "))}</td><td>{e(fresh)}</td>'
                f'<td>{e(assist)}</td>'
                f'<td>{_lit(d["reviewer_declared_id"]) if d else "—"}</td></tr>')
        if judged is None:
            continue
        # One gap per reason of the gate, grouped by dimension, with the gate's codes.
        by_dim: dict = {}
        for g in ev.gaps_of(judged, s['milestone']):
            by_dim.setdefault(g['ref'], []).append(g['kind'])
        for ref, codes in by_dim.items():
            what = ', '.join(_lit(c) for c in codes)
            if ref in DIMENSION_TITLES:
                extra = ''
                if 'peer_coverage_missing' in codes:
                    cover = (judged['dimensions'].get(ref) or {}).get('peer')
                    extra = f'; handover by a colleague: {e(_peer_gap_text(cover, doc))}'
                gap(f'{_lit(ref)} {e(DIMENSION_TITLES[ref])} for {_lit(actor)}: {what}{extra}')
            else:
                gap(f'{_lit(ref)} for {_lit(actor)}: {what}')
    simulated = any(d.get('simulated') for d in ext['decisions'].values())
    head = (f'<p>Mode {_lit(mode)}. This section is about what the team can explain and take '
            'over; it is <strong>not the scientific verdict</strong> of the study, it '
            'certifies neither general competence nor security, and its assurance is '
            f'{_lit(pol.SUPPORTED_ASSURANCE)}: reviews are attributed by local declarations, '
            'not authenticated. Freshness was computed when this report was rendered; run '
            f'{_lit("hypotrail understanding status")} for the current one.</p>')
    if simulated:
        head += '<p><strong>Some reviews here are simulated (test fixtures), not people.</strong></p>'
    table = ('<div class="scroll"><table><thead><tr><th>Dimension</th><th>Person</th>'
             '<th>Status</th><th>Freshness</th><th>Help</th><th>Reviewer</th></tr></thead><tbody>'
             + ''.join(rows) + '</tbody></table></div>') if rows else \
        '<p>No review session yet.</p>'
    gap_html = ('<h3>Gaps</h3><ul>' + ''.join(f'<li>{g}</li>' for g in gaps) + '</ul>') \
        if gaps else ''
    exports = [x for x in ext['exports'].values() if x['status'] == 'published']
    links = ''
    if exports:
        links = '<h3>Exported reviews</h3><ul>' + ''.join(
            f'<li>{_lit("docs/understanding/" + x["review_id"])}</li>'
            for x in sorted(exports, key=lambda x: x['recorded_revision'])) + '</ul>'
    return (f'<section class="card" id="understanding"><h2>Understanding and handover</h2>'
            f'{head}{table}{gap_html}{links}</section>')


__all__ = ['section', 'DIMENSIONS']
