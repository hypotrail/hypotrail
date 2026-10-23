"""Browser tests of the Overview view (WP-U1; COMPANION-ADVANCED §6.1, §3.3, §13): scope S,
simulated browser, real document and CSP, models from the real ``lib/models/*.js`` on the
WP-0 fixtures. Every test checks that no remote request, page error, or CSP violation
happened. Requirement ids are in the test names. Not a VS Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

from conftest import inline_styles_ok

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
MOMENTS = ['Frame the change', 'Prepare evidence', 'Work and compare', 'Conclude and hand over']
INTERRUPTED = 'e_4c1d9a7b2e3f5a6b7c8d9e0f'
SUSPECTED = 'e_8e7d6c5b4a39281706f5e4d3'
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
    panel.init(stage=stage, task=summary['task'], **init)
    panel.snapshot(summary)
    return panel


def assert_clean(panel):
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())
    assert inline_styles_ok(panel.page), 'no inline style attribute (CSP)'


def expand(page):
    """Open "Checks of the deliverables" and wait for the view to ask for the check."""
    page.locator('[data-check-summary]').click()
    page.locator('[data-check-loading]').wait_for()


def overview_text(page) -> str:
    return page.locator('#panel-overview').inner_text()


# --- Your next move (§6.1.0, WP-A5) -----------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov0_the_next_move_is_the_first_block_and_answers_in_decisions(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    assert page.locator('#panel-overview [data-ov]').first.get_attribute('data-ov') == 'hero'
    hero = page.locator('[data-ov="hero"]')
    assert hero.get_attribute('data-hero') == 'await_user_words'
    assert hero.locator('[data-hero-eyebrow]').inner_text().upper() == 'YOUR NEXT MOVE · PAUSE 3 · BUSINESS TRADE-OFF'
    assert hero.locator('[data-hero-title]').inner_text() == 'Answer the proposal on the decision rule'
    assert hero.locator('[data-hero-restatement="p_5"]').inner_text() == binary['proposals'][0]['restatement']
    value = hero.locator('[data-hero-value]')
    assert value.inner_text() == 'Select the top 100 by score'
    assert value.get_attribute('title') == 'Recorded value: capacity:100', 'the recorded value in the hover'
    assert 'which cases to act on' in hero.locator('[data-hero-why="policy"]').inner_text()
    # Two-layer copy: the engine's instruction to the assistant is under Details only.
    agent = binary['nextAction']['message']
    assert agent not in hero.inner_text()
    assert agent in hero.locator('[data-hero-details]').text_content()
    assert 'p_5' not in hero.inner_text() and 'capacity:100' not in hero.inner_text()
    hero.locator('[data-hero-action="proposal:p_5"]').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'decisions'
    assert page.evaluate('document.activeElement.closest("[data-nav]").dataset.nav') == 'proposal:p_5'
    assert_clean(panel)


# --- Where we are (§6.1.1) -------------------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov1_where_we_are_goal_and_decisions_in_words_junior_recap_under_details(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    section = page.locator('[data-ov="where"]')
    assert section.locator('[data-recap-line="Goal"] dd').inner_text() == binary['recapJunior'][0][len('Goal: '):]
    decided = section.locator('[data-decided-item]')
    assert decided.evaluate_all('ds => ds.map(d => d.dataset.decidedItem)') == \
        ['prediction_time', 'feature_availability', 'split', 'policy']
    policy = section.locator('[data-decided-item="policy"] [data-value-raw]')
    assert policy.inner_text() == 'Select every case scored 0.2 or more'
    assert policy.get_attribute('data-value-raw') == 'threshold:0.2'
    split = section.locator('[data-decided-item="split"] [data-value-raw]').inner_text()
    assert split == 'Stratified random split, 30% of the rows for validation'
    # OV-1 (amended): the junior recap, byte for byte, under Details; never the agent recap.
    assert section.locator('[data-recap-details] li').all_text_contents() == binary['recapJunior']
    text = page.locator('#panel-overview').text_content()
    for line in binary['recap']:
        if line not in binary['recapJunior']:
            assert line not in text, line
    assert_clean(panel)


def test_ov2_without_a_recap_there_is_no_recap_details(open_panel, binary):
    panel = opened(open_panel, {**binary, 'recap': [], 'recapJunior': []})
    assert panel.page.locator('[data-recap-details]').count() == 0
    assert panel.page.locator('[data-ov="where"] [data-recap-line="Goal"]').count() == 0
    assert panel.page.locator('[data-ov="where"] [data-decided-item]').count() == 4
    assert_clean(panel)


# --- Study map (§6.1.2) ----------------------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov3_ov4_study_map_has_four_moments_every_step_once_and_text_marks(open_panel, regression, scheme):
    """OV-3 (v0.3, WP-E2): the journey bar lists every step once, in plan order, each with its
    moment (one of the four) in its hover."""
    panel = opened(open_panel, regression, scheme=scheme)
    page = panel.page
    moments = page.locator('[data-map] [data-step]').evaluate_all('ss => ss.map(s => s.dataset.moment)')
    assert set(moments) == set(MOMENTS)
    steps = page.locator('[data-map] [data-step]').evaluate_all('ss => ss.map(s => s.dataset.step)')
    assert steps == [s['id'] for s in regression['plan']]
    assert len(steps) == len(set(steps))
    current = page.locator('[data-step][aria-current="step"]')
    assert current.count() == 1 and current.get_attribute('data-step') == 'model_choice'
    for item in page.locator('[data-map] [data-step]').all():
        assert item.locator('.ov-mark').get_attribute('aria-hidden') == 'true'
        assert item.locator('[data-mark-text]').inner_text().strip() != '', 'OV-4: a text, not only a mark'
    choice = page.locator('[data-step="model_choice"]')
    assert '●' in choice.inner_text()
    assert choice.locator('[data-mark-text]').text_content() == 'waiting for you: '
    assert choice.locator('[data-sub]').inner_text() == 'pause 3 · waiting for you'
    assert page.locator('[data-step="split"] [data-sub]').inner_text() == 'pause 2 · your words'
    assert page.locator('[data-step="train_eda"] [data-sub]').count() == 0
    assert page.locator('[data-step="conclusion"] [data-sub]').inner_text() == 'ready'
    assert_clean(panel)


def test_ov3_map_labels_for_delegated_reconfirmation_and_blocked_steps(open_panel, binary):
    plan = []
    for s in binary['plan']:
        s = dict(s)
        if s['id'] == 'split':
            s['basis'] = 'delegated_default'
        if s['id'] == 'policy':
            s['status'] = 'needs_reconfirmation'
        if s['id'] == 'conclusion':
            s['status'] = 'blocked'
            s['after'] = {'id': 'policy', 'title': 'Choose a decision policy'}
        plan.append(s)
    panel = opened(open_panel, {**binary, 'plan': plan})
    page = panel.page
    assert page.locator('[data-step="split"] [data-sub]').inner_text() == 'pause 2 · delegated'
    policy = page.locator('[data-step="policy"]')
    assert '↺' in policy.inner_text()
    assert policy.locator('[data-sub]').inner_text() == 'pause 3 · confirm again'
    assert policy.locator('[data-mark-text]').text_content() == 'confirm again: '
    blocked = page.locator('[data-step="conclusion"]')
    assert blocked.locator('[data-sub]').inner_text() == 'after Choose a decision policy'
    assert blocked.locator('[data-mark-text]').text_content() == 'blocked: '
    assert_clean(panel)


def test_map_without_moments_lists_the_plan_in_order(open_panel, binary):
    panel = opened(open_panel, {**binary, 'moments': []})
    steps = panel.page.locator('[data-map] [data-step]').evaluate_all('ss => ss.map(s => s.dataset.step)')
    assert steps == [s['id'] for s in binary['plan']]
    assert_clean(panel)


# --- Since your last session (§6.1.3) --------------------------------------------------------

ITEMS = 'li[data-digest-item]:not([data-digest-item="deliverables"])'


@pytest.mark.parametrize('scheme', THEMES)
def test_ov5_ov6_digest_grouped_in_the_panels_words_engine_record_under_details(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    section = page.locator('[data-ov="since"]')
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
    deliverables = section.locator('[data-digest-item="deliverables"]')
    assert deliverables.inner_text().endswith('The report and notebook are up to date.')
    # Two-layer copy: the engine's third-person record, verbatim, under Details only.
    assert section.locator('[data-digest-details] li').all_text_contents() == [i['text'] for i in binary['digest']['items']]
    assert "junior's" not in section.inner_text()
    header = section.locator('[data-since-header]').inner_text()
    assert header.startswith('Since ') and header != 'This session'
    # OV-6: no revision number outside the select's option labels.
    text = section.evaluate("s => { const c = s.cloneNode(true); c.querySelectorAll('option').forEach(o => o.remove());"
                            " return c.textContent; }")
    assert not re.search(r'revision \d', text), text
    options = section.locator('[data-since-select] option').all_inner_texts()
    assert options == ['your last session (revision 23)', 'the start of the study']
    assert_clean(panel)


def test_ov5_choosing_the_start_of_the_study_rereads_the_summary_with_since(open_panel, binary):
    panel = opened(open_panel, binary)
    page = panel.page
    page.locator('[data-since-select]').select_option('1')
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'summary', 'since': 1}
    assert page.locator('[data-updating="summary"]').inner_text() == 'Updating...'
    older = copy.deepcopy(binary)
    older['digest'] = {**older['digest'], 'since': 1, 'truncated': True,
                       'items': [{**older['digest']['items'][0], 'text': 'The split was confirmed in the junior\'s words.'}]
                       + older['digest']['items']}
    panel.view_data('summary', older)
    section = page.locator('[data-ov="since"]')
    assert section.locator('[data-since-header]').inner_text() == 'Since the start of the study'
    # Beyond four changes the rest is collapsed under "Show all N changes".
    assert section.locator(f'[data-digest] {ITEMS}').count() == 4
    assert section.locator(ITEMS).count() == 5
    more = section.locator('[data-digest-more]')
    assert more.locator('summary').inner_text() == 'Show all 5 changes'
    assert more.get_attribute('open') is None
    assert section.locator('[data-truncated]').inner_text() == \
        'Older changes are not listed. The Decisions tab has the full history.'
    page.locator('[data-since-select]').select_option('23')
    assert section.locator(ITEMS).count() == 4
    assert section.locator('[data-digest-more]').count() == 0
    assert_clean(panel)


def test_digest_of_one_session_truncated_and_empty(open_panel, regression, binary):
    panel = opened(open_panel, regression)
    section = panel.page.locator('[data-ov="since"]')
    assert section.locator('[data-since-header]').inner_text() == 'This session'
    assert section.locator('[data-truncated]').count() == 1
    assert section.locator('[data-since-select]').count() == 0, 'the boundary is already the start'
    panel.snapshot({**binary, 'revision': 27, 'digest': {**binary['digest'], 'items': [], 'since': 27, 'until': 27}})
    assert section.locator('[data-nothing-changed]').inner_text() == 'Nothing has changed since then.'
    panel.snapshot({**binary, 'revision': 28, 'digest': None})
    assert section.locator('[data-no-digest]').count() == 1, 'an engine without C1 (CA.14)'
    assert_clean(panel)


# --- Deliverables (§6.1.4) -------------------------------------------------------------------

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
    rows = page.locator('[data-ov="deliverables"] [data-artifact]')
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.artifact)') == ['report', 'notebook', 'workbench']
    for a in binary['artifacts']:
        row = page.locator(f'[data-ov="deliverables"] [data-artifact="{a["name"]}"]')
        # Two-layer copy: the junior variant; the engine message (it names paths) in the hover.
        expected = '' if a['name'] == 'workbench' else a['juniorMessage']
        assert row.locator('[data-message]').inner_text() == expected
        assert row.locator('[data-message]').get_attribute('title') == a['message']
    assert page.locator('[data-ov="deliverables"] [data-artifact="report"] .ov-deliverable-label').inner_text() == \
        'Report · study.html'
    assert page.locator('[data-artifact="workbench"] [data-status-chip]').inner_text() == 'yours'
    assert page.locator('[data-write="render"]').count() == 0
    page.get_by_role('button', name='Open the report in the browser').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}
    page.get_by_role('button', name='Open workbench in the editor').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench'}
    # The local launch (ADR 0004 "local launch"): read the generated notebook, edit the workbench.
    page.get_by_role('button', name='Open in Marimo (read)').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'notebook'}
    page.get_by_role('button', name='Open in Marimo (edit)').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'workbench'}
    assert page.locator('[data-launch="notebook"]').inner_text() == MARIMO['notebook']
    assert page.locator('[data-launch="workbench"]').inner_text() == MARIMO['workbench']
    assert MARIMO['kernel'] in page.locator('[data-kernel]').inner_text()
    assert_clean(panel)


def test_ov7_reviewer_has_no_marimo_edit(open_panel, binary):
    panel = opened(open_panel, binary, reviewer=True, marimo=MARIMO)
    page = panel.page
    assert page.locator('[data-marimo="workbench"]').count() == 0
    assert page.locator('[data-marimo="notebook"]').count() == 1
    assert_clean(panel)


def test_ov7_editable_study_notebook_opens_for_editing_and_reviewer_cannot_edit(open_panel, binary):
    summary = copy.deepcopy(binary)
    generated = next(a for a in summary['artifacts'] if a['name'] == 'notebook')
    editable = {**generated, 'name': 'editable', 'label': 'Editable study notebook',
                'path': 'notebooks/study_editable.py', 'generated': False,
                'message': 'The editable study notebook follows the generated notebook until you edit it.',
                'juniorMessage': 'This copy is yours to edit.'}
    workbench_at = next(i for i, a in enumerate(summary['artifacts']) if a['name'] == 'workbench')
    summary['artifacts'].insert(workbench_at, editable)

    panel = opened(open_panel, summary, marimo=MARIMO_EDITABLE)
    row = panel.page.locator('[data-artifact="editable"]')
    assert row.locator('[data-status-chip]').inner_text() == 'yours'
    row.locator('[data-marimo="editable"]').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_marimo', 'artifact': 'editable'}
    assert panel.page.locator('[data-launch="editable"]').inner_text() == MARIMO_EDITABLE['editable']
    assert_clean(panel)

    reviewer = opened(open_panel, summary, reviewer=True, marimo=MARIMO_EDITABLE)
    assert reviewer.page.locator('[data-marimo="editable"]').count() == 0
    assert_clean(reviewer)


def test_ov7_ov8_regenerate_when_stale_busy_and_outcome_with_problems(open_panel, health, payload):
    panel = opened(open_panel, health)
    page = panel.page
    button = page.locator('[data-write="render"]')
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
    out = page.locator('[data-ov="deliverables"] [data-outcome="ok_with_problems"]')
    assert out.locator('.title').inner_text() == 'Regenerated with problems'
    assert out.locator('li').all_inner_texts() == [a['message'] for a in artifacts]
    assert page.locator('#outcome [data-outcome]').count() == 0, 'shown in place, not twice'
    assert_clean(panel)


def test_ov8_regenerate_success_lists_each_message(open_panel, health, payload):
    panel = opened(open_panel, health)
    done = payload('render.binary')['artifacts']
    artifacts = [{'name': n, 'status': a['status'], 'message': a['message']} for n, a in done.items()]
    panel.send({'type': 'outcome', 'op': 'W5', 'kind': 'ok', 'target': 'render', 'exitCode': 0, 'revision': 26,
                'artifacts': artifacts})
    out = panel.page.locator('[data-ov="deliverables"] [data-outcome="ok"]')
    assert out.locator('.title').inner_text() == 'Regenerated the report and notebook.'
    assert out.locator('li').all_inner_texts() == [a['message'] for a in artifacts]
    assert_clean(panel)


# --- Health (§6.1.5) -------------------------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_he1_he2_execution_cards_empty_reply_disabled_until_typed_and_no_rerun(open_panel, health, scheme):
    panel = opened(open_panel, health, scheme=scheme)
    page = panel.page
    cards = page.locator('[data-execution-card]')
    assert cards.evaluate_all('cs => cs.map(c => c.dataset.executionCard)') == [INTERRUPTED, SUSPECTED]
    card = page.locator(f'[data-execution-card="{INTERRUPTED}"]')
    # WP-I: the engine names the activity policy.evaluation (policy.evaluate is the CLI alias).
    assert card.locator('h4').inner_text() == 'policy.evaluation: the outcome is unknown. Nothing will be restarted.'
    area = card.get_by_label('Your reply, in your own words')
    assert area.input_value() == '', 'INV-5: never pre-filled'
    hint = card.locator(f'#ack-hint-{INTERRUPTED}')
    assert area.get_attribute('aria-describedby') == f'ack-hint-{INTERRUPTED}'
    assert hint.inner_text() == ("Say that you know this run was interrupted and its outcome is unknown. "
                                 "'ok' alone is not enough.")
    button = card.get_by_role('button', name='Acknowledge in my words')
    assert button.get_attribute('data-write') == 'acknowledge'
    assert button.is_disabled()
    area.fill('  \n ')
    assert button.is_disabled()
    words = 'I know the policy run was cut off and nobody knows what it did.'
    area.fill(words)
    assert button.is_enabled()
    # CR.3: a draft is the junior's words and the revision at which they started typing.
    assert panel.state()['ackDrafts'] == {INTERRUPTED: {'text': words, 'revision': health['revision']}}, 'the junior\'s own draft only'
    button.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'acknowledge', 'executionId': INTERRUPTED, 'words': words,
                                  'revision': 26}
    # HE-2: no restart and no run control; the line points to the chat.
    assert card.locator('[data-rerun]').inner_text() == 'To run it again, ask the agent in the chat.'
    names = page.locator('#panel-overview button').all_inner_texts()
    assert not [n for n in names if re.match(r'(Restart|Run|Rerun)\b', n)], names
    assert page.locator('[data-write="run_eda"], [data-write="propose"]').count() == 0
    late = page.locator('[data-late-item]')
    assert late.inner_text() == ('eda.rate_by: a result was computed for a state that no longer holds; '
                                 'it is stored, not used.')
    assert late.locator('button, textarea').count() == 0
    assert_clean(panel)


def test_he1_refusal_of_a_bare_ok_is_shown_verbatim_in_the_card(open_panel, health, node):
    refusal = __import__('json').loads(node(
        "const {describe}=require('./lib/refusals');const {payload}=require('./test/fixture-cli');"
        "process.stdout.write(JSON.stringify(describe(payload('error.bare_acknowledgement'))))"))
    panel = opened(open_panel, health)
    page = panel.page
    card = page.locator(f'[data-execution-card="{INTERRUPTED}"]')
    card.get_by_label('Your reply, in your own words').fill('ok')
    card.get_by_role('button', name='Acknowledge in my words').click()
    panel.send({'type': 'outcome', 'op': 'W6', 'kind': 'refused', 'target': INTERRUPTED, 'exitCode': 2, 'refusal': refusal})
    alert = card.locator('[data-outcome="refused"]')
    assert alert.get_attribute('role') == 'alert'
    assert alert.get_attribute('data-code') == 'ambiguous_confirmation'
    assert alert.get_attribute('data-reason') == 'bare_acknowledgement'
    assert alert.locator('[data-engine-message]').inner_text() == refusal['engineMessage']
    assert alert.locator('[data-human]').inner_text().endswith('Nothing was recorded.')
    assert card.get_by_label('Your reply, in your own words').input_value() == 'ok', 'kept for the junior to edit'
    assert page.locator('#outcome [data-outcome]').count() == 0
    assert_clean(panel)


def test_he1_success_drops_the_draft_and_keeps_the_recorded_words_visible(open_panel, health):
    panel = opened(open_panel, health)
    page = panel.page
    words = 'I know the policy run was cut off and nobody knows what it did.'
    card = page.locator(f'[data-execution-card="{INTERRUPTED}"]')
    card.get_by_label('Your reply, in your own words').fill(words)
    card.get_by_role('button', name='Acknowledge in my words').click()
    panel.send({'type': 'outcome', 'op': 'W6', 'kind': 'ok', 'target': INTERRUPTED, 'exitCode': 0, 'revision': 28,
                'recorded': {'userWords': words, 'status': 'acknowledged'}})
    page.locator(f'[data-execution-card="{INTERRUPTED}"] [data-outcome="ok"]').wait_for()
    assert panel.state().get('ackDrafts') == {}, 'the draft is dropped after a successful acknowledgement'
    after = copy.deepcopy(health)
    after['revision'] = 28
    after['executions']['interrupted'] = []
    panel.snapshot(after)
    assert page.locator(f'[data-execution-card="{INTERRUPTED}"]').count() == 0
    done = page.locator('[data-acknowledged] [data-outcome="ok"]')
    assert done.locator('q').inner_text() == words
    assert_clean(panel)


def test_he3_checks_load_on_expand_show_findings_counts_and_open(open_panel, health, model):
    panel = opened(open_panel, health)
    page = panel.page
    summary = page.locator('[data-check-summary]')
    assert summary.inner_text() == 'Checks of the deliverables'
    assert not [m for m in panel.posted() if m.get('view') == 'check'], 'not read until expanded'
    summary.click()
    assert page.locator('[data-check-loading]').inner_text() == 'Running the checks...'
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'check'}
    panel.view_data('check', model('check', 'check.binary'))
    assert summary.inner_text() == 'Checks of the deliverables · 1 error, 1 warning'
    stale = page.locator('[data-finding="stale_number"]')
    assert stale.locator('.ov-severity').inner_text().lower() == 'error'
    assert stale.locator('[data-finding-message]').inner_text() == '11.0% cites result b7e3c1d0, which is not current.'
    assert stale.locator('[data-where]').inner_text() == 'reports/study.html'
    stale.get_by_role('button', name='Open reports/study.html').click()
    # WP-I (U1 request): from v1 the report opens at the cited result's anchor and an
    # editor deliverable at the finding's line (open_artifact.resultId and .line).
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report',
                                  'resultId': 'b7e3c1d09a4f5e6b8c2d1f0e3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b'}
    page.locator('[data-finding="causal_wording"]').get_by_role('button').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench', 'line': 42}
    loads = [m for m in panel.posted() if m.get('view') == 'check']
    assert len(loads) == 1, 'cached per revision: one read'
    panel.view_data('check', model('check', 'check.binary.clean'))
    assert summary.inner_text() == 'Checks of the deliverables · clean'
    assert_clean(panel)


def test_he3_at_v2_open_goes_to_the_cited_result_anchor(open_panel, health, model, payload):
    panel = opened(open_panel, health, stage='v2')
    page = panel.page
    expand(page)
    panel.view_data('check', model('check', 'check.binary'))
    page.locator('[data-finding="stale_number"]').get_by_role('button').click()
    rid = payload('check.binary')['findings'][0]['details']['result_id']
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report', 'resultId': rid}
    assert_clean(panel)


def test_checks_stale_and_failed_states(open_panel, health, model):
    panel = opened(open_panel, health)
    page = panel.page
    expand(page)
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
    assert page.locator('[data-finding]').count() == 2
    assert_clean(panel)


def test_not_yet_defensible_and_alert_navigation_to_health(open_panel, health):
    panel = opened(open_panel, health)
    page = panel.page
    # WP-A5: every limit once, with its severity, blocking first; the junior variant (or
    # the panel's words for an id) as text, never a text written for the agent.
    nyd = page.locator('[data-health="nyd"]')
    top = health['notYetDefensible']['top']
    ids = nyd.locator('li[data-nyd]').evaluate_all('ls => ls.map(l => l.dataset.nyd)')
    assert sorted(ids) == sorted([i['id'] for i in top] + health['notYetDefensible']['more'])
    assert len(ids) == len(set(ids)), 'each limit is listed once'
    severities = nyd.locator('li[data-nyd]').evaluate_all('ls => ls.map(l => l.dataset.severity)')
    order = ['blocking', 'caveat', 'sealed', 'context']
    assert severities == sorted(severities, key=order.index)
    assert severities[0] == 'blocking'
    for i in top:
        text = nyd.locator(f'li[data-nyd="{i["id"]}"] [data-limit-text]').inner_text()
        assert text == (i['juniorText'] or i['text'])
        if i['audience'] == 'agent':
            assert i['text'] not in nyd.inner_text()
    assert nyd.locator('li[data-nyd="no_causality"] [data-chip]').inner_text() == 'context'
    assert 'no_causality' not in nyd.inner_text(), 'no raw id as text'
    page.locator('[role="tab"][data-tab="decisions"]').click()
    assert page.locator('[data-alert="interrupted_executions"]').count() == 0, 'one alert per event'
    page.locator('[data-alert="outcome_unknown"] button').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'overview'
    focused = page.evaluate('document.activeElement.closest("[data-nav]").dataset.nav')
    assert focused == 'limit:outcome_unknown'
    assert page.locator(f'[data-nav="limit:outcome_unknown"] [data-execution-card="{SUSPECTED}"]').count() == 1
    navs = page.locator('#panel-overview [data-nav]').evaluate_all('ns => ns.map(n => n.dataset.nav)')
    assert len(navs) == len(set(navs)), 'navigation targets are unique'
    assert_clean(panel)


def test_navigation_focuses_an_h4_heading_of_its_own_target(open_panel, health):
    # WP-I (U1 request): the frame focuses the target's own h2, h3, or h4, never the
    # heading of a navigation target nested inside it.
    panel = opened(open_panel, health)
    page = panel.page
    panel.send({'type': 'navigate', 'tab': 'overview', 'kind': 'execution', 'id': INTERRUPTED})
    assert page.evaluate('document.activeElement.tagName') == 'H4'
    assert page.evaluate('document.activeElement.id') == f'ov-exec-{INTERRUPTED}'
    panel.send({'type': 'navigate', 'tab': 'overview', 'kind': 'limit', 'id': 'outcome_unknown'})
    assert page.evaluate('document.activeElement.dataset.nav') == 'limit:outcome_unknown'
    assert_clean(panel)


# --- states: reviewer, v0, loading, accessibility, vocabulary --------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_rv2_reviewer_overview_has_no_write_control_and_keeps_reads(open_panel, health, model, scheme):
    panel = opened(open_panel, health, reviewer=True, scheme=scheme)
    page = panel.page
    assert page.locator('[data-write]').count() == 0
    assert page.locator('textarea').count() == 0
    assert page.get_by_role('button', name='Regenerate the report and notebook').count() == 0
    assert page.get_by_role('button', name='Acknowledge in my words').count() == 0
    assert page.locator('[data-execution-card]').count() == 2, 'the cards are still read'
    page.get_by_role('button', name='Open the report in the browser').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}
    expand(page)
    panel.view_data('check', model('check', 'check.binary'))
    assert page.locator('[data-finding]').count() == 2
    assert_clean(panel)


def test_v0_shows_the_v0_subset_only(open_panel, health):
    panel = opened(open_panel, health, stage='v0')
    page = panel.page
    # WP-A5: v0 has the next move, the plan, where we are, the limits, and the deliverables.
    assert page.locator('#panel-overview [data-ov]').evaluate_all('ss => ss.map(s => s.dataset.ov)') == \
        ['hero', 'map', 'where', 'limits', 'deliverables', 'guide']
    assert page.locator('[data-recap-details] li').count() == 5
    for hook in ['[data-digest]', '[data-check]', '[data-write="render"]', '[data-ov="health"]',
                 '[data-write="acknowledge"]', '[data-stage]']:
        assert page.locator(hook).count() == 0, hook
    assert_clean(panel)


def test_v1_sections_carry_their_stage_and_loading_is_busy(open_panel, binary):
    panel = open_panel()
    panel.init(stage='v1', task='binary')
    page = panel.page
    assert page.locator('#panel-overview').get_attribute('aria-busy') == 'true'
    assert page.locator('#panel-overview').inner_text() == 'Reading the study...'
    panel.snapshot(binary)
    for hook in ['where', 'map', 'deliverables']:
        assert page.locator(f'[data-ov="{hook}"]').get_attribute('data-stage') == 'v1', hook
    assert page.locator('.ov-grid').get_attribute('data-stage') == 'v1'
    assert page.locator('[data-ov="hero"]').get_attribute('data-stage') is None, 'the next move is in every stage'
    assert page.locator('[data-ov="health"]').count() == 0, 'Health shows nothing when nothing is wrong'
    assert_clean(panel)


@pytest.mark.parametrize('scheme', THEMES)
def test_a11y_names_labels_headings_and_tabindex(open_panel, health, scheme):
    panel = opened(open_panel, health, scheme=scheme)
    page = panel.page
    expand(page)
    unnamed = page.evaluate("""() => [...document.querySelectorAll(
        '#panel-overview button, #panel-overview select, #panel-overview textarea, #panel-overview summary')].filter(e => {
          const label = e.id && document.querySelector(`label[for="${e.id}"]`);
          return !((e.getAttribute('aria-label') || '').trim() || (e.textContent || '').trim() || (label && label.textContent.trim()));
        }).map(e => e.outerHTML)""")
    assert unnamed == []
    assert page.locator('#panel-overview [tabindex]:not([tabindex="-1"]):not([tabindex="0"])').count() == 0
    # v0.3 (WP-E2): section titles are uppercase captions in CSS; the text is unchanged.
    assert page.locator('#panel-overview h2').all_text_contents() == [
        'A run stopped before it finished', 'Needs attention', 'The journey', 'Since your last session',
        'What you cannot claim yet', 'Where we are', 'Your deliverables', 'How this panel works']
    assert page.locator('#panel-overview section[aria-labelledby]').count() >= 5
    button = page.get_by_role('button', name='Open the report in the browser')
    button.focus()
    page.keyboard.press('Shift+Tab')
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.getAttribute("aria-label")') == 'Open the report in the browser'
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != 'none', 'focus is visible'
    assert_clean(panel)


@pytest.mark.parametrize('scheme', THEMES)
def test_inv12_regression_overview_holds_no_decision_rule_vocabulary(open_panel, regression, regression_health, model,
                                                                    scheme):
    for summary in (regression, regression_health):
        panel = opened(open_panel, summary, scheme=scheme)
        page = panel.page
        expand(page)
        panel.view_data('check', model('check', 'check.binary.clean'))
        text = page.locator('body').inner_text()
        found = FORBIDDEN.search(text)
        assert not found, found and found.group(0)
        assert_clean(panel)
    assert page.locator('[data-execution-card]').count() == 2
    assert page.locator('[data-write="render"]').count() == 1
