"""Contract P1 (CLI-CONTRACT §17.2, the one-page study panel): the digest additions of
``status --summary --digest``, read along real walkthroughs through the CLI's own code path.

* ``automation`` and ``review_queue`` through an ``init --automation`` study walked to its
  review: ``done`` and ``total`` move as the junior adopts or changes each automatic decision;
* ``defensibility``: ``pending`` at step 1, ``warn`` while a decision is reopened or an
  automatic decision waits for its review, ``limits`` at the end;
* ``ledger``: the final test's openings, the looks at the target (exploration and step-1
  sample), the configurations tried;
* ``headlines``: one line per done step, every number a registered value of a listed result
  (or of the decision's own value), ``check --text`` clean on each line, in both languages;
* ``criterion_configurations``: the absolute bound from registered values and each
  configuration's status (Auto MPG: 10 % below the mean baseline's out-of-fold MAE of
  7.16 mpg; the binary study: the baseline's precision at the adopted rule plus the minimum);
* ``results.<slot>.channel``: a chart requested from the panel (``webview``), a run of the
  automatic runner (``cli``), a run of the chat (``chat``);
* ``data_contingent`` (§17.2.6): a first rule or model is not marked; a changed one after the
  evaluation of the first is, with its text in both languages, in ``decide propose``, the
  digest, the report and the notebook.

The synthetic binary case stands for the binary walkthrough (the Bank one takes minutes); the
words of the junior are a test script, not a Copilot session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import flowkit as fk
import test_automation as ta
import test_journey_walkthrough as jw
from mlkit.study import cite, companion_env, notebook_view, panel_digest as pd, read
from mlkit.study import view as view_mod

PRECISION_WORDS = 'Yes, I adopt that rule because the desk can act on that share'


def _digest(f: fk.Flow) -> dict:
    return f.call('status', '--summary', '--digest', '--study', f.study)


def _call(f: fk.Flow, *args, expect=0):
    return f.call(*args, '--request-id', f.rid(), '--expected-revision', f.rev(), '--study',
                  f.study, expect=expect)


def _leaves(values) -> list[float]:
    return [v for _, v in cite.leaves(values)]


def _assert_headlines(f: fk.Flow, digest: dict, tmp_path: Path) -> None:
    """Every number of every headline is a figure of a listed (current) result or a number of
    the decision's own value in words; ``check --text`` traces each line; only done steps."""
    view = f.view()
    done = [s['id'] for s in view['plan'] if s['status'] == 'done']
    assert list(digest['headlines']) == [s for s in done if s in digest['headlines']]
    by_id = {r['result_id']: r for r in view['results'].values()}
    for lang in ('en', 'fr'):
        lines = digest['texts'][lang]['headlines']
        assert list(lines) == list(digest['headlines'])
        for step_id, line in lines.items():
            entry = digest['headlines'][step_id]
            assert tuple(entry) == pd.HEADLINE_KEYS
            listed = [by_id[rid] for rid in entry['results']]
            assert all(r['current'] and r['integrity'] == 'ok' for r in listed), step_id
            leaves = [v for r in listed for v in _leaves(r['values'])]
            words = pd._decision_words({**view, 'language': lang}, entry['decision_id']) \
                if entry['decision_id'] else ''
            own = {t.value for t in cite.parse_numbers(words or '', lang)}
            for token in cite.parse_numbers(line, lang):
                assert token.value in own or any(cite.shown_matches(token, v) for v in leaves), \
                    (lang, step_id, line, token.text)
            if lang == (view.get('language') or 'en'):
                path = tmp_path / f'headline-{step_id}.txt'
                path.write_text(line, encoding='utf-8')
                check = f.call('check', '--text', path, '--study', f.study, expect=None)
                assert check['clean'], (line, check['findings'])


