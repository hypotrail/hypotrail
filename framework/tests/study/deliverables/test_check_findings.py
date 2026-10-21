"""``hypotrail check`` (plan WP3.3; E1 findings F3, F4, F5)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.reliability import CommandRefused
from mlkit.study import cmd_check, commands as cmd, manifest as mf, read, view
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
    orphan = b.put('eda.target_rate', {'rate': 0.5, 'n_positive': 1, 'n_rows': 2}, promote=False)
    page = _report(study).read_text()
    _report(study).write_text(page.replace(
        '<main>', f'<main><p><data value="0.5" data-result-id="{orphan}" data-path="rate">'
        '50.0%</data></p>', 1))
    assert 'stale_result_cited' in codes(cmd_check.run_check(study))


def test_features_without_status_or_excluded_are_reported(study, synthetic_case_dir):
    b = fx.Builder(study, synthetic_case_dir)
    b.n = 500
    b.put('fit.logistic', {'features': ['ghost', fx.NOT_AVAILABLE],
                          'validation': {'roc_auc': 0.6, 'n_rows': 90}},
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


def test_percentage_points_match_only_a_registered_difference(study):
    """D4 (ii): "22.8 percentage points" is the paired delta 0.2278 times 100; a rate written
    in percentage points (11.9, the base rate) is not a difference and stays untraceable."""
    v = view.build(study)
    rid = v['results']['policy.evaluation']['result_id']
    for text in ('The model selects 22.8 percentage points more subscribers.',
                 'A gain of 22.8 pp in precision.'):
        result = text_check(study, text)
        assert result['findings'] == [], (text, result['findings'])
        traced = result['traced'][0]
        assert traced['result_id'] == rid and 'deltas' in traced['path']
    result = text_check(study, 'The base rate is 11.9 percentage points.')
    assert codes(result) == ['untraceable_number']


def test_a_unicode_minus_makes_a_number_negative(study):
    """D4 (iii): "−1" (U+2212) is the special value -1; "−0.714" is not the AUC 0.714."""
    from mlkit.study import cite
    assert [t.value for t in cite.parse_numbers('−0.99 and -1 and 10-18')] == \
        [-0.99, -1.0, 10.0, 18.0]
    result = text_check(study, 'The sentinel −1 marks a missing lapse.')
    assert result['findings'] == [] and result['traced'][0]['value'] == -1
    result = text_check(study, 'The AUC was −0.714.')
    assert codes(result) == ['untraceable_number']


@pytest.mark.parametrize('text', [
    'I compared capacity:100 with threshold:0.25 before proposing.',
    'The status now reads revision 26 instead of 24.',
    'Revision 24 to 26 changed the prediction moment; revisions 24, 25 and 26 are listed.',
    'The fit process ended with exit 137; the CLI returned exit code 4.',
])
def test_identifiers_revisions_and_exit_codes_are_not_claims(study, text):
    """D4 (iii): rule identifiers, revision comparisons, and exit codes are not figures."""
    result = text_check(study, text)
    assert result['findings'] == [], result['findings']


def _digit_only(rid: str, n: int = 8) -> str:
    """A digit-only string of ``n`` characters that is not a prefix of ``rid``."""
    return ('1' if rid[0] != '1' else '2') * n


@pytest.mark.parametrize('lead', ['result', 'result_id', 'rid', 'id', 'execution'])
def test_a_digit_only_id_after_an_id_word_is_not_a_claim(study, lead):
    """R3: "(result 52659681)" cites a result; its digit-only id prefix is not a figure."""
    rid = view.build(study)['results']['split']['result_id']
    number = _digit_only(rid)
    result = text_check(study, f'These validation rows are listed ({lead} {number}).')
    assert result['findings'] == [], result['findings']
    assert {'text': number, 'source': 'identifier', 'id': 'result_id',
            'value': float(number)} in result['traced']


def test_a_digit_only_registry_prefix_is_not_a_claim(study, monkeypatch):
    """R3: a digit-only prefix (6 or more characters) of a registry result_id is an id,
    even without the word "result" before it."""
    monkeypatch.setattr(cmd_check, 'registry_ids', lambda s: ['52659681' + 'a' * 56])
    result = text_check(study, 'The validation rows are those of 52659681 and 526596.')
    assert result['findings'] == [], result['findings']
    assert [t['id'] for t in result['traced']] == ['result_id', 'result_id']


@pytest.mark.parametrize('text, number', [
    ('The model selected 12345678 clients.', '12345678'),          # not a registry prefix
    ('The model selected 526597 clients.', '526597'),             # diverges from the id
    ('See result 42 for the count.', '42'),                       # fewer than 6 digits
    ('The result 1357.5 is untraced.', '1357.5'),                  # not digits only
    ('(result 52659681%)', '52659681%'),                           # a percentage
])
def test_a_real_untraced_number_is_still_reported(study, monkeypatch, text, number):
    """R3, the other way: the exemption covers digit-only id prefixes only."""
    monkeypatch.setattr(cmd_check, 'registry_ids', lambda s: ['52659681' + 'a' * 56])
    result = text_check(study, text)
    assert codes(result) == ['untraceable_number'], result['findings']
    assert result['findings'][0]['details']['number'] == number


def test_the_registry_holds_the_ids_a_prefix_may_abbreviate(study):
    ids = cmd_check.registry_ids(read.open(study))
    assert view.build(study)['results']['split']['result_id'] in ids
    assert all(len(i) == 64 for i in ids)


def test_a_revision_does_not_exempt_the_figure_that_follows_it(study):
    result = text_check(study, 'At revision 26 and 115 clients selected, nothing changed.')
    assert [f['details']['number'] for f in result['findings']] == ['115']


def test_the_juniors_own_numbers_may_be_repeated(study):
    """D4 (i): the manager's "100 calls", given by the junior, is not an untraceable figure
    when the junior's text is passed; it stays untraceable otherwise."""
    draft = 'Your manager can staff 100 calls, so the capacity is the constraint.'
    assert codes(text_check(study, draft)) == ['untraceable_number']
    result = cmd_check.run_check(study, draft, ['My manager says we can only make 100 calls.'])
    assert result['findings'] == []
    assert result['traced'] == [{'text': '100', 'source': 'user_text', 'id': 'user_text:1',
                                 'value': 100.0}]


