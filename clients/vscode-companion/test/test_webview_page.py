"""The one page on the five states of the approved mockup (scope S, simulated browser; ADR 0004
decision 13; COMPANION-ADVANCED §4, §6; docs/plans/mockups/panel-synthesis-fr.html).

The real document under the real CSP, offline, on the contract-P1 payloads of
``test/fixtures/captured/summary.regression.<state>`` (step 1, the model choice, the reopened
preparation and the same study once a run was interrupted, the automatic review, the end) and
the one-page study's reads, captured from the engine. Each test follows the junior
through one state and checks several requirements at once: the order of the page, what Now
asks and offers, what the path and To handle hold, and the honesty rules. Not a VS Code
session; no Copilot.
"""
from __future__ import annotations

import copy
import re

import pytest

from panel_cases import STATES, click_fold, load_views, open_all, open_case, set_language

NNBSP = ' '
# The digest keys of contract P1 (CLI-CONTRACT §17.2), absent from an older engine's summary.
P1_KEYS = ('panel_contract', 'automation', 'review_queue', 'defensibility', 'ledger', 'sample', 'headlines',
           'criterion_configurations')
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)


@pytest.fixture(scope='module')
def views(model, payload):
    return load_views(model, payload)


def blocks(page):
    return page.evaluate("() => [...document.querySelectorAll('[data-block]')].map(n => n.getAttribute('data-block'))")


def now_parts(page):
    """The parts of Now in DOM order (NOW-1)."""
    return page.evaluate("""() => {
      const now = document.querySelector('[data-block="now"]');
      const keys = ['h2', '.ht-who', 'h3.ht-question', '[data-options]', '[data-options-note]', '[data-copy-question]',
        '[data-context]', '[data-fold-id="effects"]', '[data-limit]', '[data-next]'];
      const found = [];
      for (const n of now.querySelectorAll('*')) {
        const k = keys.find(s => n.matches(s));
        if (k && !found.includes(k) && n.closest('[data-block="now"]') === now) found.push(k);
      }
      return found;
    }""")


@pytest.mark.parametrize('lang', ['en', 'fr'])
@pytest.mark.parametrize('state', STATES)
def test_pg1_now1_op3_the_page_order_and_now_follow_the_engine(open_panel, views, state, lang):
    """PG-1, OP-1, NOW-1, NOW-2, OP-3, HON-10: the fixed order of the blocks, no tab; Now asks the
    engine's question in the panel language with its options as plain text; one copy button
    whose label shows the question it copies, and nothing else to press."""
    panel = open_case(open_panel, views, case=state, theme='dark-modern', width=420, lang=lang)
    page = panel.page
    order = [b for b in blocks(page) if b not in ('progress',)]
    expected = {'step1': ['header', 'now', 'path', 'tools'], 'choice': ['header', 'since', 'now', 'path', 'tools'],
                'reopened': ['header', 'since', 'now', 'waiting', 'path', 'tools'],
                'review': ['header', 'since', 'now', 'path', 'tools'], 'done': ['header', 'since', 'now', 'after', 'path', 'tools']}
    assert order == expected[state], order
    assert page.locator('[role="tablist"], [data-tab]').count() == 0, 'OP-1: no tab'
    summary = views[f'summary.{state}']
    texts = summary['texts'][lang]
    if state != 'done':
        heading = page.locator('[data-block="now"] h2').text_content()
        assert heading.startswith('Now · ' if lang == 'en' else 'Maintenant · ')
        assert now_parts(page)[:3] == ['h2', '.ht-who', 'h3.ht-question']
        # NOW-1, NOW-2: the engine's question in the panel language, byte for byte (the panel's
        # French typography leaves the engine's text as it came: `data-verbatim`).
        question = page.locator('[data-block="now"] h3.ht-question').text_content()
        assert question == texts['question']
    if lang == 'fr':
        # The panel's own French copy carries a narrow no-break space before ? ! : ; and inside
        # quotation marks; no plain or no-break space is left there outside the engine's texts.
        loose = page.evaluate("""() => {
          const out = [];
          const walk = document.createTreeWalker(document.getElementById('app'), NodeFilter.SHOW_TEXT);
          for (let n = walk.nextNode(); n; n = walk.nextNode()) {
            const p = n.parentElement;
            if (!p || p.closest('code, pre, .ht-mono, data, svg, textarea, option, [data-verbatim]')) continue;
            if (/[ \\u00a0][?!:;\u00bb]|\u00ab[ \\u00a0]/.test(n.data)) out.push(n.data);
          }
          return out;
        }""")
        assert loose == [], loose
    # OP-3: the options are text, never a control.
    options = page.locator('[data-options] [data-option]')
    assert options.all_inner_texts() == [o['label'] for o in texts['options']]
    assert page.locator('[data-options] button, [data-options] [data-write]').count() == 0
    # HON-10, NOW-3: the copy button shows its question; pressing it sends that question only.
    copy = page.locator('[data-block="now"] [data-copy-question], [data-block="after"] [data-copy-question]').first
    label = copy.inner_text()
    before = len(panel.posted())
    copy.click()
    sent = panel.posted()[before:]
    assert len(sent) == 1 and sent[0]['type'] == 'ask_agent' and sent[0]['mode'] == 'copy', sent
    assert sent[0]['question'].replace(' ', ' ') in label.replace(NNBSP, ' ').replace(' ', ' '), (label, sent)
    # FOCUS-2: the control keeps the focus after the re-render; a polite "Copied" follows it.
    assert page.evaluate("() => document.activeElement.hasAttribute('data-copy-question')")
    assert page.locator('[data-copied][role="status"]').count() == 1
    # PG-10: the footer is the last element of the page, right after Tools.
    assert page.evaluate("""() => { const f = document.querySelector('#app footer');
      const main = document.querySelector('#main');
      const after = f && f.nextElementSibling;  // only the polite live region, which shows nothing
      return Boolean(f) && (after === null || after.id === 'outcome') && f.previousElementSibling === main
        && main.lastElementChild === document.querySelector('[data-block="tools"]'); }""")
    assert panel.clean()


