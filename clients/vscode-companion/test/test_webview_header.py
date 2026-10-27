"""The sticky region of the one page (scope S, simulated browser; COMPANION-ADVANCED §6.1, §6.2,
§13.2, §13.3; ADR 0004 decision 13): the header (study, theme, more; the pills) and the
progress. Real document, real CSP, offline, on the contract-P1 states. Not a VS Code session.
"""
from __future__ import annotations

import pytest

import themes
from panel_cases import STATES, load_views, open_case


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def sticky_height(page):
    return page.evaluate("() => document.querySelector('[data-block=\"header\"]').getBoundingClientRect().height")


def test_pg2_pg8_only_the_header_and_the_progress_are_sticky_and_short(open_panel, views):
    """PG-2, PG-8, NAR-1: at 420 and 600 px at most 110 px high, at 320 px at most 150 px, in
    both languages, on every state; the pills wrap rather than overflow; To handle and Now flow
    under it; the progress names the step and its moment in one label, and a sentence for
    screen readers."""
    for state in STATES:
        for width, limit in ((320, 150), (420, 110), (600, 110)):
            for lang in ('en', 'fr'):
                panel = open_case(open_panel, views, case=state, width=width, lang=lang, deliver=False)
                page = panel.page
                assert sticky_height(page) <= limit, (state, width, lang, sticky_height(page))
                assert page.evaluate("() => getComputedStyle(document.querySelector('[data-block=\"header\"]')).position") == 'sticky'
                assert page.locator('[data-block="header"] [data-block="todo"], [data-block="header"] [data-block="now"]').count() == 0
                assert page.evaluate('document.scrollingElement.scrollWidth') <= width
                panel.context.close()
    panel = open_case(open_panel, views, case='choice', width=420, lang='en', deliver=False)
    assert panel.page.locator('[data-block="progress"] .ht-plbl').inner_text() == 'Step 11/13 · Work and compare'
    assert panel.page.locator('[data-block="progress"] .sr-only').text_content() == 'Step 11 of 13, phase Work and compare.'
    assert panel.page.locator('[data-block="progress"] .ht-bar[aria-hidden="true"]').count() == 1


def test_pg4_pg5_pg6_pg14_focus3_the_pills_and_the_defensibility_popover(open_panel, views):
    """PG-3 to PG-6, PG-14, FOCUS-3, HON-5: the pills in order; the seal's hover; the pill's text,
    tone and items are the engine's `defensibility` in its order, each with its severity in
    words; the popover opens over the page, takes the focus, closes on Escape (focus back on
    its button) and on a click outside; opening the "more" menu closes it."""
    panel = open_case(open_panel, views, case='reopened', width=420, lang='en')
    page = panel.page
    pills = page.locator('[data-pill]')
    assert [p.get_attribute('data-pill') for p in pills.all()] == ['seal', 'defensible']
    assert page.locator('[data-pill="seal"]').get_attribute('title') == '80 rows set aside at creation; no chart or computation reads them.'
    pill = page.locator('[data-pill="defensible"]')
    assert pill.get_attribute('data-defensibility') == 'warn' and pill.get_attribute('aria-haspopup') == 'dialog'
    y = page.locator('[data-block="now"]').bounding_box()['y']
    pill.click()
    pop = page.locator('[data-popover="def"]')
    assert pop.get_attribute('role') == 'dialog'
    assert page.evaluate("() => document.activeElement.getAttribute('data-popover')") == 'def'
    assert page.locator('[data-block="now"]').bounding_box()['y'] == y, 'the popover never pushes the page down'
    items = views['summary.reopened']['defensibility']['items']
    assert [li.get_attribute('data-item') for li in pop.locator('li').all()] == [i['id'] for i in items]
    assert pop.locator('h3').inner_text().lower() == 'what keeps the study from being defended'
    assert pop.locator('[data-severity]').first.inner_text() == 'blocking'
    page.keyboard.press('Escape')
    assert page.locator('[data-popover]').count() == 0
    assert page.evaluate("() => document.activeElement.getAttribute('data-pill')") == 'defensible'
    pill.click()
    page.locator('[data-block="path"] h2').click()
    assert page.locator('[data-popover]').count() == 0, 'a click outside closes it'
    pill.click()
    page.locator('[data-more]').click()
    assert page.locator('[data-popover="def"]').count() == 0 and page.locator('[data-popover="more"]').count() == 1
    for state, text in (('step1', 'Defensible at the end · 3 points'), ('done', 'Defensible · 3 limits')):
        p = open_case(open_panel, views, case=state, width=420, lang='en', deliver=False)
        assert p.page.locator('[data-pill="defensible"]').inner_text() == text
        p.context.close()
    assert panel.clean()


