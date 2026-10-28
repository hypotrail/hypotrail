"""Owner session 2026-10-26, lot L1 (R3, R2b, R2c): a picker at every closed question.

* R3: every pause with options labels them in the study language (``pause.option_labels``),
  so a client's picker shows the engine's words: adopt, change, explain at a decision; go on,
  explain at a step change.
* R2c (D2): at a free choice (the model choice, the conclusion, ``recommended`` null),
  ``next_action.choice_options`` lists exactly the values a confirmation would accept now,
  each ``{id, value, label}``; the pause is of kind ``choice``, one option per value, none
  recommended. A pick is proposed, then adopted at its own pause: ``--channel choice`` stays
  the adoption option of an open proposal (ADR 0005 amendment 4).

The agent side (the Copilot instructions) is pinned in ``test_agent_files.py``; the walkers
of ``test_review_round6_engine.py`` and ``test_review_round5_engine.py`` check every free
choice met from ``init`` to ``done``.

R24 (owner session 2026-10-27): the review of an automatic decision is an adoption pause
(``test_a_review_pause_is_an_adoption_pause``; on real runs, ``test_automation.py``).
"""
from __future__ import annotations

import pytest

import flowkit as fk
from mlkit.study import feasibility, guidance, junior, read, state as st
from test_review_round6_engine import (BASES, accepted_on_a_clone, candidate_values,
                                       check_choice_options, execute)

LABELS = {'en': {'adopt': 'I adopt this decision', 'change': 'Change something',
                 'explain': 'Explain first', 'continue': "Let's continue"},
          'fr': {'adopt': "J'adopte cette décision", 'change': 'Changer quelque chose',
                 'explain': "Expliquer d'abord", 'continue': 'On continue'}}


def _view(kind: str, language: str, **action) -> dict:
    view = {'next_action': {'kind': kind, **action}, 'language': language, 'revision': 7,
            'open_proposals': [{'proposal_id': 'p_1', 'restatement': 'You keep X.'}]}
    return view


@pytest.mark.parametrize('language', ['en', 'fr'])
def test_pause_option_labels_in_the_study_language(language):
    """Every kind: the options a pause offers each have their label in the study language,
    in the order of ``options``; a pause without options has none."""
    labels = LABELS[language]
    decision = guidance.pause(_view('await_user_words', language, proposal_id='p_1'))
    assert decision['kind'] == 'decision' and decision['recommended_option'] == 'adopt'
    assert decision['option_labels'] == {k: labels[k] for k in ('adopt', 'change', 'explain')}
    for kind in ('show_data_card', 'run', 'propose'):
        action = guidance.pause(_view(kind, language, question='Shall we?'))
        assert action['kind'] == 'action' and action['recommended_option'] == 'continue'
        assert action['option_labels'] == {'continue': labels['continue'],
                                           'explain': labels['explain']}
    for kind, pause_kind in (('done', 'complete'), ('blocked', 'blocked'),
                             ('outcome_unknown', 'blocked'), ('explain', 'explanation')):
        pause = guidance.pause(_view(kind, language))
        assert pause['kind'] == pause_kind
        assert pause['options'] == [] and pause['option_labels'] == {}
    choice = guidance.pause(_view('propose', language, decision='conclusion', question='Q?',
                                  choice_options=[
                                      {'id': 'keep_baseline', 'value': {'verdict': 'keep_baseline'},
                                       'label': 'Keep it'},
                                      {'id': 'inconclusive', 'value': {'verdict': 'inconclusive'},
                                       'label': 'Not sure'}]))
    assert choice['kind'] == 'choice' and choice['recommended_option'] is None
    assert choice['options'] == ['keep_baseline', 'inconclusive']
    assert choice['option_labels'] == {'keep_baseline': 'Keep it', 'inconclusive': 'Not sure'}
    assert choice['question'] == 'Q?'
    assert list(decision)[list(decision).index('options') + 1] == 'option_labels'


