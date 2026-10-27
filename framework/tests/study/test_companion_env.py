"""Owner session 2026-10-26 (R1, R1b) and contract P1 (CLI-CONTRACT §17.1, ADR 0004 decision
13): the engine tells the agent whether the study panel is on, at which stage, and which place
of its one page shows the next step (``where``) and what the command produced (``shown``),
by an anchor (``next_action.panel`` version 2, :mod:`mlkit.study.companion_env`). Absent when
the panel is off, so the default payload is unchanged. Rewritten for version 2: the tab form
(``tabs``, ``where.tab``, ``shown.tab``, ``shown.section``) is gone, with its tests; the labels
are checked against the panel's copy in ``clients/vscode-companion/test/test_panel_labels.py``.
"""
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


# --- anchors, where and shown (CLI-CONTRACT §17.1.1 to §17.1.3) -----------------------------

# A binary study's plan as ``state.derive_plan`` gives it (ids, decisions, activities).
PLAN = [{'id': i, 'decision': d, 'activities': a} for i, d, a in (
    ('discover_data', None, []), ('prediction_time', 'prediction_time', []),
    ('feature_availability', 'feature_availability', []), ('split', 'split', ['split']),
    ('success_criterion', 'success_criterion', []), ('structural_eda', None, ['eda.quality']),
    ('preprocessing', 'preprocessing', []),
    ('train_eda', None, ['eda.target_rate', 'eda.special_values']),
    ('models', None, ['fit.baseline', 'fit.logistic']),
    ('model_variant', 'model_variant', ['fit.variant', 'fit.variant:2']),
    ('model_choice', 'model_choice', []),
    ('policy', 'policy', ['policy.evaluation', 'diag.binary']),
    ('final_test', 'final_test', ['final_test.evaluation']), ('conclusion', 'conclusion', []))]


def test_the_step_of_a_result():
    """§17.1.1: the plan step that lists the slot or the activity; an ``eda.*`` chart that read
    no target in the structural step, any other in the exploration; a fit or a diagnostic in
    the models; the final evaluation and its diagnostics in the final test."""
    cases = {('eda.target_rate', None, None): 'train_eda',
             ('fit.variant', 'fit.variant:2', None): 'model_variant',
             ('diag.binary', 'diag.binary', None): 'policy',
             ('eda.distribution', 'eda.distribution:age', False): 'structural_eda',
             ('eda.rate_by', 'eda.rate_by:job', True): 'train_eda',
             ('eda.correlation', 'eda.correlation', False): 'structural_eda',
             ('fit.variant', 'fit.variant:3', None): 'model_variant',
             ('diag.regression', None, None): 'models',
             ('diag.final_test', None, None): 'final_test',
             ('final_test.evaluation', None, None): 'final_test'}
    for (activity, slot, target_read), step in cases.items():
        assert ce.step_of(activity, slot, PLAN, target_read) == step, activity
    without = [s for s in PLAN if s['id'] != 'structural_eda']
    assert ce.step_of('eda.quality', None, without, False) == 'train_eda'


WHERE = [({'kind': 'outcome_unknown', 'activity': 'fit.logistic'}, 'todo:execution', None),
         ({'kind': 'acknowledge_interruption'}, 'todo:execution', None),
         ({'kind': 'show_data_card', 'step': 'discover_data'}, 'now', 'data_card'),
         ({'kind': 'propose', 'decision': 'split'}, 'now', 'question'),
         ({'kind': 'await_user_words', 'decision': 'split'}, 'now', 'question'),
         ({'kind': 'await_user_words', 'decision': 'split', 'review': True}, 'now', 'review'),
         ({'kind': 'reconfirm', 'decision': 'preprocessing'}, 'now', 'reopened'),
         ({'kind': 'propose', 'decision': 'conclusion', 'choice_options': [{'id': 'a'}]},
          'now', 'choice'),
         ({'kind': 'resolve_hold', 'step': 'split'}, 'now', 'hold'),
         ({'kind': 'run', 'activity': 'fit.logistic'}, 'now', 'running'),
         ({'kind': 'blocked', 'step': 'conclusion'}, 'now', 'blocked'),
         ({'kind': 'done'}, 'now', 'done')]