def test_pg3_the_more_menu_holds_the_language_theme_refresh_switch_and_guide(open_panel, views):
    """PG-3, §6.1 "more" menu, PG-11: real buttons and radio groups (not role=menu), in order;
    Refresh says its age and revision; Change study from v1; "How this panel works" opens its
    fold at the end of Tools; the task and stage line."""
    panel = open_case(open_panel, views, case='choice', width=420, lang='en', stage='v1', deliver=False)
    page = panel.page
    more = page.locator('[data-more]')
    assert more.get_attribute('aria-label') == 'More options' and more.get_attribute('aria-haspopup') == 'dialog'
    more.click()
    menu = page.locator('[data-more-menu]')
    assert menu.locator('[role="menu"]').count() == 0
    assert menu.locator('[role="radiogroup"]').count() == 2
    assert menu.locator('[data-language-toggle] [role="radio"]').all_inner_texts() == ['English', 'Français']
    assert menu.locator('[data-refresh]').inner_text().startswith('Refresh · read ')
    assert menu.locator('[data-refresh]').inner_text().endswith('revision 38')
    assert menu.locator('[data-switch-study]').inner_text() == 'Change study: auto mpg ▾'
    assert menu.locator('[data-stage-line]').inner_text() == 'Regression · experimental panel, stage v1'
    before = len(panel.posted())
    menu.locator('[data-refresh]').click()
    assert panel.posted()[before:] == [{'v': 2, 'type': 'refresh'}]
    page.locator('[data-more-menu] [data-how]').click()
    assert page.locator('[data-how-panel][open]').count() == 1
    assert page.locator('[data-how-panel]').inner_text().count('chat') >= 1
    low = open_case(open_panel, views, case='choice', width=420, lang='en', stage='v0', deliver=False)
    low.page.locator('[data-more]').click()
    assert low.page.locator('[data-switch-study]').count() == 0


def test_theme1_to_theme4_the_panel_theme_control(open_panel, views):
    """THEME-1, THEME-2, THEME-3, THEME-4: the button cycles Auto → Dark → Light → Auto and names its state; the
    menu offers the same choice; one value in setState, no message; `data-theme` on body lays
    the board; High Contrast keeps the editor's colours and says so."""
    panel = open_case(open_panel, views, case='choice', theme='light-modern', width=420, lang='en', deliver=False)
    page = panel.page
    button = page.locator('[data-theme-control]')
    bg = lambda: page.evaluate('getComputedStyle(document.body).backgroundColor')
    light_bg = bg()
    assert button.get_attribute('aria-label') == 'Panel theme: follows VS Code (change)'
    before = len(panel.posted())
    button.click()
    assert page.locator('body').get_attribute('data-theme') == 'dark'
    assert panel.state()['theme'] == 'dark' and bg() != light_bg
    assert page.evaluate("() => document.activeElement.hasAttribute('data-theme-control')"), 'FOCUS-2'
    button.click()
    assert page.locator('body').get_attribute('data-theme') == 'light' and bg() == light_bg
    button.click()
    assert page.locator('body').get_attribute('data-theme') == 'auto' and 'theme' not in panel.state()
    page.locator('[data-more]').click()
    page.locator('[data-more-menu] [data-theme="dark"]').click()
    assert page.locator('body').get_attribute('data-theme') == 'dark'
    assert panel.posted()[before:] == [], 'the theme is the viewer\'s, never a message'
    hc = open_case(open_panel, views, case='choice', theme='hc', width=420, lang='en', deliver=False, panel_theme='light')
    hc_bg = hc.page.evaluate('getComputedStyle(document.body).backgroundColor')
    assert hc_bg in ('rgb(0, 0, 0)',), hc_bg
    assert 'High Contrast theme in use' in hc.page.locator('[data-theme-control]').get_attribute('aria-label')
    assert panel.clean() and hc.clean()


