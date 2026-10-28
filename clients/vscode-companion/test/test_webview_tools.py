"""The tools of the one page and the learning layer (scope S, simulated browser; COMPANION-ADVANCED
§6.7, §A.1.4, §A.6; ADR 0004 decision 13): the drawers "The data" (W4), "What if?" with its
warning, "My notions" with the concept cards, "Deliverables" (Open, the Marimo launches, W5,
W7, the session report); the notions in place and "predict before you look" in Now. Real
document, real CSP, offline, contract-P1 states and captured payloads. Not a VS Code session.
"""
from __future__ import annotations

import pytest

from panel_cases import click_fold, load_views, open_case


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def drawer(page, name):
    click_fold(page, f't-{name}')
    return page.locator(f'details[data-drawer="{name}"]')


def loads(panel):
    return [m['view'] for m in panel.posted() if m['type'] == 'load']


def test_tool1_to_tool3_the_data_drawer_files_charts_in_the_path_and_runs_w4(open_panel, views):
    """TOOL-1 to TOOL-3, ED-12, PATH-7: a closed drawer reads nothing; opened, it shows the data
    card (with the sample), the quality check, the charts as links to their place in the path,
    and "Run another chart" (W4) with its question; the drawer holds no cited figure outside
    the charts' cards; W4 sends exactly the catalog's activity and column."""
    panel = open_case(open_panel, views, case='choice', width=600, lang='en', deliver=False)
    page = panel.page
    assert 'data' not in loads(panel) and 'eda' not in loads(panel)
    d = drawer(page, 'data')
    assert {'eda', 'data'} <= set(loads(panel))
    panel.view_data('eda', views['eda.p1'])
    panel.view_data('data', views['data.p1'])
    assert d.locator('[data-data-card]').count() == 1 and d.locator('[data-sample]').count() == 1
    assert d.locator('[data-quality-card]').count() == 1
    links = d.locator('[data-chart-links] button')
    assert links.count() >= 3
    first = links.first.get_attribute('data-goto')
    assert first.startswith('path:') and '/' in first
    links.first.click()
    assert page.locator(f'details[data-anchor="{first}"][open]').count() == 1, 'the link opens the chart in the path'
    run = d.locator('[data-write="run_eda"]').first
    assert d.locator('[data-chart-filed]').inner_text() == 'It is filed under Exploration, in the path, and counts as a look.'
    before = len(panel.posted())
    run.click()
    sent = [m for m in panel.posted()[before:] if m['type'] == 'run_eda']
    assert len(sent) == 1 and set(sent[0]) <= {'v', 'type', 'activity', 'column', 'revision'}
    # TOOL-2: before the split there is no control, a line says why.
    step1 = open_case(open_panel, views, case='step1', width=600, lang='en')
    drawer(step1.page, 'data')
    assert step1.page.locator('[data-chart-after-split]').inner_text() == 'Another chart: after the split, on training rows only.'
    assert step1.page.locator('[data-card-in-now]').count() == 1, 'at step 1 the card is in Now'
    assert panel.clean() and step1.clean()


def test_tool4_hon7_wi1_the_what_if_drawer_warns_first_in_every_state(open_panel, views):
    """TOOL-4, HON-7, WI-1, §6.10: the warning is the first element of the drawer, loading or
    populated, in both languages; it names no value and offers no control; the drawer is absent
    until an evaluation is current."""
    for lang, start in (('en', 'Replays another rule or choice'), ('fr', 'Rejoue une autre règle')):
        panel = open_case(open_panel, views, case='choice', width=420, lang=lang, deliver=False)
        d = drawer(panel.page, 'whatif')
        warning = d.locator('[data-whatif-warning]')
        assert warning.inner_text().startswith(start)
        assert d.locator('.ht-drawer-body > *').first.get_attribute('data-whatif-warning') == ''
        assert warning.locator('button, data').count() == 0
        panel.view_data('whatif', views['whatif.p1'])
        assert d.locator('.ht-drawer-body > *').first.get_attribute('data-whatif-warning') == ''
        assert d.locator('[data-experiment]').count() >= 1
        panel.context.close()
    step1 = open_case(open_panel, views, case='step1', width=420, lang='en', deliver=False)
    assert step1.page.locator('[data-drawer="whatif"]').count() == 0


def test_tool6_ov7_ov8_the_deliverables_drawer(open_panel, views, payload):
    """TOOL-6, OV-7, OV-8, TODO-3: the four deliverables with Open and the Marimo launches at
    every stage; Regenerate (W5) from v1 when one is stale, in To handle and in the drawer; its
    outcome lists each message; at v0 the line says to ask in the chat."""
    marimo = {'kernel': '/py', 'notebook': 'marimo run notebooks/study_generated.py',
              'editable': 'marimo edit notebooks/study_editable.py', 'workbench': 'marimo edit notebooks/workbench.py'}
    for stage in ('v0', 'v1'):
        # the interrupted capture: its deliverables are stale, so To handle offers them too
        panel = open_case(open_panel, views, case='interrupted', width=420, lang='en', stage=stage, deliver=False)
        panel.init(stage=stage, task='regression', panelContract=2, marimo=marimo)
        d = drawer(panel.page, 'deliverables')
        assert [x.get_attribute('data-artifact') for x in d.locator('[data-artifact]').all()] == ['report', 'notebook', 'editable', 'workbench']
        before = len(panel.posted())
        d.locator('[data-marimo="notebook"]').click()
        assert panel.posted()[before:] == [{'v': 2, 'type': 'open_marimo', 'artifact': 'notebook'}]
        regen = panel.page.locator('[data-write="render"]')
        if stage == 'v0':
            assert regen.count() == 0
            assert panel.page.locator('[data-todo="deliverables"]').inner_text().endswith('Ask for it in the chat.')
        else:
            assert regen.count() == 2, 'To handle and the drawer'
            before = len(panel.posted())
            regen.first.click()
            assert panel.posted()[before:] == [{'v': 2, 'type': 'render'}]
            panel.send({'type': 'outcome', 'op': 'W5', 'kind': 'ok_with_problems', 'target': 'render',
                        'artifacts': [{'name': 'report', 'status': 'failed', 'message': 'The report failed.'}]})
            assert panel.page.locator('[data-artifact-message="report"]').first.inner_text() == 'The report failed.'
        panel.context.close()


