"""Compact, localized pause payloads derived from one already-built view (J5).

Owner session 2026-10-26 (L1, R3, R2c): every pause with options carries
``option_labels`` (``{option_id: label}``, in the study language), so a client's picker
shows the engine's words instead of the agent's translation; a free choice among the
values the engine accepts now (``next_action.choice_options``, the model choice and the
conclusion when ``recommended`` is null) is the kind ``choice``, one option per value and
none recommended.

Owner session 2026-10-27 (R24): the review of a decision the automatic mode recorded
(``next_action.review``, a ``reconfirm`` or an ``await_user_words``) is an adoption question,
not a step change: a pause of kind ``decision`` with the options adopt, change, explain, none
recommended (the value is the engine's, the junior adopts or changes it in their own words),
the recorded value in words as the quoted block (``proposal_text``) when no proposal is open
yet, and ``position.step_id`` the step of the reviewed decision.
"""
from __future__ import annotations

from typing import Mapping

SCHEMA = 'hypotrail.pause/1'
KINDS = ('decision', 'action', 'explanation', 'blocked', 'complete', 'choice')
# The labels of the fixed options, (English, French). ``adopt``, ``change`` and ``explain``
# are the labels the agent instructions fix for the adoption picker (``--channel choice``
# records the adopt label verbatim, CLI-CONTRACT §5.4).
OPTION_LABELS = {'adopt': ('I adopt this decision', "J'adopte cette décision"),
                 'change': ('Change something', 'Changer quelque chose'),
                 'explain': ('Explain first', "Expliquer d'abord"),
                 'continue': ("Let's continue", 'On continue')}


def option_labels(options, language: str, choices=()) -> dict:
    """``{option_id: label}`` for ``options`` in ``language``: a fixed option's label from
    :data:`OPTION_LABELS`, a choice's from its ``choice_options`` entry."""
    own = {c['id']: c['label'] for c in choices or ()}
    fr = language == 'fr'
    return {o: own[o] if o in own else OPTION_LABELS[o][fr] for o in options}


def pause(view: Mapping) -> dict:
    action = view.get('next_action') or {}
    source_kind = action.get('kind')
    proposal = next((p for p in view.get('open_proposals', [])
                     if p['proposal_id'] == action.get('proposal_id')), None)
    review = bool(action.get('review')) and source_kind in ('reconfirm', 'await_user_words')
    if source_kind == 'await_user_words' and proposal is not None:
        kind = 'decision'
    elif review:
        kind = 'decision'
    elif source_kind == 'done':
        kind = 'complete'
    elif source_kind in ('blocked', 'outcome_unknown', 'acknowledge_interruption'):
        kind = 'blocked'
    elif source_kind == 'explain':
        kind = 'explanation'
    elif action.get('choice_options'):
        kind = 'choice'
    else:
        kind = 'action'
    language = view.get('language', 'en')
    plan = list(view.get('plan') or [])
    completed = sum(step.get('status') == 'done' for step in plan)
    limitations = [{'code': item['id'], 'text': item.get('junior_text') or item['text']}
                   for item in (view.get('not_yet_defensible') or [])[:3]]
    proposal_text = ((proposal.get('label') or proposal.get('restatement'))
                     if proposal is not None else None)
    step_id = view.get('current_step')
    if review:
        step_id = next((s.get('id') for s in plan if s.get('decision') == action.get('decision')),
                       step_id)
        if proposal_text is None:
            from .automation_words import review_restatement
            proposal_text = review_restatement(view, action.get('decision'),
                                               action.get('default_value'))
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
        # R24: a review recommends nothing: the junior adopts or changes the automatic value.
        recommended = None if review else 'adopt'
    elif kind == 'action':
        question = action.get('question') or action.get('junior_message')
        options = ['continue', 'explain']
        recommended = 'continue'
    elif kind == 'choice':
        # The junior's own choice (R2c): no option is the engine's recommendation, and a
        # pick is proposed, then adopted at its own pause (never a confirmation).
        question = action.get('question') or action.get('junior_message')
        options = [c['id'] for c in action['choice_options']]
    nonlinear = ((view.get('model_families') or {}).get('recommendation')
                 == 'compare_nonlinear')
    topics = ['metric', 'uncertainty']
    if nonlinear:
        topics.append('why-consider-a-nonlinear-family')
    return {
        'schema': SCHEMA, 'kind': kind, 'language': language,
        'revision': view['revision'],
        'position': {'step_id': step_id, 'completed': completed,
                     'total': len(plan)},
        'learned': [], 'limitations': limitations,
        'proposal_id': proposal['proposal_id'] if proposal is not None else None,
        'proposal_text': proposal_text,
        'recommended_option': recommended, 'options': options,
        'option_labels': option_labels(options, language, action.get('choice_options')),
        'question': question,
        'evidence_refs': [], 'detail_topics': topics,
    }
