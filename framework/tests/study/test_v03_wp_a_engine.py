"""v0.3 WP-A, engine correctness (owner demo 2: R25 note, R32, R33, R34; journey review).

* one number tracer for ``hypotrail check`` and ``decide propose``
  (:mod:`mlkit.study.numtrace`): a text one accepts, the other accepts;
* rounding: a figure written at its displayed decimals, as a percentage or in percentage
  points of a share, with its sign, matches the registered value (the exact R33 values),
  and a figure no result holds, or rounded wrongly, is still refused;
* scope-bound matching: a number of a sentence that names a result, or a group, binds to
  it, never to a coincident value elsewhere;
* the single-feature signal's scores and a diagnostic's segment counts are citable;
* every write returns the post-write revision (the final-test opening);
* the binary diagnostics are keyed on the rule they were computed at (R34), and stale
  results reach the junior only when a junior surface cites them;
* ``decide propose`` says whether a preprocessing is data-contingent, and why (R32);
* "je confirme ce choix" is an endorsement, not a restatement (R25 note).

Studies and cases live in ``tmp_path``.
"""
from __future__ import annotations

import json

import pytest

from mlkit.study import cmd_check, confirm as cf, governance, numtrace, read
from mlkit.study import state as st

import flowkit as fk
from flowkit import Flow

RID = {'signal': 'a1' * 32, 'deltas': 'b2' * 32, 'month': 'c3' * 32, 'diag': 'd4' * 32,
       'target': 'e5' * 32}


def _item(rid, values, n_rows=9864, current=True):
    return {'result_id': rid, 'values': values, 'n_rows': n_rows, 'current': current,
            'integrity': 'ok', 'activity': None, 'params': {}}


def _view():
    """A view holding the R33 figures where the engine registers them."""
    signals = [{'feature': 'PageValues', 'availability': 'not_available',
                'score': 0.8658264740028677, 'rank': 1, 'flag': True},
               {'feature': 'ExitRates', 'availability': 'uncertain_included',
                'score': 0.7058538699324447, 'rank': 2, 'flag': False}]
    return {
        'results': {
            'eda.single_feature_signal': _item(RID['signal'], {
                'partition': 'train', 'metric': 'roc_auc', 'signals': signals,
                'median': 0.613035874222362, 'level': 0.75}),
            'policy.evaluation': _item(RID['deltas'], {'deltas': {
                'fit.logistic': {'precision': {'point': 0.028, 'low': 0.004, 'high': 0.051},
                                 'recall': {'point': 0.118, 'low': 0.07, 'high': 0.16}},
                'fit.variant': {'precision': {'point': -0.0244, 'low': -0.05,
                                              'high': 0.003}}}}),
            'eda.rate_by:Month': _item(RID['month'], {
                'column': 'Month', 'overall_rate': 0.1547,
                'groups': [{'value': 'Nov', 'n_rows': 2400, 'rate': 0.1416},
                           {'value': 'Dec', 'n_rows': 1394, 'rate': 0.1262}]}),
            'eda.target_rate': _item(RID['target'], {'rate': 0.1547}),
            'diag.binary': _item(RID['diag'], {'models': {'fit.logistic': {
                'confusion': {'selected': 985.0, 'precision': 0.3918},
                'segments': [{'column': 'Month', 'groups': [
                    {'value': 'Nov', 'n': 2400, 'selected': 184.0, 'precision': 0.40217,
                     'precision_low': 0.33, 'precision_high': 0.47},
                    {'value': 'Dec', 'n': 1394, 'selected': 28.0, 'precision': 0.3214,
                     'precision_low': 0.18, 'precision_high': 0.51}]}]}}}),
        },
        'decisions': {}, 'open_proposals': [], 'settings': {'bootstrap': {'level': 0.95}},
        'dataset': {}, 'facts': {'by_status': {}}, 'plan': [], 'final_test': {}}


def _numbers(text, **pool):
    findings, traced = numtrace.trace_text(numtrace.Pool(_view(), **pool), text, 'text')
    return [f['details']['number'] for f in findings
            if f['code'] in numtrace.NUMBER_CODES], traced


R33_TEXTS = [
    # "0.87" (0.8658) and "0.61" (0.6130): the single-feature signal's score and median.
    ('PageValues ranks the development rows with an out-of-fold AUC of 0.87 on its own, '
     'far above the other features (median 0.61).', ['0.87', '0.61']),
    # "2.8 points" (0.028), "11.8 points" (0.118), "-2.4" points (-0.0244): differences.
    ("The logistic model's precision gains 2.8 points over the baseline, and its recall "
     "11.8 points.", ['2.8', '11.8']),
    ("The variant's precision changes by -2.4 points.", ['-2.4']),
    # "14.2 %" (0.1416): a group's rate; "40.2 %" (0.40217) and "184": a segment.
    ('In Nov the purchase rate is 14.2 %.', ['14.2 %']),
    ('Le taux d\'achat en Nov est de 14,2 %.', ['14,2 %']),
    ('In Nov, the logistic model selected 184 sessions at the rule, with a precision of '
     '40.2 %.', ['184', '40.2 %']),
]