def test_todo5_changed_sources_and_integrity_show_the_engine_junior_text(open_panel, views, model, payload):
    """TODO-5: `sources_changed` and `result_integrity` items of To handle show the engine's
    junior text (`texts.<lang>.limits.<id>`) in the panel language, the engine text under
    "Details"; the panel writes neither."""
    raw = copy.deepcopy(payload('captured/summary.regression.reopened'))
    engine = {'sources_changed': 'Sources changed since revision 31 (data hash, case file).',
              'result_integrity': 'Result fit.logistic failed its integrity check (stored hash differs).'}
    junior = {'en': {'sources_changed': 'The data file changed since the last results.',
                     'result_integrity': 'One stored result no longer matches what was computed.'},
              'fr': {'sources_changed': 'Le fichier de données a changé depuis les derniers résultats.',
                     'result_integrity': 'Un résultat enregistré ne correspond plus à ce qui a été calculé.'}}
    raw['not_yet_defensible']['top'] += [{'id': rid, 'text': text, 'audience': 'junior', 'junior_text': None}
                                         for rid, text in engine.items()]
    # as the engine lists them: every limit in `defensibility.items` too (P1 §17.2.2)
    raw['defensibility']['items'] += [{'id': rid, 'severity': 'blocking'} for rid in engine]
    for lang in ('en', 'fr'):
        raw['texts'][lang].setdefault('limits', {}).update(junior[lang])
    for lang in ('en', 'fr'):
        panel = open_case(open_panel, views, case='reopened', width=420, lang=lang)
        page = panel.page
        panel.snapshot(model('summary', raw))
        for kind, rid in (('sources', 'sources_changed'), ('integrity', 'result_integrity')):
            item = page.locator(f'[data-block="todo"] [data-todo="{kind}"]')
            assert item.count() == 1, kind
            assert junior[lang][rid] in item.inner_text().replace(NNBSP, ' ').replace('\u00a0', ' '), (lang, kind)
            assert item.locator('details > summary').count() == 1
            assert engine[rid] in item.locator('details').text_content()
            assert item.locator('[data-write], button:not(.ht-term)').count() == 0
        assert panel.clean()
        panel.context.close()