@pytest.mark.parametrize('language', ['en', 'fr'])
def test_a_review_pause_is_an_adoption_pause(language):
    """Owner session 2026-10-27 (R24): the review of an automatic decision (``review: true``,
    a ``reconfirm`` before the value is proposed again, an ``await_user_words`` after) is a
    ``decision`` pause: adopt, change, explain in the study language, nothing recommended,
    the recorded value in words as the quoted block, and the reviewed decision's step as the
    position (not the step the plan stands at). A reconfirmation that is not a review stays
    a step change."""
    labels = LABELS[language]
    plan = [{'id': 'prediction_time', 'decision': 'prediction_time', 'status': 'done'},
            {'id': 'feature_availability', 'decision': 'feature_availability',
             'status': 'done'},
            {'id': 'final_test', 'decision': 'final_test', 'status': 'ready'}]
    value = {'acceleration': 'uncertain_excluded', 'weight': 'available_at_prediction'}
    view = {**_view('reconfirm', language, decision='feature_availability', review=True,
                    default_value=value),
            'plan': plan, 'current_step': 'final_test'}
    pause = guidance.pause(view)
    assert (pause['kind'], pause['recommended_option'], pause['proposal_id']) == (
        'decision', None, None)
    assert pause['option_labels'] == {k: labels[k] for k in ('adopt', 'change', 'explain')}
    assert pause['position'] == {'step_id': 'feature_availability', 'completed': 2, 'total': 3}
    assert pause['proposal_text'] == {
        'en': 'The feature availability: keep weight; exclude acceleration (its timing is '
              'uncertain) (value recorded by the automatic mode, not yet in your words).',
        'fr': 'La disponibilité des variables : garder weight ; exclure acceleration (moment '
              'incertain) (valeur enregistrée par le mode automatique, pas encore avec vos '
              'mots).'}[language]
    closed = {'en': 'Do you adopt this decision?', 'fr': 'Adoptez-vous cette décision ?'}
    assert pause['question'].replace('\xa0', ' ') == \
        f'{pause["proposal_text"]}\n\n{closed[language]}'
    # Proposed again: the pause holds the proposal, still without a recommendation.
    again = guidance.pause({**view, 'next_action': {
        'kind': 'await_user_words', 'decision': 'feature_availability', 'proposal_id': 'p_1',
        'review': True}})
    assert (again['kind'], again['recommended_option'], again['proposal_text']) == (
        'decision', None, 'You keep X.')
    assert again['position']['step_id'] == 'feature_availability'
    # A reconfirmation after an invalidation (no review) is unchanged.
    plain = guidance.pause({**view, 'next_action': {'kind': 'reconfirm',
                                                    'decision': 'feature_availability',
                                                    'question': 'Again?'}})
    assert (plain['kind'], plain['recommended_option']) == ('action', 'continue')
    assert plain['position']['step_id'] == 'final_test'


@pytest.mark.parametrize('language', ['en', 'fr'])
def test_the_step_change_picker_on_a_real_study(tmp_path, synthetic_case_dir, language):
    """R3: at step 0 (the data card) the pause offers go on / explain first in the study
    language, and the view's presentation snapshot carries the same pause."""
    flow = fk.Flow(tmp_path / 'study', synthetic_case_dir)
    flow.call('init', '--case', synthetic_case_dir, '--study', flow.study, '--lang', language)
    summary = flow.call('status', '--summary', '--study', flow.study)
    pause = summary['next_action']['pause']
    assert summary['next_action']['kind'] == 'show_data_card' and pause['kind'] == 'action'
    assert pause['option_labels'] == {'continue': LABELS[language]['continue'],
                                      'explain': LABELS[language]['explain']}
    assert 'choice_options' not in summary['next_action']
    view = flow.view()
    assert view['presentation']['pending_action'] == view['next_action']['pause']


def _advance(s, until, limit=90) -> dict:
    """Execute ``next_action`` as given until ``until(next_action)`` holds."""
    for _ in range(limit):
        nxt = s.view()['next_action']
        if until(nxt):
            return nxt
        assert nxt['kind'] not in ('done', 'blocked'), nxt
        out = execute(s, nxt)
        assert out.get('ok'), (nxt, out.get('error'))
    raise AssertionError('never reached')


def _proposes(decision):
    return lambda nxt: nxt['kind'] == 'propose' and nxt.get('decision') == decision