@pytest.mark.parametrize('text, shown', R33_TEXTS)
def test_r33_figures_are_traced_at_their_displayed_precision(text, shown):
    numbers, traced = _numbers(text)
    assert numbers == []
    assert [t['text'] for t in traced] == shown
    assert all('result_id' in t for t in traced)


@pytest.mark.parametrize('text, refused', [
    ('PageValues has an out-of-fold AUC of 0.88 on its own.', ['0.88']),      # wrong rounding
    ('PageValues has an out-of-fold AUC of 0.865 on its own.', ['0.865']),    # 0.8658 -> 0.866
    ("The logistic model's precision gains 2.9 points.", ['2.9']),
    ("The variant's precision changes by -2.5 points.", ['-2.5']),
    ("The variant's precision changes by 2.4 points.", ['2.4']),               # sign
    ('In Nov the purchase rate is 14.1 %.', ['14.1 %']),
    ('In Nov, the logistic model selected 185 sessions, with a precision of 40.3 %.',
     ['185', '40.3 %']),
    ('The model reaches 41.7 % precision on 4321 future sessions.', ['41.7 %', '4321']),
    # A share is no difference: written in points it stays untraceable (D4).
    ('The base rate is 15.5 points.', ['15.5']),
    # A metric figure is never a setting (the bootstrap level, 0.95).
    ('The model reaches 95% precision.', ['95%']),
])
def test_unregistered_or_wrongly_rounded_figures_are_still_refused(text, refused):
    assert _numbers(text)[0] == refused


def test_a_named_group_binds_its_figures_never_another_groups():
    # 184 is Nov's count: said of Dec, it is untraceable.
    assert _numbers('In Dec, the logistic model selected 184 sessions at the rule.')[0] \
        == ['184']
    # A segment figure is cited with its group named, never by coincidence.
    assert _numbers('The logistic model selected 184 sessions at the rule.')[0] == ['184']
    # Each group's own figure binds to that group.
    _, traced = _numbers('In Nov 184 sessions were selected; in Dec, 28.')
    assert [(t['text'], t['path']) for t in traced] == [
        ('184', 'models.[fit.logistic].segments.0.groups.0.selected'),
        ('28', 'models.[fit.logistic].segments.0.groups.1.selected')]


def test_a_named_result_or_the_checks_scope_binds_its_numbers():
    # 15.5 % is the overall rate of two results; a sentence that names one binds to it.
    _, traced = _numbers('In eda.rate_by:Month the overall rate is 15.5 %.')
    assert traced[0]['result_id'] == RID['month']
    _, traced = _numbers(f'Result {RID["target"][:8]} gives a rate of 15.5 %.')
    assert traced[0]['result_id'] == RID['target']
    # A figure of another result in a sentence that names one is not traced to it.
    assert _numbers('In diag.binary the purchase rate is 14.2 %.')[0] == ['14.2 %']
    # ``check --result``: the scope of every sentence that names no result.
    _, traced = _numbers('The overall rate is 15.5 %.', scope=['eda.target_rate'])
    assert traced[0]['result_id'] == RID['target']
    pool = numtrace.Pool(_view(), scope=['nothing-here'])
    assert pool.unknown_scope == ['nothing-here']


def test_digits_glued_to_a_word_are_traced_by_check_too():
    assert _numbers('Call the top250 sessions.')[0] == ['250']
    assert _numbers('The p_5 proposal, request r_1a2b, digest 1a2b3c4d5e and x2.')[0] == []


# --- check and propose share the tracer (real studies) ------------------------------------

def _ready(tmp_path, task='binary', n_rows=600) -> Flow:
    case_dir = fk.make_case(tmp_path / 'case', task=task, n_rows=n_rows)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir)
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.model_decisions()
    flow.run('split')
    return flow


def _propose(flow, decision, value, restatement, expect=0, rationale='It fits.'):
    return flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                     '--restatement', restatement, '--rationale', rationale,
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study, expect=expect)


def _clean(flow, text, **kw):
    out = cmd_check.run_check(flow.study, text, **kw)
    return [f['details'].get('number') for f in out['findings'] if f['severity'] == 'error']


