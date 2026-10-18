"""``hypotrail check`` (plan WP3.3; E1 findings F3, F4, F5)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import cmd_check, manifest as mf, read, view
from mlkit.study.store import StudyStore

import phase3_study as fx

FRAMEWORK = Path(__file__).resolve().parents[3]


def codes(result) -> list[str]:
    return [f['code'] for f in result['findings']]


def text_check(study, text):
    return cmd_check.run_check(study, text)


def _report(study) -> Path:
    return study / mf.ARTIFACTS['report']


def _commit(study, mutate):
    store = StudyStore(study)
    with store.writing() as state:
        mutate(state)
        store.commit(state, {'request_id': None, 'action': 'test.mutate', 'params': {},
                             'result': {}})


@pytest.fixture
def study(full_study):
    from mlkit.study import cmd_render
    cmd_render.render_all(full_study)
    return full_study


def test_rendered_study_is_clean(study):
    result = cmd_check.run_check(study)
    assert result['schema'] == cmd_check.SCHEMA and result['target'] == 'study'
    assert result['findings'] == [] and result['clean'] is True
    assert list(result) == ['schema', 'ok', 'study', 'revision', 'target', 'clean', 'counts',
                            'findings', 'traced']


def test_number_outside_a_cited_value_is_reported(study):
    page = _report(study).read_text()
    _report(study).write_text(page.replace('<main>', '<main><p>We reached 42 renewals and '
                                           '<span data-literal="revision">7</span>.</p>', 1))
    result = cmd_check.run_check(study)
    found = [f for f in result['findings'] if f['code'] == 'number_outside_result']
    assert [f['details']['number'] for f in found] == ['42']
    assert result['clean'] is False


def test_unknown_id_and_value_mismatches_are_reported(study):
    page = _report(study).read_text()
    rid = view.build(study)['results']['eda.target_rate']['result_id']
    marker = f'data-result-id="{rid}" data-path="rate"'
    assert marker in page
    i = page.index(marker)
    start = page.rindex('<data ', 0, i)
    end = page.index('</data>', i) + len('</data>')
    good = page[start:end]
    variants = {
        'unknown_result_id': good.replace(rid, 'f' * 64),
        'value_mismatch': good.replace('>11.9%<', '>12.9%<'),
    }
    for code, bad in variants.items():
        _report(study).write_text(page.replace(good, bad, 1))
        assert code in codes(cmd_check.run_check(study)), code
    _report(study).write_text(page.replace(good, good.replace('value="0.119', 'value="0.129'), 1))
    assert 'value_mismatch' in codes(cmd_check.run_check(study))
    _report(study).write_text(page.replace(good, good.replace('data-path="rate"',
                                                              'data-path="nope"'), 1))
    assert 'value_mismatch' in codes(cmd_check.run_check(study))


def test_a_cited_result_that_is_not_current_is_reported(study, synthetic_case_dir):
    b = fx.Builder(study, synthetic_case_dir)
    orphan = b.put('eda.target_rate', {'rate': 0.5, 'positives': 1, 'rows': 2}, promote=False)
    page = _report(study).read_text()
    _report(study).write_text(page.replace(
        '<main>', f'<main><p><data value="0.5" data-result-id="{orphan}" data-path="rate">'
        '50.0%</data></p>', 1))
    assert 'stale_result_cited' in codes(cmd_check.run_check(study))


def test_features_without_status_or_excluded_are_reported(study, synthetic_case_dir):
    b = fx.Builder(study, synthetic_case_dir)
    b.n = 500
    b.put('fit.logistic', {'auc': 0.6, 'n': 90}, params={'features': ['ghost', fx.NOT_AVAILABLE]},
          partition='validation', purpose='validation_model_evaluation', keys=b.validation_keys)
    result = cmd_check.run_check(study)
    by_code = {f['code']: f for f in result['findings']}
    assert by_code['feature_without_status']['details']['feature'] == 'ghost'
    assert by_code['excluded_feature_used']['details']['feature'] == fx.NOT_AVAILABLE


def test_draft_numbers_are_traced_to_the_registry(study):
    v = view.build(study)
    text = ('At revision 17 (step 6), precision was 35.0% for capacity:20, interval 15% to 55%. '
            'Training rows: 210, base rate 11.9%. Seed 20261017. Generated 2026-10-18.\n'
            '1. First point\n2. Second point\n')
    result = text_check(study, text)
    assert result['findings'] == [], result['findings']
    traced = {t['text']: t for t in result['traced']}
    assert traced['11.9%']['result_id'] == v['results']['eda.target_rate']['result_id']
    assert traced['11.9%']['path'] == 'rate'
    assert {'35.0%', '15%', '55%', '210', '20', '20261017'} <= set(traced)


@pytest.mark.parametrize('number', ['0.47', '42', '12.3%', '3.14159'])
def test_fabricated_numbers_are_untraceable(study, number):
    result = text_check(study, f'The model reached {number} on validation rows.')
    assert codes(result) == ['untraceable_number']
    assert result['findings'][0]['details']['number'] == number


def test_a_number_only_in_a_stale_result_is_reported(study):
    rid = view.build(study)['results']['fit.logistic']['result_id']
    _commit(study, lambda s: s['stale'].__setitem__(rid, {'reason': 'split changed', 'since': 1}))
    result = text_check(study, 'The ranking quality was 0.714.')
    assert codes(result) == ['stale_number']
    assert result['findings'][0]['details']['result_id'] == rid


@pytest.mark.parametrize('text, expected', [
    ('Holding items open causes renewals.', ['causal_wording']),
    ('Reminders lead to more renewals.', ['causal_wording']),
    ('The visit band drives the outcome.', ['causal_wording']),
    # known false positives that must stay silent
    ('This does not show that reminders cause renewals.', []),
    ('The effect of a reminder is not measured.', []),
    ('Rank rows by score; see the `cause` column in the dictionary.', []),
    ('Associations do not show that acting would change the outcome.', []),
])
def test_causal_wording(study, text, expected):
    assert codes(text_check(study, text)) == expected


@pytest.mark.parametrize('text, expected', [
    ('Expect about 7 renewals per 20 calls.', ['forecast_wording']),
    ('With capacity:20 you will get 7 renewals.', ['forecast_wording']),
    ('We will reach 35.0% precision next time.', ['forecast_wording']),
    ('Per 20 calls you will see 7 renewals.', ['forecast_wording']),
    # known false positives that must stay silent
    ('We will propose the split next.', []),
    ('Ties are counted pro rata, as an expected value.', []),
    ('These validation figures are not a forecast: 35.0% is optimistic.', []),
    ('You will not get 35.0% on new rows; it is a validation figure.', []),
])
def test_forecast_wording(study, text, expected):
    assert codes(text_check(study, text)) == expected


def test_notebook_numbers_and_result_ids_are_checked(study):
    path = study / mf.ARTIFACTS['notebook']
    source = path.read_text()
    rid = view.build(study)['results']['split']['result_id']
    path.write_text(source.replace(rid, 'a' * 64, 1).replace(
        '**Question.** At what moment', '**Question.** In 42 cases, at what moment', 1))
    result = cmd_check.run_check(study)
    found = {f['code'] for f in result['findings'] if f['where'] == mf.ARTIFACTS['notebook']}
    assert {'unknown_result_id', 'number_outside_result'} <= found
    numbers = [f['details']['number'] for f in result['findings']
               if f['code'] == 'number_outside_result']
    assert numbers == ['42']                     # "## 3." heading ordinals are exempt


def test_stale_artifacts_and_untracked_files_are_warnings(study):
    _commit(study, lambda s: None)
    (study / 'scratch.py').write_text('import pandas\n')
    (study / 'notebooks' / 'mine.py').write_text('x = 1\n')
    result = cmd_check.run_check(study)
    warn = {f['code']: f for f in result['findings'] if f['severity'] == 'warning'}
    assert warn['untracked_files']['details']['files'] == ['notebooks/mine.py', 'scratch.py']
    stale = [f['where'] for f in result['findings'] if f['code'] == 'artifact_not_current']
    assert 'artifact:report' in stale and 'artifact:notebook' in stale
    assert 'artifact:workbench' not in stale


def test_conclusion_text_is_checked(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='policy')
    b.decide('conclusion', {'verdict': 'adopt_policy',
                            'text': 'Adopt it: we expect 9 renewals per 20 calls.'},
             'You adopt the policy.', 'I adopt the capacity rule as written.')
    result = cmd_check.run_check(b.study)
    where = {(f['code'], f['where']) for f in result['findings']}
    assert ('untraceable_number', 'decision:conclusion') in where
    assert ('forecast_wording', 'decision:conclusion') in where


def _cli(*argv, stdin=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith('HYPOTRAIL_')}
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, argv)], input=stdin,
                          capture_output=True, text=True, env=env, cwd=FRAMEWORK, timeout=120)
    return proc.returncode, json.loads(proc.stdout)


def test_cli_check_reads_a_draft_from_stdin_and_never_writes(study):
    before = sorted((p.name, p.stat().st_mtime_ns) for p in (study / '.hypotrail').rglob('*')
                    if p.is_file())
    code, payload = _cli('check', '--text', '-', '--study', study,
                         stdin='We expect 0.47 precision.')
    assert code == 0 and payload['clean'] is False
    assert sorted(f['code'] for f in payload['findings']) == ['forecast_wording',
                                                              'untraceable_number']
    code, payload = _cli('check', '--study', study)
    assert code == 0 and payload['clean'] is True
    code, payload = _cli('check', '--text', study / 'missing.txt', '--study', study)
    assert code == 2 and payload['error']['code'] == 'invalid_arguments'
    after = sorted((p.name, p.stat().st_mtime_ns) for p in (study / '.hypotrail').rglob('*')
                   if p.is_file())
    assert after == before