NARROW = """() => {
  const out = { charts: [], steps: [], pills: [] };
  for (const svg of document.querySelectorAll('#app svg.ht-chart')) {
    const r = svg.getBoundingClientRect();
    if (!r.width) continue;
    const box = svg.viewBox.baseVal;
    const parent = svg.parentElement.getBoundingClientRect();
    out.charts.push([box.width, Math.round(r.width), Math.round(parent.width)]);
  }
  for (const v of document.querySelectorAll('.ht-path .ht-v')) {
    const t = v.parentElement.querySelector('.ht-t');
    if (t && v.getBoundingClientRect().width) out.steps.push([t.getBoundingClientRect().bottom, v.getBoundingClientRect().top]);
  }
  for (const p of document.querySelectorAll('[data-pill]')) out.pills.push(p.getBoundingClientRect().right);
  return out;
}"""


def test_nar3_charts_steps_and_pills_at_320_px(open_panel, views):
    """NAR-3: at 320 px a chart is never wider than its frame (its text is never scaled up) nor
    than its container; each step line of the path wraps its value under its name; the pills
    wrap inside the viewport. At 420 px the step value stays on the name's line when it fits."""
    panel = open_case(open_panel, views, case='choice', theme='light-modern', width=320, lang='fr')
    open_all(panel, views, 'p1')
    found = panel.page.evaluate(NARROW)
    assert found['charts'], 'the model choice shows at least one drawn chart'
    for frame, shown, container in found['charts']:
        assert shown <= frame + 0.5 and shown <= container + 0.5, (frame, shown, container)
    assert found['steps']
    for name_bottom, value_top in found['steps']:
        assert value_top >= name_bottom - 1, (name_bottom, value_top)
    assert found['pills'] and max(found['pills']) <= 320
    assert panel.clean()
    wide = open_case(open_panel, views, case='choice', theme='light-modern', width=420, lang='en')
    rows = wide.page.evaluate(NARROW)['steps']
    assert any(value_top < name_bottom - 1 for name_bottom, value_top in rows), 'one line at 420 px'


# Every word of the first column of the development / final-test table, as rendered lines: a
# word laid out on more than one line was broken inside it ("modè/le").
BROKEN_WORDS = """() => {
  const out = [];
  for (const cell of document.querySelectorAll('table[data-dev-final] tr > :first-child')) {
    const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      for (const m of n.data.matchAll(/\\S+/g)) {
        const r = document.createRange();
        r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        const tops = new Set([...r.getClientRects()].filter(x => x.width).map(x => Math.round(x.top)));
        if (tops.size > 1) out.push(m[0]);
      }
    }
  }
  return out;
}"""


def test_nar3_the_dev_final_table_never_breaks_a_word_at_320_px(open_panel, views):
    """NAR-3, HON-1 (review fix 8): at 320 px the first column of the development / final-test
    table at the end breaks between words only ("modèle linéaire", never "modè/le/linéai/re");
    the table scrolls sideways in its region instead."""
    for lang in ('fr', 'en'):
        panel = open_case(open_panel, views, case='done', theme='light-modern', width=320, lang=lang)
        open_all(panel, views, panel.case_reads)
        page = panel.page
        # R52 (lot P): one row per configuration (linear, the variant, the reference), then the
        # difference with the reference and the criterion.
        assert page.locator('table[data-dev-final] tbody tr').count() == 5
        assert page.evaluate(BROKEN_WORDS) == [], lang
        assert panel.clean()
        panel.context.close()


def test_path_rows_do_not_repeat_the_step_name(open_panel, views, payload):
    """PATH-3 (review fix 6): a step line prints the step's short name, then the engine's
    headline, which holds no step name (no "Découpage  Découpage : …")."""
    for lang in ('fr', 'en'):
        panel = open_case(open_panel, views, case='done', width=600, lang=lang)
        open_all(panel, views, panel.case_reads)
        rows = panel.page.evaluate("""() => [...document.querySelectorAll('.ht-path [data-step]')].map(li => {
          const t = li.querySelector('.ht-t'); const v = li.querySelector('.ht-v');
          return [li.getAttribute('data-step'), t ? t.textContent.trim() : '', v ? v.textContent.trim() : ''];
        })""")
        headlines = payload('captured/summary.regression.done')['texts'][lang]['headlines']
        assert rows and any(step in headlines for step, _, _ in rows)
        for step, name, value in rows:
            assert name and not value.startswith(name + ' :') and not value.startswith(name + ':') \
                and not value.startswith(name + '\u202f:'), (lang, step, name, value)
            if step in headlines:
                assert value == headlines[step], (lang, step, value)
        panel.context.close()