@pytest.fixture(scope='module')
def evaluated(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('wpa')
    flow = _ready(tmp)
    flow.run('eda.single_feature_signal')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='I adopt capacity 40 because the desk can make 40 calls')
    flow.run('diag.binary')
    return flow


@pytest.fixture
def flow(evaluated, tmp_path):
    return Flow(fk.clone(evaluated.study, tmp_path / 'study'), evaluated.case_dir, prefix='c')


def test_the_engines_own_signal_questions_pass_check_and_propose(flow):
    values = flow.view()['results']['eda.single_feature_signal']['values']
    texts = [q['text'] for q in values.get('questions') or []]
    signal = values['signals'][0]
    texts.append(f"{signal['feature']} ranks the development rows with an out-of-fold AUC of "
                 f"{signal['score']:.2f} on its own (median {values['median']:.2f}).")
    for text in texts:
        assert _clean(flow, text) == [], text
        out = _propose(flow, 'prediction_time', 'when the record is created', text)
        assert out['result']['status'] == 'open'


def test_a_criterion_interval_accepted_by_check_is_accepted_at_propose(flow):
    crit = flow.view()['criterion']
    assert crit['gain'] is not None and crit['low'] is not None
    text = (f"On the development rows, precision gains {crit['gain']:.1f} points over the "
            f"baseline (interval {crit['low']:.1f} to {crit['high']:.1f}). This is an "
            f"association on past rows, not an effect.")
    assert _clean(flow, text) == []
    out = _propose(flow, 'conclusion', {'verdict': 'adopt_policy', 'text': text},
                   'You adopt the policy.')
    assert out['result']['status'] == 'open'
    # A figure no result holds is refused by both, with the same number.
    bad = text.replace(f"{crit['gain']:.1f} points", '97.3 points')
    assert _clean(flow, bad) == ['97.3']
    out = _propose(flow, 'conclusion', {'verdict': 'adopt_policy', 'text': bad},
                   'You adopt the policy.', expect=2)
    assert out['error']['code'] == 'literal_number_in_text'
    assert out['error']['details']['numbers'] == ['97.3']


def test_a_diagnostic_segment_count_is_citable_with_its_group(flow):
    values = flow.view()['results']['diag.binary']['values']
    segment = values['models']['fit.logistic']['segments'][0]
    group = next(g for g in segment['groups'] if g['selected'] and g['precision'] is not None
                 and numtrace._citable_label(str(g['value'])))
    text = (f"For {segment['column']} {group['value']}, the model selected "
            f"{group['selected']:.0f} rows at the rule, with a precision of "
            f"{100 * group['precision']:.1f} %.")
    assert _clean(flow, text) == []
    _propose(flow, 'prediction_time', 'when the record is created', text)


def test_check_result_option_binds_the_draft_to_known_results(flow, tmp_path):
    draft = tmp_path / 'draft.txt'
    rid = flow.view()['results']['diag.binary']['result_id']
    roc = flow.view()['results']['diag.binary']['values']['models']['fit.logistic']['roc_auc']
    draft.write_text(f'The AUC is {roc:.2f}.', encoding='utf-8')
    out = flow.call('check', '--study', flow.study, '--text', draft, '--result', rid[:8])
    assert out['clean'] and out['traced'][0]['result_id'] == rid
    out = flow.call('check', '--study', flow.study, '--text', draft, '--result', 'nope-nope',
                    expect=None)
    assert out['ok'] is False and out['error']['code'] == 'invalid_arguments'
    out = flow.call('check', '--study', flow.study, '--result', rid[:8], expect=None)
    assert out['ok'] is False and out['error']['code'] == 'invalid_arguments'


# --- post-write revision ------------------------------------------------------------------

def test_every_write_returns_the_post_write_revision(tmp_path):
    flow = _ready(tmp_path)
    for activity in ('fit.baseline', 'fit.logistic'):
        out = flow.run(activity)
        assert out['revision'] == flow.rev()
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    p = _propose(flow, 'policy', 'capacity:40', 'You call the 40 best-scored clients.')
    assert p['revision'] == flow.rev()
    done = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                     'I adopt capacity 40 because the desk can make 40 calls',
                     '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                     '--study', flow.study)
    assert done['revision'] == flow.rev()
    value = st.b1_default_value(flow.state(), 'final_test')
    p = _propose(flow, 'final_test', value, 'You open the sealed final test once.')
    opened = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                       'Yes, I open the final test now, because the model and the rule are '
                       'fixed', '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                       '--study', flow.study)
    assert opened['result']['opening']['status'] == 'promoted'
    # The opening ran after the confirmation: the payload gives the revision after both,
    # and the next command accepts it as its expected revision.
    assert opened['revision'] == flow.rev() == opened['result']['opening']['revision']
    flow.call('run', 'diag.final_test', '--request-id', flow.rid(), '--expected-revision',
              opened['revision'], '--study', flow.study)