def _assert_final_configuration(crit: dict, view: dict, metric: str) -> None:
    """``criterion_configurations.final_test`` (§17.2.4): judged on the final test, every
    figure is a registered value of the current final evaluation (its bound from the final
    test's own baseline), never the development bound or value."""
    final = crit['final_test']
    evaluation = view['results']['final_test.evaluation']
    values = evaluation['values']
    assert tuple(final) == pd.FINAL_CONFIGURATION_KEYS
    assert tuple(final['bound']) == pd.CRITERION_BOUND_KEYS
    assert final['slot'] == view['criterion']['model'] == values['model']
    assert final['result_id'] == final['bound']['result_id'] == evaluation['result_id']
    assert final['value'] == cite.resolve(values, cite.parse_path(final['path']))
    reference = cite.resolve(values, cite.parse_path(final['bound']['path']))
    assert final['bound']['path'] == f'models.[fit.baseline].{metric}'
    assert final['bound']['reference'] == reference
    minimum = final['bound']['minimum']
    if metric == 'mae':
        assert final['bound']['value'] == pytest.approx((1 - minimum) * reference)
        assert final['point_meets_bound'] == (final['value'] <= final['bound']['value'] + 1e-12)
    else:
        assert final['bound']['value'] == pytest.approx(reference + minimum / 100)
        assert final['point_meets_bound'] == (final['value'] >= final['bound']['value'] - 1e-12)
    for key in ('gain', 'low', 'high'):
        assert final[key] == values['criterion'][key], key
    assert final['status'] == view['criterion']['final_test']['status']
    # not the development figures
    assert final['bound']['result_id'] != crit['bound']['result_id']
    assert final['bound']['value'] != crit['bound']['value']


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    """A synthetic binary study walked from ``init`` to ``done`` (English); the payload of the
    first rule proposal."""
    base = tmp_path_factory.mktemp('digest-binary')
    f, task, _ = jw.journey_flow(base, 'synthetic', 'en')
    first = {}
    jw.walk(f, task, on_write=lambda label, p: first.setdefault(label, p))
    return f, first


@pytest.fixture(scope='module')
def regression(tmp_path_factory):
    """Auto MPG walked from ``init`` to ``done`` in French; the first model choice proposal."""
    base = tmp_path_factory.mktemp('digest-regression')
    f, task, _ = jw.journey_flow(base, 'auto-mpg', 'fr')
    first = {}
    jw.walk(f, task, on_write=lambda label, p: first.setdefault(label, p))
    return f, first


def test_step_1_is_pending_with_its_sample_and_an_empty_ledger(tmp_path, synthetic_case_dir):
    f = fk.Flow(tmp_path / 'study', synthetic_case_dir)
    f.init()
    d = _digest(f)
    assert d['panel_contract'] == 2 and d['automation'] is None and d['review_queue'] is None
    assert d['defensibility']['kind'] == 'pending'
    kinds = {x['id']: x['severity'] for x in d['defensibility']['items']}
    assert kinds['unconfirmed_decisions'] == 'not_final' and kinds['no_causality'] == 'context'
    assert d['defensibility']['count'] == sum(s != 'context' for s in kinds.values())
    assert d['ledger'] == {'final_test': {'openings': 0, 'max': 1},
                           'target_looks': {'eda': 0, 'sample': 1, 'total': 1},
                           'configurations': {'tried': 0, 'reference': False}}
    assert d['sample']['recorded'] is True and len(d['sample']['row_keys']) == 8
    assert d['sample']['row_keys'] == [i['row_key'] for i in
                                       f.call('data', '--study', f.study)['rows']['items']]
    assert d['headlines'] == {} and d['criterion_configurations'] is None
    for lang in ('en', 'fr'):
        texts = d['texts'][lang]
        assert texts['sample_note'] and texts['headlines'] == {}
        assert texts['question'] is not None and texts['junior_digest']


