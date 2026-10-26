"""Owner session 2026-10-26, remark R1: the engine tells the agent whether the study panel is
on, at which stage, and which tab shows the current step (``next_action.panel``,
:mod:`mlkit.study.companion_env`). Absent when the panel is off, so the default payload is
unchanged. The labels are checked against the panel's copy in
``clients/vscode-companion/test/test_panel_labels.py``."""
from __future__ import annotations

import json

import pytest

from mlkit.study import commands as cmd, companion_env as ce, launch, view

from flowkit import Flow


@pytest.fixture(autouse=True)
def _panel_env_cleared(monkeypatch):
    monkeypatch.delenv(ce.ENV_VAR, raising=False)
    monkeypatch.delenv(ce.STAGE_ENV, raising=False)


def _settings(study, text: str):
    path = study / ce.SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


# --- the flag and the stage, as the extension reads them (lib/flag.js) ---------------------

@pytest.mark.parametrize('raw, stage', [
    ('v0', 'v0'), ('v1', 'v1'), ('v2', 'v2'), ('v3', 'v3'),
    ('v4', 'v3'), ('v99', 'v3'), ('v999', 'v3'),           # a later stage: the highest known
    ('v1000', 'v0'), ('V2', 'v0'), ('v', 'v0'), ('v-1', 'v0'), ('v2 ', 'v0'), ('2', 'v0'),
    ('', 'v0'), (None, 'v0'), (2, 'v0'), (True, 'v0')])
def test_stage_normalisation_matches_the_extension(raw, stage):
    assert ce.normalize_stage(raw) == stage


def test_the_environment_turns_the_panel_on_with_1_only(tmp_path):
    assert ce.SETTINGS == launch.SETTINGS
    assert ce.enabled(tmp_path, env={}) is False
    assert ce.enabled(tmp_path, env={ce.ENV_VAR: '1'}) is True
    for value in ('0', 'true', 'yes', 'on', '', ' 1'):
        assert ce.enabled(tmp_path, env={ce.ENV_VAR: value}) is False, value


def test_the_study_settings_turn_the_panel_on_with_true_only(tmp_path):
    _settings(tmp_path, json.dumps({ce.SETTING_ENABLED: True}))
    assert ce.enabled(tmp_path, env={}) is True
    for value in (False, 'true', 1, None):
        _settings(tmp_path, json.dumps({ce.SETTING_ENABLED: value}))
        assert ce.enabled(tmp_path, env={}) is False, value
    # VS Code's own format: comments and trailing commas; strings that look like comments
    _settings(tmp_path, '{\n  // the panel\n  "python.defaultInterpreterPath": "/a//b/*c*/",\n'
                        '  /* on */ "hypotrail.companion.enabled": true,\n'
                        '  "hypotrail.companion.stage": "v2",\n}\n')
    assert ce.read_settings(tmp_path)['python.defaultInterpreterPath'] == '/a//b/*c*/'
    assert ce.enabled(tmp_path, env={}) is True and ce.stage(tmp_path, env={}) == 'v2'
    for broken in ('{"hypotrail.companion.enabled": true', '[true]', 'not json', ''):
        _settings(tmp_path, broken)
        assert ce.enabled(tmp_path, env={}) is False, broken
        assert ce.stage(tmp_path, env={}) == 'v0', broken
    (tmp_path / ce.SETTINGS).unlink()
    assert ce.read_settings(tmp_path) == {} and ce.enabled(tmp_path, env={}) is False


def test_the_stage_comes_from_the_environment_then_the_settings(tmp_path):
    assert ce.stage(tmp_path, env={}) == 'v0'
    _settings(tmp_path, json.dumps({ce.SETTING_STAGE: 'v1'}))
    assert ce.stage(tmp_path, env={}) == 'v1'
    assert ce.stage(tmp_path, env={ce.STAGE_ENV: 'v3'}) == 'v3'
    assert ce.stage(tmp_path, env={ce.STAGE_ENV: ''}) == 'v1'           # empty: the setting
    assert ce.stage(tmp_path, env={ce.STAGE_ENV: 'beta'}) == 'v0'       # invalid: v0
    _settings(tmp_path, json.dumps({ce.SETTING_STAGE: 'v7'}))
    assert ce.stage(tmp_path, env={}) == 'v3'
    _settings(tmp_path, json.dumps({ce.SETTING_STAGE: 3}))
    assert ce.stage(tmp_path, env={}) == 'v0'


