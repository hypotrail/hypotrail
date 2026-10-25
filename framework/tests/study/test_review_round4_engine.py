"""Review round 4 of the study engine (2026-10-25): E4-1..E4-6 and the number-tracing gaps.

Every study is a temporary synthetic one (the reviewer's scripts, ported).

* E4-1: a final test confirmed but not opened (an interrupted execution refused the opening
  that follows the confirmation, or the process stopped between the two) never opens on
  evidence or a choice that changed: a change of what it rests on makes its confirmation
  ``reconfirm_required`` (the safe option: the junior confirms it again, on the configuration
  the study then chooses), and the reservation of ``final_test.evaluation`` applies the
  confirmation's whole rule (``preconditions.opening_missing``: the stale map, full
  currency, the configuration chosen now, nothing to confirm again), with a junior message
  in the study language; nothing is opened when it refuses.
* E4-2: after an opening made before the delayed-label fix, ``next_action`` says the final
  test cannot be recomputed and names what remains (the conclusion, with the verdicts its
  rule allows), never ``run diag.final_test`` in a loop.
* E4-3: every ``next_action`` the engine emits in these scenarios runs as given (a policy
  evaluation carries its ``rules``; a reconfirmation its ``default_value``).
* E4-4: a clock value is written exactly ("20170301", never "2.01703e+07") and traced.
* E4-5: the report shows the development rows, the delayed-label rows left out and the rows
  used apart, and describes a forward-chaining plan as one (warm-up rows never scored), in
  English and French; ``check`` passes.
* E4-6: a French report reads "1,286" as 1.286 (the French renderer groups thousands with a
  narrow no-break space): the review-v1 binary reports, French and English, with and without
  delayed labels, pass ``hypotrail check`` with no error.
* The number-tracing gaps: "241k", "241e3" and an integer right after an ISO date are traced
  or reported, never ignored.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import (activities as act, cite, cli, commands as cmd, dependencies as dep,
                         junior, numtrace, partition, read, state as st)

import flowkit as fk
from test_review_round2_training_exclusions import OPEN, ReviewFlow
from test_review_round3_engine import (ADOPT, CHOOSE, _changed, _confirm_final, _sealed,
                                       _to_choice)

ACK = "Understood, the distribution was interrupted and its outcome is unknown; don't restart it."
WORDS = {'model_choice': CHOOSE, 'policy': ADOPT, 'final_test': OPEN,
         'conclusion': 'Yes, I conclude it is inconclusive, because the final test cannot be '
                       'recomputed'}
CONCLUSION_TEXT = ('The development evidence is all the study can cite: the final test was opened '
                   'once and cannot be recomputed.')


# --- driving the studies ----------------------------------------------------------------------

def _interrupt(f) -> None:
    """A real process killed right after its reservation (the reviewer's ``run_after_reserve``):
    the next write records an execution with an unknown outcome."""
    env = fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_after_reserve')
    subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'eda.distribution',
                    '--column', 'visit_band', '--request-id', 'kill1', '--expected-revision',
                    str(f.rev()), '--study', str(f.study)], env=env, capture_output=True,
                   text=True, timeout=600)


def _acknowledge(f) -> None:
    eid = f.view()['next_action']['execution_id']
    f.call('run', '--acknowledge-interruption', eid, '--user-words', ACK, '--request-id', f.rid(),
           '--expected-revision', f.rev(), '--study', f.study)


def _confirmed_not_opened(f) -> dict:
    """The reviewer's ``a5n``: an interrupted execution makes the opening that follows the
    confirmation refuse; the final test is confirmed and sealed."""
    _to_choice(f)
    _interrupt(f)
    out = _confirm_final(f, expect=None)
    assert out['ok'] and out['result']['opening']['status'] == 'refused'
    assert out['result']['opening']['error']['code'] == 'interrupted_execution_pending'
    assert f.state()['decisions']['final_test']['status'] == 'confirmed'
    _sealed(f)
    _acknowledge(f)
    return out


def _execute(f, nxt: dict) -> dict:
    """Execute one ``next_action`` as the engine gives it (E4-3): a run with its ``rules``,
    a proposal or reconfirmation with its ``default_value`` (the recommended value, or for
    the conclusion the first verdict it names), the junior's words on a waiting proposal."""
    kind = nxt['kind']
    if kind == 'run':
        args = [nxt['activity']]
        for rule in nxt.get('rules') or []:
            args += ['--rule', rule]
        out = f.call('run', *args, '--request-id', f.rid(), '--expected-revision', f.rev(),
                     '--study', f.study, expect=None)
        assert out.get('ok') and out['status'] in ('promoted', 'already_current'), (nxt, out)
        return out
    decision = nxt.get('decision')
    if kind == 'await_user_words':
        out = f.call('decide', 'confirm', nxt['proposal_id'], '--user-words',
                     WORDS.get(decision) or fk.default_words(decision), '--request-id', f.rid(),
                     '--expected-revision', f.rev(), '--study', f.study, expect=None)
        assert out.get('ok'), (nxt, out)
        return out
    assert kind in ('propose', 'reconfirm'), nxt
    if decision == 'conclusion':
        value = {'verdict': (nxt.get('verdicts') or ['inconclusive'])[0], 'text': CONCLUSION_TEXT}
    else:
        value = nxt.get('default_value')
        if value is None:
            value = (nxt.get('recommended') or {}).get('value')
    assert value is not None, nxt
    return f.decide(decision, value, words=WORDS.get(decision))


def _follow(f, limit: int = 14, until=lambda nxt: False) -> list[dict]:
    """Follow ``next_action`` until it is done (or ``until``): every action runs as given."""
    seen = []
    for _ in range(limit):
        nxt = f.view()['next_action']
        seen.append(nxt)
        if nxt['kind'] in ('done', 'blocked') or until(nxt):
            return seen
        _execute(f, nxt)
    steps = [(n['kind'], n.get('activity') or n.get('decision')) for n in seen]
    raise AssertionError(f'next_action did not settle: {steps}')


def _final_exposures(f) -> list[str]:
    return [e['activity'] for e in fk.exposure_records(f.study)
            if e['partition'] == partition.FINAL_TEST and e['activity'] == act.FINAL]


# --- E4-1: a confirmed final test opens only on what it was confirmed on -----------------------

def test_a_choice_changed_after_a_refused_opening_asks_the_final_test_again(tmp_path):
    """The reviewer's ``a5n`` and ``a6``: the junior changes the model choice after the
    opening was refused; the final test is never opened on the model the study no longer
    chooses, the run is refused with a junior message, and following ``next_action`` opens
    it once on the variant, after the junior confirms it again."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _confirmed_not_opened(f)
    f.decide('model_choice', 'fit.variant', words=CHOOSE)
    state = f.state()
    assert state['decisions']['policy']['status'] == 'reconfirm_required'
    assert state['decisions']['final_test']['status'] == 'reconfirm_required'
    assert 'confirmed but not opened' in state['decisions']['final_test']['reason']
    assert state['decisions']['final_test']['value'] == {'model': 'fit.logistic',
                                                          'rule': 'share:0.2'}
    record = state['invalidations'][-1]
    assert 'final_test' in record['reconfirm_required']
    out = f.run(act.FINAL, expect=2)
    error = out['error']
    assert error['code'] == 'precondition_missing'
    needs = {m['requirement'] for m in error['details']['missing']}
    assert {'decision_confirmed', 'nothing_to_reconfirm'} <= needs
    junior_message = error['details']['junior_message']
    assert junior_message.startswith('The final test cannot be opened now')
    assert 'the decision policy' in junior_message
    assert 'confirm the final test again, in your own words' in junior_message
    assert junior_message.endswith('No final-test row was read: the final test is still sealed.')
    _sealed(f)
    # The next actions: confirm the policy again (on the variant), then the final test.
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['decision'], nxt['default_value']) == (
        'reconfirm', 'policy', 'share:0.2@fit.variant')
    seen = _follow(f, until=lambda n: st.final_test_opened(f.state()))
    kinds = [(n['kind'], n.get('decision') or n.get('activity')) for n in seen]
    assert ('reconfirm', 'final_test') in kinds, kinds
    final = next(n for n in seen if (n['kind'], n.get('decision')) == ('reconfirm', 'final_test'))
    assert final['default_value'] == {'model': 'fit.variant', 'rule': 'share:0.2'}
    assert final['junior_message'].startswith('The final test is still sealed')
    state = f.state()
    assert st.final_test_opened(state)
    assert state['partition']['opening']['model'] == 'fit.variant'
    assert state['decisions']['final_test']['value'] == {'model': 'fit.variant',
                                                          'rule': 'share:0.2'}
    assert _final_exposures(f) == [act.FINAL]
    assert read.open(f.study).is_current(act.FINAL)
    # Confirming the final test again changed no result (its own mutation is quiet).
    assert all(inv['mutation'] != 'unknown' for inv in state['invalidations'])


def _confirmed_by_a_stopped_process(f, monkeypatch) -> None:
    """The process stopped between the confirmation's commit and the reservation (the
    opening never ran)."""
    _to_choice(f)
    with monkeypatch.context() as m:
        m.setattr(cmd, '_opening', lambda store, payload, request_id: None)
        _confirm_final(f)
    assert f.state()['decisions']['final_test']['status'] == 'confirmed'
    _sealed(f)


def test_results_run_again_after_a_stopped_opening_ask_the_final_test_again(tmp_path,
                                                                            monkeypatch):
    """The reviewer's ``a2``: the process stopped before the opening; the candidate and the
    variant are fitted again under an engine change no attestation covers, so the policy
    evaluation and the diagnostics become stale (the stale map, which the reservation did not
    read): the run is refused and nothing is opened; following ``next_action`` runs them
    again, asks the policy and the final test again, and opens it."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _confirmed_by_a_stopped_process(f, monkeypatch)
    with monkeypatch.context() as m:
        _changed(m, 'mlkit.study.governance')
        for activity in ('fit.logistic', 'fit.variant'):
            f.run(activity)
        state = f.state()
        assert sorted(s for s, r in state['current'].items() if r in state['stale']) == [
            'diag.binary', 'policy.evaluation']
        assert state['decisions']['final_test']['status'] == 'reconfirm_required'
        out = f.run(act.FINAL, expect=2)
        error = out['error']
        assert error['code'] == 'precondition_missing'
        missing = error['details']['missing']
        stale = next(x for x in missing if x['requirement'] == 'nothing_stale')
        assert stale['slots'] == ['policy.evaluation']
        assert {x['requirement'] for x in missing} >= {'decision_confirmed', 'nothing_stale',
                                                      'nothing_to_reconfirm'}
        text = error['details']['junior_message']
        assert 'First run again: the policy evaluation and the development diagnostics.' in text
        assert text.index('First run again') < text.index('Then confirm again: the decision '
                                                          'policy.')
        _sealed(f)
        seen = _follow(f, until=lambda n: st.final_test_opened(f.state()))
        assert [(n['kind'], n.get('activity') or n.get('decision')) for n in seen] == [
            ('run', 'policy.evaluation'), ('reconfirm', 'policy'), ('run', 'diag.binary'),
            ('reconfirm', 'final_test'), ('run', 'diag.final_test')]
        assert seen[0]['rules'] == ['share:0.2'] and seen[0]['reconfirm'] == 'policy'
        assert seen[2]['reconfirm'] == 'final_test'
        assert st.final_test_opened(f.state())
        assert _final_exposures(f) == [act.FINAL]
        s = read.open(f.study)
        assert all(s.currency(rid)['current'] for slot, rid in s.state['current'].items()
                   if slot in ('policy.evaluation', 'diag.binary', act.FINAL))


