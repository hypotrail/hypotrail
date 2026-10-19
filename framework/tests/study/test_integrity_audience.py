"""v0.2a, WP-A1: integrity fixes and the audience of engine messages.

* R7: ``init`` writes the study's ``.vscode/settings.json`` (engine Python) only when it is
  absent, else returns a notice with the line to add; ``__marimo__/`` is git-ignored once;
  ``check`` never reports ``.vscode/`` or ``__marimo__/``; the launch commands of the two
  notebooks are in ``init`` and ``status --summary``.
* Every message for a surface carries ``audience`` and a junior variant that names no
  command, flag, or decision id; the HTML report shows the junior variants.
* The recap never says "up to date" before a render.
* ``hypotrail --help`` lists every command; ``explain`` and ``evidence`` print text.
* Feature availability has a per-feature basis; an undiscussed feature is never "Your
  decision" in the report.
* The committed cases and the report carry no tutorial provenance string.
* The glossary has the v0.2a terms, term first, then a contextual example.

Scope U and S (in-process CLI code path, temporary studies only).
"""
from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path

import pytest
import yaml

import flowkit as fk
from mlkit.study import audience, cli, launch, texts
from mlkit.study import view as view_model

# What a junior-facing text must never hold: a command, a flag, a field or decision id.
AGENT_TOKENS = re.compile(r'--|\bhypotrail\b|\b[a-z]+_[a-z_]+\b|\brecord the user')


def _junior_clean(text: str) -> None:
    assert text and not AGENT_TOKENS.search(text), text


@pytest.fixture
def flow(tmp_path, synthetic_case_dir):
    f = fk.Flow(tmp_path / 'study', synthetic_case_dir, prefix='a1')
    f.init()
    return f


# --- R7 ---------------------------------------------------------------------------------

def test_init_writes_the_editor_settings_and_ignores_the_marimo_cache(flow):
    settings = flow.study / '.vscode' / 'settings.json'
    assert json.loads(settings.read_text()) == {launch.INTERPRETER_KEY: launch.interpreter()}
    assert (flow.study / '.gitignore').read_text().splitlines() == ['__marimo__/']
    # Idempotent: a second call writes nothing more.
    assert launch.install_gitignore(flow.study) is False
    assert launch.install_settings(flow.study) is None
    # check: Marimo's cache and the editor settings are not computations outside hypotrail.
    (flow.study / '__marimo__').mkdir()
    (flow.study / '__marimo__' / 'session.json').write_text('{}')
    findings = flow.call('check', '--study', flow.study)['findings']
    untracked = [f for f in findings if f['code'] == 'untracked_files']
    assert untracked == [], untracked


def test_existing_settings_are_kept_and_the_line_is_given(tmp_path, synthetic_case_dir):
    study = tmp_path / 'study'
    (study / '.vscode').mkdir(parents=True)
    own = '{\n  "editor.tabSize": 2\n}\n'
    (study / '.vscode' / 'settings.json').write_text(own)
    (study / '.gitignore').write_text('*.log')
    payload = fk.Flow(study, synthetic_case_dir).init()
    assert (study / '.vscode' / 'settings.json').read_text() == own        # never overwritten
    assert (study / '.gitignore').read_text() == '*.log\n__marimo__/\n'
    [notice] = payload['notices']
    assert tuple(notice) == launch.NOTICE_KEYS and notice['code'] == 'vscode_settings_kept'
    assert notice['audience'] == 'agent' and notice['line'] in notice['message']
    assert notice['line'] == f'"{launch.INTERPRETER_KEY}": {json.dumps(launch.interpreter())}'
    _junior_clean(notice['junior_message'])


def test_launch_commands_open_the_two_notebooks_with_the_engine(flow):
    init_deliverables = launch.deliverables(flow.study)
    assert flow.view()['deliverables'] == init_deliverables
    launch_ = init_deliverables['launch']
    assert set(launch_) == {'notebook', 'workbench'}
    for name, mode, rel in (('notebook', 'run', 'notebooks/study_generated.py'),
                            ('workbench', 'edit', 'notebooks/workbench.py')):
        item = launch_[name]
        assert tuple(item) == launch.LAUNCH_KEYS and item['mode'] == mode
        assert item['path'] == rel
        assert item['argv'][-3:] == ['marimo', mode, str(flow.study.resolve() / rel)] or \
            item['argv'][-4:] == ['-m', 'marimo', mode, str(flow.study.resolve() / rel)]
    recorded = json.loads((flow.study / '.hypotrail' / 'agent.json').read_text())['cli']['argv']
    if recorded[:3] == ['uv', 'run', '--project']:
        assert launch_['notebook']['argv'][:4] == recorded[:4]


# --- audience ---------------------------------------------------------------------------