# --- the tabs, their labels, and where a step is shown ---------------------------------------

def test_the_tabs_of_each_stage():
    assert ce.tabs('v0') == ()                                        # one page, no tabs
    assert ce.tabs('v1') == ('overview', 'decisions')
    assert ce.tabs('v2') == ('overview', 'eda', 'decisions', 'evidence', 'whatif')
    assert ce.tabs('v3') == ce.TAB_ORDER


@pytest.mark.parametrize('lang, labels, title', [
    ('en', {'overview': 'Overview', 'eda': 'Data & EDA', 'decisions': 'Decisions',
            'evidence': 'Evidence', 'whatif': 'What if?', 'learn': 'Learn & hand off'},
     'Hypotrail study'),
    ('fr', {'overview': "Vue d'ensemble", 'eda': 'Données et EDA', 'decisions': 'Décisions',
            'evidence': 'Preuves', 'whatif': 'Et si ?', 'learn': 'Apprendre et transmettre'},
     'Étude Hypotrail')])
def test_the_labels_are_in_the_study_language(tmp_path, lang, labels, title):
    found = ce.panel({'kind': 'show_data_card', 'step': 'discover_data'}, tmp_path, lang,
                     env={ce.ENV_VAR: '1', ce.STAGE_ENV: 'v3'})
    assert list(found) == list(ce.PANEL_KEYS)
    assert found['stage'] == 'v3' and found['title'] == title and found['tabs'] == labels
    assert list(found['where']) == list(ce.WHERE_KEYS)
    assert found['where']['tab'] == 'eda' and found['where']['label'] == labels['eda']
    assert labels['eda'] in found['where']['line']
    other = ce.panel({}, tmp_path, 'de', env={ce.ENV_VAR: '1'})       # unknown: English
    assert other['title'] == 'Hypotrail study' and other['tabs'] == {}


STEPS = [
    ({'kind': 'show_data_card', 'step': 'discover_data'}, 'eda'),
    ({'kind': 'run', 'step': 'train_eda', 'activity': 'eda.target_rate'}, 'eda'),
    ({'kind': 'run', 'step': 'train_eda', 'activity': 'eda.distribution:age'}, 'eda'),
    ({'kind': 'propose', 'step': 'prediction_time', 'decision': 'prediction_time'}, 'decisions'),
    ({'kind': 'await_user_words', 'step': 'split', 'decision': 'split'}, 'decisions'),
    ({'kind': 'reconfirm', 'step': 'preprocessing', 'decision': 'preprocessing'}, 'decisions'),
    ({'kind': 'resolve_hold', 'step': 'success_criterion'}, 'decisions'),
    ({'kind': 'propose', 'step': 'final_test', 'decision': 'final_test'}, 'decisions'),
    ({'kind': 'run', 'step': 'split', 'activity': 'split'}, 'evidence'),
    ({'kind': 'run', 'step': 'models', 'activity': 'fit.logistic'}, 'evidence'),
    ({'kind': 'run', 'step': 'models', 'activity': 'fit.variant'}, 'evidence'),
    ({'kind': 'run', 'step': 'models', 'activity': 'diag.binary'}, 'evidence'),
    ({'kind': 'run', 'step': 'final_test', 'activity': 'final_test.evaluation'}, 'evidence'),
    ({'kind': 'run', 'step': 'conclusion', 'activity': 'diag.final_test'}, 'evidence'),
    ({'kind': 'run', 'step': 'policy', 'activity': 'policy.evaluation'}, 'whatif'),
    ({'kind': 'propose', 'step': 'policy', 'decision': 'policy'}, 'whatif'),
    ({'kind': 'await_user_words', 'step': 'model_choice', 'decision': 'model_choice'},
     'whatif'),
    ({'kind': 'done'}, 'overview'),
    ({'kind': 'blocked', 'step': 'conclusion'}, 'overview'),
    ({'kind': 'outcome_unknown', 'activity': 'fit.logistic'}, 'overview'),
    ({'kind': 'acknowledge_interruption'}, 'overview'),
]


