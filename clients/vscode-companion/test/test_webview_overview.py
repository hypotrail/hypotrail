"""Browser tests of the former Overview on the one page (WP-U1 re-pointed by ADR 0004 d13;
COMPANION-ADVANCED §6.3, §6.4, §6.6, §6.7.4, §3.3, §13): scope S, simulated browser, real
document and CSP, models from the real ``lib/models/*.js`` on the WP-0 fixtures. Every test
checks that no remote request, page error, or CSP violation happened. Not a VS Code session.

Where the Overview's parts went (§18): the next move is Now (OV-0 → NOW-12); the study map is
the path (OV-3, OV-4 → PATH-2, PATH-4); "Since your last session" is the fold "Since your last
visit" (OV-5, OV-6 → SINCE-1, SINCE-2); the deliverables, their launches, Regenerate and the
checks are the Deliverables drawer and To handle (OV-7, OV-8, HE-3 → TOOL-6, TODO-3, TODO-4);
an interrupted run is an item of To handle, or Now when the next action is about it (HE-1,
HE-2 → TODO-2). Withdrawn, with their tests: "Where we are" and its recap (OV-1, OV-2), the
alert strip and its navigation, the "What you cannot claim yet" list (→ the defensibility
pill, PG-6, `test_webview_header.py`), the tab's headings and accessibility scan (A11Y-1 on
the whole page, `test_webview_header.py`).
"""
from __future__ import annotations

import copy
import re

import pytest

from conftest import inline_styles_ok
from panel_cases import click_fold, open_all

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
MOMENTS = ['Frame the change', 'Prepare evidence', 'Work and compare', 'Conclude and hand over']
INTERRUPTED = 'e_4c1d9a7b2e3f5a6b7c8d9e0f'
SUSPECTED = 'e_8e7d6c5b4a39281706f5e4d3'
LATE = 'e_1f2e3d4c5b6a79880a1b2c3d'
THEMES = ['light', 'dark']


@pytest.fixture(scope='module')
def binary(model):
    return model('summary', 'summary.binary')


@pytest.fixture(scope='module')
def health(model):
    return model('summary', 'summary.binary.health')


@pytest.fixture(scope='module')
def regression(model):
    return model('summary', 'summary.regression')


@pytest.fixture(scope='module')
def regression_health(model, payload):
    """Auto MPG with an interrupted and a late execution, and a stale report."""
    p = copy.deepcopy(payload('summary.regression'))
    p['executions'] = {
        'active': [],
        'interrupted': [{'execution_id': 'e_r1', 'activity': 'evaluate.regression',
                         'reason': 'the process stopped before the result was promoted'}],
        'late': [{'execution_id': 'e_r2', 'activity': 'eda.mean_by', 'reason': 'the split changed while it ran',
                  'result_id': '6' * 64}],
        'suspected_interrupted': [{'execution_id': 'e_r3', 'activity': 'fit.linear', 'liveness': 'outcome_unknown',
                                   'reason': 'no process holds its lease'}],
    }
    p['artifacts']['status'] = 'stale'
    p['artifacts']['items']['report']['status'] = 'stale'
    p['artifacts']['items']['report']['message'] = 'The report (reports/study.html) is stale: it shows an earlier state.'
    return model('summary', p)


def opened(open_panel, summary, stage='v1', scheme='light', **init):
    panel = open_panel(color_scheme=scheme)
    panel.init(stage=stage, task=summary['task'], panelContract=2, **init)
    panel.snapshot(summary)
    return panel


def deliverables(panel):
    """Open the Deliverables drawer (TOOL-6)."""
    click_fold(panel.page, 't-deliverables')
    return panel.page.locator('[data-drawer="deliverables"]')


def since(panel):
    """Open "Since your last visit" (§6.4, v1)."""
    click_fold(panel.page, 'since')
    return panel.page.locator('[data-ov="since"]')


def assert_clean(panel):
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page), 'no inline style attribute (CSP)'


def expand(panel):
    """Open the checks of the deliverables and wait for the view to ask for the check."""
    deliverables(panel)
    click_fold(panel.page, 'checks')
    panel.page.locator('[data-check-loading]').wait_for()