@pytest.mark.parametrize('action, anchor, content', WHERE)
def test_where_each_next_action_is_shown(action, anchor, content):
    """§17.1.2: an unknown or interrupted run in To handle, every other next action in Now,
    whatever the stage (the data card reads as the question below v2)."""
    assert ce.where_anchor(action) == (anchor, content)
    for stage_id in ce.STAGES:
        found = ce.where(action, stage_id, 'en')
        assert list(found) == list(ce.WHERE_KEYS) and found['anchor'] == anchor
        assert ce.ANCHOR_RE.fullmatch(found['anchor'])
        shown_content = ('question' if content == 'data_card' and stage_id in ('v0', 'v1')
                         else content)
        if anchor == 'now':
            assert found['line'] == f'In the panel: Now, {ce.CONTENT_LABELS["en"][shown_content]}.'
            assert found['label'] == f'Now, {ce.CONTENT_LABELS["en"][shown_content]}'
        else:
            assert found['line'] == 'In the panel: To handle, the interrupted run.'


CHOICE = {'kind': 'propose', 'decision': 'conclusion', 'step': 'conclusion',
          'choice_options': [{'id': 'keep_baseline', 'value': 'keep_baseline', 'label': 'x'}]}
# (what the command produced, the next action it returned) -> (anchor, content) (§17.1.3).
SHOWN = [
    ({'command': 'init'}, {'kind': 'show_data_card'}, ('now', 'data_card')),
    ({'command': 'status'}, {'kind': 'show_data_card'}, ('now', 'data_card')),
    ({'command': 'plan'}, CHOICE, ('now', 'choice')),
    ({'command': 'status'}, {'kind': 'await_user_words'}, (None, None)),
    (None, {'kind': 'done'}, (None, None)),
    ({'command': 'init'}, {'kind': 'propose'}, (None, None)),
    ({'command': 'decide', 'action': 'decide.propose'}, {'kind': 'await_user_words'},
     ('now', 'question')),
    ({'command': 'decide', 'action': 'decide.propose'},
     {'kind': 'await_user_words', 'review': True}, ('now', 'review')),
    ({'command': 'decide', 'action': 'decide.resolve_note'}, {'kind': 'await_user_words'},
     ('now', 'question')),
    ({'command': 'decide', 'action': 'decide.note', 'kind': 'hold', 'decision_id': 'split'},
     {'kind': 'resolve_hold'}, ('now', 'hold')),
    ({'command': 'decide', 'action': 'decide.confirm', 'decision_id': 'split', 'opening': None},
     {'kind': 'run', 'activity': 'split'}, ('path:split', None)),
    ({'command': 'decide', 'action': 'decide.withdraw', 'decision_id': 'policy'},
     {'kind': 'propose', 'decision': 'policy'}, ('path:policy', None)),
    ({'command': 'decide', 'action': 'decide.note', 'kind': 'correction',
      'decision_id': 'prediction_time'}, {'kind': 'run'}, ('path:prediction_time', None)),
    ({'command': 'decide', 'action': 'decide.confirm', 'decision_id': 'final_test',
      'opening': {'status': 'promoted'}}, CHOICE, ('path:final_test/final_test.evaluation', None)),
    ({'command': 'decide', 'action': 'decide.confirm', 'decision_id': 'final_test',
      'opening': {'status': 'refused'}}, {'kind': 'propose'}, ('path:final_test', None)),
    ({'command': 'decide', 'action': 'decide.withdraw_note'}, {'kind': 'propose'}, (None, None)),
    ({'command': 'decide', 'action': 'study.set_mode'}, {'kind': 'run'}, ('now', 'answer_rules')),
    # a run of the current step: its figure in Now; of another step: in the path
    ({'command': 'run', 'activity': 'eda.target_rate', 'slot': 'eda.target_rate',
      'status': 'promoted'}, {'kind': 'run', 'step': 'train_eda',
                              'activity': 'eda.special_values'}, ('now', 'figure:eda.target_rate')),
    ({'command': 'run', 'activity': 'eda.special_values', 'slot': 'eda.special_values',
      'status': 'already_current'}, {'kind': 'propose', 'decision': 'preprocessing'},
     ('path:train_eda/eda.special_values', None)),
    ({'command': 'run', 'activity': 'split', 'slot': 'split', 'status': 'promoted'},
     {'kind': 'propose', 'decision': 'success_criterion', 'step': 'success_criterion'},
     ('path:split/split', None)),
    ({'command': 'run', 'activity': 'fit.variant', 'slot': 'fit.variant:2', 'status': 'promoted'},
     CHOICE, ('path:model_variant/fit.variant:2', None)),
    ({'command': 'run', 'activity': 'policy.evaluation', 'slot': 'policy.evaluation',
      'status': 'promoted'}, {'kind': 'run', 'step': 'policy', 'activity': 'diag.binary'},
     ('now', 'figure:policy.evaluation')),
    ({'command': 'run', 'activity': 'eda.distribution', 'slot': 'eda.distribution:age',
      'status': 'promoted', 'target_read': False}, {'kind': 'propose', 'decision': 'preprocessing'},
     ('path:structural_eda/eda.distribution:age', None)),
    # nothing the panel shows: a failed run, an acknowledgement, a capture; an interrupted
    # run is to handle
    ({'command': 'run', 'activity': 'fit.logistic', 'status': 'failed'}, {'kind': 'run'},
     (None, None)),
    ({'command': 'run', 'activity': 'fit.logistic', 'status': 'interrupted_unknown'},
     {'kind': 'outcome_unknown'}, ('todo:execution', None)),
    ({'command': 'run', 'action': 'run.acknowledge', 'activity': 'eda.distribution',
      'status': 'acknowledged'}, {'kind': 'run'}, (None, None)),
    ({'command': 'run', 'activity': 'predictor.capture', 'status': 'promoted'}, {'kind': 'done'},
     (None, None)),
]