def test_the_reservation_applies_the_whole_rule_to_a_choice_changed_before_this_fix(
        tmp_path, monkeypatch):
    """A study the engine wrote before this fix: its final test stayed ``confirmed`` when the
    model choice changed after a refused opening. The reservation applies the confirmation's
    rule: refused (``chosen_configuration``, ``nothing_to_reconfirm``) before anything is
    opened, with a junior message; ``next_action`` asks the policy, then proposes the final test
    again on the configuration chosen now, never ``run final_test.evaluation``."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _confirmed_not_opened(f)
    old_engine = monkeypatch.context()
    m = old_engine.__enter__()
    m.setattr(dep, '_final_test_basis_changed', lambda *args, **kwargs: False)
    f.decide('model_choice', 'fit.variant', words=CHOOSE)
    assert f.state()['decisions']['final_test']['status'] == 'confirmed'
    out = f.run(act.FINAL, expect=2)
    assert out['error']['code'] == 'precondition_missing'
    missing = out['error']['details']['missing']
    assert [x['requirement'] for x in missing] == ['decision_confirmed', 'nothing_to_reconfirm']
    assert missing[0]['decision'] == 'policy' and missing[1]['decisions'] == ['policy']
    _sealed(f)
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['decision']) == ('reconfirm', 'policy')
    _execute(f, nxt)
    old_engine.__exit__(None, None, None)       # the new engine from here on
    assert f.state()['decisions']['final_test']['status'] == 'confirmed'
    out = f.run(act.FINAL, expect=2)
    missing = out['error']['details']['missing']
    assert [x['requirement'] for x in missing] == ['chosen_configuration']
    assert missing[0]['chosen'] == {'model': 'fit.variant', 'rule': 'share:0.2'}
    text = out['error']['details']['junior_message']
    assert ('You confirmed it for the logistic model with the rule "select the top 20% by '
            'score", and the study now chooses the variant with the rule "select the top 20% by '
            'score".') in text
    _sealed(f)
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['decision'], nxt['default_value']) == (
        'propose', 'final_test', {'model': 'fit.variant', 'rule': 'share:0.2'})
    assert nxt['junior_message'] == text
    _follow(f, until=lambda n: st.final_test_opened(f.state()))
    assert f.state()['partition']['opening']['model'] == 'fit.variant'
    assert _final_exposures(f) == [act.FINAL]


def test_a_stopped_process_with_nothing_changed_still_opens(tmp_path, monkeypatch):
    """Nothing changed after the confirmation (the kill between its commit and the
    reservation): the reservation's rule holds and ``run final_test.evaluation`` opens."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _confirmed_by_a_stopped_process(f, monkeypatch)
    assert f.view()['next_action']['activity'] == act.FINAL
    from mlkit.study import preconditions, store as sto
    assert preconditions.opening_missing(f.state(), sto.StudyStore(f.study)) == []
    # In memory: a hold on the policy (or on the final test itself) withdraws the agreement
    # the opening rests on, so the final test is asked again too.
    import copy
    for held in ('policy', 'final_test'):
        state = copy.deepcopy(f.state())
        record = dep.apply_hold(state, held, 'n_1', revision=state['revision'] + 1)
        assert 'final_test' in record['reconfirm_required'], held
        assert state['decisions']['final_test']['status'] == 'reconfirm_required'
    assert f.run(act.FINAL)['status'] == 'promoted'
    # Once opened, the opening is never asked again.
    state = copy.deepcopy(f.state())
    record = dep.apply_hold(state, 'policy', 'n_1', revision=state['revision'] + 1)
    assert 'final_test' not in record['reconfirm_required']
    assert state['decisions']['final_test']['status'] == 'confirmed'