def test_the_binary_walkthrough(binary, tmp_path):
    """The end of a binary walkthrough: ``limits``, the ledger, the headlines, the precision
    bound at the adopted rule, the channels; then a changed rule is marked, a first one not."""
    f, first = binary
    d = _digest(f)
    # the walk adopts a rule whose criterion the final test does not meet: a blocking limit
    assert f.view()['criterion']['contradicts_verdict'] is True
    assert d['defensibility']['kind'] == 'warn'
    assert {'id': 'verdict_contradicts_criterion', 'severity': 'blocking'} in \
        d['defensibility']['items']
    assert d['defensibility']['count'] == sum(x['severity'] != 'context'
                                              for x in d['defensibility']['items'])
    view = f.view()
    assert d['ledger']['final_test'] == {'openings': 1, 'max': 1}
    assert d['ledger']['target_looks'] == {'eda': view['eda_looks']['target_looks'], 'sample': 1,
                                           'total': view['eda_looks']['target_looks'] + 1}
    assert d['ledger']['configurations'] == {'tried': view['trials']['count'],
                                             'reference': True}
    _assert_headlines(f, d, tmp_path)
    assert {'policy', 'final_test', 'train_eda'} <= set(d['headlines'])
    assert d['headlines']['policy']['results'] == [view['results']['policy.evaluation']
                                                   ['result_id']]
    assert d['headlines']['policy']['basis'] == view['decisions']['policy'][
        'confirmation']['basis']

    crit = d['criterion_configurations']
    assert tuple(crit) == pd.SUMMARY_CRITERION_CONFIG_KEYS and crit['metric'] == 'precision_gain'
    evaluation = view['results']['policy.evaluation']
    rule = view['criterion']['rule']
    raw = next(r for r in evaluation['values']['rules'] if r == rule or r.startswith(rule))
    at_rule = evaluation['values']['rules'][raw]
    reference = at_rule['models']['fit.baseline']['precision']
    minimum = view['decisions']['success_criterion']['value']['min_points']
    assert crit['bound'] == {'value': reference + minimum / 100, 'reference': reference,
                             'minimum': minimum, 'result_id': evaluation['result_id'],
                             'path': f'rules.[{raw}].models.[fit.baseline].precision'}
    slots = [c['slot'] for c in crit['configurations']]
    assert slots[0] == 'fit.logistic' and slots[-1] == 'fit.baseline'
    assert set(slots) == set(evaluation['params']['models'])
    for c in crit['configurations']:
        assert tuple(c) == pd.CRITERION_CONFIGURATION_KEYS
        assert c['value'] == at_rule['models'][c['slot']]['precision']
        assert c['point_meets_bound'] == (c['value'] >= crit['bound']['value'] - 1e-12)
        if c['slot'] == 'fit.baseline':           # no paired interval with itself
            assert c['gain'] is None and c['status'] == 'not_assessed'
        else:
            delta = at_rule['deltas'][c['slot']]['precision']
            assert c['gain'] == pytest.approx(100 * delta['point'])
        if c['slot'] == view['criterion']['model']:
            assert c['judged_on'] == 'final_test'
            assert c['status'] == view['criterion']['final_test']['status']
        else:
            assert c['judged_on'] == 'development'
    _assert_final_configuration(crit, view, 'precision')

    # channels: the chat's runs, then a chart requested from the panel (W4)
    assert {r['channel'] for r in d['results'].values()} == {'chat'}
    column = next(v['name'] for g in f.call('data', '--study', f.study)['groups']
                  for v in g['variables'] if v['role'] == 'feature' and v['type'] == 'numeric')
    _call(f, 'run', 'eda.distribution', '--column', column, '--channel', 'webview')
    d = _digest(f)
    assert d['results'][f'eda.distribution:{column}']['channel'] == 'webview'
    assert list(d['results']['split'])[-2:] == ['step', 'channel']
    # The step of every result is the engine's (§17.1.1, §17.2.5), target-aware: a feature's
    # distribution under the quality step, the target's (a W4 chart) under the exploration.
    target = f.call('data', '--study', f.study)['target']['column']
    _call(f, 'run', 'eda.distribution', '--column', target, '--channel', 'webview')
    d = _digest(f)
    assert d['results'][f'eda.distribution:{column}']['step'] == 'structural_eda'
    assert d['results'][f'eda.distribution:{target}']['step'] == 'train_eda'
    view = f.view()
    for slot, item in d['results'].items():
        found = view['results'][slot]
        assert item['step'] == companion_env.step_of(
            found['activity'], slot, view['plan'],
            companion_env.target_read_of(found['activity'], found['values'])), slot
    assert d['results']['final_test.evaluation']['step'] == 'final_test'
    assert d['results']['policy.evaluation']['step'] == 'policy'

    # P1.13: the first rule was not marked; a changed rule after its evaluation is.
    assert first['propose:policy']['result']['data_contingent'] is False
    assert first['propose:policy']['result']['data_contingent_reason'] is None
    other = next(r for r in evaluation['params']['rules'] if r != rule)
    out = _call(f, 'decide', 'propose', 'policy', '--value', other, '--restatement',
                'You act on another share.', '--rationale', 'The junior asked.')
    reason = out['result']['data_contingent_reason']
    assert out['result']['data_contingent'] is True
    assert reason['kind'] == 'changed_after_validation' and reason['previous_value'] == rule
    assert reason['evaluation'] == evaluation['result_id']
    assert reason['junior_text'].startswith('This rule is proposed after you saw')
    d = _digest(f)
    [proposal] = [p for p in d['open_proposals'] if p['decision_id'] == 'policy']
    assert proposal['data_contingent'] is True and list(proposal)[-1] == 'data_contingent'
    assert d['texts']['en']['data_contingent'] == {proposal['proposal_id']:
                                                   reason['junior_text']}
    assert d['texts']['fr']['data_contingent'][proposal['proposal_id']].startswith(
        'Cette règle est proposée')
    _call(f, 'decide', 'confirm', proposal['proposal_id'], '--user-words', PRECISION_WORDS)
    html = (f.study / 'reports/study.html').read_text(encoding='utf-8')
    assert 'Changed after the earlier value' in html and 'Modifié après avoir vu' in html
    assert f.call('check', '--study', f.study, expect=None)['counts']['error'] == 0
    # a reopened decision: the pill warns
    _call(f, 'decide', 'propose', 'prediction_time', '--value', 'one week before the renewal',
          '--restatement', 'You predict a week before.', '--rationale', 'The junior asked.')
    d = _digest(f)
    pending = [p for p in d['open_proposals'] if p['decision_id'] == 'prediction_time']
    _call(f, 'decide', 'confirm', pending[0]['proposal_id'], '--user-words',
          'Yes, I want the prediction moment one week before the renewal')
    d = _digest(f)
    assert d['defensibility']['kind'] == 'warn'
    assert any(x['severity'] == 'blocking' for x in d['defensibility']['items'])
    for step_id in d['headlines']:
        assert next(s for s in f.view()['plan'] if s['id'] == step_id)['status'] == 'done'