def test_a_w4_target_distribution_is_under_exploration_and_its_anchor_resolves(open_panel, views):
    """§17.1.1 (review fix 1): a chart of the target requested from the panel (W4) is filed
    where the engine files it (`results.<slot>.step`: the exploration, it read the target), and
    the chat's anchor for it (`shown.anchor`, the engine's step) is a place of the page."""
    summary = copy.deepcopy(views['summary.choice'])
    rid = 'c' * 64
    summary['results']['eda.distribution:mpg'] = {'resultId': rid, 'current': True, 'staleReason': None,
                                                  'integrity': 'ok', 'channel': 'webview', 'step': 'train_eda'}
    panel = open_case(open_panel, views, case='choice', width=600, lang='en')
    panel.snapshot(summary)
    page = panel.page
    anchor = 'path:train_eda/eda.distribution:mpg'
    # the chat's line names that anchor; the panel goes there as a deep link does (NAV-1)
    panel.send({'type': 'navigate', 'anchor': anchor})
    page.wait_for_function("""a => !!document.querySelector(`[data-anchor="${CSS.escape(a)}"]`)""", arg=anchor)
    assert page.locator('[data-step="train_eda"]').locator(f'[data-anchor="{anchor}"]').count() == 1
    assert page.locator('[data-anchor="path:structural_eda/eda.distribution:mpg"]').count() == 0
    assert panel.clean()


def test_now12_the_question_is_in_the_first_viewport_at_every_width(open_panel, views):
    """NOW-12: Now's heading and question within the first 800 px below the sticky region, at
    320, 420 and 600 px, in both languages; no raw id or token in Now's prose."""
    for state in STATES:
        for width in (320, 420, 600):
            for lang in ('en', 'fr'):
                panel = open_case(open_panel, views, case=state, width=width, lang=lang, height=800)
                page = panel.page
                target = '[data-block="now"] h2' if state == 'done' else '[data-block="now"] h3.ht-question'
                bottom = page.locator(target).bounding_box()
                assert bottom['y'] + bottom['height'] <= 800, (state, width, lang, bottom)
                # Lot P (R41): a column name set as code (a data name, as in the per-column
                # quality view) is not prose; every other text of Now is.
                prose = page.evaluate("""() => { const n = document.querySelector('[data-block="now"]').cloneNode(true);
                  for (const c of n.querySelectorAll('code')) c.remove(); document.body.appendChild(n);
                  const t = n.innerText; n.remove(); return t; }""")
                assert not re.search(r'\b[0-9a-f]{12,64}\b|\bp_\d+\b|\b[a-z]+_[a-z0-9_]+\b', prose), (state, width, lang)
                panel.context.close()


def test_sample1_to_5_hon6_hon1_the_data_card_of_step_1(open_panel, views):
    """SAMPLE-1, SAMPLE-2, SAMPLE-3, SAMPLE-4, SAMPLE-5, HON-6, HON-1, NOW-1, NAR-2 (step 1):
    eight seeded rows, the row key then the target marked "to predict", in a focusable region
    that may scroll sideways; the counted look said under it, not folded (SAMPLE-2); the fold
    "Why a random draw" (SAMPLE-4); the special rows without the target in a fold; no
    final-test row; the frame line names a structural reading plus a counted preview. Below v2
    a line says where the card appears."""
    panel = open_case(open_panel, views, case='step1', width=420, lang='en')
    page = panel.page
    card = page.locator('[data-context="data_card"]')
    assert card.locator('[data-frame="structural"]').inner_text().startswith('Structural reading, plus a preview of eight rows')
    rows = card.locator('[data-sample] tbody tr')
    keys = [r.get_attribute('data-sample-row') for r in rows.all()]
    assert len(keys) == 8 and keys == sorted(keys, key=lambda k: int(k[1:])), 'eight rows, in row-key order'
    heads = card.locator('[data-sample] thead th').all_text_contents()
    assert heads[:2] == ['row', 'mpg ◂ to predict'], heads
    assert card.locator('[data-scroll-ok][role="region"][tabindex="0"][aria-label]').count() >= 1
    look = card.locator('[data-sample-look="counted"]')
    assert look.is_visible() and look.locator('xpath=ancestor::details').count() == 0
    assert 'these 8 values of mpg are seen now' in look.inner_text()
    # SAMPLE-4: why a random draw, and why it is a look, in a fold under the sample.
    why = card.locator('details', has=page.locator('summary', has_text='Why a random draw, and why it is a look'))
    assert why.count() == 1
    # SAMPLE-5: the rows are exactly the engine's development sample; the panel adds none.
    assert keys == [r['rowKey'] for r in views['data.p1']['rows']['items']]
    assert page.locator('[data-fold-id="special-rows"] [data-special-row]').count() == 0, 'a closed fold reads nothing'
    click_fold(page, 'special-rows')
    special = page.locator('[data-special-row]')
    assert special.count() == 6
    assert 'mpg' not in page.locator('[data-special-rows] thead').inner_text()
    assert page.locator('[data-block="now"] [data-limit="step1"]').inner_text().startswith('Nothing is measured yet')
    # The ledger line counts the preview (PATH-1, HON-6).
    assert 'one of them the preview' in page.locator('[data-ledger]').first.inner_text()
    for stage in ('v0', 'v1'):
        low = open_case(open_panel, views, case='step1', width=420, lang='en', stage=stage)
        assert low.page.locator('[data-sample]').count() == 0
        assert low.page.locator('[data-stage-line="v2"]').inner_text().startswith('The data card and the preview appear from stage v2')
    assert panel.clean()