# --- OV-0 → NOW-12: the next move is Now --------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov0_now12_the_next_move_is_now_in_the_panels_words(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    blocks = page.locator('#main > [data-block]').evaluate_all('ns => ns.map(n => n.dataset.block)')
    assert blocks.index('now') < blocks.index('path'), 'Now before the path'
    now = page.locator('[data-block="now"]')
    assert now.get_attribute('data-now') == 'proposal' and now.get_attribute('data-now-step') == 'policy'
    assert now.locator('[data-restatement="p_5"]').inner_text() == binary['proposals'][0]['restatement']
    value = now.locator('.ht-plainsay [data-value-raw]')
    assert value.inner_text() == 'Select the top 100 by score'
    assert value.get_attribute('title') == 'capacity:100', 'the recorded value in the hover'
    # Two-layer copy: the engine's instruction to the assistant is never in Now.
    assert binary['nextAction']['message'] not in now.inner_text()
    assert 'p_5' not in now.inner_text() and 'capacity:100' not in now.inner_text()
    copy_button = now.locator('[data-copy-question="policy"]')
    assert copy_button.get_attribute('data-write') is None
    copy_button.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'step', 'id': 'policy'}, 'mode': 'copy',
                                  'question': page.evaluate('() => globalThis.Hypotrail.copy.page.askQuestions.policy')}
    assert_clean(panel)


# --- OV-3, OV-4 → PATH-2, PATH-3, PATH-4: the path ------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov3_ov4_path2_path4_the_path_has_four_moments_every_step_once_and_text_marks(open_panel, regression, scheme):
    panel = opened(open_panel, regression, scheme=scheme)
    page = panel.page
    open_all(panel)
    path = page.locator('[data-block="path"]')
    assert path.locator('.ht-phase-t').all_text_contents() == MOMENTS
    steps = path.locator('[data-step]').evaluate_all('ss => ss.map(s => s.dataset.step)')
    assert steps == [s['id'] for s in regression['plan']]
    assert len(steps) == len(set(steps))
    current = path.locator('[data-step][aria-current="step"]')
    assert current.count() == 1 and current.get_attribute('data-step') == 'model_choice'
    for item in path.locator('li[data-step]').all():
        assert item.locator('.ht-mk').first.get_attribute('aria-hidden') == 'true'
        assert item.locator('.sr-only').first.text_content().strip() != '', 'OV-4: a text, not only a mark'
    choice = path.locator('li[data-step="model_choice"]')
    assert '●' in choice.locator('.ht-mk').first.inner_text()
    assert choice.locator('[data-badge="current"]').text_content() == 'waiting for you'
    assert_clean(panel)


def test_ov3_path3_badges_for_delegated_and_reconfirmation(open_panel, binary):
    summary = copy.deepcopy(binary)
    summary['decisions']['split'] = {**summary['decisions']['split'], 'basis': 'delegated_default'}
    for s in summary['plan']:
        if s['id'] == 'prediction_time':
            s['status'] = 'needs_reconfirmation'
    panel = opened(open_panel, summary)
    page = panel.page
    open_all(panel)
    split = page.locator('li[data-step="split"]')
    assert split.get_attribute('data-step-state') == 'delegated'
    assert split.locator('[data-badge="delegated"]').first.text_content().startswith('delegated')
    moment = page.locator('li[data-step="prediction_time"]')
    assert moment.get_attribute('data-step-state') == 'again'
    assert '↺' in moment.locator('.ht-mk').first.inner_text()
    assert moment.locator('[data-badge="again"]').text_content() == 'to confirm again'
    assert_clean(panel)


def test_path_without_moments_lists_the_plan_in_order(open_panel, binary):
    panel = opened(open_panel, {**binary, 'moments': []})
    open_all(panel)
    steps = panel.page.locator('[data-block="path"] [data-step]').evaluate_all('ss => ss.map(s => s.dataset.step)')
    assert steps == [s['id'] for s in binary['plan']]
    assert_clean(panel)


# --- OV-5, OV-6 → SINCE-1, SINCE-2: since your last visit -------------------------------------------

ITEMS = 'li[data-digest-item]:not([data-digest-item="deliverables"])'