def test_the_regression_walkthrough(regression, tmp_path):
    """Auto MPG in French: the bound is 10 % below the mean baseline's out-of-fold MAE
    (7.16 mpg), every configuration of the evaluation is listed, the baseline is not
    assessed; the headlines quote registered values in both languages; a changed model
    choice is marked."""
    f, first = regression
    d = _digest(f)
    view = f.view()
    assert d['defensibility']['kind'] == 'limits'                  # the end, nothing blocking
    caveats = [x for x in d['defensibility']['items'] if x['severity'] == 'caveat']
    assert d['defensibility']['count'] == len(caveats)
    _assert_headlines(f, d, tmp_path)
    # The French table carries its own typography (CLI-CONTRACT §17.2.3): a narrow no-break
    # space before the semicolon, as the panel shows it verbatim. A line holds no step name
    # (the panel prints it beside the line): no "Choix : Choix : …" on the path.
    choice = d['texts']['fr']['headlines']['model_choice']
    assert '\u202f; ' in choice and choice.startswith('Le modèle linéaire')
    for lang in ('en', 'fr'):
        for step_id, line in d['texts'][lang]['headlines'].items():
            name = companion_env.step_label(step_id, lang)
            assert not line.startswith(name + ':') and not line.startswith(name + '\u202f:'), \
                (lang, step_id, line)
    fr = d['texts']['fr']
    shown = json.dumps({k: fr[k] for k in view_mod.FRENCH_TYPOGRAPHY_KEYS}, ensure_ascii=False)
    for sign in ';:?!\u00bb':
        assert f' {sign}' not in shown and f'\u00a0{sign}' not in shown, sign
    assert '\u00ab ' not in shown and '\u202f:' in shown
    crit = d['criterion_configurations']
    evaluation = view['results']['evaluate.regression']
    reference = evaluation['values']['models']['fit.baseline']['mae']
    assert round(reference, 2) == 7.16 and crit['unit'] == 'mpg'
    assert crit['metric'] == 'mae_reduction'
    assert crit['bound'] == {'value': pytest.approx(0.9 * reference), 'reference': reference,
                             'minimum': 0.1, 'result_id': evaluation['result_id'],
                             'path': 'models.[fit.baseline].mae'}
    assert [c['slot'] for c in crit['configurations']][0] == evaluation['params']['candidate']
    assert {c['slot'] for c in crit['configurations']} == set(evaluation['params']['models'])
    for c in crit['configurations']:
        mae = evaluation['values']['models'][c['slot']]['mae']
        assert c['value'] == mae and c['path'] == f'models.[{c["slot"]}].mae'
        assert c['point_meets_bound'] == (mae <= crit['bound']['value'] + 1e-12)
        if c['slot'] == 'fit.baseline':
            assert (c['gain'], c['status'], c['point_meets_bound']) == (None, 'not_assessed',
                                                                        False)
        else:
            assert c['status'] in ('met', 'uncertain', 'not_met') and c['low'] <= c['high']
    chosen = next(c for c in crit['configurations'] if c['slot'] == view['criterion']['model'])
    assert chosen['judged_on'] == 'final_test'
    _assert_final_configuration(crit, view, 'mae')

    assert first['propose:model_choice']['result']['data_contingent'] is False
    other = next(m for m in evaluation['params']['models']
                 if m not in ('fit.baseline', view['decisions']['model_choice']['value']))
    out = _call(f, 'decide', 'propose', 'model_choice', '--value', other, '--restatement',
                'Vous choisissez un autre modèle.', '--rationale', 'The junior asked.')
    assert out['result']['data_contingent'] is True
    assert out['result']['data_contingent_reason']['junior_text'].startswith(
        'Ce modèle est proposé après')
    d = _digest(f)
    [proposal] = [p for p in d['open_proposals'] if p['decision_id'] == 'model_choice']
    assert d['texts']['en']['data_contingent'][proposal['proposal_id']].startswith(
        'This model is proposed after')
    assert 'data-contingent="true"' not in notebook_view.decision_html(read.open(f.study),
                                                                       'model_choice')
    _call(f, 'decide', 'confirm', proposal['proposal_id'], '--user-words',
          "Oui, je choisis ce modèle parce que son erreur est plus petite")
    # the notebook's decision cell marks the confirmed change (its decision_html)
    assert 'data-contingent="true"' in notebook_view.decision_html(read.open(f.study),
                                                                   'model_choice')


