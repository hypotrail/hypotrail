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
from . import service as sv, snapshot as snap

e = html.escape
WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven',
         8: 'eight', 9: 'nine', 10: 'ten'}


def _lit(text) -> str:
    return f'<code data-literal="identifier">{e(str(text))}</code>'


def _word(n: int) -> str:
    return WORDS.get(n, 'many')


def section(study_dir, state: Mapping) -> str:
    """The HTML of the section, or ``''`` when the study never enabled the review."""
    ext = model.of(state)
    if not ext or ext.get('schema') != STATE_SCHEMA:
        return ''
    store = sv.open_store(study_dir)
    try:
        doc = sv.policy_doc(store, ext)
    except Exception:          # noqa: BLE001 - the report still renders
        doc = None
    mode = pol.mode(doc)
    rows, gaps = [], []
    sessions = sorted(ext['sessions'].values(), key=lambda s: s['created_revision'])
    current = sv.current_for(store, state, ext)
    for s in sessions[-3:]:
        actor = s['actor_declared_id']
        try:
            captured = sv.session_snapshot(store, s)['local']
            now_ = current(s)
            taskset = sv.blob_json(store, s['taskset_blob'], 'taskset')
        except Exception:          # noqa: BLE001 - freshness unknown, the report renders
            captured = now_ = taskset = None
        for dim in s['dimensions']:
            v = ev.dimension_view(ext, actor, dim)
            d = ext['decisions'].get(v['decision_id']) if v['decision_id'] else None
            assist = ev.assistance_summary(ext, d['attempt_ids']) if d else 'none'
            fresh = 'unknown'
            if d and captured is not None:
                fresh = snap.freshness(captured, now_, ev.decision_dependency_keys(
                    ext, d, taskset))['status']
            rows.append(
                f'<tr><td>{_lit(dim)} {e(DIMENSION_TITLES[dim])}</td><td>{_lit(actor)}</td>'
                f'<td>{e(v["status"].replace("_", " "))}</td><td>{e(fresh)}</td>'
                f'<td>{e(assist)}</td>'
                f'<td>{_lit(d["reviewer_declared_id"]) if d else "—"}</td></tr>')
            if v['status'] != 'demonstrated':
                gaps.append(f'{_lit(dim)} {e(DIMENSION_TITLES[dim])} for {_lit(actor)}: '
                            f'{e(v["status"].replace("_", " "))}')
        for dim in (doc or {}).get('peer_required_dimensions', []):
            if dim in s['dimensions']:
                cover = ev.peer_coverage(ext, actor, dim, None, None)
                if cover['status'] != 'current':
                    gaps.append(f'{_lit(dim)} handover by a colleague: {e(cover["status"])}')
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