def test_the_reservation_message_is_in_the_study_language():
    from mlkit.study import opening
    state = {'language': 'fr'}
    text = opening.reservation_message(state, [
        {'requirement': 'chosen_configuration', 'value': {'model': 'fit.logistic',
                                                          'rule': 'share:0.2'},
         'chosen': {'model': 'fit.variant', 'rule': 'share:0.2'}},
        {'requirement': 'nothing_stale', 'slots': ['policy.evaluation']},
        {'requirement': 'decision_confirmed', 'decision': 'policy'}])
    assert text.startswith("Le test final ne peut pas s'ouvrir maintenant")
    assert "l'étude choisit maintenant la variante" in text
    assert text.index('Relancez') < text.index('Confirmez ensuite')
    assert 'confirmez à nouveau le test final, avec vos propres mots' in text
    assert text.endswith("Aucune ligne de l'échantillon de test final n'a été lue : il reste "
                         'scellé.')
    from mlkit.study import audience
    junior_message = audience.next_action({'kind': 'reconfirm', 'decision': 'final_test',
                                           'message': 'x'}, 'fr')['junior_message']
    assert junior_message.startswith('Le test final est toujours scellé')


def test_confirming_the_final_test_again_changes_no_result():
    """E4-1: the final test's own mutation is quiet (it was the ``unknown`` row, which made
    everything stale, before any study could confirm it twice)."""
    state = {'decisions': {d: {} for d in st.B2_DECISION_IDS}, 'task': 'binary'}
    out = dep.effects(state, 'final_test', {'model': 'fit.logistic', 'rule': 'share:0.2'},
                      {'model': 'fit.variant', 'rule': 'share:0.2'})
    assert out['mutation'] == dep.FINAL_TEST_RECONFIRMED
    assert all(not out[k] for k in ('refit', 're_eda', 're_policy', 'reconfirm'))
    assert dep.FINAL_TEST_RECONFIRMED in dep.QUIET_MUTATIONS