def test_automation_review_queue_and_channels(tmp_path):
    """An ``until_final_test`` study on Auto MPG: the runner's computations are ``cli``, its
    decisions wait for review (the pill warns); each adoption in the junior's words moves
    ``done`` towards ``total``."""
    f = ta._created(tmp_path / 'auto', '--automation', 'until_final_test')
    f.call('automation', 'run', '--request-id', 'auto', '--expected-revision', f.rev(),
           '--study', f.study)
    d = _digest(f)
    state = f.state()
    assert tuple(d['automation']) == pd.SUMMARY_AUTOMATION_KEYS
    assert d['automation']['variant'] == 'until_final_test'
    assert d['automation']['started_revision'] == state['automation']['started_revision']
    assert d['automation']['active'] == (state['automation']['status'] == 'running')
    assert (d['automation']['ended'] is None) == d['automation']['active']
    queue = d['review_queue']
    assert tuple(queue) == pd.SUMMARY_REVIEW_KEYS and queue['done'] == 0
    assert queue['total'] == len(queue['items']) > 3
    assert [i['decision_id'] for i in queue['items']] == \
        [x['decision_id'] for x in f.view()['review_queue']]
    assert {r['channel'] for r in d['results'].values()} == {'cli'}
    assert d['defensibility']['kind'] == 'warn'
    assert {'id': 'automatic_decisions_to_review', 'severity': 'blocking'} in \
        d['defensibility']['items']
    for _ in range(6):                   # the junior adopts the first reviews in their words
        nxt = f.view()['next_action']
        assert nxt.get('review') and nxt['kind'] in ('propose', 'reconfirm', 'await_user_words')
        if nxt['kind'] == 'await_user_words':
            ta._confirm(f, nxt['proposal_id'])
        else:
            ta._propose(f, nxt['decision'], nxt.get('default_value'))
    later = _digest(f)['review_queue']
    assert later['total'] == queue['total'] and 0 < later['done'] < queue['total']
    assert later['done'] + len(later['items']) == later['total']