def test_recorded_words_and_evaluated_rules_are_literals(study):
    """D4 (i): numbers in the junior's recorded confirmation and in the rules of the current
    policy evaluation are decision material, not computations."""
    v = view.build(study)
    draft = 'We said 140 calls a week; capacity 175 was evaluated too.'
    assert [f['code'] for f in cmd_check.check_text(v, draft)[0]] == ['untraceable_number'] * 2
    v['decisions']['split']['confirmation']['user_words'] = 'Fine, we can call 140 a week.'
    v['results']['policy.evaluation']['params']['rules'].append('capacity:175')
    findings, traced = cmd_check.check_text(v, draft)
    assert findings == []
    assert {(t['source'], t['value']) for t in traced} == {('user_words', 140.0), ('rule', 175.0)}


def test_cli_allow_user_text(study, tmp_path):
    draft = tmp_path / 'draft.txt'
    draft.write_text('Your manager can staff 100 calls.')
    code, payload = _cli('check', '--text', draft, '--allow-user-text', '-', '--study', study,
                         stdin='We can only call 100 people this week.')
    assert code == 0 and payload['clean'] is True, payload
    code, payload = _cli('check', '--text', '-', '--allow-user-text', '-', '--study', study,
                         stdin='x')
    assert code == 2 and payload['error']['code'] == 'invalid_arguments'
    code, payload = _cli('check', '--allow-user-text', draft, '--study', study)
    assert code == 2 and payload['error']['code'] == 'invalid_arguments'


def test_cli_reads_the_juniors_words_from_a_shell_pipe(study):
    """The agent passes the junior's words with a process substitution, ``<(printf ...)``,
    and the draft on stdin: no file is written anywhere."""
    proc = subprocess.run(
        ['bash', '-c', f'{sys.executable} -m mlkit.study.cli check --text - --allow-user-text '
                       f'<(printf "%s" "We can only call 100 people.") --study "$0"', str(study)],
        input='Your manager can staff 100 calls.', capture_output=True, text=True, cwd=FRAMEWORK,
        env={k: v for k, v in os.environ.items() if not k.startswith('HYPOTRAIL_')}, timeout=120)
    assert proc.returncode == 0 and proc.stderr == '', proc.stderr
    payload = json.loads(proc.stdout)
    assert payload['clean'] is True and payload['traced'][0]['source'] == 'user_text'


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


def test_the_declared_case_and_dataset_inside_the_study_are_not_untracked(tmp_path,
                                                                          synthetic_case_dir):
    """D9: a junior naturally keeps the case folder inside the study; its case and dataset
    files are the study's own inputs. Any other data or script file there is still reported."""
    import shutil
    from mlkit.study import commands as cmd

    study = tmp_path / 'study'
    case_dir = study / 'case'
    case_dir.mkdir(parents=True)
    for name in ('case.yaml', 'data.csv'):
        shutil.copy(synthetic_case_dir / name, case_dir / name)
    cmd.init(case_dir / 'case.yaml', study)
    (case_dir / 'extract.csv').write_text('a,b\n1,2\n')
    (study / 'scratch.py').write_text('import pandas\n')
    result = cmd_check.run_check(study)
    warn = {f['code']: f for f in result['findings'] if f['severity'] == 'warning'}
    assert warn['untracked_files']['details']['files'] == ['case/extract.csv', 'scratch.py']


def test_conclusion_text_is_checked(tmp_path, synthetic_case_dir, monkeypatch):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='policy')
    # 47 is in no result. (9 was used before the canonical shapes; the policy evaluation now
    # also reports the baseline's expected false negatives, 8.5556, which rounds to 9.)
    text = 'Adopt it: we expect 47 renewals per 20 calls.'
    # Since review fix M1 such a conclusion is refused when proposed ...
    with pytest.raises(CommandRefused) as refused:
        b.decide('conclusion', {'verdict': 'adopt_policy', 'text': text},
                 'You adopt the policy.', 'I adopt the capacity rule as written.')
    assert refused.value.code == 'literal_number_in_text'
    # ... and check still reports one recorded by a study written before that fix.
    monkeypatch.setattr(cmd, 'check_conclusion', lambda *a, **k: None)
    b.decide('conclusion', {'verdict': 'adopt_policy', 'text': text},
             'You adopt the policy.',
             'I adopt the capacity rule as written, because it ranks better.')
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