# --- E4-2: after an old opening, next_action names what remains ------------------------------

def _old_opening(tmp_path, monkeypatch, language='en'):
    """A review-v1 study whose results and opening were computed before the delayed-label
    fix (simulated: the engine ignores the exclusions while they are computed)."""
    f = ReviewFlow(tmp_path, name=f'old{language}', language=language)
    with monkeypatch.context() as m:
        m.setattr(partition, 'training_exclusions', lambda state: None)
        _to_choice(f)
        f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    assert st.final_test_opened(f.state())
    return f


def _verdicts_agree(state) -> None:
    """The read side's verdicts (``opening.conclusion_verdicts``) are the ones the
    conclusion's precondition accepts."""
    from mlkit.study import opening, preconditions as pre
    assert opening.conclusion_verdicts(state) == [
        v for v in pre.conclusion_verdicts(state)
        if not pre.missing_for_decision(state, 'conclusion', {'verdict': v})]


def test_an_old_opening_never_loops_on_the_final_diagnostics(tmp_path, monkeypatch):
    """The reviewer's ``a8``: ``next_action`` was ``run diag.final_test`` forever (refused
    every time) with the opening question as its junior message."""
    f = _old_opening(tmp_path, monkeypatch)
    nxt = f.view()['next_action']
    assert nxt['kind'] == 'propose' and nxt['decision'] == 'conclusion'
    assert nxt['verdicts'] == ['inconclusive']
    _verdicts_agree(f.state())
    assert nxt['not_recomputable'] == ['diag.final_test']
    assert nxt['junior_message'].startswith('The final test was opened once, and its evaluation '
                                            'cannot be computed again: it was computed with '
                                            'development rows whose label was not known yet')
    assert 'What remains possible: conclude the study from the development evidence '\
        '(inconclusive)' in nxt['junior_message']
    assert 'do you open the sealed final test' not in json.dumps(nxt)
    # The refusal it avoids is unchanged (E3-4).
    assert f.run('diag.final_test', expect=2)['error']['code'] == 'precondition_missing'
    seen = _follow(f)
    assert [(n['kind'], n.get('decision')) for n in seen] == [('propose', 'conclusion'),
                                                             ('done', None)]
    done = seen[-1]
    assert done['not_recomputable'] == ['diag.final_test']
    assert done['junior_message'].endswith('Your conclusion is recorded; a new, independent '
                                           'final test needs a new study.')
    assert f.state()['decisions']['conclusion']['value']['verdict'] == 'inconclusive'