def test_next_action_messages_carry_their_audience(flow):
    first = flow.view()['next_action']
    assert first['audience'] == 'junior' and first['junior_message'] == first['message']
    p = flow.call('decide', 'propose', 'prediction_time', '--value', 'at expiry',
                  '--restatement', 'You predict at expiry.', '--rationale', 'Scenario.',
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                  '--study', flow.study)
    assert p['ok']
    action = flow.view()['next_action']
    assert action['kind'] == 'await_user_words' and action['audience'] == 'agent'
    assert 'record the user' in action['message']           # the agent's text is unchanged
    _junior_clean(action['junior_message'])
    assert 'your own words' in action['junior_message']
    assert flow.call('plan', '--study', flow.study)['next_action'] == action
    for kind, extra in (('outcome_unknown', {'activity': 'fit.logistic'}),
                        ('acknowledge_interruption', {'execution_id': 'e_1'}),
                        ('reconfirm', {'decision': 'feature_availability'}),
                        ('blocked', {'step': 'split', 'requires': ['prediction_time']}),
                        ('done', {})):
        out = audience.next_action({'kind': kind, 'message': 'agent text', **extra})
        assert out['audience'] == 'agent', kind
        _junior_clean(out['junior_message'])


def test_limits_and_deliverables_carry_their_audience(flow):
    v = flow.view()
    by_id = {x['id']: x for x in v['not_yet_defensible']}
    unconfirmed = by_id['unconfirmed_decisions']
    assert unconfirmed['audience'] == 'agent' and 'prediction_time' in unconfirmed['text']
    _junior_clean(unconfirmed['junior_text'])
    assert 'the prediction moment' in unconfirmed['junior_text']
    for x in v['not_yet_defensible']:
        assert x['audience'] in audience.AUDIENCES and x['junior_text']
        if x['audience'] == 'junior':
            assert x['junior_text'] == x['text']
    top = flow.call('status', '--summary', '--study', flow.study)['not_yet_defensible']['top']
    for x in top:            # compact: the junior variant only where the text is the agent's
        assert (x['junior_text'] is None) == (x['audience'] == 'junior'), x
    held = audience.limit({'id': 'open_holds', 'decisions': ['policy'],
                           'text': "The junior set a condition ..."})
    assert held['audience'] == 'agent' and held['junior_text'].startswith('You set')
    for status in ('ok', 'stale', 'failed', 'not_rendered'):
        item = audience.artifact('report', {'status': status})
        assert item['audience'] == 'agent'
        _junior_clean(item['junior_message'])
    assert 'your free space' in audience.artifact('workbench', {'generated': False})[
        'junior_message']


def test_recap_says_not_rendered_then_up_to_date_and_has_a_junior_variant(flow):
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['recap'][2].endswith('report and notebook not rendered yet.')
    assert summary['recap_audience'] == 'agent'
    assert len(summary['recap_junior']) == len(view_model.RECAP_LABELS)
    flow.call('render', '--study', flow.study)
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['recap'][2].endswith('the report and notebook are up to date.'), summary['recap']
    # Only the report rendered: the notebook is named as not rendered (unit).
    items = {'report': {'status': 'ok'}}
    assert view_model._deliverables_line(items) == 'notebook not rendered yet'
    assert view_model._deliverables_line({'report': {'status': 'stale'},
                                          'notebook': {'status': 'ok'}}) == 'report not up to date'