@pytest.mark.parametrize('scheme', THEMES)
def test_ov5_ov6_since1_since2_digest_grouped_in_the_panels_words_engine_record_under_details(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    fold = page.locator('details[data-block="since"]')
    assert fold.get_attribute('open') is None, 'closed by default'
    section = since(panel)
    rows = section.locator(f'[data-digest] {ITEMS}')
    got = rows.evaluate_all('is => is.map(i => [i.dataset.group, i.querySelector("[data-digest-text]").textContent])')
    assert got == [
        ['needs', 'The decision rule was proposed.'],
        ['evaluated', 'The decision-rule evaluation was computed again.'],
        ['resolved', 'Your condition on the decision rule, "don\'t adopt anything until I bring my manager\'s figure", '
                     'was resolved in your words: "my manager says the team can make 100 calls per wave".'],
        ['other', 'The policy needs confirmation again: its evaluation changed.'],
    ], 'needs you first, then re-evaluated, resolved; an item the panel has no words for keeps the engine text'
    assert rows.evaluate_all('is => is.map(i => i.querySelector("[data-chip]").textContent)') == \
        ['needs you', 're-evaluated', 'resolved', 'other']
    replaced = section.locator('[data-digest-item="result_replaced"]')
    assert replaced.locator('strong[data-kept-fits]').inner_text() == 'Models unchanged, nothing refitted.'
    assert section.locator('strong[data-kept-fits]').count() == 1
    assert section.locator('[data-digest-item="deliverables"]').inner_text().endswith('The report and notebook are up to date.')
    # Two-layer copy: the engine's third-person record, verbatim, under Details only.
    assert section.locator('[data-digest-details] li').all_text_contents() == [i['text'] for i in binary['digest']['items']]
    assert "junior's" not in section.inner_text()
    header = section.locator('[data-since-header]').inner_text()
    assert header.startswith('Since ') and header != 'This session'
    # OV-6, SINCE-2: no revision number outside the select's option labels.
    text = section.evaluate("s => { const c = s.cloneNode(true); c.querySelectorAll('option').forEach(o => o.remove());"
                            " return c.textContent; }")
    assert not re.search(r'revision \d', text), text
    options = section.locator('[data-since-select] option').all_inner_texts()
    assert options == ['your last session (revision 23)', 'the start of the study']
    assert_clean(panel)


def test_ov5_choosing_the_start_of_the_study_rereads_the_summary_with_since(open_panel, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    section = since(panel)
    section.locator('[data-since-select]').select_option('1')
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'summary', 'since': 1}
    assert page.locator('[data-updating="summary"]').inner_text() == 'Updating...'
    older = copy.deepcopy(binary)
    older['digest'] = {**older['digest'], 'since': 1, 'truncated': True,
                       'items': [{**older['digest']['items'][0], 'text': 'The split was confirmed in the junior\'s words.'}]
                       + older['digest']['items']}
    panel.view_data('summary', older)
    assert section.locator('[data-since-header]').inner_text() == 'Since the start of the study'
    # Beyond four changes the rest is collapsed under "Show all N changes".
    assert section.locator(f'[data-digest] {ITEMS}').count() == 4
    assert section.locator(ITEMS).count() == 5
    more = section.locator('[data-digest-more]')
    assert more.locator('summary').inner_text() == 'Show all 5 changes'
    assert more.get_attribute('open') is None
    assert section.locator('[data-truncated]').inner_text() == \
        'Older changes are not listed. Each step of the path has its full history.'
    section.locator('[data-since-select]').select_option('23')
    assert section.locator(ITEMS).count() == 4
    assert section.locator('[data-digest-more]').count() == 0
    assert_clean(panel)


def test_digest_of_one_session_truncated_and_empty(open_panel, regression, binary):
    panel = opened(open_panel, regression)
    section = since(panel)
    assert section.locator('[data-since-header]').inner_text() == 'This session'
    assert section.locator('[data-truncated]').count() == 1
    assert section.locator('[data-since-select]').count() == 0, 'the boundary is already the start'
    # §6.4: the fold is absent when the digest has no item since the boundary, and with an
    # engine without the digest (C1, CA.14).
    panel.snapshot({**binary, 'revision': 27, 'digest': {**binary['digest'], 'items': [], 'since': 27, 'until': 27}})
    assert panel.page.locator('[data-block="since"]').count() == 0
    panel.snapshot({**binary, 'revision': 28, 'digest': None})
    assert panel.page.locator('[data-block="since"]').count() == 0
    assert_clean(panel)


# --- OV-7, OV-8 → TOOL-6, TODO-3: the Deliverables drawer --------------------------------------------

MARIMO = {'kernel': '/opt/hypotrail/framework/.venv',
          'notebook': 'uv run --project /opt/hypotrail/framework marimo run notebooks/study_generated.py',
          'workbench': 'uv run --project /opt/hypotrail/framework marimo edit notebooks/workbench.py'}
MARIMO_EDITABLE = {**MARIMO,
    'editable': 'uv run --project /opt/hypotrail/framework marimo edit notebooks/study_editable.py'}


@pytest.mark.parametrize('scheme', THEMES)
@pytest.mark.parametrize('stage', ['v0', 'v1'])
def test_ov7_deliverables_junior_messages_open_file_and_marimo_launches(open_panel, binary, scheme, stage):
    panel = opened(open_panel, binary, scheme=scheme, stage=stage, marimo=MARIMO)
    page = panel.page
    drawer = deliverables(panel)
    rows = drawer.locator('[data-ov="deliverables"] [data-artifact]')
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.artifact)') == ['report', 'notebook', 'editable', 'workbench']
    for a in binary['artifacts']:
        row = drawer.locator(f'[data-artifact="{a["name"]}"]')
        # Two-layer copy: the junior variant; the engine message (it names paths) in the hover.
        expected = '' if a['name'] == 'workbench' else a['juniorMessage']
        assert row.locator('[data-message]').inner_text() == expected
        if a['name'] == 'editable':
            assert expected and 'not official evidence' in expected
        assert row.locator('[data-message]').get_attribute('title') == a['message']
    assert drawer.locator('[data-artifact="report"] .ov-deliverable-label').inner_text() == 'Report · study.html'
    assert drawer.locator('[data-artifact="workbench"] [data-status-chip]').inner_text() == 'yours'
    assert page.locator('[data-write="render"]').count() == 0
    drawer.get_by_role('button', name='Open the report in the browser').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}
    drawer.get_by_role('button', name='Open workbench in the editor').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench'}
    # The local launch (ADR 0004 "local launch"): read the generated notebook, edit the workbench.
    drawer.get_by_role('button', name='Open in Marimo (read)').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'notebook'}
    drawer.locator('[data-artifact="workbench"]').get_by_role('button', name='Open in Marimo (edit)').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'workbench'}
    # The two "edit" buttons have distinct accessible names that name their deliverable, and
    # each starts with its visible text.
    names = drawer.locator('[data-marimo]').evaluate_all(
        'bs => bs.map(b => [b.dataset.marimo, b.getAttribute("aria-label"), b.textContent])')
    assert names == [['notebook', 'Open in Marimo (read): Study notebook', 'Open in Marimo (read)'],
                     ['editable', 'Open in Marimo (edit): Editable study copy', 'Open in Marimo (edit)'],
                     ['workbench', 'Open in Marimo (edit): Your workbench', 'Open in Marimo (edit)']]
    drawer.get_by_role('button', name='Open in Marimo (edit): Editable study copy', exact=True).click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'editable'}
    assert drawer.locator('[data-launch="notebook"]').inner_text() == MARIMO['notebook']
    assert drawer.locator('[data-launch="workbench"]').inner_text() == MARIMO['workbench']
    assert MARIMO['kernel'] in drawer.locator('[data-kernel]').inner_text()
    assert_clean(panel)