def test_an_old_opening_says_so_in_french(tmp_path, monkeypatch):
    f = _old_opening(tmp_path, monkeypatch, language='fr')
    nxt = f.view()['next_action']
    assert nxt['kind'] == 'propose' and nxt['verdicts'] == ['inconclusive']
    assert nxt['junior_message'].startswith("Le test final a été ouvert une fois, et son "
                                            'évaluation ne peut pas être recalculée')
    assert 'étiquettes tardives' in nxt['junior_message']
    assert '(non concluant)' in nxt['junior_message']


def test_an_interrupted_opening_never_asks_to_run_the_final_test_again(tmp_path, monkeypatch):
    """The opening's own process stopped after the reservation (the final test is opened
    and consumed, no evaluation recorded): once acknowledged, ``next_action`` never names
    ``run final_test.evaluation`` (refused as already opened)."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _confirmed_by_a_stopped_process(f, monkeypatch)
    env = fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_after_reserve')
    subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', act.FINAL, '--request-id',
                    'kill-final', '--expected-revision', str(f.rev()), '--study', str(f.study)],
                   env=env, capture_output=True, text=True, timeout=600)
    _interrupt_ack = f.view()['next_action']
    assert _interrupt_ack['kind'] in ('outcome_unknown', 'acknowledge_interruption')
    f.call('run', '--acknowledge-interruption', _interrupt_ack['execution_id'], '--user-words',
           "Understood, the final test evaluation was interrupted and its outcome is unknown; "
           "don't restart it.", '--request-id', f.rid(), '--expected-revision', f.rev(),
           '--study', f.study)
    state = f.state()
    assert st.final_test_opened(state) and act.FINAL not in state['current']
    nxt = f.view()['next_action']
    assert nxt['kind'] == 'propose' and nxt['decision'] == 'conclusion'
    assert nxt['not_recomputable'] == ['final_test.evaluation', 'diag.final_test']
    _verdicts_agree(state)
    assert nxt['verdicts'] == ['adopt_policy', 'keep_baseline', 'inconclusive']
    assert 'the opening was interrupted before its evaluation was recorded' in \
        nxt['junior_message']
    assert f.run(act.FINAL, expect=2)['error']['code'] == 'final_test_already_opened'
    seen = _follow(f)
    assert seen[-1]['kind'] == 'done'


# --- E4-3: every next_action runs as given ------------------------------------------------------

def test_the_opening_replacement_carries_its_rule(tmp_path, monkeypatch):
    """The reviewer's ``a7``: the action that replaces the opening named ``run
    policy.evaluation`` without a rule (``invalid_arguments``)."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _to_choice(f)
    with monkeypatch.context() as m:
        _changed(m, 'mlkit.study.policy')
        nxt = f.view()['next_action']
        assert (nxt['kind'], nxt['activity'], nxt['rules']) == ('run', 'policy.evaluation',
                                                               ['share:0.2'])
        assert nxt['not_current'] == ['policy.evaluation', 'diag.binary']
        seen = _follow(f, until=lambda n: st.final_test_opened(f.state()))
        assert seen[0] is not None and st.final_test_opened(f.state())
        assert read.open(f.study).is_current(act.FINAL)


@pytest.mark.parametrize('module', ['mlkit.study.trials', 'mlkit.study.governance'])
def test_every_next_action_after_a_code_change_runs_as_given(tmp_path, monkeypatch, module):
    """The round-3 scenario (``codechange_open``) and a change under the fits: from the
    adopted rule to the opened final test and the conclusion, every next action is executed
    exactly as given (``_execute`` asserts each one is accepted)."""
    f = ReviewFlow(tmp_path, outcome_delay=0)
    _to_choice(f)
    with monkeypatch.context() as m:
        _changed(m, module)
        seen = _follow(f, limit=20)
    assert seen[-1]['kind'] == 'done'
    assert st.final_test_opened(f.state())
    kinds = [(n['kind'], n.get('activity') or n.get('decision')) for n in seen]
    assert ('run', act.FINAL) not in kinds or kinds.count(('run', act.FINAL)) == 1


