"""Browser tests of the junior's draft words in vscode.setState (scope S, simulated browser;
decisions CR.2 and CR.3, COMPANION-ADVANCED §6.1.5, §10, INV-5).

* CR.2 (review finding H2): drafts belong to one study. The extension sends a study key in
  `init`; the webview drops every draft (`ackDrafts`, `askDraft`) of another study, so words
  typed in study A never appear in study B, even for the same execution id (the study switch
  reloads the same webview, which keeps its state).
* CR.3 (review finding M1): each draft is `{text, revision}`, the revision at which the
  junior started typing; clearing the words and typing again starts at the revision shown.
* WP-E1 (v0.3 narrowing, ADR 0004 amendment): the confirmation drafts (`drafts`) went with
  W1; a state saved by an earlier panel loses them on load.

The words typed here are those of an acknowledgement of an interrupted execution (W6, the
Overview's Health). This is not a VS Code session.
"""
from __future__ import annotations

import json

STUDY_A = 'aaaaaaaaaaaaaaaa'
STUDY_B = 'bbbbbbbbbbbbbbbb'
WORDS_A = 'I know the evaluation of study A stopped before it finished'
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


def area(panel):
    return panel.page.locator(f'#ack-{EID}')


def test_cr2_words_typed_in_study_a_never_appear_in_study_b(open_panel, model):
    panel = open_panel()
    page = panel.page
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(health(model))
    area(panel).fill(WORDS_A)
    saved = panel.state()
    assert saved['study'] == STUDY_A
    assert saved['ackDrafts'][EID]['text'] == WORDS_A
    # The study switch: the same webview loads the document again, with its state.
    reload_with(panel, saved)
    panel.init(stage='v1', task='binary', study=STUDY_B)
    panel.snapshot(health(model, '/other/study B'))
    assert area(panel).input_value() == ''
    assert page.locator(f'button[data-execution="{EID}"][data-write="acknowledge"]').is_disabled()
    assert WORDS_A not in json.dumps(panel.state())
    assert WORDS_A not in page.locator('body').inner_text()
    assert panel.state()['study'] == STUDY_B
    assert panel.clean()


def test_cr2_the_same_study_keeps_its_drafts_across_a_reload(open_panel, model):
    panel = open_panel()
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(health(model))
    area(panel).fill(WORDS_A)
    reload_with(panel, panel.state())
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(health(model))
    assert area(panel).input_value() == WORDS_A
    assert panel.clean()


def test_cr2_a_state_without_a_study_key_keeps_no_words(open_panel, model):
    s = health(model)
    panel = open_panel()
    reload_with(panel, {'ackDrafts': {EID: {'text': WORDS_A, 'revision': s['revision']}}, 'askDraft': WORDS_A})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(s)
    assert area(panel).input_value() == ''
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


def test_cr3_clearing_the_words_and_typing_again_starts_at_the_current_revision(open_panel, model):
    s = health(model)
    panel = open_panel()
    panel.init(stage='v1', task='binary')
    panel.snapshot(s)
    area(panel).fill('First words about the stop')
    assert panel.state()['ackDrafts'][EID] == {'text': 'First words about the stop', 'revision': s['revision']}
    panel.snapshot({**s, 'revision': s['revision'] + 1})
    area(panel).fill('')
    assert EID not in (panel.state().get('ackDrafts') or {})
    area(panel).fill('New words, after reading it again')
    assert panel.state()['ackDrafts'][EID] == {'text': 'New words, after reading it again', 'revision': s['revision'] + 1}
    assert panel.clean()
