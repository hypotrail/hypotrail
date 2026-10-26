"""Wave W1 end to end on a real study (owner session 2026-10-26; R16 with L1, L7 D15).

L2 built the Decisions choice card (DC-13) before L1 existed, on hand-made payloads; L7 added
``next_action.after_study`` without a panel view. This check drives a real study through the
engine's CLI code path (``cli.run``, the walkthrough of ``test_journey_walkthrough.py``) with
the study panel on at stage v3 and, on the payloads it really emits:

* at the conclusion (and the model choice), with no recommendation, the summary carries
  ``choice_options``, the pause is of kind ``choice``, ``panel.shown`` names the choice card
  on a read while the write that led there names what it produced (D3), the panel's summary
  model holds the same options, and the Decisions tab renders them as the read-only card;
* HO-3: at ``done``, the summary carries ``after_study``; Overview ("Your next move") and the
  Learn & hand off tab show its junior text read only, and the export plan line only when
  the engine says the model is supported; no new write control appears.

Simulated browser (headless Chromium, ``conftest.py``); not a VS Code or Copilot session.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'study'))

import test_journey_walkthrough as journey  # noqa: E402
from mlkit.study import companion_env as ce  # noqa: E402

CHOICE_SHOWN = {'en': {'tab': 'decisions', 'section': 'choice', 'label': 'Waiting for your answer',
                       'line': 'In the panel: Decisions → Waiting for your answer.'},
                'fr': {'tab': 'decisions', 'section': 'choice', 'label': 'En attente de votre réponse',
                       'line': 'Dans le panneau : Décisions → En attente de votre réponse.'}}


def _walk(tmp_path, monkeypatch, case, lang):
    """The walkthrough to ``done``; the summaries (``--digest``) read at each free choice and
    at the end, with the payload of the write that led to each choice."""
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    f, task, _ = journey.journey_flow(tmp_path, case, lang)
    last = {}
    choices = {}

    def on_write(label, payload):
        last['write'] = (label, payload)

    def on_read(label, action):
        decision = action.get('decision')
        if action.get('choice_options') and decision not in choices:
            choices[decision] = {'action': action, 'write': last.get('write'),
                                 'summary': f.call('status', '--summary', '--digest', '--json',
                                                   '--study', f.study)}

    journey.walk(f, task, on_write=on_write, on_read=on_read)
    done = f.call('status', '--summary', '--digest', '--json', '--study', f.study)
    return task, choices, done


def _decisions_tab(open_panel, summary_model, stage='v3'):
    panel = open_panel()
    panel.init(stage=stage)
    panel.snapshot(summary_model)
    panel.page.locator('[role="tab"][data-tab="decisions"]').click()
    return panel


@pytest.mark.parametrize('case, lang', [('auto-mpg', 'en'), ('synthetic', 'fr')])
def test_w1_choice_card_and_after_study_on_a_real_study(tmp_path, monkeypatch, open_panel, model,
                                                         case, lang):
    task, choices, done = _walk(tmp_path, monkeypatch, case, lang)
    assert set(choices) == {'model_choice', 'conclusion'}, sorted(choices)
    for decision, seen in choices.items():
        action = seen['action']
        options = action['choice_options']
        # L1 (R2c): a free choice, no recommendation, one pause option per accepted value.
        assert action['kind'] == 'propose' and action['recommended'] is None
        assert action['pause']['kind'] == 'choice'
        assert action['pause']['options'] == [o['id'] for o in options]
        assert action['pause']['option_labels'] == {o['id']: o['label'] for o in options}
        # L2 (R16): a read names the choice card; D3: the write that led there names what it
        # produced (the opening: the final test; a fit or the diagnostics: the evidence).
        assert action['panel']['shown'] == CHOICE_SHOWN[lang]
        label, write = seen['write']
        shown = write['next_action']['panel']['shown']
        expected = ({'final_test'} if label == 'confirm:final_test'
                    else {'development', 'diagnostics'})
        assert label.startswith(('run:', 'confirm:')) and shown['section'] in expected, \
            (label, shown)
        # The panel's summary model holds the same options, labels verbatim; a conclusion's
        # value reads as its verdict, never as raw JSON.
        raw = seen['summary']
        assert raw['next_action']['choice_options'] == options
        m = model('summary', raw)
        assert [(o['id'], o['label']) for o in m['nextAction']['choiceOptions']] == \
            [(o['id'], o['label']) for o in options]
        if decision == 'conclusion':
            assert [o['value'] for o in m['nextAction']['choiceOptions']] == [o['id'] for o in options]
            assert ('adopt_model' if task == 'regression' else 'adopt_policy') in [o['id'] for o in options]
        # The Decisions tab renders the read-only card with exactly those options.
        panel = _decisions_tab(open_panel, m)
        card = panel.page.locator(f'[data-choice-card="{decision}"]')
        assert card.count() == 1, decision
        assert card.locator('[data-choice-option]').all_inner_texts() == [o['label'] for o in options]
        assert card.locator('textarea, input, select, [data-write]').count() == 0
        assert card.locator('button').count() == 1                    # the copy-only ask button
        assert panel.page.locator('[data-nothing-waiting]').count() == 0
        assert panel.clean(), (panel.requests, panel.errors, panel.csp)

    # L7 (D15): at done, what comes after the study, read only.
    after = done['next_action']['after_study']
    assert done['next_action']['kind'] == 'done' and after['junior_text']
    supported = after['azureml']['supported']
    m = model('summary', done)
    assert m['nextAction']['afterStudy'] == {'juniorText': after['junior_text'],
                                             'exportPlanAvailable': supported,
                                             'cloudStatus': 'not_qualified'}
    for stage in ('v0', 'v3'):
        panel = open_panel()
        panel.init(stage=stage)
        panel.snapshot(m)
        page = panel.page
        if stage != 'v0':
            page.locator('[role="tab"][data-tab="overview"]').click()
        hero = page.locator('[data-ov="hero"]')
        assert hero.get_attribute('data-hero') == 'done'
        block = hero.locator('[data-after-study]')
        assert block.count() == 1 and after['junior_text'] in block.inner_text()
        assert block.locator('[data-after-study-export]').count() == (1 if supported else 0)
        assert block.locator('button, a, input, textarea, select, [data-write]').count() == 0
        assert panel.clean(), (panel.requests, panel.errors, panel.csp)
        hero_text = hero.inner_text()
    page.locator('[role="tab"][data-tab="learn"]').click()
    learn = page.locator('[data-view="learn"]')
    block = learn.locator('[data-after-study]')
    assert block.count() == 1 and after['junior_text'] in block.inner_text()
    assert block.get_attribute('data-after-study') == ('export_plan' if supported else 'handoff')
    assert block.locator('[data-after-study-export]').count() == (1 if supported else 0)
    assert block.locator('button, a, input, textarea, select, [data-write]').count() == 0
    # The tab's only write is still the handoff pack (W7).
    assert [learn.locator('[data-write]').nth(i).get_attribute('data-write')
            for i in range(learn.locator('[data-write]').count())] == ['export']
    # No command, id or revision of the engine reaches the panel's text.
    text = learn.inner_text() + hero_text
    for raw in ('hypotrail ', '--expected-revision', 'export azureml', after['handoff']['command']):
        assert raw not in text, raw
    # The same payload where the engine says the model is not supported (a boosting model,
    # unit-tested in test_after_study.py): the text only, no export plan line.
    refused = copy.deepcopy(done)
    refused['next_action']['after_study']['azureml'].update(
        supported=False, reason_id='family_not_supported', plan_command=None)
    m = model('summary', refused)
    assert m['nextAction']['afterStudy']['exportPlanAvailable'] is False
    panel = open_panel()
    panel.init(stage='v3')
    panel.snapshot(m)
    panel.page.locator('[role="tab"][data-tab="learn"]').click()
    block = panel.page.locator('[data-view="learn"] [data-after-study]')
    assert block.get_attribute('data-after-study') == 'handoff'
    assert block.locator('[data-after-study-export]').count() == 0
