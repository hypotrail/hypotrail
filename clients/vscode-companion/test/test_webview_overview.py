"""Browser tests of the Overview view (WP-U1; COMPANION-ADVANCED §6.1, §3.3, §13): scope S,
simulated browser, real document and CSP, models from the real ``lib/models/*.js`` on the
WP-0 fixtures. Every test checks that no remote request, page error, or CSP violation
happened. Requirement ids are in the test names. Not a VS Code session.
"""
from __future__ import annotations

import copy
import re

import pytest

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
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
    assert panel.page.locator('[style]').count() == 0, 'no inline style attribute (CSP)'


def expand(page):
    """Open "Checks of the deliverables" and wait for the view to ask for the check."""
    page.locator('[data-check-summary]').click()
    page.locator('[data-check-loading]').wait_for()


def overview_text(page) -> str:
    return page.locator('#panel-overview').inner_text()


# --- Where we are (§6.1.1) -------------------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov1_recap_lines_are_rendered_verbatim_as_a_definition_list(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    rows = page.locator('[data-recap-list] [data-recap-line]')
    assert rows.count() == 5
    got = rows.evaluate_all("rs => rs.map(r => r.querySelector('dt').textContent + ': ' + "
                            "r.querySelector('[data-recap-text]').textContent)")
    assert got == binary['recap'], 'byte for byte'
    assert page.locator('[data-recap-list] dt').all_inner_texts() == ['Goal', 'Decided', 'Now', 'Next', 'Limit']
    # "Open in Decisions" after the Next line (await_user_words), and only there.
    link = page.locator('[data-open-decisions]')
    assert link.count() == 1
    assert link.get_attribute('data-open-decisions') == 'p_5'
    link.click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'decisions'
    assert_clean(panel)


def test_ov2_without_a_recap_the_section_says_so(open_panel, binary):
    panel = opened(open_panel, {**binary, 'recap': []})
    assert panel.page.locator('[data-no-recap]').inner_text() == 'No recap yet.'
    assert panel.page.locator('[data-recap-list]').count() == 0
    assert_clean(panel)


# --- Study map (§6.1.2) ----------------------------------------------------------------------

@pytest.mark.parametrize('scheme', THEMES)
def test_ov3_ov4_study_map_has_four_moments_every_step_once_and_text_marks(open_panel, regression, scheme):
    panel = opened(open_panel, regression, scheme=scheme)
    page = panel.page
    assert page.locator('[data-moment] h3').evaluate_all('hs => hs.map(h => h.textContent)') == MOMENTS
    steps = page.locator('[data-map] [data-step]').evaluate_all('ss => ss.map(s => s.dataset.step)')
    assert sorted(steps) == sorted(s['id'] for s in regression['plan'])
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

@pytest.mark.parametrize('scheme', THEMES)
def test_ov5_ov6_digest_items_verbatim_kept_fits_in_bold_and_no_revision(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    section = page.locator('[data-ov="since"]')
    items = section.locator('[data-digest] li')
    assert items.evaluate_all('is => is.map(i => i.textContent)') == [i['text'] for i in binary['digest']['items']]
    replaced = section.locator('[data-digest-item="result_replaced"]')
    assert replaced.locator('strong[data-kept-fits]').inner_text() == 'Models unchanged, nothing refitted.'
    assert section.locator('strong[data-kept-fits]').count() == 1
    assert 'needs confirmation again' in section.inner_text()
    assert 'my manager says the team can make 100 calls per wave' in section.inner_text()
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
    assert section.locator('[data-digest] li').count() == 5
    assert section.locator('[data-truncated]').inner_text() == \
        'Older changes are not listed. The Decisions tab has the full history.'
    page.locator('[data-since-select]').select_option('23')
    assert section.locator('[data-digest] li').count() == 4
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

@pytest.mark.parametrize('scheme', THEMES)
def test_ov7_deliverables_messages_verbatim_open_and_no_regenerate_when_current(open_panel, binary, scheme):
    panel = opened(open_panel, binary, scheme=scheme)
    page = panel.page
    rows = page.locator('[data-ov="deliverables"] [data-artifact]')
    assert rows.evaluate_all('rs => rs.map(r => r.dataset.artifact)') == ['report', 'notebook', 'workbench']
    for a in binary['artifacts']:
        row = page.locator(f'[data-ov="deliverables"] [data-artifact="{a["name"]}"]')
        assert row.locator('[data-message]').inner_text() == a['message']
    assert page.locator('[data-ov="deliverables"] [data-artifact="report"] .ov-deliverable-label').inner_text() == \
        'Report · study.html'
    assert page.locator('[data-write="render"]').count() == 0
    page.get_by_role('button', name='Open the report in the browser').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}
    page.get_by_role('button', name='Open workbench in the editor').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench'}
    assert_clean(panel)


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
    assert card.locator('h4').inner_text() == 'policy.evaluate: the outcome is unknown. Nothing will be restarted.'
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
    assert panel.state()['ackDrafts'] == {INTERRUPTED: words}, 'the junior\'s own draft only'
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
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'report'}, 'v1: no anchor yet'
    page.locator('[data-finding="causal_wording"]').get_by_role('button').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench'}
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
    assert page.locator('[data-updating="check"]').inner_text() == 'Updating...'
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'check'}, 'a newer revision reads again'
    assert page.locator('[data-finding]').count() == 2, 'older findings stay visible while updating'
    assert_clean(panel)


def test_not_yet_defensible_and_alert_navigation_to_health(open_panel, health):
    panel = opened(open_panel, health)
    page = panel.page
    nyd = page.locator('[data-health="nyd"]')
    assert nyd.locator('li').all_inner_texts() == [i['text'] for i in health['notYetDefensible']['top']]
    assert nyd.locator('[data-nyd-more]').inner_text() == 'More: no_causality, workbench_not_tracked'
    page.locator('[role="tab"][data-tab="decisions"]').click()
    page.locator('[data-alert="interrupted_executions"] button').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'overview'
    assert page.evaluate('document.activeElement.id') == 'ov-executions'
    page.locator('[data-alert="outcome_unknown"] button').click()
    focused = page.evaluate('document.activeElement.closest("[data-nav]").dataset.nav')
    assert focused == 'limit:outcome_unknown'
    assert page.locator(f'[data-nav="limit:outcome_unknown"] [data-execution-card="{SUSPECTED}"]').count() == 1
    navs = page.locator('#panel-overview [data-nav]').evaluate_all('ns => ns.map(n => n.dataset.nav)')
    assert len(navs) == len(set(navs)), 'navigation targets are unique'
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
    assert page.locator('[data-recap] li').count() == 5
    for hook in ['[data-ov]', '[data-map]', '[data-digest]', '[data-check]', '[data-write="render"]',
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
    for hook in ['where', 'map', 'health']:
        assert page.locator(f'[data-ov="{hook}"]').get_attribute('data-stage') == 'v1', hook
    assert page.locator('.ov-grid').get_attribute('data-stage') == 'v1'
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
    assert page.locator('#panel-overview h2').all_inner_texts() == [
        'Where we are', 'Study map', 'Since your last session', 'Deliverables', 'Health']
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
