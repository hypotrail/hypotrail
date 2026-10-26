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


# --- R1b: where the panel shows what the command produced (``panel.shown``) -------------------

# (what the command produced, the next action it returned) -> the section that shows it.
PRODUCED = [
    ({'command': 'init'}, {'kind': 'show_data_card'}, 'data_card'),
    ({'command': 'status'}, {'kind': 'show_data_card'}, 'data_card'),
    ({'command': 'decide', 'action': 'decide.propose'}, {'kind': 'await_user_words'}, 'waiting'),
    ({'command': 'decide', 'action': 'decide.confirm', 'opening': None}, {'kind': 'run'},
     'history'),
    ({'command': 'decide', 'action': 'decide.confirm', 'opening': {'status': 'promoted'}},
     {'kind': 'run'}, 'final_test'),
    ({'command': 'decide', 'action': 'decide.confirm', 'opening': {'status': 'refused'}},
     {'kind': 'propose'}, 'history'),
    ({'command': 'decide', 'action': 'decide.withdraw'}, {'kind': 'propose'}, 'history'),
    ({'command': 'decide', 'action': 'decide.note', 'kind': 'hold'}, {'kind': 'resolve_hold'},
     'holds'),
    ({'command': 'decide', 'action': 'decide.note', 'kind': 'correction'}, {'kind': 'run'},
     'history'),
    ({'command': 'decide', 'action': 'decide.resolve_note'}, {'kind': 'await_user_words'},
     'waiting'),
    ({'command': 'decide', 'action': 'study.set_mode'}, {'kind': 'run'}, 'mode'),
    ({'command': 'run', 'activity': 'eda.quality', 'slot': 'eda.quality', 'status': 'promoted'},
     {'kind': 'run'}, 'quality'),
    ({'command': 'run', 'activity': 'eda.target_rate', 'slot': 'eda.target_rate',
      'status': 'promoted'}, {'kind': 'propose'}, 'eda.target_rate'),
    ({'command': 'run', 'activity': 'eda.rate_by', 'slot': 'eda.rate_by:job',
      'status': 'already_current'}, {'kind': 'run'}, 'eda.rate_by:job'),
    ({'command': 'run', 'activity': 'split', 'slot': 'split', 'status': 'promoted'},
     {'kind': 'run'}, 'development'),
    ({'command': 'run', 'activity': 'fit.logistic', 'slot': 'fit.logistic',
      'status': 'promoted'}, {'kind': 'run'}, 'development'),
    ({'command': 'run', 'activity': 'fit.variant', 'slot': 'fit.variant:2',
      'status': 'promoted'}, {'kind': 'run'}, 'development'),
    ({'command': 'run', 'activity': 'policy.evaluation', 'slot': 'policy.evaluation',
      'status': 'promoted'}, {'kind': 'run'}, 'development'),
    ({'command': 'run', 'activity': 'evaluate.regression', 'slot': 'evaluate.regression',
      'status': 'promoted'}, {'kind': 'run'}, 'development'),
    ({'command': 'run', 'activity': 'diag.binary', 'slot': 'diag.binary', 'status': 'promoted'},
     {'kind': 'propose'}, 'diagnostics'),
    ({'command': 'run', 'activity': 'diag.regression', 'slot': 'diag.regression',
      'status': 'promoted'}, {'kind': 'propose'}, 'diagnostics'),
    ({'command': 'run', 'activity': 'final_test.evaluation', 'slot': 'final_test.evaluation',
      'status': 'promoted'}, {'kind': 'run'}, 'final_test'),
    ({'command': 'run', 'activity': 'diag.final_test', 'slot': 'diag.final_test',
      'status': 'promoted'}, {'kind': 'propose'}, 'final_test'),
]
# Nothing new for the panel to show: reads, a failed or interrupted run, an acknowledgement,
# a capture, a withdrawn note.
NOTHING = [
    ({'command': 'status'}, {'kind': 'await_user_words'}),
    ({'command': 'plan'}, {'kind': 'run', 'activity': 'fit.logistic'}),
    (None, {'kind': 'done'}),
    ({'command': 'init'}, {'kind': 'propose'}),
    ({'command': 'run', 'activity': 'fit.logistic', 'status': 'failed'}, {'kind': 'run'}),
    ({'command': 'run', 'activity': 'fit.logistic', 'status': 'interrupted_unknown'},
     {'kind': 'outcome_unknown'}),
    ({'command': 'run', 'action': 'run.acknowledge', 'activity': 'eda.distribution',
      'status': 'acknowledged'}, {'kind': 'run'}),
    ({'command': 'run', 'activity': 'predictor.capture', 'status': 'promoted'}, {'kind': 'done'}),
    ({'command': 'decide', 'action': 'decide.withdraw_note'}, {'kind': 'propose'}),
]
SECTION_TAB = {'data_card': 'eda', 'quality': 'eda', 'waiting': 'decisions',
               'holds': 'decisions', 'history': 'decisions', 'mode': 'decisions',
               'development': 'evidence', 'diagnostics': 'evidence', 'final_test': 'evidence'}
