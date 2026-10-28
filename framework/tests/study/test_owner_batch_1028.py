"""Owner batch of 2026-10-28, engine part (CLI-CONTRACT §17.6; remarks R35 to R49 of
``docs/acceptance/runs/copilot-companion-2026-10-26.md``).

One real-CLI walkthrough of Auto MPG, in French, with the study panel on at stage v3 (through
``cli.run``, as the agent's terminal does), where the junior chooses the RMSE as the
criterion's metric. It checks, on the outputs the agent and the panel read:

* R35: within the session the walkthrough runs in, a place at Now has no panel line; a place
  elsewhere (the path, a figure of another step) has its line, in the block-quote form;
* R36, R37: ``next_action.plan_recap`` lists the study's own steps in plan order (Qualité,
  Préparation, Exploration) and the split names k;
* R38: the step-1 card and the digest give the duplicates and the declared groups
  (``car_name``) before the split, the same in both;
* R40, R45: the plan runs the exploration charts itself (the target by each kept feature,
  the correlation matrix, the distributions), each target chart counted as a look;
* R40: ``evidence`` names the results each proposal rests on;
* R40, R41: the preparation's per-column verdicts, the changed column first, the others
  with the threshold that left them unchanged;
* R46: an unknown metric is refused; the RMSE criterion, its selection and the criterion per
  configuration read the RMSE;
* R47: the trial budget reads two of three after two confirmed and fitted variants;
* R43, R48: the step's limit line and the criterion judged on the final test.

The agent's words are a test script; this is not a Copilot or Claude Code session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import flowkit as fk
import test_journey_walkthrough as jw
from mlkit.study import companion_env as ce, criterion as crit, governance

MARK = ce.LINE_MARK['fr']
RMSE = {'metric': 'rmse_reduction', 'min_share': 0.1}
KEPT = ('cylinders', 'displacement', 'horsepower', 'weight', 'origin')


class _RmseFlow(fk.Flow):
    """The test junior chooses the RMSE at the success criterion (R46). Since the lot of
    2026-10-28 (EN-9) a new study chooses the measure at its own step first, so the junior
    chooses the RMSE there too."""

    def call(self, *args, expect=0):
        args = [str(a) for a in args]
        if args[:3] == ['decide', 'propose', 'success_criterion'] and '--value-json' in args:
            args[args.index('--value-json') + 1] = json.dumps(RMSE)
        if args[:3] == ['decide', 'propose', 'error_metric'] and '--value-json' in args:
            args[args.index('--value-json') + 1] = json.dumps({'metric': 'rmse'})
        return super().call(*args, expect=expect)


def _digest(f) -> dict:
    return f.call('status', '--summary', '--digest', '--study', f.study)


@pytest.fixture(scope='module')
def walked(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv(ce.ENV_VAR, '1')
    mp.setenv(ce.STAGE_ENV, 'v3')
    base = tmp_path_factory.mktemp('owner-1028')
    f = _RmseFlow(base / 'study', jw.AUTO_MPG, prefix='o')
    seen = {'init': f.call('init', '--case', jw.AUTO_MPG, '--study', f.study, '--lang', 'fr'),
            'card': f.call('data', '--study', f.study),
            'step1_digest': _digest(f), 'reads': [], 'writes': [], 'refused': None,
            'explore_digest': None}

    def on_read(label, action):
        seen['reads'].append((label, action))
        if action.get('decision') == 'success_criterion' and seen['refused'] is None:
            seen['refused'] = fk.Flow.call(
                f, 'decide', 'propose', 'success_criterion', '--value-json',
                json.dumps({'metric': 'r2_reduction', 'min_share': 0.1}), '--restatement',
                'x.', '--rationale', 'r', '--request-id', f.rid(), '--expected-revision',
                f.rev(), '--study', f.study, expect=2)
        if action.get('kind') == 'run' and action.get('activity') == 'eda.mean_by' \
                and seen['explore_digest'] is None:
            seen['explore_digest'] = _digest(f)
    seen['writes'] = jw.walk(f, 'regression', on_read=on_read)
    seen['done_digest'] = _digest(f)
    seen['full'] = f.call('status', '--summary', '--fields', 'model_selection',
                          '--study', f.study)
    seen['view'] = f.call('status', '--study', f.study)['view']
    yield f, seen
    mp.undo()


def _first(reads, predicate):
    return next(a for _, a in reads if predicate(a))


def test_the_panel_line_only_where_it_adds_something(walked):
    """R35: init opens the session (its line names the data card); afterwards a place at
    Now has no line, the end-of-study block excepted, and every other place has its line."""
    f, seen = walked
    assert seen['init']['next_action']['panel']['shown']['line'] == \
        f'{MARK}Maintenant, la fiche des données'
    elsewhere = 0
    for label, payload in seen['writes']:
        panel = payload['next_action']['panel']
        for place in (panel['where'], panel['shown']):
            if place is None:
                continue
            if place['anchor'] == 'now' and not place['label'].endswith(
                    ce.CONTENT_LABELS['fr']['done']):
                assert place['line'] is None, (label, place)
            else:
                assert place['line'] == MARK + place['label'], (label, place)
                elsewhere += place['anchor'] != 'now'
    assert elsewhere > 10


def test_the_plan_recap_follows_the_plan(walked):
    """R36, R37: the recap is the study's plan in its order, never a fixed sentence; the
    split's question names k."""
    f, seen = walked
    action = _first(seen['reads'], lambda a: a.get('decision') == 'preprocessing')
    recap = action['plan_recap']
    assert recap.startswith("Le plan, dans l'ordre : ")
    # Lot 2026-10-28 (EN-14, EN-21): full step names, the error measure's step (14 steps),
    # and « validation croisée à 5 plis » without "k".
    assert recap.index('Mesure de l\'erreur') < recap.index('Critère de succès') \
        < recap.index('Contrôle de qualité') < recap.index('Préparation') \
        < recap.index('Exploration') < recap.index('Modèles') < recap.index('Conclusion')
    assert recap.endswith('Étape actuelle : Préparation (8 sur 14).')
    split = _first(seen['reads'], lambda a: a.get('decision') == 'split')
    assert split['question'] == 'Évaluez-vous avec cette validation croisée à 5 plis ?'