def test_now4_now8_hon1_hon2_the_choice_card(open_panel, views, model, payload):
    """NOW-4, NOW-8, HON-1, HON-2, PATH-7, SINCE-3: at the model choice the card frames the
    development evidence, shows the comparison, and the criterion line reads the engine's bound
    and statuses, cited; a holdout split has no one-standard-error rule line; the chart asked
    from the panel is filed under Exploration and says so."""
    panel = open_case(open_panel, views, case='choice', width=600, lang='en')
    page = panel.page
    card = page.locator('[data-context="choice"]')
    assert card.locator('[data-frame="development"]').inner_text() == 'Development evidence · used to choose'
    assert card.locator('[data-comparison]').count() == 1
    line = card.locator('[data-criterion="configurations"]')
    text = line.inner_text()
    # R45 (lot P): the reference of a regression is "the reference (predict the mean)"; R48: the
    # words are the engine's (texts.en.criterion_words), fit to the development frame.
    assert 'Your criterion, validation error at least 10% below the reference (predict the mean) (9.24 mpg or better)' in text, text
    assert 'met by all 2 configurations' in text and 'judged for good on the final test' in text
    bound = line.locator('data[data-result-id]').first
    assert bound.get_attribute('data-path') == 'models.[fit.baseline].mae'
    # The engine assessed both configurations (a paired interval each): each reads its status.
    assert line.locator('[data-config="fit.variant"]').inner_text().endswith('· met')
    # NOW-8: a configuration the engine did not assess reads from `point_meets_bound` only.
    raw = copy.deepcopy(payload('captured/summary.regression.choice'))
    variant = next(c for c in raw['criterion_configurations']['configurations'] if c['slot'] == 'fit.variant')
    variant.update(gain=None, low=None, high=None, status='not_assessed')
    panel.snapshot(model('summary', raw))
    line = page.locator('[data-context="choice"] [data-criterion="configurations"]')
    assert line.locator('[data-config="fit.variant"]').inner_text().endswith('meets the bound on its average; no interval')
    panel.snapshot(views['summary.choice'])
    assert page.locator('text=one-standard-error').count() == 0, 'HON-2: no rule line without folds'
    assert page.locator('[data-options] [data-option]').all_inner_texts() == ['The linear model',
                                                                              'The variant · stronger regularisation',
                                                                              'The mean baseline']
    assert page.locator('[data-options-note]').inner_text() == 'From the simplest to the most flexible; the order is not a recommendation.'
    # PATH-7, SINCE-3: the W4 chart is under its step, marked as asked from this panel.
    click_fold(page, 'ph-evidence')
    click_fold(page, 'st-train_eda')
    fig = page.locator('[data-anchor="path:train_eda/eda.mean_by:model_year"]')
    # R50 (lot P): the figure is drawn inline in the opened step, no "See the figure" fold.
    panel.view_data('eda', views['eda.p1'])
    assert fig.locator('[data-from-panel]').inner_text() == 'Requested from this panel.'
    assert fig.locator('[data-eda-card="eda.mean_by:model_year"]').count() == 1
    assert panel.clean()