SHOWN_EXAMPLES = {
    ('en', 'history'): 'In the panel: Decisions → Decision history.',
    ('fr', 'history'): 'Dans le panneau : Décisions → Historique des décisions.',
    ('en', 'waiting'): 'In the panel: Decisions → Waiting for your answer.',
    ('fr', 'waiting'): 'Dans le panneau : Décisions → En attente de votre réponse.',
    ('fr', 'data_card'): 'Dans le panneau : Données et EDA → Fiche des données.',
    ('fr', 'quality'): 'Dans le panneau : Données et EDA → Qualité des données.',
    ('en', 'development'): 'In the panel: Evidence → Development evidence · used to choose.',
    ('fr', 'final_test'): 'Dans le panneau : Preuves → Test final.',
    ('fr', 'eda.rate_by:job'): 'Dans le panneau : Données et EDA → Taux de résultat par groupe '
                               '· job.',
    ('en', 'eda.target_rate'): 'In the panel: Data & EDA → Outcome rate.',
}


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('stage_id', ce.STAGES)
@pytest.mark.parametrize('produced, action, section', PRODUCED)
def test_shown_names_the_section_of_each_command(produced, action, section, stage_id, lang):
    """R1b: the line names the tab and the section that show what the command produced, at
    every stage: the section when the stage shows it, else the closest tab (no section),
    and at v0 the panel's one page (with the section when the page shows it)."""
    assert ce.shown_section(produced, action) == section
    found = ce.shown(produced, action, stage_id, lang)
    assert list(found) == list(ce.SHOWN_KEYS)
    tab = SECTION_TAB.get(section, 'eda')
    label = ce.section_label(section, lang)
    since = ce.SECTIONS['eda_card' if section.startswith('eda.') else section][1]
    reached = ce.STAGES.index(stage_id) >= ce.STAGES.index(since)
    if stage_id == 'v0':
        assert found['tab'] is None
        if reached:                                   # the one page shows it (a waiting card)
            assert found['section'] == section and found['label'] == label
            assert found['line'] == ce.SHOWN_LINES[lang]['page'].format(
                title=ce.TITLES[lang], section=label)
        else:
            assert found == {'tab': None, 'section': None, 'label': ce.TITLES[lang],
                             'line': ce.LINES[lang]['page'].format(label=ce.TITLES[lang])}
    elif reached and tab in ce.tabs(stage_id):
        assert found['tab'] == tab and found['section'] == section and found['label'] == label
        assert found['line'] == ce.SHOWN_LINES[lang]['tab'].format(
            tab=ce.TAB_LABELS[lang][tab], section=label)
        if (lang, section) in SHOWN_EXAMPLES:
            assert found['line'] == SHOWN_EXAMPLES[(lang, section)]
    else:                                             # the closest tab the stage has
        assert found['section'] is None
        assert found['tab'] == ce.where({'kind': 'run', 'activity': 'fit.logistic'}
                                        if tab == 'evidence' else
                                        {'kind': 'show_data_card'} if tab == 'eda' else
                                        {'kind': 'done'}, stage_id, lang)['tab']
        assert found['line'] == ce.LINES[lang]['tab'].format(label=ce.TAB_LABELS[lang][found['tab']])


@pytest.mark.parametrize('stage_id', ce.STAGES)
@pytest.mark.parametrize('produced, action', NOTHING)
def test_shown_is_null_for_reads_and_render(produced, action, stage_id):
    """R1b: no line after a command that produced nothing the panel shows (a read, a failed
    or interrupted run, an acknowledgement). ``render`` gives no ``next_action`` at all."""
    assert ce.shown_section(produced, action) is None
    assert ce.shown(produced, action, stage_id, 'fr') is None


CHOICE = {'kind': 'propose', 'step': 'conclusion', 'decision': 'conclusion',
          'choice_options': [{'id': 'keep_baseline', 'value': 'keep_baseline',
                              'label': 'Garder la référence'}]}


# What a command produced, and the section it names whatever the next action is (D3).
PRODUCED_FOR_CHOICE = [
    ({'command': 'decide', 'action': 'decide.confirm', 'opening': {'status': 'promoted'}},
     'final_test'),
    ({'command': 'run', 'activity': 'diag.final_test', 'status': 'promoted'}, 'final_test'),
    ({'command': 'run', 'activity': 'fit.variant', 'slot': 'fit.variant', 'status': 'promoted'},
     'development'),
    ({'command': 'decide', 'action': 'decide.confirm', 'opening': None}, 'history')]
# Commands that produced nothing the panel shows: a read, a failed run, an acknowledgement.
NOTHING_FOR_CHOICE = [{'command': 'status'}, None,
                      {'command': 'run', 'activity': 'fit.variant', 'status': 'failed'},
                      {'command': 'run', 'activity': 'fit.variant', 'status': 'acknowledged'}]