@pytest.mark.parametrize('base', ['legacy-binary-en', 'legacy-regression-fr'])
def test_choice_options_are_exactly_the_accepted_values(tmp_path, monkeypatch, base):
    """R2c: at the model choice and at the conclusion (before the opening and after it), the
    options are exactly the values a confirmation accepts, checked through the real CLI on
    clones; labels in the study language; the binary baseline is never an option, the
    regression baseline is; before the opening no adopting verdict is offered."""
    s = BASES[base](tmp_path, monkeypatch)
    language = base.rsplit('-', 1)[1]
    regression = s.task == 'regression'
    # The model choice.
    nxt = _advance(s, _proposes('model_choice'))
    assert nxt['recommended'] is None and nxt['pause']['kind'] == 'choice'
    ids = [o['id'] for o in nxt['choice_options']]
    assert ('fit.baseline' in ids) == regression
    candidate = 'fit.linear' if regression else 'fit.logistic'
    labels = {o['id']: o['label'] for o in nxt['choice_options']}
    assert labels[candidate] == {'en': 'The logistic model', 'fr': 'Le modèle linéaire'}[
        language]
    assert any(i.startswith('fit.variant') for i in ids)
    for o in nxt['choice_options']:
        assert set(o) == set(junior.CHOICE_OPTION_KEYS) and o['value'] == o['id']
        if o['id'].startswith('fit.variant'):
            assert o['label'].startswith({'en': 'The ', 'fr': 'La '}[language]) and ' · ' in \
                o['label'], o
    check_choice_options(s, nxt, tmp_path / 'model')
    # The conclusion before the opening (the final test proposed next): only the verdicts
    # that open nothing are accepted.
    nxt = _advance(s, _proposes(st.FINAL_TEST))
    state = s.state()
    accepts = feasibility.accepts(read.open(s.study), state)
    early = junior.choice_options({'kind': 'propose', 'decision': 'conclusion',
                                   'recommended': None}, state, language, accepts)
    offered = [o['value'] for o in early]
    assert {o['id'] for o in early} == {'keep_baseline', 'inconclusive'}
    for i, value in enumerate(candidate_values(state, 'conclusion')):
        assert accepted_on_a_clone(s, tmp_path / 'early' / str(i), 'conclusion', value) == \
            (value in offered), value
    # The conclusion after the opening: the adopting verdict too.
    nxt = _advance(s, _proposes('conclusion'))
    assert st.final_test_opened(s.state())
    ids = [o['id'] for o in nxt['choice_options']]
    assert ('adopt_model' if regression else 'adopt_policy') in ids, ids
    words = {o['id']: o['label'] for o in nxt['choice_options']}
    assert words['inconclusive'] == {'en': 'Do not conclude (inconclusive)',
                                     'fr': 'Ne pas conclure (non concluant)'}[language]
    if regression:
        assert words['keep_baseline'] == 'Garder la moyenne de référence'
    check_choice_options(s, nxt, tmp_path / 'conclusion')


def test_a_choice_pick_is_never_a_confirmation(tmp_path, monkeypatch):
    """D2, NR-4: a pick at a free choice records nothing by itself. ``--channel choice`` with
    the pick's label, when no proposal of the decision is open, is refused and changes
    nothing (as before L1); the pick is proposed, which opens an adoption pause of its own,
    and the adopt option's label confirms it."""
    s = BASES['legacy-binary-en'](tmp_path, monkeypatch)
    nxt = _advance(s, _proposes('model_choice'))
    pick = nxt['choice_options'][0]
    confirmed = [p for p in s.state()['proposals'].values() if p['status'] != 'open']
    rev = s.rev()
    for proposal in (confirmed[-1]['proposal_id'], 'p_999'):
        out = s.call('decide', 'confirm', proposal, '--user-words', pick['label'], '--channel',
                     'choice', '--request-id', s.rid(), '--expected-revision', rev,
                     '--study', s.study, expect=2)
        assert out['ok'] is False, out
    assert s.rev() == rev and s.state()['decisions']['model_choice']['status'] == 'open'
    p = s.call('decide', 'propose', 'model_choice', '--value-json', f'"{pick["value"]}"',
               '--restatement', 'You choose the logistic model.', '--rationale', 'Picked.',
               '--request-id', s.rid(), '--expected-revision', s.rev(), '--study', s.study)
    pid = p['result']['proposal_id']
    pause = s.view()['next_action']['pause']
    assert pause['kind'] == 'decision' and pause['proposal_id'] == pid
    out = s.call('decide', 'confirm', pid, '--user-words', pause['option_labels']['adopt'],
                 '--channel', 'choice', '--request-id', s.rid(), '--expected-revision',
                 s.rev(), '--study', s.study)
    assert out['result']['status'] == 'confirmed'
    assert s.state()['decisions']['model_choice']['value'] == pick['value']