def test_every_next_action_of_a_delayed_label_study_runs_as_given(tmp_path):
    f = ReviewFlow(tmp_path)
    _to_choice(f)
    seen = _follow(f, limit=12)
    assert seen[-1]['kind'] == 'done' and st.final_test_opened(f.state())


# --- E4-4: clock values are written exactly ------------------------------------------------------

@pytest.mark.parametrize('value, text', [(241, '241'), (999999, '999999'),
                                         (20170301, '20170301'), (20170301.0, '20170301'),
                                         (1700000000, '1700000000'),
                                         (20170301.5, '20170301.5'), (0.000125, '0.000125'),
                                         (1e20, '100000000000000000000')])
def test_a_clock_value_is_written_exactly(value, text):
    assert st._clock_value(value) == text


@pytest.mark.parametrize('start', [20170301, 1700000000, 20170301.5])
def test_a_large_clock_is_traced_in_the_limit_text(start):
    """The reviewer's ``b3``: "arrival_yyyymmdd 2.01703e+07" named a wrong boundary, untraceable."""
    item = {'id': 'delayed_labels_excluded', 'n_rows': 2, 'clock': 'arrival_yyyymmdd',
            'final_start': start}
    state = {'partition': {'order': {'by': 'arrival_yyyymmdd', 'final_start': start},
                           'training_exclusions': {
                               'n_rows': 2, 'row_keys': '0' * 64,
                               'reasons': [{'reason': partition.DELAYED_LABEL_REASON,
                                            'count': 2}]},
                           'development': {'n_rows': 240}}}
    english = st.delayed_labels_limit(state)
    assert english is not None and f'arrival_yyyymmdd {st._clock_value(start)}' in english['text']
    assert 'e+' not in english['text']
    view = {'results': {}, 'decisions': {}, 'open_proposals': [], 'settings': {},
            'dataset': {}, 'facts': {'by_status': {}}, 'plan': [], 'not_yet_defensible': [item]}
    pool = numtrace.Pool(view)
    for text in (english['text'], junior.limit_fr(item)):
        findings, traced = numtrace.trace_text(pool, text, 'draft')
        assert findings == []
        assert [t['value'] for t in traced if t['id'] == 'partition.order.final_start'] == [
            float(start)] * 2


# --- the number-tracing gaps ---------------------------------------------------------------------

def _pool(**extra):
    view = {'results': {}, 'decisions': {}, 'open_proposals': [], 'settings': {},
            'dataset': {}, 'facts': {'by_status': {}}, 'plan': [],
            'not_yet_defensible': [{'id': 'delayed_labels_excluded', 'n_rows': 3,
                                    'clock': 'prediction_tick', 'final_start': 241}], **extra}
    return numtrace.Pool(view)


def _traced(pool, text):
    findings, found = numtrace.trace_text(pool, text, 'draft')
    return ([t.get('id') or t.get('path') for t in found],
            [f['details']['number'] for f in findings])


def test_scaled_numbers_and_numbers_after_a_date_are_traced_or_reported():
    """The reviewer's ``b1`` and ``b2``: "241k", "241e3" and "On 2026-10-25 241 clients" were
    neither traced nor reported."""
    pool = _pool()
    assert _traced(pool, 'We lost 241k clients.') == ([], ['241k'])
    assert _traced(pool, 'We lost 241e3 clients.') == ([], ['241e3'])
    assert _traced(pool, 'We lost 1.5M clients.') == ([], ['1.5M'])
    assert _traced(pool, 'On 2026-10-25 241 clients left.') == ([], ['241'])
    assert _traced(pool, 'prediction_tick 241k clients.') == ([], ['241k'])
    assert _traced(pool, 'prediction_tick 241e3') == ([], ['241e3'])
    # A date between the clock and the number is not the limit's context.
    assert _traced(pool, 'prediction_tick 2026-10-25 241 clients') == ([], ['241'])
    # The limit's own context still traces.
    assert _traced(pool, 'Here 3 development rows were left out (prediction_tick 241).') == (
        ['partition.training_exclusions.n_rows', 'partition.order.final_start'], [])


def test_a_scaled_number_traces_when_it_is_a_registered_value():
    results = {'eda.quality': {'result_id': 'a' * 64, 'current': True, 'integrity': 'ok',
                               'values': {'n_rows': 241317}, 'n_rows': None}}
    pool = numtrace.Pool({'results': results, 'decisions': {}, 'open_proposals': [],
                          'settings': {}, 'dataset': {}, 'facts': {'by_status': {}}, 'plan': [],
                          'not_yet_defensible': []})
    assert _traced(pool, 'The quality check read 241k rows.') == (['n_rows'], [])
    assert _traced(pool, 'The quality check read 245k rows.')[1] == ['245k']


