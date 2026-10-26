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


# The names L1 adds to the contract, pinned here until the integrator moves them into
# ``test_contract_freeze.py`` with the wave's contract commit (plan §1.3).
PAUSE_KEYS = ('schema', 'kind', 'language', 'revision', 'position', 'learned', 'limitations',
              'proposal_id', 'proposal_text', 'recommended_option', 'options', 'option_labels',
              'question', 'evidence_refs', 'detail_topics')
PAUSE_KINDS = ('decision', 'action', 'explanation', 'blocked', 'complete', 'choice')


def test_the_l1_names_are_frozen_and_documented():
    from pathlib import Path
    doc = (Path(fk.REPO) / 'docs' / 'specs' / 'CLI-CONTRACT.md').read_text(encoding='utf-8')
    assert tuple(guidance.pause({'next_action': {'kind': 'run'}, 'revision': 1})) == PAUSE_KEYS
    assert guidance.KINDS == PAUSE_KINDS and guidance.SCHEMA == 'hypotrail.pause/1'
    assert junior.CHOICE_OPTION_KEYS == ('id', 'value', 'label')
    for name in PAUSE_KEYS + PAUSE_KINDS + ('choice_options', 'junior.choice_options',
                                            'feasibility.accepts', 'guidance.OPTION_LABELS',
                                            'junior.CHOICE_OPTION_KEYS'):
        assert f'`{name}`' in doc, name
    flat = ' '.join(doc.split())
    for label_en, label_fr in guidance.OPTION_LABELS.values():
        assert f'"{label_en}" / "{label_fr}"' in flat, label_en