def test_now5_now13_todo1_to_3_hon4_the_reopened_preparation(open_panel, views, payload):
    """NOW-5, NOW-13, TODO-1 to TODO-3, HON-4: Now is the reopened preparation ("First:"); To
    handle is absent (nothing lies outside the step); the next step waits below Now, hatched,
    "Stale", with why, and no figure; the path marks the stale steps. Once a run is interrupted
    in the same study, the engine's next action is the interruption: Now says so, To handle
    holds the run (read only, a copy) and the stale deliverables, the path keeps the preparation
    to confirm again."""
    panel = open_case(open_panel, views, case='reopened', width=420, lang='en')
    page = panel.page
    assert page.locator('[data-block="now"] h2').text_content() == 'Now · First: Decide how the model prepares the variables'
    assert page.locator('[data-block="todo"]').count() == 0
    waiting = page.locator('[data-block="waiting"]')
    assert waiting.locator('h2').text_content() == 'Waiting · Fit a mean baseline and a linear model'
    assert waiting.locator('[data-stale="true"]').count() == 1
    assert 'preprocessing changed' in waiting.inner_text() and '§' not in waiting.inner_text()
    assert waiting.locator('data, svg, [data-result-id]').count() == 0, 'INV-7: no figure of a stale result'
    states = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('[data-step]')].map(n => [n.dataset.step, n.dataset.stepState]))")
    assert states['preprocessing'] == 'current' and states['models'] == 'stale' and states['model_variant'] == 'stale'
    count = views['summary.reopened']['defensibility']['count']
    assert page.locator('[data-pill="defensible"]').inner_text() == f'Not yet defensible · {count} points'
    assert panel.clean()
    panel.context.close()
    raw = payload('captured/summary.regression.interrupted')
    [stopped] = raw['executions']['suspected_interrupted']
    panel = open_case(open_panel, views, case='interrupted', width=420, lang='en')
    page = panel.page
    assert page.locator('[data-block="now"]').get_attribute('data-now') == 'execution'
    assert page.locator('[data-block="now"] h3.ht-question').count() == 0, 'nothing to answer but the interruption'
    todo = page.locator('[data-block="todo"]')
    assert todo.locator('h2').text_content() == 'To handle (2)'
    assert [x.get_attribute('data-anchor') for x in todo.locator('li').all()] == ['todo:execution', 'todo:deliverables']
    run = todo.locator('[data-todo="execution"]')
    assert 'its outcome is unknown' in run.inner_text() and 'this panel records nothing' in run.inner_text()
    assert run.locator('textarea, [data-write]').count() == 0, 'HE-1, HE-2: no words field, no rerun'
    eid = stopped['execution_id']
    assert run.locator(f'[data-ask-execution="{eid}"]').count() == 1
    report = raw['artifacts']['items']['report']['revision']
    assert todo.locator('[data-todo="deliverables"]').inner_text().splitlines()[1] == \
        f"They date from revision {report}; the study is at revision {raw['revision']}."
    assert page.locator('[data-step="preprocessing"][data-step-state="current"]').count() == 1
    assert panel.clean()


def test_now6_hon3_pg9_path6_the_review_of_the_automatic_mode(open_panel, views):
    """NOW-6, HON-3, PG-9, PATH-6, PG-7: the review asks to adopt or change the automatic decision,
    with no recommendation; "not by you"; the limit line of HON-3; the progress counts the review;
    the path tells six automatic decisions from three computations, none of them done."""
    panel = open_case(open_panel, views, case='review', width=420, lang='en')
    page = panel.page
    assert page.locator('[data-block="now"] h2').text_content() == 'Now · Review the automatic decisions'
    assert page.locator('[data-options] [data-option]').all_inner_texts() == [o['label'] for o in views['summary.review']['texts']['en']['options']] \
        == ['I adopt this decision', 'Change something', 'Explain first']
    assert page.locator('[data-options-note]').inner_text() == 'No recommendation.'
    assert page.locator('[data-context="review"] [data-frame="automatic"]').inner_text() == 'Chosen by the automatic mode, not by you.'
    assert page.locator('[data-limit="review"]').inner_text().startswith("The path's figures rest on decisions you have not adopted yet.")
    assert 'Review 1 of 7' in page.locator('[data-block="progress"]').inner_text()
    assert page.locator('[data-pill="automation"]').inner_text() == 'automatic mode ended'
    auto = page.locator('[data-step-state="auto"]')
    computed = page.locator('[data-step-state="computed"]')
    assert auto.count() == 6 and computed.count() == 3
    assert auto.locator('[data-badge="auto"]').count() == 6 and computed.locator('[data-badge="computed"]').count() == 3
    assert page.locator('[data-step-state="auto"] .ht-mk-done, [data-step-state="computed"] .ht-mk-done').count() == 0, 'no ✓'
    assert page.locator('[data-step="prediction_time"][aria-current="step"]').count() == 1
    assert panel.clean()


