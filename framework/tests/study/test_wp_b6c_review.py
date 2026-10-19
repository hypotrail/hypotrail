"""WP-B6c: the fresh review of v0.2b, each finding with its test.

* B1: the binary final-test criterion is shown in percentage points at its registered size
  (the value is already in points); ``check`` catches a value shown 100 times too large
  (``test_report_and_notebook_real.py`` holds the real-study checks).
* H1: the data section says the final test was opened, and that something changed after.
* H3: under cross-validation a capacity or a share is applied within each fold (pure
  functions here; Bank full in ``test_wp_b1_integration.py``).
* H4: once opened, the criterion is judged on the final test; a ``keep_baseline`` verdict
  against a met final criterion is a limit and a check warning.

Studies and cases live in ``tmp_path``; the committed cases are only read.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pytest

from mlkit.study import cmd_check, commands as cmd, concepts, confirm as cf, governance
from mlkit.study import manifest as mf, policy, state as st

import flowkit as fk
from flowkit import Flow

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'


# --- helpers ----------------------------------------------------------------------------------

def _flow(tmp_path, task='binary', n_rows=600) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.linear' if task == 'regression' else 'fit.logistic')
    flow.variant()
    if task == 'binary':
        flow.run('policy.evaluate', '--rule', 'capacity:40')
        flow.decide('policy', 'capacity:40',
                    words='Yes, I adopt that rule because the desk can make that many calls')
    else:
        flow.run('evaluate.regression')
        flow.decide('model_choice', 'fit.linear',
                    words='Yes, I choose that model because its error is smaller')
    return flow


def _open(flow):
    value = st.b1_default_value(flow.state(), 'final_test')
    pid = flow.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
                    '--restatement', 'You open the sealed final test once, for the chosen '
                                     'configuration.', '--rationale', 'Everything is chosen.',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)['result']['proposal_id']
    out = flow.call('decide', 'confirm', pid, '--user-words', OPEN_WORDS, '--request-id',
                    flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)
    assert out['result']['opening']['status'] == 'promoted'


def _page(flow) -> str:
    flow.call('render', '--study', flow.study)
    return (flow.study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')


def _section(page: str, sid: str) -> str:
    return re.search(rf'<section class="card[^"]*" id="{sid}">.*?</section>', page,
                     re.S).group(0)


@pytest.fixture(scope='module')
def opened(tmp_path_factory):
    flow = _flow(tmp_path_factory.mktemp('b6c_open'))
    _open(flow)
    return flow


# --- H1: the data section after the opening ----------------------------------------------------

def test_the_data_section_says_the_final_test_was_opened(opened, tmp_path):
    flow = Flow(fk.clone(opened.study, tmp_path / 'study'), opened.case_dir, prefix='h1')
    data = _section(_page(flow), 'data')
    assert 'no final test' not in data and 'stay sealed' not in data
    assert 'it has been opened once to measure the chosen configuration' in data
    assert 'Something changed after the opening' not in data
    # A change after the opening: the data section says so too.
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    flow.decide('policy', 'capacity:30',
                words='Yes, I adopt that rule because the desk now has thirty slots')
    assert flow.view()['final_test']['post_final_test'] is True
    data = _section(_page(flow), 'data')
    assert 'Something changed after the opening' in data


# --- H4: the criterion judged on the final test ------------------------------------------------

def _view(final_status, dev_point, verdict, final_model='fit.logistic',
          final_rule='capacity:10'):
    gain = {'met': 8.0, 'uncertain': 6.0, 'not_met': 1.0}[final_status]
    low = {'met': 2.0, 'uncertain': -1.0, 'not_met': -3.0}[final_status]
    results = {
        'policy.evaluation': {'current': True, 'integrity': 'ok', 'result_id': 'r_pol',
                              'values': {'rules': {'capacity:10': {'deltas': {
                                  'fit.logistic': {'precision': {
                                      'point': dev_point, 'low': dev_point - 0.03,
                                      'high': dev_point + 0.03}}}}}}},
        'final_test.evaluation': {'current': True, 'integrity': 'ok', 'result_id': 'r_fin',
                                  'values': {'model': final_model, 'rule': final_rule,
                                             'criterion': {'status': final_status, 'gain': gain,
                                                           'low': low, 'high': gain + 4,
                                                           'minimum': 5,
                                                           'unit': 'percentage points',
                                                           'interval_includes_zero':
                                                               low <= 0}}}}
    decisions = {'success_criterion': {'status': 'confirmed',
                                       'value': {'metric': 'precision_gain', 'min_points': 5}},
                 'policy': {'status': 'confirmed', 'value': 'capacity:10'},
                 'conclusion': {'status': 'confirmed', 'value': {'verdict': verdict,
                                                                 'text': 'x'}}}
    return {'task': 'binary', 'decisions': decisions, 'results': results,
            'open_proposals': []}


@pytest.mark.parametrize('final_status, dev_point, verdict, judged, contradicts, keeps', [
    # The development figures met the criterion, the final test does not: adopting is
    # flagged, keeping the baseline is not.
    ('not_met', 0.10, 'adopt_policy', 'not_met', True, False),
    ('uncertain', 0.10, 'adopt_policy', 'uncertain', True, False),
    ('not_met', 0.10, 'keep_baseline', 'not_met', False, False),
    # The development figures did not meet it, the final test does: adopting is consistent,
    # keeping the baseline is a tension to explain.
    ('met', 0.02, 'adopt_policy', 'met', False, False),
    ('met', 0.02, 'keep_baseline', 'met', False, True),
])
def test_once_opened_the_criterion_is_judged_on_the_final_test(final_status, dev_point, verdict,
                                                                judged, contradicts, keeps):
    out = governance.assess(_view(final_status, dev_point, verdict))
    assert out['judged_on'] == 'final_test' and out['judged_status'] == judged
    assert out['status'] == ('met' if dev_point == 0.10 else 'not_met')   # context
    assert out['contradicts_verdict'] is contradicts
    assert governance.keeps_against_met(out) is keeps
    findings = cmd_check.check_criterion({'criterion': out})
    codes = [f['code'] for f in findings]
    if contradicts:
        assert codes == ['verdict_contradicts_criterion']
        assert findings[0]['details']['judged_on'] == 'final_test'
        assert 'on the final test' in findings[0]['message']
    elif keeps:
        assert codes == ['verdict_keeps_baseline_against_criterion']
        assert findings[0]['severity'] == 'warning'
        assert 'keeps the baseline although' in findings[0]['message']
        assert 'say which' in findings[0]['message']
    else:
        assert codes == []


def test_a_final_evaluation_of_another_configuration_does_not_judge_the_criterion():
    # The policy changed after the opening: the final test measured capacity:20.
    out = governance.assess(_view('met', 0.02, 'keep_baseline', final_rule='capacity:20'))
    assert out['judged_on'] == 'development' and out['judged_status'] == 'not_met'
    assert governance.keeps_against_met(out) is False
    out = governance.assess(_view('met', 0.10, 'adopt_policy', final_model='fit.variant'))
    assert out['judged_on'] == 'development'


def test_the_verdict_card_shows_one_judged_criterion(opened, tmp_path):
    view = opened.view()
    crit = view['criterion']
    assert crit['judged_on'] == 'final_test'
    assert crit['judged_status'] == crit['final_test']['status']
    verdict = _section(_page(Flow(fk.clone(opened.study, tmp_path / 'study'),
                                  opened.case_dir, prefix='h4')), 'verdict')
    row = verdict[verdict.index('<dt>Success criterion</dt>'):]
    row = row[:row.index('</dd>')]
    assert 'on the final test, where it is judged once the final test is opened' in row
    assert f'data-development-status="{crit["status"]}"' in row
    assert ('They differ because' in row) is (crit['status'] != crit['judged_status'])
    # One status badge for the criterion: the final-test figures row has none.
    final_row = verdict[verdict.index('Success criterion on the final test'):]
    final_row = final_row[:final_row.index('</dd>')]
    assert 'class="badge' not in final_row
    assert 'Precision gain over the baseline' in final_row


# --- H3: rules within each fold (pure) ----------------------------------------------------------

def test_a_share_is_applied_within_each_fold():
    # Two folds whose models score on different scales: pooled, the top 50 % are all rows of
    # fold 2; within folds, the best half of each fold.
    y = np.array([1, 0, 0, 0, 1, 0, 0, 0], dtype=float)
    score = np.array([0.30, 0.20, 0.10, 0.05, 0.90, 0.95, 0.85, 0.80])
    groups = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    pooled = policy.evaluate(y, score, 'share:0.25')
    within = policy.evaluate(y, score, 'share:0.25', groups)
    assert pooled['true_positives'] == 1 and pooled['selected'] == 2      # fold 2 only
    assert within['selection_scope'] == 'within_fold' and within['capacity'] == 2
    assert within['true_positives'] == 1 and within['selected'] == 2
    assert [f['capacity'] for f in within['by_fold']] == [1, 1]
    assert [f['true_positives'] for f in within['by_fold']] == [1, 0]
    assert [f['precision'] for f in within['by_fold']] == [1.0, 0.0]
    # A capacity keeps its share of the rows in each fold: capacity:4 of 8 is half of each.
    cap = policy.evaluate(y, score, 'capacity:4', groups)
    assert [f['capacity'] for f in cap['by_fold']] == [2, 2] and cap['capacity'] == 4
    assert cap['true_positives'] == 2      # fold 1: rows 0 and 1; fold 2: rows 5 and 4
    assert policy.evaluate(y, score, 'capacity:4')['true_positives'] == 1
    # A threshold reads the scores as they are.
    th = policy.evaluate(y, score, 'threshold:0.5', groups)
    assert th['selection_scope'] == 'pooled' and th['selected'] == 4
    # The weights select the same rows as the counts.
    w, _ = policy.weights(score, 'share:0.25', groups)
    assert w.tolist() == [1, 0, 0, 0, 0, 1, 0, 0]
    gain = policy.gain_points(y, score, shares=(0.25,), groups=groups)
    assert gain['selection_scope'] == 'within_fold'
    assert gain['points'][0]['true_positives'] == 1 and gain['points'][0]['capacity'] == 2


def test_the_within_fold_bootstrap_keeps_each_fold_and_its_capacity():
    rng = np.random.default_rng(3)
    n = 300
    groups = np.repeat([1, 2, 3], 100)
    y = (rng.random(n) < 0.2).astype(float)
    score = rng.random(n) + groups            # a different scale per fold
    base = np.full(n, y.mean())
    out = policy.paired_bootstrap(y, {'fit.baseline': base, 'fit.logistic': score},
                                  'share:0.1', 50, 7, groups=groups)
    assert out['method'] == 'paired percentile bootstrap, rows resampled within each fold'
    point = policy.evaluate(y, score, 'share:0.1', groups)
    assert out['deltas']['fit.logistic']['precision']['point'] == pytest.approx(
        point['precision'] - y.mean())
    # Every replicate selects exactly the summed capacity (10 rows per fold).
    assert out['intervals']['fit.logistic']['volume']['low'] == 30
    assert out['intervals']['fit.logistic']['volume']['high'] == 30
    again = policy.paired_bootstrap(y, {'fit.baseline': base, 'fit.logistic': score},
                                    'share:0.1', 50, 7, groups=groups)
    assert again == out


# --- M3: no training or validation vocabulary in a cross-validated study ----------------------

TRAIN_VALIDATION = re.compile(r'validation|training rows?|training partition|training mean|'
                              r'training base rate|training and validation', re.I)
# Legitimate uses: the name of the scheme itself, and the generic definitions of what a model
# does with the rows it is fitted on (within a fold, the other folds' rows).
ALLOWED = re.compile(r'cross-validat\w*|cross_validation|more rows than one validation partition',
                     re.I)
GENERIC_TERMS = ('overfitting', 'regularisation', 'imputation', 'standardisation')


def _junior_text(page: str) -> str:
    """The report's text a junior reads: no annex, no style, no recorded words or values
    (the junior's own words and the case's statements are quoted as they are)."""
    from html.parser import HTMLParser

    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth, self.out = 0, []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            skip = tag in ('style', 'script') or a.get('id') == 'annex' or \
                a.get('data-literal') in ('user_words', 'decision_value', 'case', 'proposal')
            if self.depth or skip:
                self.depth += 1 if tag not in ('br', 'img', 'input', 'meta', 'link') else 0

        def handle_endtag(self, tag):
            if self.depth:
                self.depth -= 1

        def handle_data(self, data):
            if not self.depth:
                self.out.append(data)

    p = Text()
    p.feed(page)
    return ' '.join(' '.join(p.out).split())


def _offending(text: str, allowed_sentences=()) -> list[str]:
    for sentence in allowed_sentences:
        text = text.replace(' '.join(sentence.split()), ' ')
    text = ALLOWED.sub(' ', text)
    return [text[max(0, m.start() - 80):m.end() + 40] for m in TRAIN_VALIDATION.finditer(text)]


def _generic_definitions(task: str) -> list[str]:
    from mlkit.study import texts
    with texts.task_context(task), texts.scheme_context('cross_validation'):
        return [texts.glossary(t)['definition'] for t in GENERIC_TERMS if texts.glossary(t)]


@pytest.fixture(scope='module')
def opened_regression(tmp_path_factory):
    flow = _flow(tmp_path_factory.mktemp('b6c_reg'), task='regression')
    _open(flow)
    return flow


@pytest.mark.parametrize('name', ['opened', 'opened_regression'])
def test_a_cross_validated_study_speaks_of_folds_not_validation_rows(name, request, tmp_path):
    base = request.getfixturevalue(name)
    flow = Flow(fk.clone(base.study, tmp_path / 'study'), base.case_dir, prefix='m3')
    task = flow.state()['task']
    flow.run('eda.special_values')
    flow.run('eda.target_summary' if task == 'regression' else 'eda.target_rate')
    flow.run('diag.regression' if task == 'regression' else 'diag.binary')
    view = flow.view()
    assert view['decisions']['split']['value']['method'] in st.CV_METHODS
    page = _page(flow)
    found = _offending(_junior_text(page), _generic_definitions(task))
    assert not found, found
    # The plan, the next action, the limits and the junior recap.
    for step in view['plan']:
        assert not _offending(' '.join(str(step.get(k)) for k in
                                       ('title', 'question', 'expected_output'))), step
    summary = flow.call('status', '--summary', '--study', flow.study)
    texts_ = [i.get('junior_text') or i.get('text') for i in view['not_yet_defensible']]
    texts_ += list(summary['recap_junior']) + [view['next_action'].get('junior_message') or '']
    assert not [t for t in texts_ if _offending(str(t))], texts_
    # The notebook's explanations too.
    notebook = (flow.study / 'notebooks' / 'study_generated.py').read_text(encoding='utf-8')
    markdown = ' '.join(re.findall(r'mo\.md\((?:r|f)?"""(.*?)"""', notebook, re.S))
    assert not _offending(markdown, _generic_definitions(task)), _offending(markdown)
    # The split question and the regression opening are worded for the scheme and the task.
    split = next(s for s in view['plan'] if s['id'] == 'split')
    assert split['question'].startswith('How are the development rows divided into folds')
    opening = next(s for s in view['plan'] if s['id'] == 'final_test')
    if task == 'regression':
        assert opening['question'].startswith('Now that the model is chosen,')
        assert 'rule' not in opening['question']


def test_the_selection_chart_plots_the_adopted_configuration(opened, tmp_path):
    """B6c (M4): a policy that applies its rule to the variant is drawn with the variant."""
    flow = Flow(fk.clone(opened.study, tmp_path / 'study'), opened.case_dir, prefix='m4')
    chart = re.search(r'<figure data-chart="selection">.*?</figure>', _page(flow), re.S).group(0)
    assert 'models.[fit.logistic].true_positives' in chart
    assert 'Model (logistic, the candidate)' in chart
    flow.decide('policy', 'capacity:40@fit.variant',
                words='Yes, the variant with that rule because it ranks as well with fewer terms')
    assert flow.view()['criterion']['model'] == 'fit.variant'
    chart = re.search(r'<figure data-chart="selection">.*?</figure>', _page(flow), re.S).group(0)
    assert 'models.[fit.variant].true_positives' in chart
    assert 'models.[fit.logistic].true_positives' not in chart
    assert 'Model (the variant, adopted with the rule)' in chart
    assert 'each rule applied within each fold' in chart
    assert flow.call('check', '--study', flow.study)['clean'] is True


# --- H2: check binds a figure to the evidence its sentence speaks of ---------------------------

def _values(flow, slot):
    from mlkit.study import read
    return read.open(flow.study).current(slot)['output']['values']


def _check(flow, text):
    from mlkit.study import cmd_check
    return cmd_check.run_check(flow.study, text)


def _pct(v):
    return f'{100 * v:.1f}%'


def test_a_final_test_claim_traces_to_final_evidence_and_back(opened):
    final = _values(opened, 'final_test.evaluation')
    fin = final['models']['fit.logistic']
    final_auc = f'{final["ranking"]["fit.logistic"]["roc_auc"]:.3f}'
    dev_auc = f'{_values(opened, "fit.logistic")["validation"]["roc_auc"]:.3f}'
    assert final_auc != dev_auc
    # The final figure said of the final test: traced to the final evaluation.
    out = _check(opened, f'On the final test the model ranks the rows with an AUC of '
                         f'{final_auc}.')
    assert out['clean'], out['findings']
    assert out['traced'][0]['slot'] == 'final_test.evaluation'
    # A development figure said of the final test: refused.
    out = _check(opened, f'On the final test the model ranks the rows with an AUC of '
                         f'{dev_auc}.')
    assert [f['code'] for f in out['findings']] == ['untraceable_number']
    # The final figure said of the out-of-fold evidence: refused; the development one passes.
    out = _check(opened, f'Out of fold, the model ranks the rows with an AUC of {final_auc}.')
    assert [f['code'] for f in out['findings']] == ['untraceable_number']
    out = _check(opened, f'Out of fold, the model ranks the rows with an AUC of {dev_auc}.')
    assert out['clean'] and out['traced'][0]['slot'] != 'final_test.evaluation'
    # A rule's share said of the final test matches the rule the final test evaluated.
    out = _check(opened, 'With the rule of the top 40% the final test shows a precision of '
                         f'{_pct(fin["precision"])}.')
    assert 'untraceable_number' in [f['code'] for f in out['findings']]


def test_diagnostic_segment_bounds_are_not_traced_without_interval_words(opened, tmp_path):
    flow = Flow(fk.clone(opened.study, tmp_path / 'study'), opened.case_dir, prefix='h2')
    flow.run('diag.binary')
    diag = _values(flow, 'diag.binary')['models']['fit.logistic']
    bounds = [g[k] for seg in diag['segments'] for g in seg['groups']
              for k in ('precision_low', 'recall_high') if g.get(k) is not None]
    from mlkit.study import cmd_check, read, view as vm
    pool = cmd_check.Pool(vm.build(read.open(flow.study)))
    for value in bounds:
        text = f'The model selects rows with a share of {_pct(value)}.'
        _, traced = cmd_check.trace_text(pool, text, 'text')
        assert not any(t.get('slot') == 'diag.binary' and 'segments' in t.get('path', '')
                       for t in traced), traced


REVIEWER_SENTENCE = ('Avec la règle des 20 %, le test final montre une précision de {p} contre '
                     '{b} pour la base, un gain de {g} points.')


def test_a_conclusion_cannot_quote_the_final_test_after_the_rule_changed(opened, tmp_path):
    """The reviewer's sentence (Online Shoppers, os19), with this study's figures: the policy
    changed after the opening, and the final test measured another rule."""
    flow = Flow(fk.clone(opened.study, tmp_path / 'study'), opened.case_dir, prefix='h2c')
    final = _values(flow, 'final_test.evaluation')
    p = final['models']['fit.logistic']['precision']
    b = final['models']['fit.baseline']['precision']
    g = 100 * final['deltas']['fit.logistic']['precision']['point']
    text = REVIEWER_SENTENCE.format(p=f'{100 * p:.1f} %', b=f'{100 * b:.1f} %', g=f'{g:.1f}')
    before = _check(flow, text)
    assert 'final_test_figure_outdated' not in [f['code'] for f in before['findings']]
    assert 'untraceable_number' in [f['code'] for f in before['findings']]   # the 20 %
    flow.run('policy.evaluate', '--rule', 'capacity:30')
    flow.decide('policy', 'capacity:30',
                words='Yes, I adopt that rule because the desk now has thirty slots')
    assert 'policy' in flow.view()['final_test']['changed_after']
    after = _check(flow, text)
    codes = [f['code'] for f in after['findings']]
    assert codes.count('final_test_figure_outdated') == 3, after['findings']
    assert after['clean'] is False
    out = flow.call('decide', 'propose', 'conclusion', '--value-json', json.dumps(
        {'verdict': 'adopt_policy', 'text': text}), '--restatement', 'On adopte.',
        '--rationale', 'x', '--request-id', flow.rid(), '--expected-revision', flow.rev(),
        '--study', flow.study, expect=2)
    assert out['error']['code'] == 'literal_number_in_text'


def test_a_train_validation_study_keeps_its_words(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', fk.SPLIT)
    split = next(s for s in flow.view()['plan'] if s['id'] == 'split')
    assert 'between training and validation' in split['question']


# --- M1: the case's doubt survives a decision that marks the feature available ---------------

SHOPPERS = fk.REPO / 'use-cases' / 'online-shoppers'


def test_a_case_uncertain_feature_marked_available_is_a_limit(tmp_path):
    flow = Flow(tmp_path / 'study', SHOPPERS, prefix='m1')
    flow.init()
    flow.decide('prediction_time', 'when the session ends, before knowing if it purchased')
    value = {**fk.availability(SHOPPERS), 'BounceRates': 'available_at_prediction',
             'ExitRates': 'uncertain_included', 'PageValues': 'not_available'}
    flow.decide('feature_availability', value)
    item = next(i for i in flow.view()['not_yet_defensible']
                if i['id'] == 'uncertain_features_included')
    assert item['case_uncertain'] == ['BounceRates']
    assert item['features'] == ['BounceRates', 'ExitRates']
    assert 'The case calls the availability of these features uncertain' in item['text']
    assert 'BounceRates' in item['text']
    flow.call('render', '--study', flow.study)
    page = (flow.study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')
    row = re.search(r'<tr data-variable="BounceRates".*?</tr>', page, re.S).group(0)
    assert 'data-case-availability="uncertain"' in row
    assert 'The case calls its availability uncertain' in row
    other = re.search(r'<tr data-variable="ExitRates".*?</tr>', page, re.S).group(0)
    assert 'data-case-availability' not in other        # kept as uncertain: no override
    assert flow.call('check', '--study', flow.study)['clean'] is True


# --- M2: a variant that leaves a group out is confirmed with a negator ------------------------

GROUP = 'Page metrics from Google Analytics'
FR_GROUP = 'On compare le modèle avec une variante sans le groupe des métriques Google Analytics.'
EN_GROUP = 'Compare the model with a variant without the Google Analytics page metrics.'


@pytest.mark.parametrize('restatement, words', [
    (FR_GROUP, 'oui, on compare sans les métriques Google Analytics'),
    (FR_GROUP, 'Yes, compare the model without the Google Analytics page metrics'),
    (EN_GROUP, 'Yes, compare the model without the Google Analytics page metrics'),
    (EN_GROUP, 'oui, on compare sans les métriques Google Analytics'),
])
def test_a_drop_group_variant_is_confirmed_with_its_own_negator(restatement, words):
    proposal = {'proposal_id': 'p_1', 'decision_id': 'model_variant',
                'value': {'kind': 'drop_group', 'group': GROUP}, 'restatement': restatement,
                'labels': {}}
    assert cf.partial_refusal(words, proposal) is None
    state = {'task': 'binary', 'mode': 'guided', 'decisions': {}}
    assert cf.guided_problem(state, proposal, words) is None


def test_a_real_partial_refusal_of_a_variant_is_still_refused():
    proposal = {'proposal_id': 'p_1', 'decision_id': 'model_variant',
                'value': {'kind': 'regularisation', 'strength': 'strong'},
                'restatement': 'Compare the model with a strongly regularised variant.',
                'labels': {}}
    found = cf.partial_refusal('yes for the variant, not strongly regularised', proposal)
    assert found == {'negator': 'not', 'part': 'strongly'}
    message = cmd.partial_reply_message('model_variant', found)
    assert 'plafonnement' not in message and 'variant' in message
    assert '"not strongly"' in message
    assert 'plafonnement' in cmd.partial_reply_message('preprocessing')


# --- M5: the training mode asks for the timing concept of the value ----------------------------

@pytest.mark.parametrize('words, ok', [
    ('Yes, at the end of the session, before we know about the purchase', True),
    ('Yes, at the end of the session', True),
    ('Yes, before we know about the purchase', True),
    ("Oui, à la fin de la session, avant de savoir s'il y a eu achat", True),
    ('Yes, I agree with that', False),
])
def test_training_needs_the_timing_concept_of_the_value_only(words, ok):
    proposal = {'proposal_id': 'p_1', 'decision_id': 'prediction_time',
                'value': 'when the session ends, before knowing if it purchased',
                'restatement': 'The score is computed when the session ends, before we know '
                               'whether it purchased.', 'labels': {}}
    out = concepts.check({'task': 'binary', 'mode': 'training', 'decisions': {}}, proposal,
                         words)
    assert out['concepts'] == ['timing_before', 'event']
    assert (out['missing'] == []) is ok


# --- Low --------------------------------------------------------------------------------------

def test_a_final_test_value_other_than_the_choice_is_refused_when_proposed(opened, tmp_path):
    flow = Flow(fk.clone(opened.study, tmp_path / 'study'), opened.case_dir, prefix='lo')
    # Before the opening only: reproduce on a fresh choice (the clone is opened already, so
    # check the value rule directly on its state).
    state = flow.state()
    chosen = st.choice_config(state)
    assert chosen == {'model': 'fit.logistic', 'rule': 'capacity:40'}
    from mlkit.study.errors import StudyError
    from mlkit.reliability import CommandRefused
    for value in ({'model': 'fit.variant', 'rule': 'capacity:40'},
                  {'model': 'fit.logistic', 'rule': 'share:0.2'}):
        with pytest.raises((CommandRefused, StudyError)) as info:
            cmd.validate_value(state, 'final_test', value)
        assert info.value.code == 'invalid_value'
        assert info.value.details['chosen'] == chosen
    cmd.validate_value(state, 'final_test', dict(chosen))


def test_caps_or_logs_of_an_excluded_variable_are_refused(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    availability = fk.availability(case_dir)
    assert availability['desk_followups'] == 'not_available'
    flow.decide('feature_availability', availability)
    flow.decide('split', flow.view()['next_action']['default_value'])
    for field, part in (('caps', {'desk_followups': [0, 0.99]}),
                        ('log_transform', ['desk_followups'])):
        value = {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {},
                 'log_transform': [], field: part}
        out = flow.call('decide', 'propose', 'preprocessing', '--value-json', json.dumps(value),
                        '--restatement', 'You cap it.', '--rationale', 'x', '--request-id',
                        flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study,
                        expect=2)
        assert out['error']['code'] == 'invalid_value'
        assert out['error']['details']['field'] == field
        assert out['error']['details']['excluded'] == ['desk_followups']


def test_reasons_and_the_recap_are_in_the_juniors_words():
    from mlkit.study import audience
    assert audience.reason_words('policy changed (§3.7 row 5: policy.parameter)') == \
        'The decision policy changed'
    assert audience.reason_words('code of activity fit.logistic changed (§3.7 row 11)') == \
        'The code of the logistic model changed'
    assert '§' not in audience.reason_words('split changed (§3.7 row 3: x); its code changed '
                                            '(§3.7 row 11)')
    assert audience.rule_words('share:0.1') == 'select the top 10% by score'
    assert audience.rule_words('capacity:100') == 'select the top 100 by score'
    assert 'call' not in audience.rule_words('threshold:0.3')
    limit = audience.limit({'id': 'adopted_rule_not_evaluated', 'rules': ['share:0.1'],
                            'text': 'The adopted policy share:0.1 has no current evaluation.'})
    assert 'share:0.1' not in limit['junior_text']
    assert 'select the top 10% by score' in limit['junior_text']


def test_the_junior_recap_names_the_folds_and_the_opening_in_words(opened):
    from mlkit.study import read, view as vm
    recap = ' '.join(vm.summary(vm.build(read.open(opened.study)))['recap_junior'])
    assert 'stratified on the outcome' in recap and 'kfold' not in recap
    assert 'the final test, opened once' in recap
    assert 'the opening of the final test opened' not in recap
    assert ' call ' not in f' {recap} '
