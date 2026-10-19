"""Regression walkthrough through real processes (M3): Auto MPG, the synthetic variant,
and diabetes.

The same junior workflow as the binary walkthrough (``test_walkthrough.py``), for a
numeric target, on Auto MPG, on the regression variant of the synthetic generator, and on
the scikit-learn diabetes case (no time or group column: a random split, no residuals by
period; materialized in a temporary folder by its ``prepare.py``): the engine holds no
dataset-specific code. Every command is a fresh ``python -m
mlkit.study.cli`` process in a temporary folder outside the repository, and every "chat"
starts by reading ``status``.

1. init: regression instructions installed, without the vocabulary of a decision rule;
2. pause 1: prediction moment, then the junior's availability list;
3. pause 2: a random split is refused because the case declares a time column; an ordinal
   cutoff on the integer time column is confirmed and run; the group overlap is reported
   (without a time column, a stratified or ordinal split is refused and a random one run);
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
    resume recap, session report (JSON and Markdown), or installed instruction holds
    threshold, positive class, precision, recall, or capacity.

Post-v0.1 instruments on a regression study (merge of the observation kit with M3): a
number written in words followed by the target unit ("about three mpg") is traced by
``check`` (F3); the ``status --summary`` recap names the model choice, never a policy
(T8); ``session-report`` closes pause 3 on ``model_choice`` and the conclusion.
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
from mlkit.study import sessionlog

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
    # M3 generality: a real regression case without a time or group column.
    'diabetes': {
        'prediction_time': 'at the baseline visit, once its ten measurements are available',
        'restatement': 'You estimate the progression one year ahead at the baseline visit, '
                       'from its measurements.',
        'words': 'Yes, at the baseline visit, from its measurements only.',
        'exclusions': {'s5': 'uncertain_excluded'},
        'availability_words': 'Leave s5 out: even the documentation is unsure what it measures. '
                              'Keep the other nine.',
        'split': {'method': 'random', 'validation_fraction': 0.3, 'seed': 20261017},
        'mean_by': 'sex',
        'mean_by_slot': 'eda.mean_by:sex',
    },
}


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    synthetic = fk.make_case(tmp_path_factory.mktemp('regression'), task='regression',
                             n_rows=800, time=True, groups=True)
    return {'auto': AUTO, 'synthetic': synthetic['case'].parent,
            'diabetes': fk.materialize(fk.DIABETES, tmp_path_factory.mktemp('diabetes'))}


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


@pytest.mark.parametrize('name', ['auto', 'synthetic', 'diabetes'])
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
    # the opt-in session log, enabled once by one process (observation kit)
    enable = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'status', '--summary',
                             '--study', str(study)], capture_output=True, text=True, cwd=work,
                            env={**fk.env(), 'HYPOTRAIL_SESSION_LOG': '1'}, timeout=120)
    assert enable.returncode == 0 and (study / '.hypotrail/session-log.jsonl').is_file()

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
    if time_column is not None:
        for method in ({'method': 'random', 'validation_fraction': 0.3, 'seed': 1},
                       {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 1}):
            refused = chat.propose('split', method, 'A random split.', expect=2)
            assert refused['error']['code'] == 'invalid_value', refused
            assert refused['error']['details']['methods'] == ['ordinal_cutoff']
        split_value = {'method': 'ordinal_cutoff', 'column': time_column,
                       'cutoff': junior['cutoff']}
        p = chat.propose('split', split_value,
                         f'Rows with {time_column} at {junior["cutoff"]} or later are validation '
                         f'rows; earlier rows train the models.')
        chat.confirm(p, f'Yes, validate on {time_column} {junior["cutoff"]} and later, train on '
                        f'the earlier rows.')
    else:   # no time column: a random split, never stratified on a numeric target
        for method in ({'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 1},
                       {'method': 'ordinal_cutoff', 'column': junior['mean_by'], 'cutoff': 1}):
            refused = chat.propose('split', method, 'Another split.', expect=2)
            assert refused['error']['code'] == 'invalid_value', refused
            assert refused['error']['details']['methods'] == ['random']
        p = chat.propose('split', junior['split'], 'A random split: 30% of rows for '
                                                   'validation, seed 20261017, fixed now.')
        chat.confirm(p, 'Yes, fix that random split now, before we look at the outcome.')
    split = chat.run('split')
    assert split['status'] == 'promoted'
    values = split['values']
    parts = values['partitions']
    assert values['method'] == ('ordinal_cutoff' if time_column else 'random')
    assert values['stratified_on'] is None
    if time_column:
        assert parts['train']['column_max'] < junior['cutoff'] <= parts['validation']['column_min']
    assert parts['train']['n_rows'] + parts['validation']['n_rows'] == values['n_rows']
    groups = values['groups']
    group_column = chat.view['structure']['group_column']['value']
    if group_column is not None:
        assert groups['capability'] == 'grouped split (v0.2)'
        assert 0 < groups['shared_groups'] <= groups['validation_groups']
        assert groups['validation_rows_in_shared_groups'] >= groups['shared_groups']
    else:
        assert groups is None
    split_exposure = [r for r in fk.exposure_records(study) if r['activity'] == 'split']
    target = fk.c.load_case(case_dir).target_column
    assert target not in split_exposure[-1]['columns']          # no target read to split
    view = chat.status()['view']
    nyd = {x['id']: x for x in view['not_yet_defensible']}
    if group_column is not None:
        assert nyd['grouped_split_unsupported']['column'] == groups['column']
    else:
        assert 'grouped_split_unsupported' not in nyd

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
    assert not ({time_column, group_column} - {None}) & set(used)

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
    if time_column:
        [by_period] = ev['residuals_by']
        assert by_period['column'] == time_column
        assert sum(g['n_rows'] for g in by_period['groups']) == ev['n']
    else:
        assert ev['residuals_by'] == []
        by_period = {'groups': []}
    preview = chat('preview', 'policy', '--rule', 'capacity:10', expect=2)
    assert preview['error']['code'] == 'unsupported_capability'
    _check_words_in_the_target_unit(study, work, ev, chat.status()['view'])

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
    resume = Chat(study, work, 'chat4')
    view = resume.view
    for d in ('prediction_time', 'feature_availability', 'split', 'model_choice'):
        assert view['decisions'][d]['status'] == 'confirmed', d
    # the resume recap (T8) names the model choice and the ordinal split, never a policy
    recap = resume('status', '--summary')['recap']
    assert [line.split(':', 1)[0] for line in recap] == ['Goal', 'Decided', 'Now', 'Next',
                                                        'Limit']
    decided = recap[1]
    assert f'model choice: {"the linear model" if adopt else "the mean baseline"}' in decided
    # P3: the chosen model's validation MAE in the target unit, with its result citation,
    # and no revision number anywhere; the recap passes ``check`` as quoted.
    rid = evaluation['result_id']
    assert (f'(validation MAE {ev["models"][choice]["mae"]:.2f} {ev["unit"]}, result '
            f'{rid[:8]})') in decided
    assert not any('revision' in line.lower() for line in recap)
    quoted = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'check', '--text', '-',
                             '--study', str(study)], input='\n'.join(recap), capture_output=True,
                            text=True, cwd=work, env=fk.env(), timeout=120)
    assert json.loads(quoted.stdout)['clean'] is True, quoted.stdout
    if time_column:
        assert f'split (ordinal cutoff on {time_column}, validation from {junior["cutoff"]})' \
            in decided
    else:
        assert 'split (random, 30% for validation)' in decided
    for feature in junior['exclusions']:
        assert feature in decided
    assert 'policy' not in decided and not BINARY_VOCABULARY.search(' '.join(recap))
    for slot in ('split', 'eda.target_summary', 'eda.special_values', junior['mean_by_slot'],
                 'fit.baseline', 'fit.linear', 'evaluate.regression'):
        assert view['results'][slot]['current'] is True, slot
    assert {i['status'] for i in view['artifacts']['items'].values()} == {'ok'}
    assert view['current_step'] == 'conclusion'

    # 9. a conclusion checked first; then a changed model choice reuses the evaluation
    lin, base = ev['models']['fit.linear'], ev['models']['fit.baseline']
    rows_named = 'the validation rows of the later periods' if time_column else 'the validation rows'
    text = (f'On {rows_named}, the linear model has an MAE of '
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
    assert 'id="model-comparison"' in page
    assert ('class="residuals-by"' in page) == (time_column is not None)
    session = chat('session-report')
    pause3 = session['pauses'][2]
    assert pause3['decisions'] == ['model_choice', 'conclusion'] and pause3['closed_at']
    assert pause3['confirmed'] == ['conclusion', 'model_choice']
    assert {d['decision_id'] for d in session['decisions']} >= {'model_choice', 'conclusion'}
    assert session['sources']['session_log']['enabled'] is True
    # Owner decision: with the log on, ``check`` runs are logged (how often the junior
    # checks), so the word-number check above is in the report.
    assert any(c.get('in_words') for c in session['checks'])
    session_text = subprocess.run(
        [sys.executable, '-m', 'mlkit.study.cli', 'session-report', '--format', 'text',
         '--study', str(study)], capture_output=True, text=True, cwd=work, env=fk.env(),
        timeout=120)
    assert session_text.returncode == 0 and '| 3 | model_choice, conclusion |' in \
        session_text.stdout
    # The session report records what was tried: a refused command that keeps a rule
    # identifier would be left out of the vocabulary check. This walkthrough's refused
    # ``preview policy --rule capacity:10`` is a preview, which is never logged; the
    # ``status`` and ``check`` reads are (owner decision, ``sessionlog.LOGGED_READS``), and
    # everything the engine wrote of its own is in.
    tried = [x for x in session['timeline'] if x['source'] == 'session_log'
             and x.get('ok') is False and BINARY_VOCABULARY.search(json.dumps(x))]
    assert tried == []
    logged_reads = {x.get('command') for x in session['timeline'] if x['source'] == 'session_log'
                    and x.get('command') in sessionlog.READ_COMMANDS}
    assert logged_reads == set(sessionlog.LOGGED_READS), logged_reads
    own = {**session, 'timeline': [x for x in session['timeline'] if x not in tried]}
    own_text = '\n'.join(line for line in session_text.stdout.splitlines()
                         if not ('REFUSED' in line and BINARY_VOCABULARY.search(line)))
    surfaces = {'report': page,
                'session_report': json.dumps(own), 'session_report_text': own_text,
                'recap': '\n'.join(recap),
                'notebook': (study / 'notebooks/study_generated.py').read_text(),
                'workbench': (study / 'notebooks/workbench.py').read_text(),
                'status': json.dumps(final), 'summary': json.dumps(chat('status', '--summary')),
                'plan': json.dumps(chat('plan')), **_instructions(study)}
    assert _vocabulary(surfaces) == {}

    measured = {'case': name, 'split': {'cutoff': junior.get('cutoff'),
                                        'train': parts['train']['n_rows'],
                                        'validation': parts['validation']['n_rows'],
                                        'shared_groups': (groups or {}).get('shared_groups'),
                                        'validation_rows_in_shared_groups':
                                            (groups or {}).get(
                                                'validation_rows_in_shared_groups')},
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
    if name == 'auto':     # the historical protocol: 1970-1978 against 1979-1982, on the
        # 318 development rows once 80 are sealed (ADR 0006; v0.1: 280 and 118 of 398)
        assert (parts['train']['n_rows'], parts['validation']['n_rows']) == (222, 96)
        assert summary['n'] == 222


def _english(n: int) -> str:
    """``n`` (0 to 100) in English words, as ``wordnum`` reads it."""
    from mlkit.study import wordnum
    return next(w for w, v in wordnum.CARDINALS.items()
                if v == n and w.isascii() and ' ' not in w and w != 'dozen')


def _numbers(value):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _numbers(v)
    elif isinstance(value, list):
        for v in value:
            yield from _numbers(v)
    elif isinstance(value, str):
        yield from (float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', value))


def _check_words_in_the_target_unit(study: Path, work: Path, ev: dict, view: dict) -> None:
    """F3 on a regression study: "about <n> <unit>" in words is traced like digits."""
    unit = ev['unit']

    def check(text):
        proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'check', '--text', '-',
                               '--study', str(study)], input=text, capture_output=True,
                              text=True, cwd=work, env=fk.env(), timeout=120)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    mae = ev['models']['fit.linear']['mae']
    if round(mae) <= 100 and abs(mae - round(mae)) < 0.5:
        draft = (f'On the validation rows, the linear model was off by about '
                 f'{_english(round(mae))} {unit} on average.')
        out = check(draft)
        assert out['clean'] is True, out['findings']
        assert [t for t in out['traced'] if t.get('in_words')], out['traced']
    # a figure no registered value, decision, or case statement holds is reported
    known = list(_numbers(view))
    free = next((k for k in range(97, 1, -1) if all(abs(k - v) > 0.5 for v in known)), None)
    if free is not None:
        out = check(f'On the validation rows, the linear model was off by about '
                    f'{_english(free)} {unit} on average.')
        [finding] = [f for f in out['findings'] if f['code'] == 'untraceable_number']
        assert finding['details']['in_words'] is True and finding['details']['value'] == free