def test_the_structure_is_known_at_step_1(walked):
    """R38: duplicates and the declared group column, before the split, in ``data --json``,
    its text card and the digest."""
    f, seen = walked
    dev = seen['card']['development']
    assert {'rows', 'identical_feature_rows'} <= set(dev['duplicates'])
    assert all(isinstance(dev['duplicates'][k], int) for k in ('rows', 'identical_feature_rows'))
    (group,) = dev['groups']
    assert group['column'] == 'car_name' and 0 < group['rows_in_repeated_groups'] <= dev['rows']
    assert 0 < group['groups'] < dev['rows']
    structure = seen['step1_digest']['data_structure']
    assert structure == {'duplicates': {k: dev['duplicates'][k]
                                        for k in ('rows', 'identical_feature_rows')},
                         'groups': dev['groups']}
    from mlkit.study import cmd_data
    assert f'car_name : {group["groups"]} valeurs distinctes' in cmd_data.text(seen['card'])


def test_the_plan_runs_the_exploration_charts(walked):
    """R40, R45: after the target summary and the special values, the plan runs the target
    by each kept feature, the correlation matrix and the distributions, before the models;
    each target chart is one more counted look."""
    f, seen = walked
    runs = [p['result']['slot'] for label, p in seen['writes'] if label.startswith('run:')]
    explore = [s for s in runs if s.startswith(('eda.mean_by', 'eda.correlation'))]
    assert explore == [f'eda.mean_by:{c}' for c in KEPT] + ['eda.correlation']
    assert {f'eda.distribution:{c}' for c in KEPT} <= set(runs)
    assert runs.index('eda.special_values') < runs.index('eda.mean_by:cylinders') \
        < runs.index('fit.baseline')
    # Each target chart is a look: the ledger moves by one per chart (and by the two
    # diagnostics of the models, looks too), the ledger by activity names them.
    before = seen['explore_digest']['ledger']['target_looks']['eda']
    after = seen['done_digest']['ledger']['target_looks']['eda']
    by_activity = seen['view']['eda_looks']['by_activity']
    assert by_activity['eda.mean_by'] == len(KEPT)
    assert after == before + len(KEPT) + by_activity.get('diag.regression', 0)
    assert 'eda.correlation' not in by_activity and 'eda.distribution' not in by_activity
    assert all(seen['done_digest']['results'][s]['step'] == 'train_eda'
               for s in explore if s.startswith('eda.mean_by'))