def test_ov7_reviewer_has_no_marimo_edit(open_panel, binary):
    panel = opened(open_panel, binary, reviewer=True, marimo=MARIMO)
    drawer = deliverables(panel)
    assert drawer.locator('[data-marimo="workbench"]').count() == 0
    assert drawer.locator('[data-marimo="notebook"]').count() == 1
    assert_clean(panel)


def test_ov7_editable_study_notebook_opens_for_editing_and_reviewer_cannot_edit(open_panel, binary):
    summary = copy.deepcopy(binary)
    editable = next(a for a in summary['artifacts'] if a['name'] == 'editable')
    assert editable['path'] == 'notebooks/study_editable.py'
    panel = opened(open_panel, summary, marimo=MARIMO_EDITABLE)
    row = deliverables(panel).locator('[data-artifact="editable"]')
    assert row.locator('[data-status-chip]').inner_text() == 'yours'
    row.locator('[data-marimo="editable"]').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'editable'}
    assert panel.page.locator('[data-launch="editable"]').inner_text() == MARIMO_EDITABLE['editable']
    assert_clean(panel)
    reviewer = opened(open_panel, summary, reviewer=True, marimo=MARIMO_EDITABLE)
    assert deliverables(reviewer).locator('[data-marimo="editable"]').count() == 0
    assert_clean(reviewer)