def test_legitimate_engine_text_is_unchanged_by_the_new_readers():
    pool = _pool()
    # Times of day stay part of their date; identifiers are not numbers.
    assert _traced(pool, 'Recorded on 2026-10-25T03:58:12.123456+00:00 and 2026-10-25 04:01.') \
        == ([], [])
    assert _traced(pool, 'The rule capacity:100 and the result 4801e722aa were cited.') == (
        ['rule'], [])
    assert numtrace.scaled_numbers('a hex 4801e722 digest, top250k, the f3 format') == []


# --- E4-6: French numbers are read as French writes them ----------------------------------------

def test_french_formatting_and_reading_round_trip():
    assert cite.format_value(1.286, 'f3', 'fr') == '1,286'
    assert cite.format_value(-2.467, 'f3', 'fr') == '-2,467'
    assert cite.format_value(3842.8, 'auto', 'fr') == '3 842,8'
    assert cite.format_value(3164, 'auto', 'fr') == '3 164'
    assert cite.format_value(41188, 'int', 'fr') == '41 188'
    assert cite.format_value(0.125, 'pct1', 'fr') == '12,5 %'
    for value, fmt in ((1.286, 'f3'), (-2.467, 'f3'), (3842.8, 'auto'), (3164, 'auto'),
                       (41188, 'int'), (0.125, 'pct1'), (1234567.25, 'f2')):
        shown = cite.format_value(value, fmt, 'fr')
        [token] = cite.parse_numbers(shown, 'fr')
        assert cite.shown_matches(token, value), (value, shown, token)
    # English reads a comma followed by groups of three digits as thousands, French never.
    assert cite.parse_numbers('1,286', 'en')[0].value == 1286
    assert cite.parse_numbers('1,286', 'fr')[0].value == 1.286
    assert cite.parse_numbers('37 062,500', 'fr')[0].value == 37062.5
    assert cite.parse_numbers('3,842.8', 'en')[0].value == 3842.8


def test_a_french_draft_reads_three_decimals_as_decimals():
    results = {'fit.logistic': {'result_id': 'b' * 64, 'current': True, 'integrity': 'ok',
                                'values': {'coef': 1.286, 'rows': 1286}, 'n_rows': None}}
    base = {'results': results, 'decisions': {}, 'open_proposals': [], 'settings': {},
            'dataset': {}, 'facts': {'by_status': {}}, 'plan': [], 'not_yet_defensible': []}
    french = numtrace.Pool({**base, 'language': 'fr'})
    english = numtrace.Pool({**base, 'language': 'en'})
    text = 'fit.logistic donne 1,286.'
    assert [t['value'] for t in numtrace.trace_text(french, text, 'draft')[1]] == [1.286]
    assert [t['value'] for t in numtrace.trace_text(english, text, 'draft')[1]] == [1286]


def _render_and_check(f) -> dict:
    assert cli.run(['render', '--study', str(f.study)]).exit_code == 0
    return cli.run(['check', '--study', str(f.study)]).payload


