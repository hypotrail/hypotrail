"""Compact, localized pause payloads derived from one already-built view (J5)."""
from __future__ import annotations

from typing import Mapping

SCHEMA = 'hypotrail.pause/1'
KINDS = ('decision', 'action', 'explanation', 'blocked', 'complete')


def pause(view: Mapping) -> dict:
    action = view.get('next_action') or {}
    source_kind = action.get('kind')
    proposal = next((p for p in view.get('open_proposals', [])
                     if p['proposal_id'] == action.get('proposal_id')), None)
    if source_kind == 'await_user_words' and proposal is not None:
        kind = 'decision'
    elif source_kind == 'done':
        kind = 'complete'
    elif source_kind in ('blocked', 'outcome_unknown', 'acknowledge_interruption'):
        kind = 'blocked'
    elif source_kind == 'explain':
        kind = 'explanation'
    else:
        kind = 'action'
    language = view.get('language', 'en')
    plan = list(view.get('plan') or [])
    completed = sum(step.get('status') == 'done' for step in plan)
    limitations = [{'code': item['id'], 'text': item.get('junior_text') or item['text']}
                   for item in (view.get('not_yet_defensible') or [])[:3]]
    proposal_text = ((proposal.get('label') or proposal.get('restatement'))
                     if proposal is not None else None)
    question = None
    options = []
    recommended = None
    if kind == 'decision':
        closed = ('Adoptez-vous cette décision ?' if language == 'fr'
                  else 'Do you adopt this decision?')
        # Copilot may collapse surrounding assistant prose as reasoning. Keep the actual
        # interactive prompt self-contained so the decision is still visible.
        question = f'{proposal_text}\n\n{closed}' if proposal_text else closed
        options = ['adopt', 'change', 'explain']
        recommended = 'adopt'
    elif kind == 'action':
        question = action.get('question') or action.get('junior_message')
        options = ['continue', 'explain']
        recommended = 'continue'
    nonlinear = ((view.get('model_families') or {}).get('recommendation')
                 == 'compare_nonlinear')
    topics = ['metric', 'uncertainty']
    if nonlinear:
        topics.append('why-consider-a-nonlinear-family')
    return {
        'schema': SCHEMA, 'kind': kind, 'language': language,
        'revision': view['revision'],
        'position': {'step_id': view.get('current_step'), 'completed': completed,
                     'total': len(plan)},
        'learned': [], 'limitations': limitations,
        'proposal_id': proposal['proposal_id'] if proposal is not None else None,
        'proposal_text': proposal_text,
        'recommended_option': recommended, 'options': options, 'question': question,
        'evidence_refs': [], 'detail_topics': topics,
    }