@pytest.mark.parametrize('produced, action, expected', SHOWN)
def test_shown_names_what_each_command_produced(produced, action, expected):
    """§17.1.3 with D3: a command that produced something names it (even when the next action
    is a choice); a read names the data card at step 0 and the choice the chat asks, else
    nothing; a run is filed under its step, in Now when that step is the current one."""
    assert ce.shown_anchor(produced, action, PLAN) == expected
    found = ce.shown(produced, action, 'v3', 'fr', PLAN)
    if expected[0] is None:
        assert found is None
        return
    assert list(found) == list(ce.SHOWN_KEYS) and found['anchor'] == expected[0]
    assert ce.ANCHOR_RE.fullmatch(found['anchor'])
    assert found['line'].startswith('Dans le panneau : ') and found['line'].endswith('.')
    assert found['label'] == found['line'][len('Dans le panneau : '):-1]


# (anchor, content) asked -> what each stage shows (§17.1.3, stage fallback).
FALLBACK = [
    (('now', 'data_card'), {'v0': ('now', 'question'), 'v1': ('now', 'question'),
                            'v2': ('now', 'data_card'), 'v3': ('now', 'data_card')}),
    (('now', 'figure:eda.target_rate'), {'v1': ('now', 'question'),
                                         'v2': ('now', 'figure:eda.target_rate')}),
    (('path:train_eda/eda.rate_by:job', None), {'v0': ('path:train_eda', None),
                                                 'v1': ('path:train_eda', None),
                                                 'v2': ('path:train_eda/eda.rate_by:job', None)}),
    (('todo:checks', None), {'v0': ('tools:deliverables', None), 'v1': ('todo:checks', None)}),
    (('tools:data', None), {'v1': ('now', 'question'), 'v2': ('tools:data', None)}),
    (('tools:whatif', None), {'v0': ('now', 'question'), 'v3': ('tools:whatif', None)}),
    (('tools:notions', None), {'v2': (None, None), 'v3': ('tools:notions', None)}),
    (('tools:deliverables', None), {'v0': ('tools:deliverables', None)}),
    (('todo:execution', None), {'v0': ('todo:execution', None)}),
    (('path', None), {'v0': ('path', None)}),
]