def test_ov7_ov8_todo3_regenerate_when_stale_busy_and_outcome_with_problems(open_panel, health, payload):
    panel = opened(open_panel, health)
    page = panel.page
    drawer = deliverables(panel)
    assert page.locator('[data-block="todo"] [data-write="render"]').count() == 1, 'TODO-3: also in To handle'
    button = drawer.locator('[data-write="render"]')
    assert button.inner_text() == 'Regenerate the report and notebook'
    button.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'render'}
    panel.send({'type': 'busy', 'busy': True, 'op': 'W5', 'target': 'render'})
    assert button.is_disabled() and button.get_attribute('aria-busy') == 'true'
    assert button.inner_text() == 'Working...'
    assert page.locator('button[data-write]:not(:disabled)').count() == 0, 'every write button is disabled while busy'
    problems = payload('render.binary.problems')['artifacts']
    artifacts = [{'name': n, 'status': a['status'], 'message': a['message']} for n, a in problems.items()]
    panel.send({'type': 'outcome', 'op': 'W5', 'kind': 'ok_with_problems', 'target': 'render', 'exitCode': 3,
                'revision': 26, 'artifacts': artifacts})
    panel.send({'type': 'busy', 'busy': False, 'op': 'W5', 'target': 'render'})
    out = drawer.locator('[data-ov="deliverables"] [data-outcome="ok_with_problems"]')
    assert out.locator('.title').inner_text() == 'Regenerated with problems'
    assert out.locator('li').all_inner_texts() == [a['message'] for a in artifacts]
    assert page.locator('#outcome [data-outcome]').count() == 0, 'shown in place, not in a global region'
    assert_clean(panel)


def test_ov8_regenerate_success_lists_each_message(open_panel, health, payload):
    panel = opened(open_panel, health)
    drawer = deliverables(panel)
    done = payload('render.binary')['artifacts']
    artifacts = [{'name': n, 'status': a['status'], 'message': a['message']} for n, a in done.items()]
    panel.send({'type': 'outcome', 'op': 'W5', 'kind': 'ok', 'target': 'render', 'exitCode': 0, 'revision': 26,
                'artifacts': artifacts})
    out = drawer.locator('[data-ov="deliverables"] [data-outcome="ok"]')
    assert out.locator('.title').inner_text() == 'Regenerated the report and notebook.'
    assert out.locator('li').all_inner_texts() == [a['message'] for a in artifacts]
    assert_clean(panel)


# --- HE-1, HE-2 → TODO-2: interrupted runs ------------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_he1_he2_todo2_interrupted_runs_are_read_only_and_copy_a_question(open_panel, health, scheme):
    """R31 (owner decision 2026-10-27, ADR 0004 amendment): the acknowledgement of an
    interrupted execution is made in the chat. Each run says so and copies a ready question; no
    words field, no write, no restart (HE-2)."""
    panel = opened(open_panel, health, scheme=scheme)
    page = panel.page
    items = page.locator('[data-block="todo"] [data-execution-card]')
    assert items.evaluate_all('cs => cs.map(c => c.dataset.executionCard)') == [INTERRUPTED, SUSPECTED, LATE]
    run = page.locator(f'[data-execution-card="{INTERRUPTED}"]')
    what = page.evaluate("() => globalThis.Hypotrail.copy.page.activities['policy.evaluation']")
    assert what, 'the activity in words'
    assert run.inner_text().startswith('Interrupted run · ')
    assert f'{what} stopped before it finished; its outcome is unknown. Say so in the chat, in your own words: ' \
           'this panel records nothing.' in run.inner_text()
    assert page.locator('textarea').count() == 0, 'no words field: the panel takes no words'
    assert page.locator('[data-write="acknowledge"]').count() == 0
    names = page.locator('#main button').all_inner_texts()
    assert not [n for n in names if re.match(r'(Restart|Run|Rerun|Acknowledge)\b', n)], names
    assert page.locator('[data-write="run_eda"], [data-write="propose"]').count() == 0
    copy_button = run.locator(f'[data-ask-execution="{INTERRUPTED}"]')
    assert copy_button.get_attribute('data-write') is None
    copy_button.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'ask_agent', 'about': {'kind': 'execution', 'id': INTERRUPTED},
                                  'question': f'{what} was interrupted; what should we do?', 'mode': 'copy'}
    assert not [m for m in panel.posted() if m['type'] == 'acknowledge']
    late = page.locator(f'[data-execution-card="{LATE}"]')
    assert late.inner_text().startswith('Late result · ')
    assert late.inner_text().endswith('a result was computed for a state that no longer holds; it is stored, not used.')
    assert late.locator('button, textarea').count() == 0
    assert_clean(panel)


