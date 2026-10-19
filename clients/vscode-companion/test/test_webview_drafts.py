"""Browser tests of the junior's draft words in vscode.setState (scope S, simulated browser;
decisions CR.2 and CR.3, COMPANION-ADVANCED §6.2, §10, INV-5, DC-1).

* CR.2 (review finding H2): drafts belong to one study. The extension sends a study key in
  `init`; the webview drops every draft (`drafts`, `ackDrafts`, `askDraft`) of another
  study, so words typed in study A never appear in study B, even for the same proposal id
  (the study switch reloads the same webview, which keeps its state).
* CR.3 (review finding M1): each draft is `{text, revision}`, the revision at which the
  junior started typing. The "study changed" warning survives a reload, and Confirm sends
  that revision until the junior says they read the proposal again.

This is not a VS Code session.
"""
from __future__ import annotations

import copy
import json

STUDY_A = 'aaaaaaaaaaaaaaaa'
STUDY_B = 'bbbbbbbbbbbbbbbb'
WORDS_A = 'Yes, I accept a capacity of 100 calls for study A'


def reload_with(panel, saved):
    page = panel.page
    page.context.add_init_script('window.__state = ' + json.dumps(saved) + ';')
    page.reload()
    page.wait_for_load_state('load')


def decisions_tab(panel):
    panel.page.locator('[role="tab"][data-tab="decisions"]').click()


def test_cr2_words_typed_in_study_a_never_appear_in_study_b(open_panel, model):
    a = model('summary', 'summary.binary')
    pid = a['proposals'][0]['proposalId']
    b = copy.deepcopy(model('summary', 'summary.regression'))
    b['proposals'][0]['proposalId'] = pid
    b['study'] = '/other/study B'
    panel = open_panel()
    page = panel.page
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(a)
    decisions_tab(panel)
    page.locator(f'#words-{pid}').fill(WORDS_A)
    saved = panel.state()
    assert saved['study'] == STUDY_A
    # The study switch: the same webview loads the document again, with its state.
    reload_with(panel, saved)
    panel.init(stage='v1', task='regression', study=STUDY_B)
    panel.snapshot(b)
    decisions_tab(panel)
    assert page.locator(f'#words-{pid}').input_value() == ''
    assert page.locator(f'[data-proposal-card="{pid}"] [data-action="confirm"]').is_disabled()
    assert WORDS_A not in json.dumps(panel.state())
    assert WORDS_A not in page.locator('body').inner_text()
    assert panel.state()['study'] == STUDY_B
    assert panel.clean()


def test_cr2_the_same_study_keeps_its_drafts_across_a_reload(open_panel, model):
    a = model('summary', 'summary.binary')
    pid = a['proposals'][0]['proposalId']
    panel = open_panel()
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(a)
    decisions_tab(panel)
    panel.page.locator(f'#words-{pid}').fill(WORDS_A)
    reload_with(panel, panel.state())
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(a)
    decisions_tab(panel)
    assert panel.page.locator(f'#words-{pid}').input_value() == WORDS_A
    assert panel.clean()


def test_cr2_a_state_without_a_study_key_keeps_no_words(open_panel, model):
    a = model('summary', 'summary.binary')
    pid = a['proposals'][0]['proposalId']
    panel = open_panel()
    reload_with(panel, {'drafts': {pid: {'text': WORDS_A, 'revision': a['revision']}}, 'askDraft': WORDS_A})
    panel.init(stage='v1', task='binary', study=STUDY_A)
    panel.snapshot(a)
    decisions_tab(panel)
    assert panel.page.locator(f'#words-{pid}').input_value() == ''
    assert WORDS_A not in json.dumps(panel.state())
    assert panel.clean()


def test_cr3_the_typing_warning_survives_a_reload_and_confirm_names_the_starting_revision(open_panel, model):
    s = model('summary', 'summary.binary')
    pid = s['proposals'][0]['proposalId']
    panel = open_panel()
    page = panel.page
    panel.init(stage='v1', task='binary')
    panel.snapshot(s)
    decisions_tab(panel)
    page.locator(f'#words-{pid}').fill('I accept this rule because our desk handles that volume')
    later = {**s, 'revision': s['revision'] + 1}
    panel.snapshot(later)
    assert page.locator(f'[data-typing-warning="{pid}"]').count() == 1
    saved = panel.state()
    assert saved['drafts'][pid]['revision'] == s['revision']
    reload_with(panel, saved)
    panel.init(stage='v1', task='binary')
    panel.snapshot(later)
    decisions_tab(panel)
    assert page.locator(f'#words-{pid}').input_value() == 'I accept this rule because our desk handles that volume'
    assert page.locator(f'[data-typing-warning="{pid}"]').count() == 1, 'the warning survives the reload'
    page.locator(f'[data-proposal-card="{pid}"] [data-action="confirm"]').click()
    confirms = [m for m in panel.posted() if m['type'] == 'confirm']
    assert confirms[-1]['revision'] == s['revision'], 'the engine sees the change and refuses it as stale'
    page.locator(f'button[data-reread="{pid}"]').click()
    page.locator(f'[data-proposal-card="{pid}"] [data-action="confirm"]').click()
    confirms = [m for m in panel.posted() if m['type'] == 'confirm']
    assert confirms[-1]['revision'] == later['revision']
    assert panel.clean()


def test_cr3_clearing_the_words_and_typing_again_starts_at_the_current_revision(open_panel, model):
    s = model('summary', 'summary.binary')
    pid = s['proposals'][0]['proposalId']
    panel = open_panel()
    page = panel.page
    panel.init(stage='v1', task='binary')
    panel.snapshot(s)
    decisions_tab(panel)
    page.locator(f'#words-{pid}').fill('First words')
    panel.snapshot({**s, 'revision': s['revision'] + 1})
    page.locator(f'#words-{pid}').fill('')
    assert pid not in (panel.state().get('drafts') or {})
    page.locator(f'#words-{pid}').fill('New words, after reading it again')
    assert panel.state()['drafts'][pid] == {'text': 'New words, after reading it again', 'revision': s['revision'] + 1}
    assert page.locator(f'[data-typing-warning="{pid}"]').count() == 0
    assert panel.clean()