def test_now11_path9_ho3_the_end(open_panel, views, payload):
    """NOW-11, PATH-9, HO-3, HON-1: the end says what the study can claim, with the development
    and final columns, then "And after" with the engine's text and the copy, and the counts of
    the path; every phase is a closed "✓ ... steps done" fold; the ledger reads 1/1."""
    panel = open_case(open_panel, views, case='done', width=600, lang='en')
    page = panel.page
    now = page.locator('[data-block="now"]')
    assert now.locator('h2').text_content() == 'What the study can claim'
    # the conclusion in the junior's recorded words (`decisions.conclusion.value.text`)
    assert now.locator('[data-conclusion]').inner_text() == payload('captured/summary.regression.done')['decisions']['conclusion']['value']['text']
    heads = now.locator('[data-dev-final] thead th').all_text_contents()
    # R52 (lot P): one table, the development column says how it was measured.
    assert heads == ['Configuration', 'Development (out of fold, used to choose)', 'Final test (read once)']
    # HON-1: the final column cites the final evaluation the done summary names (the reads are
    # those of the end), each cell a registered value at its path; the development column
    # cites a development result, never the final one.
    from mlkit.study import cite
    done = payload('captured/summary.regression.done')
    final_rid = done['results']['final_test.evaluation']['result_id']
    evidence = payload('captured/evidence.regression.onepage.done')
    final_values = next(r for r in evidence['results'] if r['result_id'] == final_rid)['values']
    # R52 (lot P): every configuration has its row; the final test measured the chosen model and
    # the reference only, so the variant's final cell says it was not measured.
    assert now.locator('[data-dev-final] [data-not-measured="fit.variant"]').inner_text() == \
        'not measured: the final test measures only the chosen model'
    rows = now.locator('[data-dev-final] tbody tr:is([data-config="fit.linear"], [data-config="fit.baseline"])')
    assert rows.count() == 2, 'the chosen model and the reference'
    for i in range(rows.count()):
        final_cell = rows.nth(i).locator('td').nth(2).locator('data[data-result-id]')
        assert final_cell.count() == 1, f'row {i}: the final column is filled'
        assert final_cell.get_attribute('data-result-id') == final_rid
        path = final_cell.get_attribute('data-path')
        assert float(final_cell.get_attribute('data-value')) == cite.resolve(final_values, cite.parse_path(path)), path
        dev_cell = rows.nth(i).locator('td').nth(1).locator('data[data-result-id]')
        assert dev_cell.count() == 1 and dev_cell.get_attribute('data-result-id') != final_rid
    # NOW-8 at the end: the criterion judged on the final test cites the final test's own bound
    # and value (criterion_configurations.final_test), never the development bound.
    crit = done['criterion_configurations']
    line = now.locator('[data-criterion="final"]')
    cited = line.locator('data[data-result-id]')
    assert {cited.nth(i).get_attribute('data-result-id') for i in range(cited.count())} == {final_rid}
    assert [float(cited.nth(i).get_attribute('data-value')) for i in range(cited.count())] == \
        [crit['final_test']['bound']['value'], crit['final_test']['value']]
    assert crit['final_test']['bound']['value'] != crit['bound']['value']
    assert f"{crit['bound']['value']:.2f}" not in line.inner_text(), 'no development bound at the end'
    assert line.get_attribute('data-config-status') == crit['final_test']['status']
    assert now.locator('button:not([data-fold-id]), [data-write]').count() == 0, 'NOW-11: no control in the card'
    after = page.locator('[data-block="after"]')
    assert after.locator('[data-after-study]').inner_text().startswith('What comes next: the handoff pack')
    assert after.locator('[data-journey]').inner_text() == ('Your path: 13 steps, 9 decisions in your words, 11 looks at the target, '
                                                           'the final test opened once.')
    phases = page.locator('[data-phase]')
    assert phases.count() == 4 and page.locator('[data-phase-kind="done"]').count() == 4
    assert page.locator('[data-phase] details[open]').count() == 0
    assert 'final test 1/1 opening' in page.locator('[data-ledger-line]').inner_text()
    assert page.locator('[data-pill="seal"]').inner_text() == 'Final test opened · once'
    assert page.locator('[data-pill="defensible"]').inner_text() == 'Defensible · 2 limits'
    assert panel.clean()