@pytest.mark.parametrize('action, tab', STEPS)
def test_where_each_step_is_shown(action, tab):
    assert ce.wanted_tab(action) == tab
    assert ce.where(action, 'v3')['tab'] == tab
    # v1 has only the Overview and Decisions: the closest one; v0 is one page
    closest = {'eda': 'overview', 'evidence': 'overview', 'whatif': 'decisions'}.get(tab, tab)
    assert ce.where(action, 'v1')['tab'] == closest
    page = ce.where(action, 'v0', 'fr')
    assert page == {'tab': None, 'label': 'Étude Hypotrail',
                    'line': 'Dans le panneau « Étude Hypotrail ».'}
    assert ce.where({'kind': 'run', 'activity': 'fit.logistic'}, 'v2', 'fr')['line'] == \
        'Dans le panneau : onglet Preuves.'


def test_annotate_leaves_a_missing_action_alone(tmp_path):
    env = {ce.ENV_VAR: '1'}
    assert ce.annotate(None, tmp_path, 'en', env) is None
    action = {'kind': 'done'}
    assert ce.annotate(action, tmp_path, 'en', {}) == {'kind': 'done'}       # panel off
    assert ce.annotate(action, tmp_path, 'en', env)['panel']['stage'] == 'v0'
    assert list(action)[-1] == 'panel'


# --- in the command outputs: only when the panel is on ---------------------------------------

def _outputs(flow: Flow) -> dict:
    """The ``next_action`` of every command surface that gives one."""
    status = flow.call('status', '--study', flow.study)
    summary = flow.call('status', '--summary', '--study', flow.study)
    fields = flow.call('status', '--summary', '--fields', 'next_action', '--study', flow.study)
    plan = flow.call('plan', '--study', flow.study)
    return {'status': status['view']['next_action'], 'summary': summary['next_action'],
            'fields': fields['next_action'], 'plan': plan['next_action']}


def test_next_action_has_no_panel_by_default(tmp_path, synthetic_case_dir):
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    init = flow.init()
    assert 'panel' not in init['next_action']
    for surface, action in _outputs(flow).items():
        assert 'panel' not in action, surface
    out = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
                    '--restatement', 'You predict before the call.', '--rationale', 'r',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert 'panel' not in out['next_action']


def test_next_action_names_the_panel_tab_when_the_panel_is_on(tmp_path, synthetic_case_dir,
                                                              monkeypatch):
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    init = flow.init()
    assert init['next_action']['panel']['where']['tab'] == 'eda'      # step 0: the data card
    for surface, action in _outputs(flow).items():
        assert action['panel']['stage'] == 'v3', surface
        assert action['panel']['where'] == {'tab': 'eda', 'label': 'Data & EDA',
                                            'line': 'In the panel: the Data & EDA tab.'}
        assert list(action)[-1] == 'panel', surface
    out = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
                    '--restatement', 'You predict before the call.', '--rationale', 'r',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert out['next_action']['kind'] == 'await_user_words'
    assert out['next_action']['panel']['where']['tab'] == 'decisions'
    # the deliverables' view never depends on the environment
    assert 'panel' not in view.build(flow.study)['next_action']
    # stage v1: the data card's tab does not exist yet, so the Overview
    monkeypatch.setenv(ce.STAGE_ENV, 'v1')
    flow.call('decide', 'withdraw', out['result']['proposal_id'], '--reason', 'r',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    summary = cmd.status(flow.study, summary=True).payload['next_action']
    assert summary['panel']['tabs'] == {'overview': 'Overview', 'decisions': 'Decisions'}


def test_the_study_settings_turn_it_on_too(tmp_path, synthetic_case_dir):
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    flow.init()
    settings = json.loads((flow.study / ce.SETTINGS).read_text())       # init wrote it
    assert ce.SETTING_ENABLED not in settings                         # and left the panel off
    assert 'panel' not in cmd.status(flow.study, summary=True).payload['next_action']
    settings.update({ce.SETTING_ENABLED: True, ce.SETTING_STAGE: 'v2'})
    _settings(flow.study, json.dumps(settings))
    panel = cmd.status(flow.study, summary=True).payload['next_action']['panel']
    assert panel['stage'] == 'v2' and 'learn' not in panel['tabs']
    assert panel['where']['label'] == 'Data & EDA'