def test_evidence_and_verdicts_back_each_proposal(walked):
    """R40, R41: each data-backed proposal names the results that show it; the preparation
    gives every column's verdict with the threshold that decided it."""
    f, seen = walked
    prep = _first(seen['reads'], lambda a: a.get('decision') == 'preprocessing'
                  and a.get('kind') == 'propose')
    assert prep['evidence'] == ['eda.quality', 'eda.distribution:horsepower']
    verdicts = prep['recommended']['verdicts']
    assert verdicts[0]['column'] == 'horsepower' and verdicts[0]['changed']
    assert verdicts[0]['parameters'] == ['log_transform']
    skew = next(c for c in verdicts[0]['checks'] if c['rule'] == 'signed_log')
    assert skew['exceeds'] and skew['threshold'] == 1.0 and skew['value'] >= 1.0
    cylinders = next(v for v in verdicts if v['column'] == 'cylinders')
    assert not cylinders['changed'] and not any(c['exceeds'] for c in cylinders['checks'])
    assert cylinders['text'].endswith('pas de changement.')
    assert {c['rule'] for c in cylinders['checks']} == {'missing_indicator', 'signed_log',
                                                       'cap_extreme_tail'}
    variant = _first(seen['reads'], lambda a: a.get('decision') == 'model_variant')
    assert variant['evidence'] == ['diag.regression']
    choice = _first(seen['reads'], lambda a: a.get('decision') == 'model_choice')
    assert choice['evidence'][0] == 'evaluate.regression'
    done = _first(seen['reads'], lambda a: a.get('kind') == 'done')
    assert done['evidence'][0] == 'final_test.evaluation'
    for label, action in seen['reads']:
        if action.get('decision') in ('prediction_time', 'split', 'success_criterion'):
            assert action['evidence'] == [], label


def test_the_rmse_criterion(walked):
    """R46: an unknown metric is refused; the RMSE criterion is judged on the RMSE, and the
    one-standard-error selection and the criterion per configuration read it."""
    f, seen = walked
    refused = seen['refused']
    assert refused['error']['code'] == 'invalid_value'
    assert 'rmse_reduction' in refused['error']['details']['metrics']
    options = _first(seen['reads'], lambda a: a.get('decision') == 'success_criterion')
    metrics = {m['metric']: m['default'] for m in options['criterion_options']['metrics']}
    # Lot 2026-10-28 (EN-9): the picker offers the confirmed measure only (a study of before
    # the lot still offers both, test_lot_1028_guided).
    assert metrics == {'rmse_reduction': True}
    with pytest.raises(governance.ValueProblem):
        crit.check({'metric': 'rmse_reduction', 'min_share': 1.5}, 'regression')
    criterion = seen['view']['criterion']
    assert criterion['metric'] == 'rmse_reduction' and criterion['value'] == RMSE
    assert criterion['judged_on'] == 'final_test' and criterion['final_test']['gain'] is not None
    selection = seen['full']['model_selection']
    assert selection['metric'] == 'rmse' and selection['available']
    configs = seen['done_digest']['criterion_configurations']
    assert configs['metric'] == 'rmse_reduction'
    assert configs['bound']['path'] == 'models.[fit.baseline].rmse'
    assert all(c['path'].endswith('.rmse') for c in configs['configurations'])
    assert configs['final_test']['path'].endswith('.rmse')
    assert abs(configs['bound']['value'] - 0.9 * configs['bound']['reference']) < 1e-9


def test_the_budget_after_two_variants(walked):
    """R47: two confirmed and fitted variants use two trials of three, in the digest's ledger
    and in the budget the evaluation stored."""
    f, seen = walked
    assert seen['done_digest']['ledger']['variants'] == {'used': 2, 'max': 3, 'remaining': 1}
    from mlkit.study import read
    study = read.open(f.study)
    rid = study.state['current']['evaluate.regression']
    stored = study.result(rid)['output']['values']['model_selection']['budget']
    assert (stored['used'], stored['max'], stored['remaining']) == (2, 3, 1)


def test_the_limit_and_the_criterion_fit_the_step(walked):
    """R43, R48: the limit line fits the step (the exploration's counted looks; at the end,
    what the final test establishes); the criterion judged on the final test says so."""
    f, seen = walked
    explore = seen['explore_digest']['texts']['fr']['step_limit']
    assert explore.startswith('Ces graphiques lisent la cible des lignes de développement')
    done = seen['done_digest']['texts']
    assert done['fr']['step_limit'].startswith('Le test final mesure une fois')
    assert done['fr']['criterion_words'].startswith('erreur (RMSE) sur le test final')
    assert 'référence (prédire la moyenne)' in done['fr']['criterion_words']
    assert 'validation' not in done['fr']['criterion_words']
    assert done['en']['criterion_words'].startswith('error (RMSE) on the final test')