@pytest.mark.parametrize('stage', ['v0', 'v1', 'v2', 'v3'])
def test_pg12_a_later_stage_is_absent_not_disabled(open_panel, views, stage):
    """PG-12, §3.2: on every state no element of a later stage is in the page, every fold opened;
    v0 has no figure and no "What your answer will change"."""
    later = {'v0': ['v1', 'v2', 'v3'], 'v1': ['v2', 'v3'], 'v2': ['v3'], 'v3': []}[stage]
    for state in STATES:
        panel = open_case(open_panel, views, case=state, width=420, lang='en', stage=stage)
        open_all(panel, views, panel.case_reads)
        for s in later:
            assert panel.page.locator(f'[data-stage="{s}"]').count() == 0, (state, stage, s)
        if stage == 'v0':
            assert panel.page.locator('[data-fold-id="effects"], [data-frame="development"], [data-sample]').count() == 0, state
        assert panel.clean(), state
        panel.context.close()


def test_inv12_the_regression_page_holds_no_decision_rule_word(open_panel, views):
    """INV-12: the whole page of every Auto MPG state, every fold and drawer opened, in both
    languages, holds none of the vocabulary of a decision rule."""
    for state in STATES:
        for lang in ('en', 'fr'):
            panel = open_case(open_panel, views, case=state, width=900, lang=lang)
            open_all(panel, views, panel.case_reads)
            text = panel.page.locator('#app').text_content()
            hit = FORBIDDEN.search(text)
            assert not hit, (state, lang, text[max(0, hit.start() - 60):hit.end() + 60])
            panel.context.close()


def test_hon9_an_older_engine_degrades_without_computing(open_panel, views, model, payload):
    """HON-9, HON-5, OP-2: on a summary without the P1 keys the pill is the neutral fallback, the
    ledger line says it appears with a newer engine, and no automation pill or criterion line is
    invented: the panel decides nothing about the study's standing in their place."""
    panel = open_case(open_panel, views, case='binary', width=420, lang='en')
    page = panel.page
    raw = copy.deepcopy(payload('captured/summary.binary'))
    for key in P1_KEYS:
        del raw[key]
    panel.snapshot(model('summary', raw))
    pill = page.locator('[data-pill="defensible"]')
    assert pill.get_attribute('data-defensibility') == 'fallback'
    assert pill.inner_text().startswith('What you cannot claim yet · ')
    assert page.locator('[data-ledger]').inner_text() == 'The ledger of this study appears with a newer engine.'
    assert page.locator('[data-pill="automation"]').count() == 0
    assert panel.clean()


def test_lang1_the_language_switch_is_ui_state_and_reads_nothing(open_panel, views):
    """LANG-1, NOW-2: the "more" menu's radio switches the page and the engine's texts at once,
    keeps the choice in setState and sends no message."""
    panel = open_case(open_panel, views, case='choice', width=420, lang='en')
    before = len(panel.posted())
    set_language(panel.page, 'fr')
    assert panel.posted()[before:] == []
    assert panel.state()['language'] == 'fr'
    # The engine's French question, byte for byte (NOW-1: the engine sets its own typography).
    question = views['summary.choice']['texts']['fr']['question']
    assert question == 'Quel modèle choisissez-vous, compte tenu des erreurs et de leurs intervalles\u202f?'
    assert panel.page.locator('[data-block="now"] h3.ht-question').text_content() == question
    assert panel.page.locator('html').get_attribute('lang') == 'fr'
