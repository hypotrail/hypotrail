"""WP-A9: fixes of the fresh review of v0.2a on a real Bank Marketing study.

* H2: ``check --text`` no longer traces a false figure to a result's internals (null band,
  quality ranges, bootstrap replicates, coefficients, ...), and a number is bound to the
  results its nearby words name ("La précision du modèle est de 10 %" fails, "finds 50
  clients" fails); legitimate figures still trace, and the rendered deliverables stay clean.
* H3: an availability status nobody discussed is "Proposed by the assistant, not discussed"
  when the case states none or another one (``proposed_not_discussed``).
* H4: the policy step carries the case's default rule (``share:0.1``) as ``default_value``.
* M1: a preparation proposed after any look at the outcome is data-contingent
  (``target_looks_before``), and the report says so in words with the motivating questions.
* M3: the generated notebook applies the confirmed preparation as readable pandas steps and
  runs headless; no doubled "Preparation:".
* M4: the step-0 recap names the data card, not the end of the plan; binned groups say how
  many bins were made; the data card and ``eda.quality`` count distinct values alike; the
  split card says "Development rows".
* M5: the evidence catalog lists the quality overview and the single-feature signal with the
  rows they read; ``run --rule`` documents ``share:p``.
* M6: junior text in words (bins, flags, structure keys, grammar, the recap's policy clause,
  excluded features in the signal chart, the narrow-screen hint, the share rule in the
  glossary).

Studies live in ``tmp_path``; the committed case is only read.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest

from mlkit.study import cli, cmd_check, cmd_data, cmd_evidence, eda, read, texts, view

import flowkit as fk
from flowkit import Flow

PREP = {'missing': 'none', 'rare_category_min_rows': 30, 'caps': {'balance': [0.01, 0.99]},
        'log_transform': ['campaign']}


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    study = tmp_path_factory.mktemp('a9') / 'bank'
    f = Flow(study, fk.BANK, prefix='a9')
    f.init()
    f.pauses(model_decisions=False)
    f.decide('success_criterion', fk.criterion(f.state()))
    f.run('split')
    for a in ('eda.target_rate', 'eda.special_values', 'eda.quality',
              'eda.single_feature_signal'):
        f.run(a)
    f.run('eda.rate_by', '--column', 'poutcome')
    f.run('eda.rate_by', '--column', 'age')
    quality = f.view()['results']['eda.quality']['result_id']
    f.decide('preprocessing', {**PREP, 'motivated_by': [quality]})
    f.run('fit.baseline')
    f.run('fit.logistic')
    f.run('policy.evaluate', '--rule', 'capacity:100')
    f.decide('policy', 'capacity:100', 'Yes, call the top 100 because the desk has 100 slots')
    return study


def _flow(study):
    return Flow(study, fk.BANK, prefix='x')


def _check(study, text):
    return cmd_check.run_check(study, text)


def _numbers(out, code='untraceable_number'):
    return [f['details']['number'] for f in out['findings'] if f['code'] == code]


# --- H2: free-text tracing ------------------------------------------------------------------

@pytest.mark.parametrize('text, number', (
    ('La précision du modèle est de 10 %.', '10 %'),
    ('The model finds 50 clients.', '50'),
    ('The precision of the model is 10%.', '10%'),
))
def test_a_false_figure_is_not_traced_to_an_unrelated_internal(bank, text, number):
    out = _check(bank, text)
    assert out['clean'] is False, out['traced']
    assert number in _numbers(out), out


def test_internal_paths_are_out_of_the_free_text_pool(bank):
    pool = cmd_check.Pool(view.build(read.open(bank)))
    paths = [i['path'] for i in pool.current]
    assert paths and not any('null_band' in p for p in paths)
    assert not any(p.startswith('ranges.') for p in paths if 'quality' in p)
    assert not [i for i in pool.current if i['slot'] == 'eda.quality'
                and i['path'].startswith('ranges')]
    assert not any(p.endswith('undefined_replicates') or 'coefficients' in p for p in paths)
    assert cmd_check.internal_path('eda.quality', 'ranges.4.max')
    assert cmd_check.internal_path('eda.rate_by:age', 'groups.0.null_band.low')
    assert not cmd_check.internal_path('policy.evaluation',
                                       'rules.[capacity:100].models.[fit.logistic].precision')


def test_legitimate_figures_still_trace(bank):
    s = read.open(bank)
    at = s.current('policy.evaluation')['output']['values']['rules']['capacity:100']['models']
    precision = at['fit.logistic']['precision']
    found = at['fit.logistic']['true_positives']
    rate = s.current('eda.target_rate')['output']['values']['rate']
    text = (f'At the top 100, the logistic model finds {found:.0f} positive rows: a precision '
            f'of {100 * precision:.1f} %. The positive rate on training rows is '
            f'{100 * rate:.1f} %.')
    out = _check(bank, text)
    assert out['clean'] is True, out['findings']
    paths = {t['text']: t.get('path') for t in out['traced']}
    assert paths[f'{100 * precision:.1f} %'].endswith('precision')


def test_binding_reads_the_words_near_a_number():
    text = 'La précision du modèle est de 10 %.'
    tok = next(t for t in cmd_check.cite.parse_numbers(text))
    bind = cmd_check.binding(text, tok.start, tok.end, tok.percent)
    assert 'precision' in bind.segments and bind.model and not bind.interval
    text = 'The model finds 50 clients.'
    tok = next(t for t in cmd_check.cite.parse_numbers(text))
    assert cmd_check.binding(text, tok.start, tok.end, False).segments == ('#count',)


def test_the_rendered_deliverables_stay_clean(bank):
    out = cmd_check.run_check(bank)
    errors = [f for f in out['findings'] if f['severity'] == 'error']
    assert errors == [], errors


# --- H3: provenance of an undiscussed availability -------------------------------------------

def test_an_undiscussed_status_the_case_does_not_state_is_the_assistant_s(bank):
    basis = _flow(bank).view()['decisions']['feature_availability']['feature_basis']
    # The case states availability for balance and duration, not for age or contact.
    assert basis['balance'] == 'default_from_case'
    assert basis['duration'] == 'default_from_case'
    assert basis['age'] == 'proposed_not_discussed'
    assert basis['contact'] == 'proposed_not_discussed'
    html = (bank / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'Proposed by the assistant, not discussed' in html
    assert view.feature_basis({'a': 'available_at_prediction'},
                              {'user_words': 'ok', 'restatement': 'r'}) \
        == {'a': 'default_from_case'}


# --- H4: the default rule of a teaching case -------------------------------------------------

def test_the_policy_step_carries_the_case_default_share(tmp_path):
    f = Flow(tmp_path / 'b', fk.BANK)
    f.init()
    defaults = f.view()['scenario_defaults']
    assert defaults['capacity_share']['value'] == 0.1
    assert defaults['capacity_share']['status'] == 'scenario_assumption'
    action = {'kind': 'run', 'step': 'policy', 'activity': 'policy.evaluation', 'message': 'm'}
    assert view._with_default_rule(action, defaults)['default_value'] == 'share:0.1'
    other = {'kind': 'propose', 'step': 'preprocessing', 'decision': 'preprocessing'}
    assert 'default_value' not in view._with_default_rule(other, defaults)
    assert 'default_value' not in view._with_default_rule(action, None)


def test_the_agent_templates_ask_the_capacity_as_a_share():
    root = fk.FRAMEWORK / 'mlkit' / 'study' / 'agent'
    claude = ' '.join((root / 'CLAUDE.md.in').read_text(encoding='utf-8').split())
    skill = ' '.join((root / 'dot-claude/skills/hypotrail-study/SKILL.md')
                     .read_text(encoding='utf-8').split())
    for doc in (claude, skill):
        assert 'scenario_defaults.capacity_share' in doc
        assert '5, 10 and 20 %' in doc and 'gain_points.points' in doc
        assert "exercise's assumption" in doc
        assert 'subscribers' not in doc
    assert 'share:<p>' in claude and 'whole campaign' not in claude


# --- M1: data-contingent preparation ---------------------------------------------------------

def test_a_preparation_after_target_looks_is_data_contingent(bank):
    value = _flow(bank).state()['decisions']['preprocessing']['value']
    assert value['data_contingent'] is True
    assert value['target_looks_before'] >= 3        # target rate, special values, rates by
    html = (bank / 'reports' / 'study.html').read_text(encoding='utf-8')
    card = html[html.index('data-decision="preprocessing"'):]
    card = card[:card.index('</article>')]
    assert 'Chosen after looking at the outcome on training rows' in card
    assert 'look' in card and 'Questions behind this preparation' in card
    question = read.open(bank).current('eda.quality')['output']['values']['question']
    assert question in card


def test_a_preparation_before_any_look_is_not_contingent(tmp_path, synthetic_case_dir):
    f = Flow(tmp_path / 's', synthetic_case_dir)
    f.init()
    f.pauses(model_decisions=False)
    f.decide('success_criterion', fk.criterion(f.state()))
    f.run('split')
    f.decide('preprocessing', {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {},
                               'log_transform': []})
    value = f.state()['decisions']['preprocessing']['value']
    assert value['data_contingent'] is False and value['target_looks_before'] == 0
    out = f.call('decide', 'propose', 'preprocessing', '--value-json', json.dumps(
        {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {}, 'log_transform': [],
         'target_looks_before': 4}), '--restatement', 'r', '--rationale', 'r',
        '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study, expect=2)
    assert out['error']['code'] == 'invalid_value'


# --- M3: readable preparation steps in the notebook -------------------------------------------

def test_the_notebook_shows_the_preparation_as_pandas_steps_and_runs(bank):
    source = (bank / 'notebooks' / 'study_generated.py').read_text(encoding='utf-8')
    assert 'Preparation: Preparation:' not in source
    assert 'nv.design_inputs(' in source
    assert '.clip(_low, _high)' in source and 'np.log1p(np.abs(_v))' in source
    assert '"(rare)"' in source and '.quantile(0.01)' in source
    assert 'pd.testing.assert_frame_equal(X_train, _engine_train)' in source
    script = ('import importlib.util, sys\n'
              f'spec = importlib.util.spec_from_file_location("nb", '
              f'{str(bank / "notebooks" / "study_generated.py")!r})\n'
              'nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n'
              'outputs, defs = nb.app.run()\n'
              'print(float(defs["validation_auc"]))\n')
    proc = subprocess.run([sys.executable, '-c', script], cwd=bank.parent, env=fk.env(),
                          capture_output=True, text=True, timeout=300,
                          stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    auc = read.open(bank).current('fit.logistic')['output']['values']['validation']['roc_auc']
    assert float(proc.stdout.strip().splitlines()[-1]) == pytest.approx(auc, abs=1e-6)


# --- M4 ---------------------------------------------------------------------------------------

def test_the_step_zero_recap_names_the_data_card(tmp_path):
    f = Flow(tmp_path / 'b', fk.BANK)
    f.init()
    summary = f.call('status', '--summary', '--study', f.study)
    nxt = summary['recap'][3]
    assert 'nothing left in the plan' not in nxt and 'data card' in nxt
    assert 'the prediction is made before the call' in summary['recap'][0]
    assert 'made Before' not in summary['recap'][0]


def test_binning_says_how_many_bins_were_made():
    assert eda.binning_words(5) == '5 training quantile bins'
    words = eda.binning_words(3)
    assert words.startswith('3 training quantile bins') and 'asked' in words


def test_bins_read_in_words(bank):
    values = read.open(bank).current('eda.rate_by:age')['output']['values']
    labels = [g['value'] for g in values['groups']]
    assert values['binned'] is True and values['binning'].startswith('5 training quantile bins')
    assert all(re.fullmatch(r'\d+ to \d+ years', v) for v in labels), labels
    assert not any('(' in v or ']' in v for v in labels)


def test_distinct_counts_agree_between_the_data_card_and_quality(bank):
    card = cmd_data.card(bank)
    card_distinct = {v['name']: v['n_distinct'] for g in card['groups'] for v in g['variables']}
    quality = read.open(bank).current('eda.quality')['output']['values']
    for item in quality['cardinality']:
        assert item['n_distinct'] == card_distinct[item['column']], item['column']
    assert card_distinct['poutcome'] == 3       # failure, other, success; "unknown" apart


def test_the_split_card_says_development_rows():
    spec = texts.activity('split')
    labels = [h['label'] for h in spec['highlights']]
    assert 'Development rows' in labels and 'Rows in the dataset' not in labels


# --- M5 ---------------------------------------------------------------------------------------

def test_the_catalog_lists_quality_and_signal_with_their_rows(bank):
    payload = cmd_evidence.evidence(bank) if hasattr(cmd_evidence, 'evidence') else None
    if payload is None:
        payload = cli.run(['evidence', '--study', str(bank)]).payload
    items = {a['activity']: a for a in payload['eda_catalog']['activities']}
    assert items['eda.quality']['partition'] == 'development'
    assert items['eda.single_feature_signal']['partition'] == 'train'
    assert items['eda.rate_by']['partition'] == 'train'
    assert not items['eda.quality']['per_column']


def test_run_help_names_the_share_rule():
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', '--help'],
                          capture_output=True, text=True, env=fk.env(), timeout=60)
    assert 'share:p' in ' '.join(proc.stdout.split())


# --- M6: junior text --------------------------------------------------------------------------

def test_the_report_speaks_in_words(bank):
    html = (bank / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert '>false<' not in html and '>False<' not in html
    assert '<code data-literal="identifier">time_column</code>' not in html
    assert '<code data-literal="identifier">group_column</code>' not in html
    assert 'Time column' in html
    assert 'Tutorial results published' not in html
    assert 'data-scroll-hint' in html and '.scroll-hint{display:none}' in html
    chart = html[html.index('data-chart="single_feature_signal"'):]
    chart = chart[:chart.index('</figure>')]
    assert 'duration' in chart and 'Not used by the model' in chart


def test_the_recap_names_the_rule_once_and_reads_well(bank):
    summary = _flow(bank).call('status', '--summary', '--study', bank)
    decided = summary['recap_junior'][1]
    assert decided.count('top 100') == 1, decided
    assert summary['recap'][1].count('capacity:100') == 1
    assert 'kept with a doubt ' not in ' '.join(summary['recap'])


def test_the_glossary_and_success_question_introduce_the_terms():
    capacity = texts.glossary('capacity')
    assert 'share' in capacity['definition']
    from mlkit.study import state as st
    step = next(s for s in st.steps('binary') if s['id'] == 'success_criterion')
    q = step['question']
    assert q.index('Precision is') < q.index('How many percentage points')
    assert 'baseline' in q and 'rule' in q



# --- WP-A9 merge with WP-B1 -----------------------------------------------------------------

def test_residual_bins_read_in_words_and_name_their_rows():
    import numpy as np
    import pandas as pd
    from mlkit.study import activities as act
    values = pd.Series(np.arange(100, dtype=float) * 10 + 1500)
    y = np.linspace(10, 40, 100)
    out = act._residual_groups('weight', values, y, {'fit.linear': y + 1.0}, 'lb',
                               'out-of-fold')
    assert out['binned'] is True
    assert out['binning'] == '5 out-of-fold quantile bins'
    labels = [g['value'] for g in out['groups']]
    assert labels[0] == '1500 to 1690 lb' and all(' to ' in v for v in labels)
    tied = act._residual_groups('x', pd.Series([1.0] * 80 + list(range(2, 32))), np.zeros(110),
                                {'fit.linear': np.zeros(110)})
    assert tied['binning'].startswith(f'{len(tied["groups"])} validation quantile bins')
    assert 'asked' in tied['binning']


@pytest.fixture(scope='module')
def cv_bank(tmp_path_factory):
    """A Bank study with cross-validation, the variant, the policy and the final test
    opened (WP-B1); the final test refuses an opening without a reason or off topic."""
    from mlkit.study import state as st
    study = tmp_path_factory.mktemp('a9cv') / 'bank'
    f = Flow(study, fk.BANK, prefix='cv')
    f.init()
    f.decide('prediction_time', 'before the call')
    f.decide('feature_availability', fk.availability(fk.BANK))
    f.decide('split', f.view()['next_action']['default_value'])
    f.model_decisions()
    f.run('split')
    f.run('eda.target_rate')
    f.run('fit.baseline')
    f.run('fit.logistic')
    f.variant()
    f.run('policy.evaluate', '--rule', 'capacity:100')
    f.decide('policy', 'capacity:100', words='Yes, call the top 100 because the desk has 100 slots')
    value = st.b1_default_value(f.state(), 'final_test')
    p = f.call('decide', 'propose', 'final_test', '--value-json', json.dumps(value),
               '--restatement', 'You open the sealed final test once.', '--rationale', 'r',
               '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    pid = p['result']['proposal_id']
    # v0.3 (WP-B, R27): no reason is required any more; off-topic words are still refused.
    for words, code in (('oui, la pizza du client est bonne', 'ambiguous_confirmation'),
                        ('ok, but not yet', 'ambiguous_confirmation')):
        out = f.call('decide', 'confirm', pid, '--user-words', words, '--request-id', f.rid(),
                     '--expected-revision', f.rev(), '--study', f.study, expect=2)
        assert out['error']['code'] == code, (words, out['error'])
    f.call('decide', 'confirm', pid, '--user-words',
           'Yes, I open the final test now, because the model and the rule are fixed',
           '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    return study


def test_cv_and_final_test_internals_are_out_of_the_free_text_pool(cv_bank):
    pool = cmd_check.Pool(view.build(read.open(cv_bank)))
    paths = [i['path'] for i in pool.current]
    assert not any('per_fold' in p or 'fold_rows' in p or p.startswith('refit') for p in paths)
    assert not any(p.endswith('undefined_replicates') for p in paths)
    assert _numbers(_check(cv_bank, 'La précision du modèle est de 10 %.')) == ['10 %']


def test_cv_and_final_test_figures_still_trace(cv_bank):
    s = read.open(cv_bank)
    spread = s.current('fit.logistic')['output']['values']['cross_validation']['spread']['roc_auc']
    final = s.current('final_test.evaluation')['output']['values']
    precision = final['models']['fit.logistic']['precision']
    text = (f'Out of fold, the AUC of the logistic model is {spread["mean"]:.2f} (from '
            f'{spread["min"]:.2f} to {spread["max"]:.2f} across folds). On the {final["n"]} '
            f'final-test rows, the precision of the logistic model at the top 100 is '
            f'{100 * precision:.1f} %.')
    out = _check(cv_bank, text)
    assert out['clean'] is True, out['findings']