@pytest.mark.parametrize('asked, by_stage', FALLBACK)
def test_the_stage_fallback_never_names_an_absent_place(asked, by_stage):
    for stage_id, expected in by_stage.items():
        assert ce.at_stage(*asked, stage_id) == expected, stage_id


LINES = {
    ('now', 'data_card'): ('In the panel: Now, the data card.',
                           'Dans le panneau : Maintenant, la fiche des données.'),
    ('path', None): ('In the panel: the path, its ledger line.',
                     'Dans le panneau : le parcours, sa ligne de registre.'),
    ('path:split', None): ('In the panel: the path, Split.', 'Dans le panneau : le parcours, '
                                                              'Découpage.'),
    ('path:train_eda/eda.rate_by:job', None): (
        'In the panel: the path, Explore → Outcome rate by group · job.',
        'Dans le panneau : le parcours, Exploration → Taux de résultat par groupe · job.'),
    ('path:final_test/final_test.evaluation', None): (
        'In the panel: the path, Final test → the final test result.',
        'Dans le panneau : le parcours, Test final → le résultat du test final.'),
    ('path:model_variant/fit.variant:2', None): (
        'In the panel: the path, Variants → the variants.',
        'Dans le panneau : le parcours, Variantes → les variantes.'),
    ('now', 'figure:policy.evaluation'): (
        'In the panel: Now, the model comparison.',
        'Dans le panneau : Maintenant, la comparaison des modèles.'),
    ('todo:execution', None): ('In the panel: To handle, the interrupted run.',
                               "Dans le panneau : À traiter, l'exécution interrompue."),
    ('tools:whatif', None): ('In the panel: Tools → What if? (without deciding).',
                             'Dans le panneau : Outils → Et si ? (sans décider).'),
    ('tools:deliverables', None): ('In the panel: Tools → Deliverables.',
                                   'Dans le panneau : Outils → Livrables.'),
}


@pytest.mark.parametrize('asked, lines', list(LINES.items()))
def test_the_lines_in_both_languages(asked, lines):
    """§17.1.4: the line and its label (after the colon, without the final period), in the
    study language; an unknown language reads as English."""
    for lang, line in zip(('en', 'fr'), lines):
        found = ce.place(*asked, lang)
        assert found == {'anchor': asked[0], 'line': line,
                         'label': line.split(':', 1)[1].strip()[:-1]}
    assert ce.place(*asked, 'de')['line'] == lines[0]


def test_the_labels_cover_both_languages():
    for table in (ce.ANCHOR_LABELS, ce.CONTENT_LABELS, ce.DRAWER_LABELS, ce.STEP_LABELS,
                  ce.EDA_CARD_LABELS, ce.FIGURE_LABELS, ce.LINES):
        assert set(table['en']) == set(table['fr'])
    assert set(ce.CONTENT_LABELS['en']) == set(ce.CONTENTS)
    assert set(ce.DRAWER_LABELS['en']) == set(ce.DRAWERS)
    assert {f'todo:{k}' for k in ce.TODO_KINDS} <= set(ce.ANCHOR_LABELS['en'])
    for anchor in ('now', 'path', 'path:split', 'path:train_eda/eda.rate_by:job',
                   'path:model_variant/fit.variant:2', 'tools:notions'):
        assert ce.ANCHOR_RE.fullmatch(anchor), anchor
    for bad in ('tab:eda', 'todo:other', 'tools:learn', 'path:', 'Now', 'path:Split'):
        assert not ce.ANCHOR_RE.fullmatch(bad), bad