# --- R34: diagnostics keyed on the rule they were computed at ------------------------------

def test_adopting_the_rule_the_diagnostics_were_computed_at_keeps_them_current(tmp_path):
    flow = _ready(tmp_path)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()
    diag = flow.run('diag.binary')
    rule = diag['values']['rule']
    assert diag['values']['rule_source'] in ('scenario_default', 'engine_default')
    flow.run('policy.evaluate', '--rule', rule, '--rule', 'capacity:40')
    flow.decide('policy', rule, words=f'I adopt {rule} because it fits our capacity')
    state = flow.state()
    assert state['current']['diag.binary'] == diag['result_id']
    assert diag['result_id'] not in state['stale']
    # Another rule makes them stale: they describe the rule they were computed at.
    flow.decide('policy', 'capacity:40',
                words='I adopt capacity 40 because the desk can make 40 calls')
    assert diag['result_id'] in flow.state()['stale']


def test_stale_results_reach_the_junior_only_when_cited(new_study):
    state = read.open(new_study.study_dir).state
    rid = 'f6' * 32
    state['current']['eda.target_rate'] = rid
    state['stale'] = {rid: {'reason': 'split changed', 'since': 3}}
    item = next(x for x in st.not_yet_defensible(state) if x['id'] == 'stale_results')
    assert item['junior'] is False and item['cited_by'] == []
    dec = state['decisions']['preprocessing']
    dec.update(status='confirmed', value={**governance.DEFAULT_PREPROCESSING,
                                          'motivated_by': [rid]})
    item = next(x for x in st.not_yet_defensible(state) if x['id'] == 'stale_results')
    assert item['junior'] is True
    assert item['cited_by'] == [{'result_id': rid, 'decision_id': 'preprocessing',
                                 'proposal_id': dec.get('proposal_id')}]


def test_an_uncited_stale_result_is_not_the_juniors_limit(tmp_path):
    flow = _ready(tmp_path)
    flow.run('eda.target_rate')
    # A changed preprocessing parameter after the fits marks results stale; none is cited.
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.decide('preprocessing', {**governance.DEFAULT_PREPROCESSING,
                                  'rare_category_min_rows': 5})
    state = flow.state()
    assert state['stale']
    summary = flow.call('status', '--study', flow.study, '--summary')
    limits = {x['id']: x for x in flow.view()['not_yet_defensible']}
    assert limits['stale_results']['junior'] is False
    assert not summary['recap_junior'][-1].startswith('Limit: Some results are')
    report = (flow.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-nyd="stale_results"' not in report


# --- R32: data contingency said at propose ------------------------------------------------

def test_propose_says_whether_a_preprocessing_is_data_contingent(tmp_path):
    flow = _ready(tmp_path)
    value = dict(governance.DEFAULT_PREPROCESSING)
    out = _propose(flow, 'preprocessing', value, 'The model uses the variables as they are.')
    assert out['result']['data_contingent'] is False
    assert out['result']['data_contingent_reason'] is None
    flow.run('eda.target_rate')
    out = _propose(flow, 'preprocessing', value, 'The model uses the variables as they are.')
    assert out['result']['data_contingent'] is True
    why = out['result']['data_contingent_reason']
    assert why['target_looks_before'] == 1
    assert why['looks_by_activity'] == {'eda.target_rate': 1}
    assert why['motivating_results_reading_target'] == []
    assert 'eda.target_rate' in why['text']
    # Another decision is not assessed.
    out = _propose(flow, 'prediction_time', 'when the record is created', 'You score then.')
    assert out['result']['data_contingent'] is None
    assert out['result']['data_contingent_reason'] is None


# --- R25 note: restated or endorsed --------------------------------------------------------

PROPOSAL = {'restatement': 'You follow up the top 10% of sessions by score; this choice fixes '
                           'the rule.',
            'labels': {'fr': 'Tu relances les 10 % de sessions les mieux notées ; ce choix '
                             'fixe la règle.'},
            'value': 'share:0.1'}


@pytest.mark.parametrize('words, basis', [
    ('je confirme ce choix', st.ENDORSED),
    ('je confirme cette décision', st.ENDORSED),
    ('I confirm this choice', st.ENDORSED),
    ('oui je confirme les 10 %', st.RESTATED),
    ('je confirme la relance des sessions', st.RESTATED),
])
def test_only_content_words_of_the_proposal_make_a_restatement(words, basis):
    assert cf.recorded_basis(words, PROPOSAL) == basis
