"""Browser tests of the currency of the panel's data (scope S, simulated browser; decision
CR.1, COMPANION-ADVANCED §5, §11).

A model read at the snapshot's revision but under another currency (a dataset edit, a
deleted or edited deliverable, without a new revision) is not current: the webview asks
for it again, and "If you confirm" is read again. The explicit Refresh makes every view
read again, at the same revision and currency. A failed load is asked again at the next
version, or with the view's Retry, never in a loop. On the one page (ADR 0004 d13) a block
reads only when it is shown: Now's "What your answer will change" and a step's history are
opened first (§11). This is not a VS Code session.
"""
from __future__ import annotations

import copy

from panel_cases import click_fold
from test_webview_decisions import effects_message, open_effects, open_history, opened, wait_until

CURRENCY_A = '00000000000000aa'
CURRENCY_B = '00000000000000bb'


def loads(panel, view):
    return [m for m in panel.posted() if m['type'] == 'load' and m['view'] == view]


def effects_asked(panel, pid='p_5'):
    return [m for m in panel.posted() if m['type'] == 'preview_effects' and m['proposalId'] == pid]


def settle(panel):
    """Two animation frames: IntersectionObserver callbacks (a card's preview) have run."""
    panel.page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')


def wait_effects(panel, count, pid='p_5'):
    wait_until(panel.page, f"window.__posted.filter(m => m.type === 'preview_effects' && m.proposalId === '{pid}').length >= {count}")
    settle(panel)


def shown(panel):
    """Open what reads `decisions` and `preview effects`: Now's effects fold and a step's history."""
    open_history(panel, 'policy')
    return open_effects(panel)


def with_currency(summary, currency):
    out = copy.deepcopy(summary)
    out['currency'] = currency
    return out


def test_cr1_a_new_currency_at_the_same_revision_reads_the_tab_and_the_effects_again(open_panel, model):
    a = with_currency(model('summary', 'summary.binary'), CURRENCY_A)
    panel = opened(open_panel, a)
    page = panel.page
    effects = shown(panel)
    panel.view_data('decisions', model('decisions', 'decisions.binary'), revision=a['revision'])
    eff = model('effects', 'preview_effects.binary')
    panel.send({**effects_message(eff, a['revision']), 'currency': CURRENCY_A})
    assert effects.locator('[data-effects-box="kept"]').count() == 1
    assert effects.locator('[data-effects-updating]').count() == 0
    assert page.locator('[data-updating]').count() == 0
    wait_effects(panel, 1)
    n_loads, n_effects = len(loads(panel, 'decisions')), len(effects_asked(panel))
    # Same summary again (a watch event that changed nothing): nothing is read again.
    panel.snapshot(a)
    settle(panel)
    assert (len(loads(panel, 'decisions')), len(effects_asked(panel))) == (n_loads, n_effects)
    # The same revision under a new currency: the history and the preview are read again,
    # and what is shown says it is updating.
    panel.snapshot(with_currency(a, CURRENCY_B))
    assert len(loads(panel, 'decisions')) == n_loads + 1
    wait_effects(panel, n_effects + 1)
    assert len(effects_asked(panel)) == n_effects + 1
    assert effects.locator('[data-effects-updating]').count() == 1
    assert page.locator('[data-updating]').count() == 1
    panel.view_data('decisions', model('decisions', 'decisions.binary'), revision=a['revision'])
    panel.send({**effects_message(eff, a['revision']), 'currency': CURRENCY_B})
    assert effects.locator('[data-effects-updating]').count() == 0
    assert page.locator('[data-updating]').count() == 0
    assert panel.clean()


def test_cr1_the_explicit_refresh_reads_every_view_again_at_the_same_version(open_panel, model):
    a = with_currency(model('summary', 'summary.binary'), CURRENCY_A)
    panel = opened(open_panel, a)
    shown(panel)
    panel.view_data('decisions', model('decisions', 'decisions.binary'), revision=a['revision'])
    panel.send({**effects_message(model('effects', 'preview_effects.binary'), a['revision']), 'currency': CURRENCY_A})
    wait_effects(panel, 1)
    n_loads, n_effects = len(loads(panel, 'decisions')), len(effects_asked(panel))
    panel.page.locator('[data-more]').click()
    panel.page.locator('[data-refresh]').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'refresh'}
    panel.snapshot(a)   # the controller's answer: the same revision and currency
    assert len(loads(panel, 'decisions')) == n_loads + 1
    wait_effects(panel, n_effects + 1)
    assert len(effects_asked(panel)) == n_effects + 1
    assert panel.clean()


