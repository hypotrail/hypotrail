"""Regression walkthrough through real processes (M3): Auto MPG and the synthetic variant.

The same junior workflow as the binary walkthrough (``test_walkthrough.py``), for a
numeric target, on Auto MPG and on the regression variant of the synthetic generator: the
engine holds no dataset-specific code. Every command is a fresh ``python -m
mlkit.study.cli`` process in a temporary folder outside the repository, and every "chat"
starts by reading ``status``.

1. init: regression instructions installed, without the vocabulary of a decision rule;
2. pause 1: prediction moment, then the junior's availability list;
3. pause 2: a random split is refused because the case declares a time column; an ordinal
   cutoff on the integer time column is confirmed and run; the group overlap is reported;
4. training EDA: target summary, special values, mean by group (an activity of a binary
   study is refused);
5. ``fit.baseline`` (training mean) and ``fit.linear``;
6. ``evaluate.regression`` (MAE, RMSE, paired intervals, residuals by period), recorded
   as a validation model evaluation; ``preview policy`` is refused;
7. pause 3: ``model_choice`` from the paired MAE difference; "ok" is refused;
8. a new process sees every decision, result, and deliverable;
9. the conclusion, checked before it is proposed; changing the model choice afterwards
   reuses the evaluation (row 13: no refit) and asks for the conclusion again;
10. ``check`` of the report and the notebook is clean, and no deliverable, status output,
    or installed instruction holds threshold, positive class, precision, recall, or
    capacity.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

import flowkit as fk

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
BINARY_VOCABULARY = re.compile(r'threshold|positive class|precision|recall|capacity', re.I)

JUNIOR = {
    'auto': {
        'prediction_time': 'when the technical characteristics of a new model are fixed, '
                           'before its fuel efficiency is measured',
        'restatement': 'You estimate fuel efficiency once the technical characteristics are '
                       'fixed, before any measurement of it.',
        'words': 'Yes, once the technical characteristics are fixed and before measuring it.',
        'exclusions': {'acceleration': 'uncertain_excluded'},
        'availability_words': 'Leave acceleration out, its measurement is unclear; keep the '
                              'other characteristics and the origin.',
        'cutoff': 79,
        'mean_by': 'model_year',
        'mean_by_slot': 'eda.mean_by:model_year',
    },
    'synthetic': {
        'prediction_time': 'before the month starts, from the branch plan',
        'restatement': 'You estimate the loans of a branch before the month starts, from '
                       'what the branch plan holds.',
        'words': 'Yes, before the month starts, from the branch plan only.',
        'exclusions': {'returns_logged': 'not_available', 'heating_cost': 'uncertain_excluded'},
        'availability_words': 'Drop the returns logged, they come after the month, and leave '
                              'the heating cost out because we do not know when it is recorded.',
        'cutoff': 7,
        'mean_by': 'branch_type',
        'mean_by_slot': 'eda.mean_by:branch_type',
    },
}


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    synthetic = fk.make_case(tmp_path_factory.mktemp('regression'), task='regression',
                             n_rows=800, time=True, groups=True)
    return {'auto': AUTO, 'synthetic': synthetic['case'].parent}


class Chat:
    """One conversation: a status read first, then commands, each its own process."""

    def __init__(self, study: Path, work: Path, name: str):
        self.study, self.work, self.name, self.n = study, work, name, 0
        self.view = self.status()['view']

    def __call__(self, *args, expect=0):
        return fk.hyp(*args, '--study', self.study, cwd=self.work, expect=expect)[1]

    def status(self):
        return self('status', '--json')

    def rev(self) -> int:
        return self.status()['revision']

    def rid(self, what: str) -> str:
        self.n += 1
        return f'{self.name}-{self.n}-{what}'

    def propose(self, decision, value, restatement, expect=0):
        flag = '--value' if isinstance(value, str) else '--value-json'
        shown = value if isinstance(value, str) else json.dumps(value)
        out = self('decide', 'propose', decision, flag, shown, '--restatement', restatement,
                   '--rationale', 'It fits the use case.', '--request-id',
                   self.rid(f'propose-{decision}'), '--expected-revision', self.rev(),
                   expect=expect)
        return out['result']['proposal_id'] if expect == 0 else out

    def confirm(self, proposal, words, expect=0):
        return self('decide', 'confirm', proposal, '--user-words', words, '--request-id',
                    self.rid('confirm'), '--expected-revision', self.rev(), expect=expect)

    def run(self, activity, *options, expect=0):
        return self('run', activity, *options, '--request-id', self.rid(f'run-{activity}'),
                    '--expected-revision', self.rev(), expect=expect)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _instructions(study: Path) -> dict[str, str]:
    names = ('CLAUDE.md', '.github/copilot-instructions.md',
             '.claude/skills/hypotrail-study/SKILL.md', '.github/skills/hypotrail-study/SKILL.md',
             '.claude/commands/hypotrail-resume.md', '.github/prompts/hypotrail-resume.prompt.md',
             '.hypotrail/agent/glossary.yaml')
    return {n: (study / n).read_text(encoding='utf-8') for n in names}


def _vocabulary(texts: dict[str, str]) -> dict[str, list[str]]:
    return {name: sorted({m.group(0).lower() for m in BINARY_VOCABULARY.finditer(text)})
            for name, text in texts.items() if BINARY_VOCABULARY.search(text)}


@pytest.mark.parametrize('name', ['auto', 'synthetic'])
def test_regression_walkthrough(name, cases, tmp_path, capsys):
    case_dir = cases[name]
    junior = JUNIOR[name]
    study, work = tmp_path / 'study', tmp_path / 'work'
    work.mkdir()

    # 1. init installs the regression instructions
    code, init = fk.hyp('init', '--case', case_dir, '--study', study, cwd=work)
    assert code == 0 and init['agent_instructions']['status'] == 'copied'
    assert [s['id'] for s in init['plan']] == ['prediction_time', 'feature_availability',
                                               'split', 'train_eda', 'models',
                                               'model_choice', 'conclusion']
    claude = (study / 'CLAUDE.md').read_text()
    assert '### Regression study' in claude and 'evaluate.regression' in claude
    assert 'hypotrail:task' not in claude
    assert _vocabulary(_instructions(study)) == {}

    # 2. pause 1: prediction moment, then the junior's availability list
    chat = Chat(study, work, 'chat1')
    assert chat.view['task'] == 'regression'
    assert 'policy' not in chat.view['decisions']
    p = chat.propose('prediction_time', junior['prediction_time'], junior['restatement'])
    assert chat.confirm(p, 'ok', expect=2)['error']['code'] == 'ambiguous_confirmation'
    chat.confirm(p, junior['words'])
    availability = fk.availability(case_dir, **junior['exclusions'])
    p = chat.propose('feature_availability', availability,
                     'You exclude the variables you listed and keep the others.')
    chat.confirm(p, junior['availability_words'])

    # 3. pause 2: a random split is refused (declared time column); an ordinal cutoff is used
    chat = Chat(study, work, 'chat2')
    assert chat.run('eda.target_summary', expect=2)['error']['code'] == 'precondition_missing'
    time_column = chat.view['structure']['time_column']['value']
    for method in ({'method': 'random', 'validation_fraction': 0.3, 'seed': 1},
                   {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 1}):
        refused = chat.propose('split', method, 'A random split.', expect=2)
        assert refused['error']['code'] == 'invalid_value', refused
        assert refused['error']['details']['methods'] == ['ordinal_cutoff']
    split_value = {'method': 'ordinal_cutoff', 'column': time_column, 'cutoff': junior['cutoff']}
    p = chat.propose('split', split_value,
                     f'Rows with {time_column} at {junior["cutoff"]} or later are validation '
                     f'rows; earlier rows train the models.')
    chat.confirm(p, f'Yes, validate on {time_column} {junior["cutoff"]} and later, train on '
                    f'the earlier rows.')
    split = chat.run('split')
    assert split['status'] == 'promoted'
    values = split['values']
    parts = values['partitions']
    assert values['method'] == 'ordinal_cutoff' and values['stratified_on'] is None
    assert parts['train']['column_max'] < junior['cutoff'] <= parts['validation']['column_min']
    assert parts['train']['n_rows'] + parts['validation']['n_rows'] == values['n_rows']
    groups = values['groups']
    assert groups['capability'] == 'grouped split (v0.2)'
    assert 0 < groups['shared_groups'] <= groups['validation_groups']
    assert groups['validation_rows_in_shared_groups'] >= groups['shared_groups']
    split_exposure = [r for r in fk.exposure_records(study) if r['activity'] == 'split']
    target = fk.c.load_case(case_dir).target_column
    assert target not in split_exposure[-1]['columns']          # no target read to split
    view = chat.status()['view']
    nyd = {x['id']: x for x in view['not_yet_defensible']}
    assert nyd['grouped_split_unsupported']['column'] == groups['column']

    # 4. training EDA (an activity of a binary study is refused)
    assert chat.run('eda.target_rate', expect=2)['error']['code'] == 'invalid_arguments'
    summary = chat.run('eda.target_summary')['values']
    assert summary['n_rows'] == parts['train']['n_rows'] and summary['n_missing'] == 0
    assert summary['min'] <= summary['q25'] <= summary['median'] <= summary['q75'] <= summary['max']
    specials = chat.run('eda.special_values')['values']
    assert all('mean_target' in s and 'rate' not in s for s in specials['special_values'])
    mean_by = chat.run('eda.mean_by', '--column', junior['mean_by'])
    assert mean_by['result']['slot'] == junior['mean_by_slot']
    assert sum(g['n_rows'] for g in mean_by['values']['groups']) == parts['train']['n_rows']
    eda_exposure = [r for r in fk.exposure_records(study) if r['purpose'] == 'train_eda']
    assert {r['partition'] for r in eda_exposure} == {'train'}

    # 5. both fits
    baseline = chat.run('fit.baseline')
    linear = chat.run('fit.linear')
    assert baseline['values']['model'] == 'train_mean'
    assert baseline['values']['train_mean'] == pytest.approx(summary['mean'])
    used = linear['values']['features']
    for feature, status in junior['exclusions'].items():
        assert (feature in used) == (status == 'uncertain_included'), feature
    assert time_column not in used and groups['column'] not in used

    # 6. the regression evaluation on validation rows, recorded as model evaluation
    chat = Chat(study, work, 'chat3')
    before = len(fk.exposure_records(study))
    evaluation = chat.run('evaluate.regression')
    assert evaluation['status'] == 'promoted'
    ev = evaluation['values']
    new = fk.exposure_records(study)[before:]
    assert [(r['purpose'], r['partition']) for r in new] == [('validation_model_evaluation',
                                                             'validation')]
    assert ev['n'] == parts['validation']['n_rows'] == new[0]['n_rows']
    for model in ('fit.baseline', 'fit.linear'):
        m = ev['models'][model]
        assert m['rmse'] >= m['mae'] > 0
        assert ev['intervals'][model]['mae']['low'] <= m['mae'] <= ev['intervals'][model]['mae']['high']
        assert m['mae'] == pytest.approx((baseline if model == 'fit.baseline'
                                          else linear)['values']['validation']['mae'])
    delta = ev['deltas']['fit.linear']['mae']
    assert delta['point'] == pytest.approx(ev['models']['fit.linear']['mae']
                                           - ev['models']['fit.baseline']['mae'])
    assert delta['low'] <= delta['point'] <= delta['high']
    [by_period] = ev['residuals_by']
    assert by_period['column'] == time_column
    assert sum(g['n_rows'] for g in by_period['groups']) == ev['n']
    preview = chat('preview', 'policy', '--rule', 'capacity:10', expect=2)
    assert preview['error']['code'] == 'unsupported_capability'

    # 7. pause 3: the model choice, from the paired MAE difference
    assert chat.propose('policy', 'capacity:10', 'x', expect=2)['error']['code'] == \
        'unknown_decision'
    adopt = delta['high'] < 0          # the whole interval says the linear model errs less
    choice = 'fit.linear' if adopt else 'fit.baseline'
    p = chat.propose('model_choice', choice,
                     'You adopt the linear model.' if adopt else 'You keep the mean baseline.')
    assert chat.confirm(p, 'ok', expect=2)['error']['code'] == 'ambiguous_confirmation'
    chat.confirm(p, 'Yes, adopt the linear model.' if adopt else 'Yes, keep the mean baseline.')

    # 8. a new process sees everything without any chat memory
    view = Chat(study, work, 'chat4').view
    for d in ('prediction_time', 'feature_availability', 'split', 'model_choice'):
        assert view['decisions'][d]['status'] == 'confirmed', d
    for slot in ('split', 'eda.target_summary', 'eda.special_values', junior['mean_by_slot'],
                 'fit.baseline', 'fit.linear', 'evaluate.regression'):
        assert view['results'][slot]['current'] is True, slot
    assert {i['status'] for i in view['artifacts']['items'].values()} == {'ok'}
    assert view['current_step'] == 'conclusion'

    # 9. a conclusion checked first; then a changed model choice reuses the evaluation
    lin, base = ev['models']['fit.linear'], ev['models']['fit.baseline']
    text = (f'On the validation rows of the later periods, the linear model has an MAE of '
            f'{lin["mae"]:.2f} against {base["mae"]:.2f} for the mean baseline, with a mean '
            f'residual of {lin["mean_residual"]:.2f}. The model was chosen on these rows, so '
            f'the comparison is optimistic and is not a forecast.')
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'check', '--text', '-',
                           '--study', str(study)], input=text, capture_output=True, text=True,
                          cwd=work, env=fk.env(), timeout=120)
    draft = json.loads(proc.stdout)
    assert proc.returncode == 0 and draft['clean'] is True, draft['findings']
    chat = Chat(study, work, 'chat5')
    verdict = 'adopt_model' if adopt else 'keep_baseline'
    p = chat.propose('conclusion', {'verdict': verdict, 'text': text},
                     'You conclude as stated and record the limits.')
    chat.confirm(p, 'I conclude as stated, with the bias on later periods as a limit.')
    fits = {e['result_id'] for e in fk.registry_entries(study) if e['activity'].startswith('fit.')}
    other = 'fit.baseline' if adopt else 'fit.linear'
    p = chat.propose('model_choice', other, 'You switch to the other model.')
    changed = chat.confirm(p, 'Yes, switch to the other model.')['result']['invalidation']
    assert changed['mutation'] == 'model_choice' and changed['row'] == 13
    assert changed['reconfirm_required'] == ['conclusion'] and changed['stale_results'] == []
    assert {e['result_id'] for e in fk.registry_entries(study)
            if e['activity'].startswith('fit.')} == fits                  # no refit
    view = chat.status()['view']
    assert view['decisions']['conclusion']['status'] == 'reconfirm_required'
    assert view['results']['evaluate.regression']['result_id'] == evaluation['result_id']
    if adopt:   # adopt_model now needs the linear model chosen
        refused = chat('decide', 'confirm',
                       chat.propose('conclusion', {'verdict': 'adopt_model', 'text': text},
                                    'You adopt the linear model.'),
                       '--user-words', 'Yes, I adopt the linear model.', '--request-id',
                       chat.rid('confirm'), '--expected-revision', chat.rev(), expect=2)
        assert refused['error']['code'] == 'precondition_missing'
    p = chat.propose('model_choice', choice, 'You return to your first choice.')
    chat.confirm(p, 'Yes, return to my first choice.')
    p = chat.propose('conclusion', {'verdict': verdict, 'text': text},
                     'You conclude as stated and record the limits.')
    chat.confirm(p, 'I conclude as stated, with the bias on later periods as a limit.')

    # 10. clean check, cited numbers, and no binary vocabulary anywhere
    final = chat.status()
    assert all(d['status'] == 'confirmed' for d in final['view']['decisions'].values())
    result = chat('check')
    assert result['clean'] is True and result['counts']['error'] == 0, result['findings']
    page = (study / 'reports/study.html').read_text()
    tags = Tags()
    tags.feed(page)
    controls = [t for t, a in tags.tags if t in ('input', 'form', 'select', 'textarea', 'option')]
    assert controls == []
    data = [a for t, a in tags.tags if t == 'data']
    assert len(data) > 50 and all(a.get('data-result-id') and a.get('data-path') for a in data)
    current = {r['result_id'] for r in final['view']['results'].values() if r['current']}
    assert {a['data-result-id'] for a in data} <= current
    assert 'id="model-comparison"' in page and 'class="residuals-by"' in page
    surfaces = {'report': page,
                'notebook': (study / 'notebooks/study_generated.py').read_text(),
                'workbench': (study / 'notebooks/workbench.py').read_text(),
                'status': json.dumps(final), 'summary': json.dumps(chat('status', '--summary')),
                'plan': json.dumps(chat('plan')), **_instructions(study)}
    assert _vocabulary(surfaces) == {}

    measured = {'case': name, 'split': {'cutoff': junior['cutoff'],
                                        'train': parts['train']['n_rows'],
                                        'validation': parts['validation']['n_rows'],
                                        'shared_groups': groups['shared_groups'],
                                        'validation_rows_in_shared_groups':
                                            groups['validation_rows_in_shared_groups']},
                'train_mean': round(summary['mean'], 3),
                'features_used': used,
                'mae': {m: [round(ev['models'][m]['mae'], 3),
                            round(ev['intervals'][m]['mae']['low'], 3),
                            round(ev['intervals'][m]['mae']['high'], 3)] for m in ev['models']},
                'rmse': {m: [round(ev['models'][m]['rmse'], 3),
                             round(ev['intervals'][m]['rmse']['low'], 3),
                             round(ev['intervals'][m]['rmse']['high'], 3)] for m in ev['models']},
                'delta_mae': [round(delta[k], 3) for k in ('point', 'low', 'high')],
                'delta_rmse': [round(ev['deltas']['fit.linear']['rmse'][k], 3)
                               for k in ('point', 'low', 'high')],
                'bias': {m: round(ev['models'][m]['mean_residual'], 3) for m in ev['models']},
                'bias_by_period': {g['value']: round(g['models']['fit.linear']['mean_residual'], 3)
                                   for g in by_period['groups']},
                'choice': choice, 'verdict': verdict}
    with capsys.disabled():
        print('\nregression walkthrough', json.dumps(measured, sort_keys=True))
    if name == 'auto':     # the historical protocol: 1970-1978 against 1979-1982
        assert (parts['train']['n_rows'], parts['validation']['n_rows']) == (280, 118)
        assert summary['n'] == 280