def test_junior_recap_quotes_a_hold_in_the_second_person(flow):
    flow.call('decide', 'note', '--about', 'prediction_time', '--text',
              'only if the branch confirms the expiry date', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert "in the junior's words" in summary['recap'][3]
    assert 'On hold in your words' in summary['recap_junior'][3]
    assert "junior" not in ' '.join(summary['recap_junior'])


def test_the_report_shows_the_junior_variants(flow):
    flow.call('render', '--study', flow.study)
    page = (flow.study / 'reports' / 'study.html').read_text()
    v = flow.view()
    assert v['next_action']['junior_message'] in page.replace('&#x27;', "'")
    unconfirmed = next(x for x in v['not_yet_defensible'] if x['id'] == 'unconfirmed_decisions')
    assert unconfirmed['junior_text'] in page and unconfirmed['text'] not in page


# --- help and text output ---------------------------------------------------------------

def test_help_lists_every_command_on_one_line_each():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(['--help']) == 0
    text = out.getvalue()
    for name in ('init', 'status', 'plan', 'decide', *cli.EXTENSIONS):
        line = next((x for x in text.splitlines() if x.strip().startswith(name + ' ')), None)
        assert line is not None and len(line.split(None, 1)) == 2, (name, text)
    assert set(cli.EXTENSION_HELP) == set(cli.EXTENSIONS)


def test_explain_and_evidence_print_text(flow):
    for command in ('explain', 'evidence'):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main([command, '--study', str(flow.study), '--format', 'text'])
        text = out.getvalue()
        assert code == 0, text
        with pytest.raises(ValueError):
            json.loads(text)
        assert not text.lstrip().startswith('{')
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.main(['explain', '--study', str(flow.study), '--format', 'text', '--term', 'leakage'])
    assert out.getvalue().startswith('Glossary of this binary study')
    assert 'Leakage\n  A variable that carries information' in out.getvalue()


# --- feature availability basis ---------------------------------------------------------

def test_undiscussed_features_are_never_the_juniors_decision(flow, synthetic_case_dir):
    flow.decide('prediction_time', 'when the membership expires, before any reminder')
    value = fk.availability(synthetic_case_dir, reminders_sent='not_available',
                            fines_outstanding='uncertain_included')
    flow.decide('feature_availability', value,
                'Exclude the reminders sent, they come after expiry, and keep fines_outstanding '
                'with a doubt.')
    decision = flow.view()['decisions']['feature_availability']
    basis = decision['feature_basis']
    assert set(basis) == set(value)
    assert {f for f, b in basis.items() if b == 'discussed'} == {'reminders_sent',
                                                                 'fines_outstanding'}
    assert all(b == 'default_from_case' for f, b in basis.items()
               if f not in ('reminders_sent', 'fines_outstanding'))
    summary = flow.call('status', '--summary', '--study', flow.study)
    grouped = summary['decisions']['feature_availability']['feature_basis']
    assert sorted(grouped['discussed']) == ['fines_outstanding', 'reminders_sent']
    flow.call('render', '--study', flow.study)
    page = (flow.study / 'reports' / 'study.html').read_text()
    labels = texts.report()
    rows = re.findall(r'<tr data-feature="([^"]+)" data-feature-basis="([^"]*)">(.*?)</tr>', page)
    assert len(rows) == len(value)
    for name, b, row in rows:
        mine = labels['availability_basis']['discussed']
        case = labels['availability_basis']['default_from_case']
        assert (mine in row) == (b == 'discussed') and (case in row) == (b != 'discussed'), row
    assert 'Your decision</th>' not in page
    # Doubled or raw labels of the case statement are gone.
    assert 'Unknown unknown' not in page and not re.search(
        r'Scenario assumption</span> <span data-literal="case">available_at_prediction', page)


def test_feature_basis_matching():
    assert view_model.mentions('reminders_sent', 'drop the Reminders sent column')
    assert view_model.mentions('reminders_sent', 'reminders-sent is late')
    assert not view_model.mentions('age', 'the agency said so')
    assert view_model.feature_basis({'a': 'x'}, None) is None
    assert view_model.feature_basis({'pdays': 'x', 'age': 'y'},
                                    {'user_words': 'keep pdays', 'restatement': ''}) == {
        'age': 'default_from_case', 'pdays': 'discussed'}


# --- provenance strings -----------------------------------------------------------------

@pytest.mark.parametrize('case_dir', [fk.BANK, fk.REPO / 'use-cases' / 'auto-mpg'])
def test_cases_carry_no_tutorial_provenance_in_their_statements(case_dir):
    doc = yaml.safe_load((case_dir / 'case.yaml').read_text(encoding='utf-8'))
    shown = {k: v for k, v in doc.items() if k != 'migration'}
    text = json.dumps(shown, ensure_ascii=False)
    for banned in ('project.json', 'Not described in project', 'sha256 ', 'Companion tutorial'):
        assert banned not in text, banned
    if (case_dir / 'results.json').is_file():
        assert any(r.startswith('prior_exposure: results.json sha256 ')
                   for r in doc['migration']['rules'])


# --- glossary ---------------------------------------------------------------------------

V02A_TERMS = ('auc', 'average_precision', 'lift', 'overfitting', 'regularisation',
              'one_hot_encoding', 'imputation', 'standardisation', 'calibration',
              'cross_validation', 'final_test', 'development_rows', 'leakage', 'base_rate',
              'confidence_interval')
BINARY_ONLY = ('auc', 'average_precision', 'lift', 'calibration', 'base_rate')


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_glossary_holds_the_v02a_terms_with_a_contextual_example(task):
    terms = texts.glossary_terms(task)
    for term in V02A_TERMS:
        if task == 'regression' and term in BINARY_ONLY:
            assert term not in terms
            continue
        entry = terms[term]
        assert entry['term'] and entry['definition'], term
        if term != 'confidence_interval' or task == 'binary':
            assert 'For example' in entry['definition'], (task, term)
        words = 'bank' if task == 'binary' else 'car'
        if term not in ('confidence_interval',):
            assert words in entry['definition'].lower(), (task, term)


def test_explain_lists_the_new_terms(flow):
    ids = {t['id'] for t in flow.call('explain', '--study', flow.study)['terms']}
    assert set(V02A_TERMS) <= ids


def test_cli_text_for_init_names_the_launch_commands(tmp_path, synthetic_case_dir):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.main(['init', '--case', str(synthetic_case_dir), '--study', str(tmp_path / 's'),
                  '--format', 'text'])
    assert 'open the notebook: ' in out.getvalue() and ' marimo run ' in out.getvalue()
    assert Path(tmp_path / 's' / '.vscode' / 'settings.json').is_file()
