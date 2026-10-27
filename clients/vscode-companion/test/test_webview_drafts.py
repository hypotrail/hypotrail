"""Browser tests of the junior's draft words in vscode.setState (scope S, simulated browser;
decisions CR.2 and CR.3, COMPANION-ADVANCED §6.1.5, §10, INV-5).

* CR.2 (review finding H2): drafts belong to one study. The extension sends a study key in
  `init`; the webview drops every draft of another study, so words typed in study A never
  appear in study B (the study switch reloads the same webview, which keeps its state).
* WP-E1 (v0.3 narrowing, ADR 0004 amendment): the confirmation drafts (`drafts`) went with
  W1; a state saved by an earlier panel loses them on load.
* R31 (owner decision 2026-10-27, ADR 0004 amendment): the acknowledgement drafts
  (`ackDrafts`, CR.3's `{text, revision}`) went with W6; a state saved by an earlier panel
  loses them on load, and the Overview's interrupted execution has no words field.

The one words field left is the question of "Ask the agent about this" (`askDraft`). This is
not a VS Code session.
"""
from __future__ import annotations

import json

STUDY_A = 'aaaaaaaaaaaaaaaa'
STUDY_B = 'bbbbbbbbbbbbbbbb'
WORDS_A = 'What does the evaluation of study A say about the stop'
EID = 'e_4c1d9a7b2e3f5a6b7c8d9e0f'


def reload_with(panel, saved):
    page = panel.page
    page.context.add_init_script('window.__state = ' + json.dumps(saved) + ';')
    page.reload()
    page.wait_for_load_state('load')


def health(model, study='/studies/bank'):
    m = json.loads(json.dumps(model('summary', 'summary.binary.health')))
    m['study'] = study
    return m


def test_cr2_a_question_typed_in_study_a_never_appears_in_study_b(open_panel, model):
    panel = open_panel()
    reload_with(panel, {'study': STUDY_A, 'askDraft': WORDS_A})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(health(model))
    saved = panel.state()
    assert saved['study'] == STUDY_A and saved['askDraft'] == WORDS_A
    # The study switch: the same webview loads the document again, with its state.
    reload_with(panel, saved)
    panel.init(stage='v1', task='binary', study=STUDY_B)
    panel.snapshot(health(model, '/other/study B'))
    assert WORDS_A not in json.dumps(panel.state())
    assert WORDS_A not in panel.page.locator('body').inner_text()
    assert panel.state()['study'] == STUDY_B
    assert panel.clean()


def test_cr2_the_same_study_keeps_its_question_across_a_reload(open_panel, model):
    panel = open_panel()
    reload_with(panel, {'study': STUDY_A, 'askDraft': WORDS_A})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(health(model))
    reload_with(panel, panel.state())
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(health(model))
    assert panel.state()['askDraft'] == WORDS_A
    assert panel.clean()


def test_cr2_a_state_without_a_study_key_keeps_no_words(open_panel, model):
    s = health(model)
    panel = open_panel()
    reload_with(panel, {'askDraft': WORDS_A})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(s)
    assert WORDS_A not in json.dumps(panel.state())
    assert panel.clean()


def test_wp_e1_confirmation_drafts_of_an_earlier_panel_are_dropped(open_panel, model):
    s = model('summary', 'summary.binary')
    pid = s['proposals'][0]['proposalId']
    panel = open_panel()
    reload_with(panel, {'study': STUDY_A, 'drafts': {pid: {'text': WORDS_A, 'revision': s['revision']}}})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(s)
    panel.page.locator('[role="tab"][data-tab="decisions"]').click()
    assert panel.page.locator('textarea').count() == 0
    assert 'drafts' not in (panel.state() or {})
    assert WORDS_A not in panel.page.locator('body').inner_text()
    assert panel.clean()


def test_r31_acknowledgement_drafts_of_an_earlier_panel_are_dropped_and_no_words_field_is_left(open_panel, model):
    s = health(model)
    panel = open_panel()
    reload_with(panel, {'study': STUDY_A, 'ackDrafts': {EID: {'text': WORDS_A, 'revision': s['revision']}}})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(s)
    page = panel.page
    card = page.locator(f'[data-execution-card="{EID}"]')
    assert card.count() == 1, 'the interrupted execution is still shown'
    assert page.locator('textarea').count() == 0
    assert page.locator('[data-write="acknowledge"]').count() == 0
    assert 'ackDrafts' not in (panel.state() or {})
    assert WORDS_A not in page.locator('body').inner_text()
    assert panel.clean()