def test_the_panel_payload_version_2(tmp_path):
    found = ce.panel({'kind': 'show_data_card', 'step': 'discover_data'}, tmp_path, 'fr',
                     env={ce.ENV_VAR: '1', ce.STAGE_ENV: 'v3'}, plan=PLAN)
    assert list(found) == list(ce.PANEL_KEYS) and found['version'] == ce.PANEL_CONTRACT == 2
    assert found['stage'] == 'v3' and found['title'] == 'Étude Hypotrail'
    assert found['where'] == {'anchor': 'now', 'label': 'Maintenant, la fiche des données',
                              'line': 'Dans le panneau : Maintenant, la fiche des données.'}
    assert found['shown'] == found['where']          # a read at step 0: the data card
    assert 'tabs' not in json.dumps(found)
    other = ce.panel({}, tmp_path, 'de', env={ce.ENV_VAR: '1'}, plan=PLAN)
    assert other['title'] == 'Hypotrail study' and other['stage'] == 'v0'
    assert ce.annotate(None, tmp_path, 'en', {ce.ENV_VAR: '1'}) is None
    action = {'kind': 'done'}
    assert ce.annotate(action, tmp_path, 'en', {}) == {'kind': 'done'}       # panel off
    assert ce.annotate(action, tmp_path, 'en', {ce.ENV_VAR: '1'})['panel']['stage'] == 'v0'
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


def test_no_panel_key_when_off(tmp_path, synthetic_case_dir):
    """NR-9: with the panel off, no payload carries ``panel``: the writes and the reads keep
    their keys, and the deliverables' view never depends on the environment."""
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    init = flow.init()
    assert 'panel' not in init['next_action']
    settings = json.loads((flow.study / ce.SETTINGS).read_text())       # init wrote it
    assert ce.SETTING_ENABLED not in settings                         # and left the panel off
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
    for surface, action in _outputs(flow).items():
        assert 'panel' not in action, surface
    # the study's settings turn it on too
    settings.update({ce.SETTING_ENABLED: True, ce.SETTING_STAGE: 'v2'})
    _settings(flow.study, json.dumps(settings))
    panel = cmd.status(flow.study, summary=True).payload['next_action']['panel']
    assert panel['stage'] == 'v2' and panel['version'] == 2
    assert 'panel' not in view.build(flow.study)['next_action']


def test_every_surface_names_its_place_when_on(tmp_path, synthetic_case_dir, monkeypatch):
    """Through the commands: ``init`` and the step-0 reads name the data card in Now; a
    proposal the question in Now; a confirmation its step in the path; a chart of a step that
    is not the current one its figure in the path; a read after step 0 nothing; ``panel`` is
    the last key of every surface."""
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    flow = Flow(tmp_path / 'study', synthetic_case_dir)
    init = flow.call('init', '--case', synthetic_case_dir, '--study', flow.study, '--lang', 'fr')
    assert init['next_action']['panel']['shown']['line'] == \
        'Dans le panneau : Maintenant, la fiche des données.'
    for surface, action in _outputs(flow).items():
        assert action['panel']['where']['anchor'] == 'now', surface
        assert action['panel']['shown']['anchor'] == 'now', surface        # the data card
        assert list(action)[-1] == 'panel', surface
    out = flow.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
                    '--restatement', 'Vous prédisez avant l’appel.', '--rationale', 'r',
                    '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                    '--study', flow.study)
    assert out['next_action']['panel']['shown']['line'] == \
        'Dans le panneau : Maintenant, la question qui vous attend.'
    for surface, action in _outputs(flow).items():                        # reads: nothing new
        assert action['panel']['shown'] is None, surface
    confirm = flow.call('decide', 'confirm', out['result']['proposal_id'], '--user-words',
                        'Oui, je veux le prediction_time exactement comme vous le dites',
                        '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                        '--study', flow.study)
    assert confirm['next_action']['panel']['shown'] == {
        'anchor': 'path:prediction_time', 'label': 'le parcours, Moment',
        'line': 'Dans le panneau : le parcours, Moment.'}
    run = flow.call('run', 'eda.quality', '--request-id', flow.rid(), '--expected-revision',
                    flow.rev(), '--study', flow.study)
    assert run['next_action']['panel']['shown']['anchor'] == 'path:structural_eda/eda.quality'
    assert 'panel' not in view.build(flow.study)['next_action']