def test_r31_an_acknowledgement_outcome_of_an_older_extension_is_dropped(open_panel, health):
    """W6 is no write id any more (protocol `WRITE_OPS`): its outcome is not shown."""
    panel = opened(open_panel, health)
    page = panel.page
    panel.send({'type': 'outcome', 'op': 'W6', 'kind': 'ok', 'target': INTERRUPTED, 'exitCode': 0, 'revision': 28,
                'recorded': {'userWords': 'I know it stopped.', 'status': 'acknowledged'}})
    assert page.locator('[data-outcome]').count() == 0
    assert page.evaluate('() => globalThis.Hypotrail.diagnostics.ignored') >= 1
    assert page.locator(f'[data-execution-card="{INTERRUPTED}"]').count() == 1
    assert_clean(panel)


# --- HE-3 → TOOL-6, TODO-4: the checks -----------------------------------------------------------------

def test_he3_todo4_checks_load_on_expand_show_findings_counts_and_open(open_panel, health, model):
    panel = opened(open_panel, health)
    page = panel.page
    deliverables(panel)
    summary = page.locator('[data-check-summary]')
    assert summary.inner_text() == 'Checks of the deliverables'
    assert not [m for m in panel.posted() if m.get('view') == 'check'], 'not read until expanded'
    click_fold(page, 'checks')
    assert page.locator('[data-check-loading]').inner_text() == 'Running the checks...'
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'check'}
    panel.view_data('check', model('check', 'check.binary'))
    assert summary.inner_text() == 'Checks of the deliverables · 1 error, 1 warning'
    drawer = page.locator('[data-drawer="deliverables"]')
    stale = drawer.locator('[data-finding="stale_number"]')
    assert stale.locator('.ov-severity').inner_text().lower() == 'error'
    assert stale.locator('[data-finding-message]').inner_text() == '11.0% cites result b7e3c1d0, which is not current.'
    assert stale.locator('[data-where]').inner_text() == 'reports/study.html'
    # TODO-4: an error finding is also in To handle.
    assert page.locator('[data-block="todo"] [data-todo="checks"] [data-finding="stale_number"]').count() == 1
    stale.get_by_role('button', name='Open reports/study.html').click()
    # WP-I (U1 request): from v1 the report opens at the cited result's anchor and an
    # editor deliverable at the finding's line (open_artifact.resultId and .line).
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report',
                                  'resultId': 'b7e3c1d09a4f5e6b8c2d1f0e3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b'}
    drawer.locator('[data-finding="causal_wording"]').get_by_role('button').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench', 'line': 42}
    loads = [m for m in panel.posted() if m.get('view') == 'check']
    assert len(loads) == 1, 'cached per revision: one read'
    panel.view_data('check', model('check', 'check.binary.clean'))
    assert summary.inner_text() == 'Checks of the deliverables · clean'
    assert page.locator('[data-todo="checks"]').count() == 0
    assert_clean(panel)


def test_he3_at_v2_open_goes_to_the_cited_result_anchor(open_panel, health, model, payload):
    panel = opened(open_panel, health, stage='v2')
    page = panel.page
    expand(panel)
    panel.view_data('check', model('check', 'check.binary'))
    page.locator('[data-drawer="deliverables"] [data-finding="stale_number"]').get_by_role('button').click()
    rid = payload('check.binary')['findings'][0]['details']['result_id']
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report', 'resultId': rid}
    assert_clean(panel)


