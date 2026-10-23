"""A20 (report section), A21 (case banks), A23 (companion untouched), A01 (report unchanged
when off)."""
from __future__ import annotations

import re

import pytest
import yaml

import flowkit as fk
import ukit
from mlkit.study import cli
from mlkit.study.understanding import taskset as bk

REPO = fk.REPO
CASES = {'hotel-booking': ('hotel-booking-resort-v1', 'binary'),
         'bank-marketing': ('uci-bank-marketing-v1', 'binary'),
         'auto-mpg': ('uci-auto-mpg-v1', 'regression')}


def render(u):
    out = cli.run(['render', '--study', str(u.study)])
    assert out.exit_code in (0, 3), out.payload
    return (u.study / 'reports' / 'study.html').read_text()


def test_report_section_is_separate_escaped_and_offline(tmp_path):
    """A20: a distinct "Understanding and handover" section, not the scientific verdict;
    entered text is escaped; no external resource; the numbers check stays clean."""
    u = ukit.U(tmp_path)
    plain = render(u)
    assert 'id="understanding"' not in plain                    # off: report unchanged
    u.set_policy(ukit.policy(mode='required'))
    _, out = u.start()
    sid = out['result']['session_id']
    task = u.call('task', '--session', sid)['task']
    a = u.submit(sid, task['task_id'])['result']['attempt_id']
    evil = '<script>alert(1)</script><a href="javascript:x">x</a>'
    d = u.decision(task['dimension_ids'][0], [a], rationale=evil)
    u.review(sid, [d], reviewer='bob')
    page = render(u)
    section = page[page.index('id="understanding"'):]
    section = section[:section.index('</section>')]
    assert 'Understanding and handover' in section
    assert 'not the scientific verdict' in section
    assert '<script>alert' not in page and 'javascript:x' not in section
    assert 'simulated' in section
    assert not re.search(r'(src|href)="https?://', page)
    check = cli.run(['check', '--study', str(u.study)])
    assert check.exit_code in (0, 3), check.payload
    findings = [f for f in check.payload.get('findings', []) if f.get('severity') == 'error'
                and 'understanding' in str(f)]
    assert findings == []


def _chromium(p):
    """The pinned Chromium, else a preinstalled build (as test_html_offline does)."""
    import glob
    import os
    try:
        return p.chromium.launch(headless=True)
    except Exception:                     # noqa: BLE001
        root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers')
        for pattern in ('chromium_headless_shell-*/chrome-linux/headless_shell',
                        'chromium-*/chrome-linux/chrome'):
            found = sorted(glob.glob(os.path.join(root, pattern)))
            if found:
                return p.chromium.launch(headless=True, executable_path=found[-1])
        pytest.skip('no Chromium available for Playwright')


def test_report_section_fits_a_small_screen_in_both_themes(tmp_path):
    """A20: no horizontal overflow of the section at 390 px, light and dark."""
    playwright = pytest.importorskip('playwright.sync_api')
    u = ukit.U(tmp_path)
    ukit.full_flow(u)
    render(u)
    path = u.study / 'reports' / 'study.html'
    with playwright.sync_playwright() as p:
        browser = _chromium(p)
        for scheme in ('light', 'dark'):
            page = browser.new_page(viewport={'width': 390, 'height': 800}, color_scheme=scheme)
            page.route('**/*', lambda r: r.abort() if not r.request.url.startswith('file:')
                       else r.continue_())
            page.goto(path.as_uri())
            box = page.locator('#understanding').bounding_box()
            assert box and box['width'] <= 390
            assert page.evaluate('document.documentElement.scrollWidth') <= 390 + 1
        browser.close()


@pytest.mark.parametrize('case', sorted(CASES))
def test_case_banks_are_valid_contextual_and_honest(case):
    """A21: each case bank validates against its case, cites the study through references
    (no figure written in a prompt), is marked to_qualify, and the regression bank never
    assumes a positive class."""
    case_id, task = CASES[case]
    bank = bk.load(REPO / 'use-cases' / case, case_id=case_id)
    assert bank['qualification']['status'] == 'to_qualify'
    assert {r['dimension_id'] for r in bank['rubrics']} == set(bk.DIMENSIONS)
    for t in bank['tasks']:
        assert not re.search(r'\d', t['prompt_template']), t['task_id']
    doc = yaml.safe_load((REPO / 'use-cases' / case / 'case.yaml').read_text())
    facts = {f['id'] for f in doc['facts']}
    for t in bank['tasks']:
        for ref in t['required_refs']:
            if ref.startswith('fact:'):
                assert ref[5:] in facts, (t['task_id'], ref)
    text = ' '.join(t['prompt_template'] for t in bank['tasks']).lower()
    if task == 'regression':
        assert 'positive' not in text and 'precision' not in text and 'unit' in text
        assert 'result:evaluate.regression' in str(bank)
    else:
        assert 'result:policy.evaluation' in str(bank)


def test_real_case_plan_resolves_from_the_study(tmp_path):
    """A21: on a real case study (Bank Marketing), the plan cites the confirmed decisions;
    a results task waits for a real result instead of inventing one."""
    u = ukit.U(tmp_path, case_dir=REPO / 'use-cases' / 'bank-marketing', repo=False)
    u.set_policy(ukit.POLICY)
    plan = u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice')
    assert plan['taskset']['qualification'] == 'to_qualify'
    assert 'D4' in {m['dimension_id'] for m in plan['prerequisites_missing']}
    plan_file = tmp_path / 'plan.json'
    u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice',
           '--write-plan', plan_file)
    out = u.m('start', '--plan-file', plan_file)
    sid = out['result']['session_id']
    task = u.call('task', '--session', sid)['task']
    assert '{' not in task['prompt']
    # A required gate never accepts a bank nobody qualified.
    u.set_policy(ukit.policy(mode='required'))
    gate = u.call('check', '--milestone', 'handoff')['gate']
    assert gate['decision'] == 'blocked'


def test_regression_case_without_decisions_lists_prerequisites(tmp_path):
    """A21: Auto MPG before its decisions: every task needing a decision or a result is a
    missing prerequisite; nothing is asked with an invented value."""
    u = ukit.U(tmp_path, case_dir=REPO / 'use-cases' / 'auto-mpg', repo=False, pauses=False)
    u.set_policy(ukit.POLICY)
    plan = u.call('plan', '--profile', 'analyst', '--milestone', 'handoff', '--actor', 'alice')
    missing = {m['dimension_id']: m['missing_refs'] for m in plan['prerequisites_missing']}
    assert 'decision:success_criterion' in missing['D4']
    assert 'result:evaluate.regression' in missing['D4']


def test_companion_is_untouched():
    """A23: the study panel neither calls nor knows the review (its permissions and write
    whitelist are unchanged)."""
    client = REPO / 'clients' / 'vscode-companion'
    text = ''.join(p.read_text(errors='ignore') for p in client.rglob('*.js')
                   if 'node_modules' not in p.parts)
    assert 'understanding' not in text.lower()
