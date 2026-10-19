"""INV-12 after interactions (scope S, simulated browser; review finding M3, decision CR.4).

In a regression study the panel's own copy never uses the vocabulary of a decision rule.
The per-view tests scan each tab as first rendered; this test also scans the whole DOM
text after every interaction a junior can make without writing: each button that is not
a write control (the "Ask the agent" modals included), each disclosure opened, each radio
and checkbox, each option of each select, each range moved, and "Select the id" of an
Evidence detail. Auto MPG fixtures, stage v3. This is not a VS Code session.
"""
from __future__ import annotations

import re

from test_webview_evidence import detail_payload

FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|selected)\b', re.I)
CONTROLS = ('button:not([data-write]):not([role="tab"]):not([disabled]), summary, input[type="radio"], '
            'input[type="checkbox"], select, input[type="range"]')
TABS = {
    'overview': [('check', 'check', 'check.binary.clean')],
    'eda': [('eda', 'eda', 'evidence.regression')],
    'decisions': [('decisions', 'decisions', 'decisions.regression'), ('evidence', 'evidence', 'evidence.regression')],
    'evidence': [('evidence', 'evidence', 'evidence.regression')],
    'whatif': [('whatif', 'whatif', 'evidence.regression')],
    'learn': [('explain', 'explain', 'explain.regression'), ('session_report', 'session_report', 'session_report.binary')],
}


def scan(page, where, hits):
    text = page.locator('body').inner_text()
    for m in FORBIDDEN.finditer(text):
        hits.append((where, m.group(0), text[max(0, m.start() - 60):m.end() + 30].replace('\n', ' ')))


def act(page, control):
    tag = control.evaluate('n => n.tagName')
    kind = control.get_attribute('type') or ''
    if tag == 'SELECT':
        for value in control.evaluate('n => [...n.options].map(o => o.value)'):
            control.select_option(value)
        return
    if kind == 'range':
        control.focus()
        for key in ('ArrowRight', 'End', 'Home'):
            page.keyboard.press(key)
        return
    control.click(timeout=1000)


def test_inv12_regression_vocabulary_after_every_interaction_in_every_tab(open_panel, model, payload):
    summary = model('summary', 'summary.regression')
    panel = open_panel()
    page = panel.page
    panel.init(stage='v3', task='regression')
    panel.snapshot(summary)
    rids = {r['result_id'] for r in payload('evidence.regression')['results']}
    hits, done, shown, selects = [], [], set(), 0
    for tab, views in TABS.items():
        page.locator(f'[role="tab"][data-tab="{tab}"]').click()
        for view, module, fixture in views:
            panel.view_data(view, model(module, fixture), revision=summary['revision'])
        scan(page, f'{tab}: shown', hits)
        i = 0
        while i < 80:
            controls = page.locator(f'#panel-{tab}').locator(CONTROLS).all()
            if i >= len(controls):
                break
            control = controls[i]
            label = (control.get_attribute('data-nav') or control.inner_text() or control.get_attribute('aria-label') or '')[:40]
            try:
                act(page, control)
            except Exception:  # noqa: BLE001 - a control hidden by an earlier action
                i += 1
                continue
            scan(page, f'{tab}: {label}', hits)
            done.append((tab, label))
            page.keyboard.press('Escape')
            asked = [m for m in panel.posted() if m['type'] == 'load' and m.get('resultId')]
            if tab == 'evidence' and asked and asked[-1]['resultId'] in rids and asked[-1]['resultId'] not in shown:
                rid = asked[-1]['resultId']
                shown.add(rid)
                panel.send({'type': 'view_data', 'view': 'evidence', 'revision': summary['revision'], 'resultId': rid,
                            'model': model('evidence', detail_payload(payload, 'evidence.regression', rid))})
                scan(page, f'{tab}: detail of {rid[:8]}', hits)
                select = page.locator('[data-select-id]')
                if select.count():
                    select.first.click(timeout=2000)
                    scan(page, f'{tab}: Select the id of {rid[:8]}', hits)
                    selects += 1
            if page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') != tab:
                page.locator(f'[role="tab"][data-tab="{tab}"]').click()
            i += 1
    assert len(done) > 20, done
    assert any(t == 'evidence' for t, _ in done)
    assert selects >= 1, 'an Evidence detail was opened and its id selected'
    assert hits == [], '\n'.join(map(str, sorted(set(hits))))
    assert panel.clean()