def test_focus4_focus_is_visible_on_every_control(open_panel, views):
    """FOCUS-4, A11Y-1, NAR-4: every control has an accessible name, a 2 px outline when focused,
    no positive tabindex, and a touch target of at least 32 × 32 px."""
    for theme in ('dark-modern', 'light-modern'):
        panel = open_case(open_panel, views, case='reopened', theme=theme, width=420, lang='en')
        page = panel.page
        controls = page.locator('#app button:visible, #app summary:visible')
        assert controls.count() > 15
        for i in range(controls.count()):
            c = controls.nth(i)
            name = c.get_attribute('aria-label') or c.inner_text().strip()
            assert name, c.evaluate('n => n.outerHTML.slice(0, 120)')
            c.focus()
            style = page.evaluate("() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth]; }")
            assert style == ['solid', '2px'], (theme, name, style)
            box = c.bounding_box()
            # NAR-4 names the fold summaries, copy buttons, theme and "more" buttons; the pills keep
            # the sticky region short (PG-2) and a link or a notion is a word of the prose.
            if not c.evaluate("n => n.matches('.ht-term, .ht-link, [data-pill]')"):
                assert box['height'] >= 31.5, (theme, name, box)
        assert page.locator('[tabindex]:not([tabindex="0"]):not([tabindex="-1"])').count() == 0
        panel.context.close()


def test_pg11_a_load_error_replaces_the_content_below_the_sticky_region(open_panel, views):
    """PG-11, §3.3: the error card replaces To handle, Now, the path and the drawers; the header
    keeps the study and the "more" button; Retry reads again."""
    panel = open_case(open_panel, views, case='reopened', width=420, lang='en')
    panel.send({'type': 'load_error', 'view': None, 'message': 'The hypotrail CLI failed.', 'detail': 'stderr'})
    page = panel.page
    assert page.locator('[data-load-error][role="alert"]').count() == 1
    assert page.locator('[data-block="todo"], [data-block="now"], [data-block="path"], [data-block="tools"]').count() == 0
    assert page.locator('[data-study-name]').inner_text() == 'auto mpg'
    assert page.locator('[data-last-read]').inner_text() == 'Last read at revision 40; the study could not be read now.'
    before = len(panel.posted())
    page.locator('[data-retry]').click()
    assert panel.posted()[before:] == [{'v': 2, 'type': 'refresh'}]
    panel.snapshot(views['summary.reopened'])
    assert page.locator('[data-block="now"]').count() == 1


def test_skew_a_different_contract_shows_one_line_and_changes_nothing_else(open_panel, views, model, payload):
    """§3.3 contract skew, CLI-CONTRACT §17.1.5: a digest without `panel_contract`, or another
    version, gives one read-only line in the "more" menu and the footer; nothing else changes."""
    raw = payload('p1/summary.choice')
    raw['panel_contract'] = 3
    skewed = model('summary', raw)
    panel = open_case(open_panel, views, case='choice', width=420, lang='en', deliver=False)
    page = panel.page
    assert page.locator('[data-skew]').count() == 0
    panel.snapshot(skewed)
    assert page.locator('footer [data-skew]').count() == 1
    page.locator('[data-more]').click()
    assert page.locator('[data-more-menu] [data-skew]').inner_text().startswith('This panel and the study engine come from different versions')


def test_reviewer_pill_and_no_write_control(open_panel, views):
    """§3.3 Reviewer, RV-2, HO-2: the reviewer pill; no `data-write` control but the export, every
    drawer opened."""
    from panel_cases import open_all
    panel = open_case(open_panel, views, case='reopened', width=420, lang='en', reviewer=True)
    open_all(panel, views, 'p1')
    page = panel.page
    assert page.locator('[data-pill="reviewer"]').inner_text() == 'Reviewer, read-only'
    writes = page.evaluate("() => [...document.querySelectorAll('[data-write]')].map(n => n.dataset.write)")
    assert set(writes) <= {'export'}, writes
    assert page.locator('[data-marimo="editable"], [data-marimo="workbench"]').count() == 0
    assert themes  # the theme helpers are the shared ones