@pytest.mark.parametrize('produced', NOTHING_FOR_CHOICE)
def test_shown_names_the_choice_card_when_the_chat_asks_a_choice(produced):
    """R16 (D20): when the next action is a choice the chat asks (``choice_options``) and the
    command produced nothing the panel shows (a read, a failed run, an acknowledgement), the
    line names the read-only card the panel shows from v1 under "Waiting for your answer"."""
    assert ce.shown_section(produced, CHOICE) is None
    for stage_id in ('v1', 'v2', 'v3'):
        found = ce.shown(produced, CHOICE, stage_id, 'fr')
        assert found == {'tab': 'decisions', 'section': 'choice',
                         'label': 'En attente de votre réponse',
                         'line': 'Dans le panneau : Décisions → En attente de votre réponse.'}
    # v0 is one page without the card: nothing.
    assert ce.shown(produced, CHOICE, 'v0', 'fr') is None
    # An empty list is no choice.
    assert ce.shown(produced, {**CHOICE, 'choice_options': []}, 'v3', 'en') is None


@pytest.mark.parametrize('stage_id', ce.STAGES)
@pytest.mark.parametrize('produced, section', PRODUCED_FOR_CHOICE)
def test_a_write_names_what_it_produced_even_before_a_choice(produced, section, stage_id):
    """D3 (wave W1 integration, coordinator ruling): the line names what the message shows.
    A command that produced something names its own section even when the next action is a
    choice the chat asks: the opening's confirmation names the final test, a variant fit the
    development evidence, a confirmation the history; never the choice card."""
    assert ce.shown_section(produced, CHOICE) == section
    found = ce.shown(produced, CHOICE, stage_id, 'fr')
    assert found == ce.shown(produced, {'kind': 'propose', 'decision': 'conclusion'}, stage_id,
                             'fr')
    assert found is not None and found['section'] != 'choice'


def test_the_section_labels_cover_both_languages():
    assert set(ce.SECTION_LABELS['en']) == set(ce.SECTION_LABELS['fr']) == \
        set(ce.SECTIONS) - {'eda_card'}
    assert set(ce.EDA_CARD_LABELS['en']) == set(ce.EDA_CARD_LABELS['fr'])
    assert ce.section_label('eda.distribution:age', 'fr') == 'Distribution · age'
    assert ce.section_label('history', 'de') == 'Decision history'      # unknown: English


def test_no_panel_key_when_off(tmp_path, synthetic_case_dir):
    """NR-9 (R1b): with the panel off, no payload carries ``panel`` (so no ``shown``): the
    writes (decide, run, acknowledge-free) and the reads keep today's keys."""
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    flow.init()
    out = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
                    '--restatement', 'You predict before the call.', '--rationale', 'r',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    confirm = flow.call('decide', 'confirm', out['result']['proposal_id'], '--user-words',
                        'Yes, I want the prediction_time exactly as you stated it',
                        '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                        '--study', flow.study)
    run = flow.call('run', 'eda.quality', '--request-id', flow.rid(), '--expected-revision',
                    flow.rev(), '--study', flow.study, expect=None)
    for payload in (out, confirm, run):
        assert 'panel' not in (payload.get('next_action') or {}), payload.get('action')
        assert 'shown' not in json.dumps(payload.get('next_action'))
    for surface, action in _outputs(flow).items():
        assert 'panel' not in action, surface


def test_every_write_names_what_it_produced(tmp_path, synthetic_case_dir, monkeypatch):
    """R1b through the commands: ``init`` names the data card, a proposal the waiting card,
    a confirmation the history, a chart its card, a read nothing (after step 0)."""
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    init = flow.call('init', '--case', synthetic_case_dir, '--study', flow.study, '--lang', 'fr')
    assert init['next_action']['panel']['shown']['line'] == \
        'Dans le panneau : Données et EDA → Fiche des données.'
    # step 0: the status read carries the data card too (the `data` command has no next action)
    assert cmd.status(flow.study, summary=True).payload['next_action']['panel']['shown'][
        'section'] == 'data_card'
    out = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
                    '--restatement', 'Vous prédisez avant l’appel.', '--rationale', 'r',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert out['next_action']['panel']['shown']['section'] == 'waiting'
    assert out['next_action']['panel']['where']['tab'] == 'decisions'    # `where` unchanged
    assert list(out['next_action']['panel']) == list(ce.PANEL_KEYS)
    for surface, action in _outputs(flow).items():                        # reads: nothing new
        assert action['panel']['shown'] is None, surface
    confirm = flow.call('decide', 'confirm', out['result']['proposal_id'], '--user-words',
                        'Oui, je veux le prediction_time exactement comme vous le dites',
                        '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                        '--study', flow.study)
    assert confirm['next_action']['panel']['shown']['line'] == \
        'Dans le panneau : Décisions → Historique des décisions.'
    run = flow.call('run', 'eda.quality', '--request-id', flow.rid(), '--expected-revision',
                    flow.rev(), '--study', flow.study)
    assert run['next_action']['panel']['shown']['section'] == 'quality'
    replay = flow.call('run', 'eda.quality', '--request-id', flow.rid(), '--expected-revision',
                       flow.rev(), '--study', flow.study)
    assert replay['status'] == 'already_current'
    assert replay['next_action']['panel']['shown']['section'] == 'quality'
    # the deliverables' view never depends on the environment
    assert 'panel' not in view.build(flow.study)['next_action']