def test_checks_stale_and_failed_states(open_panel, health, model):
    panel = opened(open_panel, health)
    page = panel.page
    expand(panel)
    panel.send({'type': 'load_error', 'view': 'check', 'message': 'The hypotrail CLI did not print one JSON document.',
                'detail': 'stderr'})
    error = page.locator('[data-check-error]')
    assert error.get_attribute('role') == 'alert'
    assert 'did not print one JSON document' in error.inner_text()
    error.get_by_role('button', name='Retry').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'check'}
    panel.view_data('check', model('check', 'check.binary'))
    panel.snapshot({**health, 'revision': 27})
    # WP-A5: older findings stay visible, dimmed and busy, with no "Updating..." label.
    stale = page.locator('[data-updating="check"]')
    assert stale.get_attribute('aria-busy') == 'true' and 'ht-stale' in stale.get_attribute('class')
    assert 'Updating' not in page.locator('[data-ov="deliverables"]').inner_text()
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'check'}, 'a newer revision reads again'
    assert stale.locator('[data-finding]').count() == 2, 'older findings stay visible while updating'
    panel.view_data('check', model('check', 'check.binary'), revision=27)
    assert page.locator('[data-updating="check"]').count() == 0, 'fresh findings are not marked'
    assert page.locator('[data-drawer="deliverables"] [data-finding]').count() == 2
    assert_clean(panel)


# --- states: reviewer, v0, loading, vocabulary ------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_rv2_reviewer_has_no_write_control_and_keeps_reads(open_panel, health, model, scheme):
    panel = opened(open_panel, health, reviewer=True, scheme=scheme)
    page = panel.page
    drawer = deliverables(panel)
    assert page.locator('[data-write]').count() == 0
    assert page.locator('textarea').count() == 0
    assert page.get_by_role('button', name='Regenerate the report and notebook').count() == 0
    assert page.locator('[data-execution-card]').count() == 3, 'the runs are still read'
    drawer.get_by_role('button', name='Open the report in the browser').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}
    click_fold(page, 'checks')
    panel.view_data('check', model('check', 'check.binary'))
    assert drawer.locator('[data-finding]').count() == 2
    assert_clean(panel)


def test_v0_shows_the_v0_subset_only(open_panel, health):
    panel = opened(open_panel, health, stage='v0')
    page = panel.page
    open_all(panel)
    for hook in ['[data-block="since"]', '[data-digest]', '[data-check]', '[data-write="render"]',
                 '[data-write="acknowledge"]', '[data-stage]', '[data-fold-id="effects"]', '[data-history]']:
        assert page.locator(hook).count() == 0, hook
    assert page.locator('[data-drawer="deliverables"] [data-artifact]').count() == 4
    assert_clean(panel)


def test_v1_blocks_carry_their_stage_and_loading_is_busy(open_panel, binary):
    panel = open_panel()
    panel.init(stage='v1', task='binary', panelContract=2)
    page = panel.page
    assert page.locator('#main').get_attribute('aria-busy') == 'true'
    assert 'Reading' in page.locator('#main').inner_text()
    panel.snapshot(binary)
    assert page.locator('#main').get_attribute('aria-busy') is None
    assert page.locator('[data-block="since"]').get_attribute('data-stage') == 'v1'
    assert page.locator('[data-fold-id="effects"]').get_attribute('data-stage') == 'v1'
    assert page.locator('[data-block="now"]').get_attribute('data-stage') is None, 'Now is in every stage'
    assert_clean(panel)


@pytest.mark.parametrize('scheme', THEMES)
def test_inv12_regression_page_with_runs_and_a_stale_report_holds_no_decision_rule_vocabulary(
        open_panel, regression, regression_health, model, scheme):
    for summary in (regression, regression_health):
        panel = opened(open_panel, summary, scheme=scheme)
        page = panel.page
        open_all(panel)
        panel.view_data('check', model('check', 'check.binary.clean'))
        text = page.locator('body').inner_text()
        found = FORBIDDEN.search(text)
        assert not found, found and found.group(0)
        assert_clean(panel)
    assert page.locator('[data-execution-card]').count() == 3
    assert page.locator('[data-write="render"]').count() == 2, 'To handle and the drawer'
