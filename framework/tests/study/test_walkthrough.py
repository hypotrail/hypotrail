"""End-to-end walkthrough through real processes (plan WP4.2, §7).

Every command is a fresh ``python -m mlkit.study.cli`` process whose working directory is
a temporary folder outside the repository, and every "chat" starts by reading
``status`` (never memory), as the study agent must. The same flow runs on Bank Marketing
and on the synthetic case, and on the scikit-learn WDBC case (materialized in a temporary
folder by its ``prepare.py``): the engine holds no dataset-specific code.

1. init (instructions installed, the recorded invocation works);
2. pause 1: ``prediction_time``, then ``feature_availability`` from the junior's list;
3. pause 2: ``split``, then ``run split``;
4. training EDA: target rate, special values, one rate by group;
5. ``fit.baseline`` and ``fit.logistic``;
6. ``policy.evaluate`` of a threshold, then pause 3: adopt it;
7. a new process: ``status`` shows every decision, result, and deliverable;
8. a capacity of 100 is evaluated **without refit** (same fit results, same predictions,
   no new fit exposure) and its adoption needs a new confirmation ("ok" is refused);
9. a proportionate conclusion, checked;
10. ``check`` of the HTML report and the notebook: no error;
11. an injected HTML render failure keeps the previous report with a stale banner (exit 3).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from mlkit.study import agent_files as af

import flowkit as fk

THRESHOLD = 'threshold:0.2'
CAPACITY = 'capacity:100'

# The junior's own availability list (pause 1), beyond what the case states.
JUNIOR = {
    'bank': {
        'prediction_time': 'before the first contact of the campaign, from the client file',
        'restatement': 'You score each client before the first call, from what the client '
                       'file holds at that moment.',
        'words': 'Yes, before the first call, using only the client file.',
        'exclusions': {'duration': 'not_available', 'day': 'not_available',
                       'month': 'not_available', 'campaign': 'not_available',
                       'contact': 'uncertain_included'},
        'availability_words': 'Drop duration, day, month and campaign: they describe the calls '
                              'of this campaign. Keep contact but list it as a doubt.',
        'rate_by': 'job',
    },
    'synthetic': {
        'prediction_time': 'when the membership expires, before any reminder is sent',
        'restatement': 'You score each member when the membership expires, before the first '
                       'reminder.',
        'words': 'Yes, at expiry, before any reminder goes out.',
        'exclusions': {'desk_followups': 'not_available', 'reminders_sent': 'not_available',
                       'last_reminder_weekday': 'not_available',
                       'fines_outstanding': 'uncertain_included'},
        'availability_words': 'Leave out the desk follow-ups and both reminder columns; keep the '
                              'fines but mark them as uncertain.',
        'rate_by': 'home_branch',
    },
    # M3 generality: a real binary case with 30 numeric features and no leaky variable.
    'wdbc': {
        'prediction_time': 'when the aspirate image has been analysed, before the pathology '
                           'diagnosis',
        'restatement': 'You score each sample once its image is analysed, before the '
                       'pathologist gives a diagnosis.',
        'words': 'Yes, once the image is analysed and before the diagnosis.',
        'exclusions': {},
        'availability_words': 'Keep all thirty measurements: they all come from the analysed '
                              'image.',
        'availability_restatement': 'You keep every measurement of the analysed image as a '
                                    'feature.',
        'rate_by': 'mean_radius',
    },
}


@pytest.fixture(scope='module')
def cases(tmp_path_factory):
    return {'bank': fk.BANK,
            'synthetic': fk.make_case(tmp_path_factory.mktemp('synthetic'),
                                      n_rows=4000)['case'].parent,
            'wdbc': fk.materialize(fk.WDBC, tmp_path_factory.mktemp('wdbc'))}


class Chat:
    """One conversation: a status read first, then commands, each its own process."""

    def __init__(self, study: Path, work: Path, name: str):
        self.study, self.work, self.name, self.n = study, work, name, 0
        self.view = self.status()['view']

    def __call__(self, *args, expect=0, extra_env=None):
        return fk.hyp(*args, '--study', self.study, cwd=self.work, expect=expect,
                      extra_env=extra_env)[1]

    def status(self):
        return self('status', '--json')

    def rev(self) -> int:
        return self.status()['revision']

    def rid(self, what: str) -> str:
        self.n += 1
        return f'{self.name}-{self.n}-{what}'

    def propose(self, decision, value, restatement, rationale='It fits the use case.'):
        flag = '--value' if isinstance(value, str) else '--value-json'
        shown = value if isinstance(value, str) else json.dumps(value)
        out = self('decide', 'propose', decision, flag, shown, '--restatement', restatement,
                   '--rationale', rationale, '--request-id', self.rid(f'propose-{decision}'),
                   '--expected-revision', self.rev())
        return out['result']['proposal_id']

    def confirm(self, proposal, words, expect=0):
        return self('decide', 'confirm', proposal, '--user-words', words, '--request-id',
                    self.rid('confirm'), '--expected-revision', self.rev(), expect=expect)

    def run(self, activity, *options, expect=0, extra_env=None):
        return self('run', activity, *options, '--request-id', self.rid(f'run-{activity}'),
                    '--expected-revision', self.rev(), expect=expect, extra_env=extra_env)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _fits(study: Path) -> list[dict]:
    return [e for e in fk.registry_entries(study) if e['activity'].startswith('fit.')]


@pytest.mark.parametrize('name', ['bank', 'synthetic', 'wdbc'])
def test_walkthrough(name, cases, tmp_path, capsys):
    case_dir = cases[name]
    junior = JUNIOR[name]
    study, work = tmp_path / 'study', tmp_path / 'work'
    work.mkdir()

    # 1. init installs the instructions; the recorded invocation reads the study
    code, init = fk.hyp('init', '--case', case_dir, '--study', study, cwd=work)
    assert code == 0 and init['agent_instructions']['status'] == 'copied'
    assert (study / 'CLAUDE.md').is_file()
    agent = json.loads((study / '.hypotrail' / af.AGENT_FILE).read_text())
    assert agent['cli']['shell'] in (study / 'CLAUDE.md').read_text()

    # 2. pause 1: prediction moment, then the junior's availability list
    chat = Chat(study, work, 'chat1')
    assert chat.view['current_step'] == 'prediction_time'
    p = chat.propose('prediction_time', junior['prediction_time'], junior['restatement'])
    refused = chat.confirm(p, 'ok', expect=2)
    assert refused['error']['code'] == 'ambiguous_confirmation'
    chat.confirm(p, junior['words'])
    availability = fk.availability(case_dir, **junior['exclusions'])
    p = chat.propose('feature_availability', availability,
                     junior.get('availability_restatement',
                                'You exclude the variables you listed and keep the doubtful '
                                'one as a stated limit.'))
    confirmed = chat.confirm(p, junior['availability_words'])
    assert confirmed['result']['user_words'] == junior['availability_words']

    # 3. pause 2: the split before any exploration (EDA before it is refused)
    chat = Chat(study, work, 'chat2')
    assert chat.run('eda.target_rate', expect=2)['error']['code'] == 'precondition_missing'
    p = chat.propose('split', fk.SPLIT, 'A stratified random split: 30% of rows for validation, '
                                        'seed 20261017, fixed before exploring.')
    chat.confirm(p, 'Yes, fix that split now, before we look at the outcome.')
    split = chat.run('split')
    assert split['status'] == 'promoted'
    parts = split['values']['partitions']

    # 4-5. authorised work between pauses: training EDA, then both fits
    target = chat.run('eda.target_rate')['values']
    specials = chat.run('eda.special_values')['values']
    rate_by = chat.run('eda.rate_by', '--column', junior['rate_by'])
    assert rate_by['result']['slot'] == f'eda.rate_by:{junior["rate_by"]}'
    assert target['n_rows'] == parts['train']['n_rows']
    baseline = chat.run('fit.baseline')
    logistic = chat.run('fit.logistic')
    used = logistic['values']['features']
    for feature, status in junior['exclusions'].items():
        assert (feature in used) == (status == 'uncertain_included'), feature

    # 6. pause 3: evaluate a threshold, adopt it with the junior's words
    chat = Chat(study, work, 'chat3')
    evaluation = chat.run('policy.evaluate', '--rule', THRESHOLD)
    assert evaluation['status'] == 'promoted'
    p = chat.propose('policy', THRESHOLD, 'You call every client whose score is at least 0.2.')
    chat.confirm(p, 'Yes, call everyone scored 0.2 or more.')

    # 7. a new process sees everything without any chat memory
    view = Chat(study, work, 'chat4').view
    decisions = view['decisions']
    for d in ('prediction_time', 'feature_availability', 'split', 'policy'):
        assert decisions[d]['status'] == 'confirmed', d
    assert decisions['prediction_time']['confirmation']['user_words'] == junior['words']
    assert decisions['policy']['value'] == THRESHOLD
    for slot in ('split', 'eda.target_rate', 'eda.special_values',
                 f'eda.rate_by:{junior["rate_by"]}', 'fit.baseline', 'fit.logistic',
                 'policy.evaluation'):
        assert view['results'][slot]['current'] is True, slot
    assert {i['status'] for i in view['artifacts']['items'].values()} == {'ok'}
    assert view['current_step'] == 'conclusion'

    # 8. a capacity of 100: re-evaluated on the stored predictions, without refit
    fits_before = {e['result_id']: e['blobs']['predictions'] for e in _fits(study)}
    exposure_before = fk.exposure_records(study)
    chat = Chat(study, work, 'chat5')
    capacity = chat.run('policy.evaluate', '--rule', CAPACITY)
    assert capacity['status'] == 'promoted'
    assert {e['result_id']: e['blobs']['predictions'] for e in _fits(study)} == fits_before
    new_exposure = fk.exposure_records(study)[len(exposure_before):]
    assert [r['purpose'] for r in new_exposure] == ['validation_policy_selection']
    state = fk.read.open(study).state
    assert state['current']['fit.logistic'] == logistic['result_id']
    assert state['current']['fit.baseline'] == baseline['result_id']
    assert capacity['values']['predictions'] == {'fit.baseline': baseline['result_id'],
                                                 'fit.logistic': logistic['result_id']}
    # the adopted threshold is not silently replaced: capacity needs its own confirmation
    assert chat.status()['view']['decisions']['policy']['value'] == THRESHOLD
    p = chat.propose('policy', CAPACITY, 'You call the 100 highest-scored clients instead.')
    assert chat.confirm(p, 'garde ça', expect=2)['error']['code'] == 'ambiguous_confirmation'
    assert chat.status()['view']['decisions']['policy']['value'] == THRESHOLD
    adopted = chat.confirm(p, 'Yes: our desk can make 100 calls, take the top 100.')
    assert adopted['result']['invalidation']['mutation'] == 'policy.rule_type'

    # 9. a proportionate conclusion, checked before it is proposed
    rule = capacity['values']['rules'][CAPACITY]
    model, base = rule['models']['fit.logistic'], rule['models']['fit.baseline']
    text = (f'On the validation rows, the 100 highest logistic scores held '
            f'{model["true_positives"]:.0f} positive rows, against {base["true_positives"]:.1f} '
            f'expected for the constant baseline. The rule was chosen on these rows, so the '
            f'comparison is optimistic and is not a forecast. Keep the baseline until a pilot '
            f'on new clients confirms the ranking.')
    chat = Chat(study, work, 'chat6')
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'check', '--text', '-',
                           '--study', str(study)], input=text, capture_output=True, text=True,
                          cwd=work, env=fk.env(), timeout=120)
    draft = json.loads(proc.stdout)
    assert proc.returncode == 0 and draft['clean'] is True, draft['findings']
    assert {t['text'] for t in draft['traced']} >= {f'{model["true_positives"]:.0f}', '100'}
    p = chat.propose('conclusion', {'verdict': 'keep_baseline', 'text': text},
                     'You keep the baseline and record why.')
    chat.confirm(p, 'I keep the baseline for now and we plan a pilot.')

    # 10. check of the HTML report and the notebook: no error
    final = chat.status()['view']
    assert all(final['decisions'][d]['status'] == 'confirmed' for d in final['decisions'])
    result = chat('check')
    assert result['clean'] is True and result['counts']['error'] == 0, result['findings']
    page = (study / 'reports/study.html').read_text()
    tags = Tags()
    tags.feed(page)
    controls = [t for t, a in tags.tags if t in ('input', 'form', 'select', 'textarea', 'option')]
    buttons = [a for t, a in tags.tags if t == 'button']
    assert controls == [] and len(buttons) == 1 and 'data-theme-toggle' in buttons[0]
    data = [a for t, a in tags.tags if t == 'data']
    assert len(data) > 50
    assert all(a.get('data-result-id') and a.get('data-path') for a in data)
    current = {r['result_id'] for r in final['results'].values() if r['current']}
    assert {a['data-result-id'] for a in data} <= current
    assert not [f for f in result['findings'] if f['code'] == 'number_outside_result']
    notebook = (study / 'notebooks/study_generated.py').read_text()
    assert f'GENERATED_REVISION = {final["revision"]}' in notebook

    # 11. an injected HTML render failure keeps the previous report, with a stale banner
    previous = page
    chat = Chat(study, work, 'chat7')
    out = chat('decide', 'propose', 'conclusion', '--value-json',
               json.dumps({'verdict': 'inconclusive', 'text': 'Not enough rows to decide.'}),
               '--restatement', 'You call the study inconclusive.', '--rationale', 'Small sample.',
               '--request-id', chat.rid('propose-again'), '--expected-revision', chat.rev(),
               expect=3, extra_env={'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': 'render_html'})
    assert out['ok'] is True and out['artifacts']['report']['status'] == 'failed'
    assert out['artifacts']['notebook']['status'] == 'ok'
    kept = (study / 'reports/study.html').read_text()
    assert 'data-hypotrail-banner="stale"' in kept
    assert re.sub(r'<!--hypotrail:banner-->.*?<!--/hypotrail:banner-->', '', kept, flags=re.S) == \
        re.sub(r'<!--hypotrail:banner-->.*?<!--/hypotrail:banner-->', '', previous, flags=re.S)
    after = Chat(study, work, 'chat8').view
    assert after['artifacts']['items']['report']['status'] == 'failed'
    assert after['artifacts']['status'] == 'failed'

    summary = {'case': name, 'rows': split['values']['n_rows'],
               'train': parts['train'], 'validation': parts['validation'],
               'train_rate': [target['n_positive'], target['n_rows'], round(target['rate'], 4)],
               'special_values': {f'{s["column"]}={s["value"]}': s['n_rows']
                                  for s in specials['special_values']},
               'rate_by_groups': len(rate_by['values']['groups']),
               'features_used': len(used),
               'auc': {'baseline': baseline['values']['validation']['roc_auc'],
                       'logistic': round(logistic['values']['validation']['roc_auc'], 4)},
               THRESHOLD: {k: evaluation['values']['rules'][THRESHOLD]['models']['fit.logistic'][k]
                           for k in ('selected', 'true_positives', 'precision', 'recall')},
               CAPACITY: {'logistic_tp': model['true_positives'],
                          'baseline_tp': round(base['true_positives'], 2),
                          'precision': model['precision'], 'recall': round(model['recall'], 4),
                          'delta_precision': rule['deltas']['fit.logistic']['precision']},
               'final_revision': final['revision']}
    with capsys.disabled():
        print('\nwalkthrough', json.dumps(summary, sort_keys=True))
    if name == 'bank':     # plan section 7 had 365 of 3,164 training rows of 4,521; since
        # ADR 0006 the split divides the 3,617 development rows (904 sealed at init)
        assert split['values']['n_rows'] == 3617
        assert (target['n_positive'], target['n_rows']) == (292, 2531)