def test_ho1_sr1_v3_export_and_session_report(open_panel, views, payload, model):
    """HO-1, HO-2, SR-1, TOOL-6: at v3 the drawer offers the export (W7, the revision it shows)
    and the session report, read when its fold opens, with the log status and no user words."""
    panel = open_case(open_panel, views, case='done', width=420, lang='en', deliver=False)
    d = drawer(panel.page, 'deliverables')
    before = len(panel.posted())
    d.locator('[data-write="export"]').click()
    assert panel.posted()[before:] == [{'v': 2, 'type': 'export_handoff', 'revision': views['summary.done']['revision']}]
    assert 'session_report' not in loads(panel)
    click_fold(panel.page, 'session-report')
    assert 'session_report' in loads(panel)
    panel.view_data('session_report', model('session_report', 'session_report.regression'))
    report = panel.page.locator('[data-session-report]')
    assert report.locator('[data-session-log]').count() == 1
    words = [d['user_words'] for d in payload('decisions.regression')['history'] if d.get('user_words')]
    assert not any(w in report.inner_text() for w in words)
    low = open_case(open_panel, views, case='done', width=420, lang='en', stage='v2', deliver=False)
    drawer(low.page, 'deliverables')
    assert low.page.locator('[data-write="export"], [data-session-report]').count() == 0


def test_not1_not2_not3_le3_notions_expand_in_place(open_panel, views):
    """NOT-1, NOT-2, LS-5, LE-3, LE-4: a marked term is a button that expands its notion in
    place, term first, then "In your study"; Enter and Escape work; its state is a fold of the
    page; My notions lists the notions met so far; with the learning layer off, nothing is
    marked and `explain` is never read."""
    panel = open_case(open_panel, views, case='step1', width=420, lang='en', deliver=False)
    page = panel.page
    panel.view_data('data', views['data.p1'])
    term = page.locator('button.ht-term[data-term="final_test"]')
    assert term.get_attribute('aria-expanded') == 'false'
    term.focus()
    page.keyboard.press('Enter')
    assert 'explain' in loads(panel)
    panel.view_data('explain', views['explain.p1'])
    term = page.locator('button.ht-term[data-term="final_test"]')
    assert term.get_attribute('aria-expanded') == 'true'
    note = page.locator(f'#{term.get_attribute("aria-controls")}')
    assert note.get_attribute('role') == 'note'
    assert note.locator('dfn').inner_text() == views['explain.p1']['terms']['final_test']['term']
    assert panel.state()['folds']['term-final_test'] is True
    assert page.evaluate("() => document.activeElement.getAttribute('data-term')") == 'final_test', 'NOT-2: focus kept'
    page.keyboard.press('Escape')
    assert page.locator('button.ht-term[data-term="final_test"]').get_attribute('aria-expanded') == 'false'
    d = drawer(page, 'notions')
    assert d.locator('[data-my-notions] [data-notion]').count() >= 1
    off = open_case(open_panel, views, case='step1', width=420, lang='en', learning=False, deliver=False)
    assert off.page.locator('button.ht-term, [data-drawer="notions"]').count() == 0
    assert 'explain' not in loads(off)
    assert panel.clean()


def test_le1_le2_concept_cards_in_my_notions_and_predictions_in_now(open_panel, views):
    """LE-1, LE-2 (kept: the integrator's correction of ADR 0004 d13), INV-6: the concept card of
    the step that waits is in My notions, labelled not a decision, and collapses to a link after
    its second sighting (the count is the extension's globalState); "predict before you look" is
    in Now at its step; an answer is kept on this computer only (learn_set), never a study write."""
    panel = open_case(open_panel, views, case='choice', width=420, lang='en', deliver=False)
    page = panel.page
    panel.view_data('explain', views['explain.p1'])
    predict = page.locator('[data-block="now"] [data-predict-now="model_choice"]')
    assert predict.count() == 1
    assert predict.locator('[data-kept-local]').inner_text() == 'Kept on this computer only. Never written to the study.'
    before = len(panel.posted())
    predict.locator('[data-choice]').first.click()
    sent = panel.posted()[before:]
    assert [m['type'] for m in sent] == ['learn_set'] and sent[0]['key'] == 'prediction'
    d = drawer(page, 'notions')
    card = d.locator('[data-concept-card="regression:model_choice"]')
    assert card.count() == 1 and 'not a decision' in card.inner_text()
    panel.send({'type': 'learn_state', 'prefs': {}, 'seen': {'regression:model_choice': 2}, 'predictions': {}})
    assert d.locator('[data-concept-card-link="regression:model_choice"]').count() == 1
    assert d.locator('[data-concept-card="regression:model_choice"]').count() == 0