def _report_text(f) -> str:
    import html
    page = (f.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', page)))


@pytest.fixture(scope='module', params=[('fr', 2), ('fr', 0), ('en', 2), ('en', 0)],
                ids=['fr-delayed', 'fr-nodelay', 'en-delayed', 'en-nodelay'])
def opened(request, tmp_path_factory):
    """The reviewer's ``c1`` and ``c2`` (and their English twins): a review-v1 binary study to
    an opened final test (with a capture), its diagnostics, rendered."""
    language, delay = request.param
    f = ReviewFlow(tmp_path_factory.mktemp(f'r4-{language}-{delay}'), language=language,
                   outcome_delay=delay)
    _to_choice(f)
    f.run('predictor.capture')
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    f.run('diag.final_test')
    f.check = _render_and_check(f)
    f.delay = delay
    return f


def test_the_review_v1_reports_pass_check(opened):
    """E4-6: the French review-v1 binary report failed its own check (``value_mismatch``:
    "1,286" read as 1,286)."""
    assert opened.check['counts'] == {'error': 0, 'warning': 0}, opened.check['findings'][:6]
    out = cli.run(['export', 'handoff', '--study', str(opened.study), '--out',
                   str(opened.study.parent / 'handoff')])
    assert out.exit_code == 0, out.payload


def test_the_report_shows_the_development_rows_apart(opened):
    """E4-5: "Development rows 238" (the rows the split uses) contradicted "240 in all, 2 left
    out"; the forward-chaining plan read "each row validated once"."""
    text = _report_text(opened)
    fr = opened.language == 'fr'
    development = 240
    if fr:
        assert f'Lignes de développement {development} ' in text
    else:
        assert f'Development rows {development} ' in text
    if opened.delay:
        if fr:
            assert ("Lignes de développement écartées pour étiquettes tardives (leur résultat "
                    "n'était pas encore connu au moment de la décision) 2 ") in text
            assert ('Lignes de développement utilisées par le découpage, les modèles et la '
                    'sélection 238 ') in text
        else:
            assert ('Development rows left out for delayed labels (their outcome was not known '
                    'yet at the decision time) 2 ') in text
            assert 'Development rows the split, the models and the selection use 238 ' in text
    for wrong in ('each row validated once', 'Stratified split.', 'Validation rows 19',
                  'Training rows 2'):
        assert wrong not in text, wrong
    if fr:
        assert 'Plis de validation croisée progressive' in text
        assert "Lignes d'amorçage (elles entraînent le premier pli et ne sont jamais évaluées)" \
            in text
        assert 'Test final 60 ' in text
    else:
        assert 'Forward-chaining folds' in text
        assert 'Warm-up rows (they train the first fold and are never scored) 40 ' in text
        assert ('Rows scored out of fold (each once, by a model fitted on earlier rows only) '
                f'{200 - opened.delay} ') in text
        assert 'the earliest rows (the warm-up) train but are never scored' in text
        assert 'Final test 60 ' in text


def _legacy_flow(base: Path, task: str, language: str) -> fk.Flow:
    case_dir = fk.make_case(base / f'case-{task}', n_rows=300, task=task)['case'].parent
    f = fk.Flow(base / f'study-{task}', case_dir, prefix=task[:3])
    f.call('init', '--case', case_dir, '--study', f.study, '--lang', language)
    f.pauses(split=False)
    f.decide('split', st.b1_default_value(f.state(), 'split'))
    f.model_decisions()
    f.run('split')
    f.run('fit.baseline')
    f.run('fit.linear' if task == 'regression' else 'fit.logistic')
    f.variant()
    if task == 'regression':
        f.run('evaluate.regression')
        f.decide('model_choice', 'fit.linear', words='Yes, I choose that model because its '
                                                     'error is smaller')
    else:
        f.run('policy.evaluate', '--rule', 'capacity:30')
        f.decide('policy', 'capacity:30', words=ADOPT)
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    return f


def _review_regression_flow(base: Path, monkeypatch, language: str) -> fk.Flow:
    """A review-v1 regression study on a future case with delayed labels (round 3's
    ``_regression_flow``, in ``language``), to an opened final test."""
    from test_review_round3_engine import REG_CRITERION, REG_WORDS, TUNED
    from mlkit.study import governance
    mod = fk._module
    original = mod.make_case
    with monkeypatch.context() as m:
        m.setattr(mod, 'make_case', lambda out_dir, n_rows=300, **kw:
                  original(out_dir, task='regression', n_rows=n_rows))
        paths = mod.make_review_case(base / 'case-reg', future=True, outcome_delay=5,
                                     n_rows=300)
    f = fk.Flow(base / 'reg', paths['case'].parent, prefix='reg')
    f.call('init', '--case', paths['case'], '--study', f.study, '--reliability-profile',
           'review-v1', '--lang', language)
    f.decide('prediction_time', 'Predict using information available at the planted decision '
                                'time')
    f.decide('feature_availability', fk.availability(f.case_dir))
    f.decide('split', st.b1_default_value(f.state(), 'split'))
    f.decide('success_criterion', REG_CRITERION)
    f.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    f.run('split')
    for activity in ('fit.baseline', 'fit.linear', 'diag.regression'):
        f.run(activity)
    f.decide('model_variant', {'variants': [TUNED]})
    f.run('fit.variant')
    f.run('evaluate.regression')
    f.decide('model_choice', 'fit.linear', words=REG_WORDS)
    f.run('diag.regression')
    f.decide('final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
    f.run('diag.final_test')
    return f


@pytest.mark.parametrize('language', ['fr', 'en'])
@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_reports_of_the_other_case_kinds_pass_check(tmp_path, task, language):
    """E4-6: the other kinds of studies (no review profile, binary and regression) pass their
    own check in French and English once their final test is opened."""
    f = _legacy_flow(tmp_path, task, language)
    out = _render_and_check(f)
    assert out['counts'] == {'error': 0, 'warning': 0}, out['findings'][:6]


@pytest.mark.parametrize('language', ['fr', 'en'])
def test_a_review_v1_regression_report_passes_check(tmp_path, monkeypatch, language):
    f = _review_regression_flow(tmp_path, monkeypatch, language)
    out = _render_and_check(f)
    assert out['counts'] == {'error': 0, 'warning': 0}, out['findings'][:6]
    text = _report_text(f)
    if language == 'fr':
        assert 'Plis de validation croisée progressive' in text
        assert "Lignes d'amorçage (elles entraînent le premier pli et ne sont jamais prédites)" \
            in text
    else:
        assert 'Warm-up rows (they train the first fold and are never predicted)' in text
        assert 'Development rows left out for delayed labels (their outcome was not known yet ' \
            'at the decision time) 5 ' in text