def test_cr1_a_failed_load_is_asked_again_at_the_next_currency_and_with_retry_never_in_a_loop(open_panel, model):
    a = with_currency(model('summary', 'summary.binary'), CURRENCY_A)
    panel = opened(open_panel, a)
    page = panel.page
    open_history(panel, 'policy')
    before = len(loads(panel, 'decisions'))
    panel.send({'type': 'load_error', 'view': 'decisions', 'message': 'The hypotrail CLI failed.', 'detail': ''})
    panel.snapshot(a)
    panel.snapshot(a)
    assert len(loads(panel, 'decisions')) == before, 'the same version does not ask again by itself'
    panel.snapshot(with_currency(a, CURRENCY_B))
    assert len(loads(panel, 'decisions')) == before + 1, 'the next currency asks again'
    panel.send({'type': 'load_error', 'view': 'decisions', 'message': 'The hypotrail CLI failed.', 'detail': ''})
    page.locator('[data-history-error]').get_by_role('button', name='Retry').click()
    assert len(loads(panel, 'decisions')) == before + 2, 'Retry asks again'
    panel.snapshot(with_currency(a, CURRENCY_B))
    assert len(loads(panel, 'decisions')) == before + 2, 'and only once'
    assert panel.clean()


def test_cr1_overview_check_and_evidence_follow_the_currency(open_panel, model):
    a = with_currency(model('summary', 'summary.binary'), CURRENCY_A)
    panel = open_panel()
    panel.init(stage='v2', task='binary', panelContract=2)
    panel.snapshot(a)
    page = panel.page
    click_fold(page, 't-deliverables')
    click_fold(page, 'checks')
    wait_until(page, "window.__posted.some(m => m.type === 'load' && m.view === 'check')")
    assert len(loads(panel, 'check')) == 1
    panel.view_data('check', model('check', 'check.binary'), revision=a['revision'])
    panel.snapshot(a)
    assert len(loads(panel, 'check')) == 1
    panel.snapshot(with_currency(a, CURRENCY_B))
    assert len(loads(panel, 'check')) == 2, 'a deleted or edited deliverable: the checks are read again'
    click_fold(page, 'ledger')
    n = len(loads(panel, 'evidence'))
    assert n >= 1
    panel.view_data('evidence', model('evidence', 'evidence.binary'), revision=a['revision'])
    panel.snapshot(with_currency(a, CURRENCY_A))
    assert len(loads(panel, 'evidence')) == n + 1, 'the dataset changed: the evidence is read again'
    assert panel.clean()


def test_cr5_read_budget_of_the_shown_blocks_on_a_watch_event_at_v2(open_panel, model):
    # §11 (decision CR.5): on a watch event the shown blocks at v2 read their data views
    # (`decisions` for the history, `evidence` for Now's figure) once each, and the preview of
    # the open proposal once, only when the version moved; nothing when it did not.
    a = with_currency(model('summary', 'summary.binary'), CURRENCY_A)
    panel = opened(open_panel, a, stage='v2')
    shown(panel)
    panel.view_data('decisions', model('decisions', 'decisions.binary'), revision=a['revision'])
    panel.view_data('evidence', model('evidence', 'evidence.binary'), revision=a['revision'])
    panel.send({**effects_message(model('effects', 'preview_effects.binary'), a['revision']), 'currency': CURRENCY_A})
    asked = lambda: [(m['type'], m.get('view') or m.get('proposalId')) for m in panel.posted()
                     if m['type'] in ('load', 'preview_effects')]
    wait_effects(panel, 1)
    n = len(asked())
    panel.snapshot(a)
    settle(panel)
    assert asked()[n:] == [], 'the same version reads nothing'
    later = {**a, 'revision': a['revision'] + 1}
    panel.snapshot(later)
    wait_effects(panel, 2)
    assert sorted(asked()[n:]) == sorted([('load', 'decisions'), ('load', 'evidence'), ('preview_effects', 'p_5')])
    panel.snapshot(later)
    settle(panel)
    assert len(asked()) == n + 3, 'once per version'
    assert panel.clean()
