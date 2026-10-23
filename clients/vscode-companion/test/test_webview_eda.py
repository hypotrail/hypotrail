"""Browser tests of the EDA tab (scope S, simulated browser; COMPANION-ADVANCED §6.3, WP-U4).

The real document under the real CSP, offline, with the models of ``lib/models/eda.js`` built
from the WP-0 fixtures ``evidence.binary`` (Bank values) and ``evidence.regression`` (Auto MPG
values), in both colour schemes. Not a VS Code session: no extension host answers the
messages; the tests post the extension's messages themselves and read what the view posts.

Requirement map: ED-1 (the request posts only catalog activities and columns; the
controller side is in test/eda.test.js), ED-2 (banner counts), ED-3 (hatch and "small"),
ED-4 (every number cited, equal to the engine value, with the precision of
content/activities.yaml), ED-5 (no validation control), ED-6 and INV-12 (Auto MPG cards and
vocabulary), INV-7 (stale cards without figures), INV-8 (refusals), INV-9/§12 (no inline
style, no CSP violation, no remote request).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from conftest import inline_styles_ok
import yaml

from mlkit.study import cite

ROOT = Path(__file__).resolve().parents[3]
ACTIVITIES_YAML = ROOT / 'framework' / 'mlkit' / 'study' / 'content' / 'activities.yaml'
FORBIDDEN = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|calling rule|decision rule|selected)\b', re.I)
BINARY_WORDS = re.compile(r'\b(outcome|positive|imbalance|base rate)\b', re.I)
SUMMARY = {'binary': 'summary.binary', 'regression': 'summary.regression'}
EVIDENCE = {'binary': 'evidence.binary', 'regression': 'evidence.regression'}
ORDER = {
    # WP-A7: the single-feature signal (leakage detector) follows the special values; the
    # quality check of the development rows sits with the data card, outside the gallery.
    'binary': ['eda.target_rate', 'eda.special_values', 'eda.single_feature_signal', 'eda.rate_by:job', 'eda.distribution:age'],
    'regression': ['eda.target_summary', 'eda.special_values', 'eda.single_feature_signal', 'eda.mean_by:model_year',
                   'eda.distribution:model_year'],
}
NON_CAUSAL = {
    'binary': 'This describes who had the outcome in the training sample. It does not say that {c} causes it, '
              'nor how future cases will go.',
    'regression': 'This describes the target in the training sample. It does not say that {c} causes it, '
                  'nor how future cases will go.',
}


def open_eda(open_panel, model, task='binary', scheme='light', eda=None, reviewer=False):
    panel = open_panel(color_scheme=scheme)
    panel.init(stage='v2', task=task, reviewer=reviewer)
    panel.snapshot(model('summary', SUMMARY[task]))
    panel.page.locator('[role="tab"][data-tab="eda"]').click()
    assert {'v': 2, 'type': 'load', 'view': 'eda'} in panel.posted(), 'the tab asks for its data view'
    eda_model = eda if eda is not None else model('eda', EVIDENCE[task])
    panel.view_data('eda', eda_model)
    return panel, eda_model


def _values_by_rid(payload):
    return {r['result_id']: r for r in payload['results']}


def _yaml_formats():
    """{activity: {path_or_key: fmt}} from content/activities.yaml (both tasks)."""
    doc = yaml.safe_load(ACTIVITIES_YAML.read_text(encoding='utf-8'))
    out = {}
    for section in ('activities', 'regression_activities'):
        for activity, spec in (doc.get(section) or {}).items():
            if not activity.startswith('eda.'):
                continue
            table = out.setdefault(activity, {})
            for h in spec.get('highlights') or []:
                table[h['path']] = h['fmt']
            for t in spec.get('tables') or []:
                for col in t['columns']:
                    if 'fmt' in col:
                        table[f"{t['rows']}.*.{col['key']}"] = col['fmt']
    return out


def _expected_format(formats, model_fmt, activity, path):
    """The YAML precision of a value path (a list index is a table row); the model's table
    for an activity the YAML does not describe yet (eda.distribution, WP-E3)."""
    table = formats.get(activity)
    if table is None:
        return None
    if path in table:
        return table[path]
    parts = path.split('.')
    if len(parts) == 3 and parts[1].isdigit():
        return table.get(f'{parts[0]}.*.{parts[2]}')
    return None


@pytest.mark.parametrize('scheme', ['light', 'dark'])
@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_gallery_shows_the_registered_eda_results_in_order(open_panel, model, task, scheme):
    panel, eda = open_eda(open_panel, model, task, scheme)
    page = panel.page
    slots = page.locator('[data-eda-card]').evaluate_all('cs => cs.map(c => c.dataset.edaCard)')
    assert slots == ORDER[task]
    assert [c['slot'] for c in eda['cards'] if c['kind'] != 'quality'] == ORDER[task]
    # Each card names its activity and result id in its faint source line (v0.3, WP-E2: six
    # characters, never in the prose); the source line opens Evidence.
    gallery = [item for item in eda['cards'] if item['kind'] != 'quality']
    for card in eda['cards']:
        hook = "data-quality-card" if card["kind"] == "quality" else "data-eda-card"
        if card['kind'] != 'quality':
            details = page.locator(f'[{hook}="{card["slot"]}"] details.eda-analysis')
            is_open = details.get_attribute('open')
            assert is_open == ('' if card['slot'] == gallery[-1]['slot'] else None)
            if is_open is None:
                details.locator(':scope > summary').click()
        chip = page.locator(f'[{hook}="{card["slot"]}"] [data-chip]')
        assert chip.get_attribute('data-chip') == card['resultId']
        assert card['resultId'][:6] in chip.inner_text()
        assert card['activity'] in chip.inner_text()
    assert page.locator('#panel-eda [data-placeholder]').count() == 0
    assert inline_styles_ok(page), 'no inline style attribute (CSP)'
    # v0.3 (WP-E2): the charts are HTML grids (and SVG for the box plot), each an image with a name.
    assert page.locator('#panel-eda [role="img"][aria-label]').count() >= 3
    assert panel.clean(), (panel.requests, panel.errors, panel.csp, panel.violations())


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed4_every_number_is_the_engine_value_cited_with_its_result_and_precision(open_panel, model, payload, node, task):
    panel, eda = open_eda(open_panel, model, task)
    results = _values_by_rid(payload(EVIDENCE[task]))
    formats = _yaml_formats()
    model_fmt = json.loads(node("process.stdout.write(JSON.stringify(require('./lib/models/eda').FMT))"))
    cited = panel.page.locator('#panel-eda [data-eda-card] [data-result-id]').evaluate_all(
        """ns => ns.map(n => ({card: n.closest('[data-eda-card]').dataset.edaCard,
              rid: n.dataset.resultId, path: n.dataset.path, value: n.dataset.value,
              text: n.textContent, svg: n.namespaceURI.endsWith('svg')}))""")
    assert len(cited) > 40
    slots = {c['slot']: c for c in eda['cards']}
    seen_cards = set()
    for c in cited:
        card = slots[c['card']]
        assert c['rid'] == card['resultId'], c
        entry = results[c['rid']]
        value = cite.resolve(entry['values'], cite.parse_path(c['path']))
        assert float(c['value']) == value, c
        fmt = _expected_format(formats, model_fmt, entry['activity'], c['path'])
        if fmt is None:
            leaf = c['path'].split('.')[-1]
            fmt = model_fmt[entry['activity']][leaf]
        shown = cite.fmt_number(value, fmt)
        # A bar's text and its values-table cell carry the denominator after the number.
        assert c['text'] == shown or c['text'].startswith(shown + ' '), (c, fmt)
        seen_cards.add(c['card'])
    assert seen_cards == set(ORDER[task]), 'every card cites its numbers'
    # A rate or a mean is shown with its denominator (the rows of its group).
    bar = 'eda.rate_by:job' if task == 'binary' else 'eda.mean_by:model_year'
    texts = panel.page.locator(f'[data-eda-card="{bar}"] .ht-val data[data-result-id]').evaluate_all('ns => ns.map(n => n.textContent)')
    # WP-A7, v0.3 (WP-E2): the confidence interval follows the value; n follows the group's label.
    assert texts and all(re.match(r'^\S+ · \S+–\S+$', t) for t in texts), texts
    labels = panel.page.locator(f'[data-eda-card="{bar}"] [data-bar] .ht-lab').all_text_contents()
    assert labels and all(re.search(r' n [\d,]+$', t) for t in labels), labels


def test_model_formats_follow_activities_yaml(node):
    formats = _yaml_formats()
    model_fmt = json.loads(node("process.stdout.write(JSON.stringify(require('./lib/models/eda').FMT))"))
    checked = 0
    for activity, table in formats.items():
        for path, fmt in table.items():
            leaf = path.split('.')[-1]
            if leaf in model_fmt[activity]:
                assert model_fmt[activity][leaf] == fmt, (activity, path)
                checked += 1
    assert checked >= 20


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed3_small_groups_are_hatched_and_say_small(open_panel, model, payload, task):
    panel, _ = open_eda(open_panel, model, task)
    page = panel.page
    results = _values_by_rid(payload(EVIDENCE[task]))
    for entry in results.values():
        if not entry['activity'] in ('eda.rate_by', 'eda.mean_by', 'eda.distribution') or not entry['values'].get('groups'):
            continue
        card = page.locator(f'[data-eda-card="{entry["slot"]}"]')
        small = [g['value'] for g in entry['values']['groups'] if g['small_count']]
        assert small, entry['slot']
        bars = card.locator('[data-bar][data-small="true"]')
        assert bars.count() == len(small), entry['slot']
        for i in range(bars.count()):
            # WP-A7: the group's own mark, not the shuffled-outcome band behind it. v0.3 (WP-E2): a
            # hatched bar (distribution) or a hollow point (rate or mean by group), in HTML.
            mark = bars.nth(i).locator('[data-hatched="true"]')
            assert mark.count() == 1
            assert 'ht-hatch' in mark.get_attribute('class') or mark.get_attribute('data-point') is not None
            assert '(small)' in bars.nth(i).locator('.ht-lab').text_content()
        caption = card.locator('[data-hatch-caption]').text_content()
        assert f"fewer than {entry['values']['min_group_rows']} rows" in caption
        # Not colour only: the values table says "small" too.
        assert card.locator('table td', has_text=re.compile(r'^small$')).count() >= len(small)
    assert panel.clean()


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_every_by_column_card_has_the_fixed_non_causal_caption(open_panel, model, task):
    panel, eda = open_eda(open_panel, model, task)
    by = [c for c in eda['cards'] if c['kind'] in ('rate_by', 'mean_by')]
    assert by
    for card in by:
        node = panel.page.locator(f'[data-eda-card="{card["slot"]}"] [data-noncausal]')
        # v0.3 (WP-E2): the caveats are under the card's "Why?" (closed): read their text.
        assert node.text_content() == NON_CAUSAL[task].format(c=card['column'])
        assert node.evaluate('n => n.closest("details.ht-why") !== null')
        warnings = panel.page.locator(f'[data-eda-card="{card["slot"]}"] [data-warnings] li').all_text_contents()
        assert warnings == card['data']['warnings'], 'engine warnings verbatim'
        assert panel.page.locator(f'[data-eda-card="{card["slot"]}"] [data-note]').text_content() == card['data']['note']


def test_ed6_regression_cards_and_no_decision_rule_or_binary_vocabulary(open_panel, model):
    panel, _ = open_eda(open_panel, model, 'regression')
    page = panel.page
    assert page.locator('[data-eda-card="eda.target_summary"] svg.ht-boxplot').count() == 1
    assert page.locator('[data-eda-card="eda.mean_by:model_year"] [data-chart="intervals"]').count() == 1
    text = page.locator('#panel-eda').text_content()  # v0.3: also the closed "Why?" texts
    assert not FORBIDDEN.search(text), FORBIDDEN.search(text).group(0)
    # The panel's own copy has no binary vocabulary; engine texts (notes, warnings,
    # table cells of meanings and labels) are task-aware already and shown verbatim.
    own = page.evaluate("""() => {
      const panel = document.getElementById('panel-eda').cloneNode(true);
      // WP-A7: a card's title is the engine's question (engine text, shown as it is).
      for (const n of panel.querySelectorAll('[data-note], [data-warnings], td, [data-question]')) n.remove();
      return panel.textContent;
    }""")
    assert not BINARY_WORDS.search(own), BINARY_WORDS.search(own).group(0)
    assert 'Target distribution' in text and 'Target mean by value' in text
    # The whole page (frame included) holds none of the INV-12 words.
    body = page.locator('body').inner_text()
    assert not FORBIDDEN.search(body), FORBIDDEN.search(body).group(0)
    assert panel.clean()


def test_binary_target_card_introduces_the_term_first(open_panel, model):
    panel, eda = open_eda(open_panel, model, 'binary')
    card = panel.page.locator('[data-eda-card="eda.target_rate"]')
    card.locator('details.eda-analysis > summary').click()
    term = card.locator('[data-term]')
    assert term.get_attribute('data-term') == 'class_imbalance'
    assert term.inner_text() == 'Class imbalance: one value of the target is much rarer.'
    assert term.locator('strong').inner_text() == 'Class imbalance'
    # A rate of 0.2 or more and 0.8 or less is a base rate, not an imbalance.
    balanced = copy.deepcopy(eda)
    balanced['cards'][0]['data']['imbalanced'] = False
    panel.view_data('eda', balanced)
    card.locator('details.eda-analysis > summary').click()
    assert term.inner_text() == 'Base rate: how often the outcome occurs in the training rows.'


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_ed2_banner_counts_training_rows_and_zero_validation(open_panel, model, payload, task):
    panel, _ = open_eda(open_panel, model, task)
    p = payload(EVIDENCE[task])
    ledger = {(r['purpose'], r['partition']): r['rows'] for r in p['exposure']['ledger']}
    page = panel.page
    train = page.locator('[data-rows-seen="train"]')
    assert train.get_attribute('data-value') == str(ledger[('train_eda', 'train')])
    assert train.text_content() == cite.fmt_number(ledger[('train_eda', 'train')], 'int')
    assert page.locator('[data-rows-seen="validation"]').text_content() == '0'
    models = page.locator('[data-rows-seen="validation-models"]')
    assert models.get_attribute('data-value') == str(p['exposure']['summary']['validation_rows_used_for_selection'])
    # v0.3 (WP-E2): one sentence, the counts and the reasons under "Why all of them?".
    banner = page.locator('.eda-banner').text_content()
    assert banner.startswith('Training rows only.')
    assert 'Every chart is a registered result, computed by the engine.' in banner
    seen = page.locator('[data-rows-scope="split"]')
    assert seen.text_content() == (f"Rows seen in EDA: {cite.fmt_number(ledger[('train_eda', 'train')], 'int')} "
                                 'training rows · 0 validation rows.')
    assert 'ht-mono' not in (seen.get_attribute('class') or ''), 'prose, not monospace (R26)'


def test_ed2_cross_validation_counts_the_development_rows_read_never_train_0(open_panel, model, payload):
    """WP-E1 (R26): under cross-validation EDA reads the development rows; there is no
    validation partition, so the banner names neither "train 0" nor unexplored validation rows."""
    raw = payload('captured/evidence.binary.cv')
    rows = next(r['rows'] for r in raw['exposure']['ledger'] if r['purpose'] == 'train_eda')
    panel, _ = open_eda(open_panel, model, 'binary', eda=model('eda', 'captured/evidence.binary.cv'))
    page = panel.page
    seen = page.locator('[data-rows-scope="development"]')
    assert seen.text_content() == f"Rows seen in EDA: {cite.fmt_number(rows, 'int')} development rows."
    assert page.locator('[data-rows-seen="development"]').get_attribute('data-value') == str(rows)
    assert page.locator('[data-rows-seen="train"], [data-rows-seen="validation"]').count() == 0
    banner = page.locator('.eda-banner').text_content()
    assert banner.startswith('Development rows only.')
    assert 'Development rows used to compare and choose, out of fold:' in banner
    text = page.locator('#panel-eda').inner_text()
    assert 'train 0' not in text and 'validation rows stay unexplored' not in text
    assert 'Validation rows are never used here' not in text
    assert page.locator('.eda-section-title').text_content() == 'Exploration of the development rows'
    assert panel.clean()


def test_the_quality_ranges_drop_meaningless_cells(open_panel, model, payload):
    """WP-E1 (R26): no "0 / 0" and no "no declared range" cell in the ranges table."""
    raw = copy.deepcopy(payload('evidence.binary'))
    quality = next(r for r in raw['results'] if r.get('slot') == 'eda.quality')
    ranges = quality['values']['ranges']
    assert ranges, 'the fixture has numeric ranges'
    for r in ranges:
        r['declared'] = None
    panel, _ = open_eda(open_panel, model, 'binary', eda=model('eda', raw))
    table = panel.page.locator('[data-quality-card="eda.quality"] table')
    # v0.3 (WP-E2): the ranges table sits in a closed disclosure: read its text.
    heads = table.locator('th').all_text_contents()
    assert 'Outside the declared range' not in heads, heads
    text = table.text_content()
    assert '0 / 0' not in text and 'no declared range' not in text
    # A column that declares a range reads "none" when nothing is outside it.
    ranges[0].update({'declared': {'min': 0, 'max': 200}, 'n_below': 0, 'n_above': 0})
    panel.view_data('eda', model('eda', raw))
    heads = table.locator('th').all_text_contents()
    assert heads[-1] == 'Outside the declared range'
    first = table.locator('tbody tr').first.locator('td').last
    assert first.text_content() == 'none'
    assert '0 / 0' not in table.text_content() and 'no declared range' not in table.text_content()
    assert panel.clean()


def test_request_lists_only_catalog_columns_and_posts_w4(open_panel, model, payload):
    panel, eda = open_eda(open_panel, model, 'binary')
    page = panel.page
    catalog = [a for a in payload('evidence.binary')['eda_catalog']['activities'] if a['per_column'] and a['runnable']]
    names = []
    for a in catalog:
        for c in a['columns']:
            if c['name'] not in [n for n, _ in names]:
                names.append((c['name'], c['role']))
    options = page.locator('#eda-variable option').evaluate_all('os => os.map(o => [o.value, o.textContent])')
    assert options == [[n, f'{n} ({r})'] for n, r in names]
    # age: a current distribution exists, so the button shows it instead of running again.
    assert page.locator('#eda-chart option').all_inner_texts() == ['Distribution', 'Outcome rate by value']
    show = page.locator('#eda-show')
    assert show.inner_text() == 'Show it' and show.get_attribute('data-write') is None
    before = len(panel.posted())
    show.click()
    assert len(panel.posted()) == before, '"Show it" does not rerun'
    assert page.evaluate('document.activeElement.closest("[data-eda-card]").dataset.edaCard') == 'eda.distribution:age'
    # The target y accepts a distribution only.
    page.locator('#eda-variable').select_option('y')
    assert page.locator('#eda-chart option').all_inner_texts() == ['Distribution']
    page.locator('#eda-variable').select_option('balance')
    page.locator('#eda-chart').select_option('eda.rate_by')
    run = page.locator('#eda-run')
    assert run.inner_text() == 'Run on training rows' and run.get_attribute('data-write') == 'run_eda'
    run.click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'run_eda', 'activity': 'eda.rate_by', 'column': 'balance',
                                  'revision': eda['revision']}
    # ED-5: no control names validation as a partition choice.
    controls = page.locator('#panel-eda').locator('select, option, button, input, label').all_inner_texts()
    assert not any('validation' in t.lower() for t in controls), controls
    assert page.locator('#panel-eda input[type="radio"], #panel-eda [data-partition]').count() == 0
    # Free exploration: the workbench.
    page.locator('[data-open="workbench"]').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'open_artifact', 'artifact': 'workbench'}
    assert 'For free exploration, use your workbench notebook' in page.locator('[data-hint]').text_content()
    assert panel.clean()


def test_regression_request_offers_target_mean_and_distribution(open_panel, model):
    panel, eda = open_eda(open_panel, model, 'regression')
    page = panel.page
    page.locator('#eda-variable').select_option('weight')
    assert page.locator('#eda-chart option').all_inner_texts() == ['Distribution', 'Target mean by value']
    page.locator('#eda-chart').select_option('eda.mean_by')
    page.locator('#eda-run').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'run_eda', 'activity': 'eda.mean_by', 'column': 'weight',
                                  'revision': eda['revision']}
    page.locator('#eda-variable').select_option('mpg')
    assert page.locator('#eda-chart option').all_inner_texts() == ['Distribution']


def test_busy_refusal_and_not_promoted_outcomes_show_in_the_request_card(open_panel, model, payload):
    panel, _ = open_eda(open_panel, model, 'binary')
    page = panel.page
    page.locator('#eda-variable').select_option('balance')
    panel.send({'type': 'busy', 'busy': True, 'op': 'W4', 'target': 'eda.distribution:balance'})
    run = page.locator('#eda-run')
    assert run.is_disabled() and run.get_attribute('aria-busy') == 'true' and run.inner_text() == 'Working...'
    panel.send({'type': 'busy', 'busy': False, 'op': 'W4', 'target': 'eda.distribution:balance'})
    engine = payload('error.stale_revision')['error']
    panel.send({'type': 'outcome', 'op': 'W4', 'kind': 'refused', 'target': 'eda.distribution:balance', 'exitCode': 2,
                'refusal': {'code': engine['code'], 'reason': engine.get('reason'), 'engineMessage': engine['message'],
                            'human': 'The study changed since you read it. Nothing was recorded.', 'details': []}})
    region = page.locator('.eda-request [data-outcome="refused"]')
    assert region.get_attribute('role') == 'alert'
    assert region.get_attribute('data-code') == engine['code']
    assert region.locator('[data-engine-message]').inner_text() == engine['message']
    assert page.locator('#outcome [data-outcome]').count() == 0, 'the view renders its own W4 outcome'
    panel.send({'type': 'outcome', 'op': 'W4', 'kind': 'not_promoted', 'target': 'eda.distribution:age',
                'message': 'The result was computed but not used: the study changed while it ran. Nothing in the study changed.'})
    assert 'computed but not used' in page.locator('.eda-request [data-outcome="not_promoted"]').inner_text()
    panel.send({'type': 'outcome', 'op': 'W4', 'kind': 'ok', 'target': 'eda.distribution:balance', 'revision': 28,
                'recorded': {'slot': 'eda.distribution:balance', 'status': 'promoted'}, 'artifacts': []})
    ok = page.locator('.eda-request [data-eda-outcome="ok"]')
    assert 'Ran on training rows.' in ok.inner_text() and 'Recorded: eda.distribution:balance (promoted).' in ok.inner_text()


def test_reviewer_mode_has_no_run_control(open_panel, model):
    panel, _ = open_eda(open_panel, model, 'binary', reviewer=True)
    page = panel.page
    assert page.locator('#panel-eda [data-write]').count() == 0
    page.locator('#eda-variable').select_option('balance')
    assert page.locator('#eda-run').count() == 0
    page.locator('#eda-variable').select_option('age')
    assert page.locator('#eda-show').count() == 1, 'navigation stays'
    assert page.locator('[data-open="workbench"]').count() == 1


def test_stale_card_is_listed_without_figures(open_panel, model, payload):
    p = copy.deepcopy(payload('evidence.binary'))
    for r in p['results']:
        if r['slot'] == 'eda.rate_by:job':
            r.update(current=False, stale_reason='upstream_changed', values=None, headline=None)
    panel, _ = open_eda(open_panel, model, 'binary', eda=model('eda', p))
    card = panel.page.locator('[data-eda-card="eda.rate_by:job"]')
    card.locator('details.eda-analysis > summary').click()
    assert card.get_attribute('data-current') == 'false'
    assert card.locator('[data-stale]').inner_text() == 'Stale · not cited'
    assert card.locator('[data-result-id]').count() == 0
    assert card.locator('svg').count() == 0
    assert not re.search(r'\d', card.locator('h3').inner_text() + card.locator('[data-stale]').inner_text())
    # The request does not offer "Show it" for a stale result.
    page = panel.page
    page.locator('#eda-variable').select_option('job')
    page.locator('#eda-chart').select_option('eda.rate_by')
    assert page.locator('#eda-run').count() == 1


def test_empty_and_not_runnable_states(open_panel, model, payload):
    p = copy.deepcopy(payload('evidence.binary'))
    p['results'] = [r for r in p['results'] if not r['activity'].startswith('eda.')]
    panel, _ = open_eda(open_panel, model, 'binary', eda=model('eda', p))
    page = panel.page
    assert page.locator('[data-eda-empty]').inner_text() == 'No exploration yet. EDA runs after the split is confirmed.'
    assert page.locator('[data-eda-card]').count() == 0
    assert page.locator('#eda-run').count() == 1, 'the catalog is offered when it is runnable'
    for a in p['eda_catalog']['activities']:
        a['runnable'] = False
        a['missing'] = [{'requirement': 'result_current', 'slot': 'split', 'detail': 'Split the data before exploring or fitting it.'}]
    panel.view_data('eda', model('eda', p))
    assert page.locator('[data-not-runnable]').inner_text() == 'Not available yet: Split the data before exploring or fitting it.'
    assert page.locator('#eda-run, #eda-variable').count() == 0


def test_loading_error_and_updating_states(open_panel, model):
    panel = open_panel()
    panel.init(stage='v2', task='binary')
    snap = model('summary', 'summary.binary')
    panel.snapshot(snap)
    page = panel.page
    page.locator('[role="tab"][data-tab="eda"]').click()
    assert page.locator('[data-eda-loading]').get_attribute('aria-busy') == 'true'
    panel.send({'type': 'load_error', 'view': 'eda', 'message': 'integrity_error: the state failed its check.', 'detail': ''})
    alert = page.locator('[data-eda-error]')
    assert alert.get_attribute('role') == 'alert' and 'integrity_error' in alert.inner_text()
    alert.get_by_role('button', name='Retry').click()
    assert panel.posted()[-1] == {'v': 2, 'type': 'load', 'view': 'eda'}
    eda = model('eda', 'evidence.binary')
    panel.view_data('eda', eda, revision=snap['revision'] - 1)
    assert page.locator('[data-updating]').inner_text() == 'Updating...'


def test_chip_opens_the_result_in_evidence(open_panel, model):
    panel, eda = open_eda(open_panel, model, 'binary')
    page = panel.page
    card = page.locator('[data-eda-card="eda.rate_by:job"]')
    card.locator('details.eda-analysis > summary').click()
    card.locator('[data-chip]').click()
    assert page.locator('[role="tab"][aria-selected="true"]').get_attribute('data-tab') == 'evidence'


def test_learning_layer_adds_the_explain_example_and_definition_when_already_read(open_panel, model):
    """The cards use an `explain` model the Learn tab has read; they never request it (§5)."""
    rid = 'a' * 64
    terms = {'base_rate': {'term': 'Base rate', 'definition': 'How often the outcome occurs.',
                           'example': [{'text': 'Here '}, {'text': '11.5%', 'resultId': rid, 'path': 'rate', 'value': 0.1154}]}}
    panel, _ = open_eda(open_panel, model, 'binary')
    page = panel.page
    assert page.locator('[data-example]').count() == 0
    assert not any(m.get('view') == 'explain' for m in panel.posted())
    panel.view_data('explain', {'terms': terms, 'steps': [], 'predictions': []}, revision=26)
    example = page.locator('[data-example="base_rate"]')
    assert example.text_content() == 'Here 11.5%'
    assert example.locator('data').get_attribute('data-result-id') == rid
    panel.init(stage='v2', task='binary', learningLayer=False)
    assert page.locator('[data-example]').count() == 0

    reg, _ = open_eda(open_panel, model, 'regression')
    reg.view_data('explain', {'terms': {'target_distribution': {'term': 'Target distribution',
                  'definition': 'How the target values spread.', 'example': None}}, 'steps': [], 'predictions': []}, revision=22)
    assert reg.page.locator('[data-term="target_distribution"]').text_content() == 'Target distribution: How the target values spread.'


def test_cr7_a_feature_not_available_at_prediction_time_is_labelled_and_still_runs_on_training_rows(open_panel, model, payload):
    # Decision CR.7 (review finding): the availability decision says `duration` is not
    # available at prediction time. The engine's catalog still lists it (EDA describes the
    # training rows); the panel says so next to the name, and still lets the junior run it.
    ev = copy.deepcopy(payload('evidence.binary'))
    for a in ev['eda_catalog']['activities']:
        if a['activity'] in ('eda.rate_by', 'eda.distribution'):
            a['columns'].append({'name': 'duration', 'role': 'feature', 'type': 'numeric', 'slot': None, 'result_id': None})
    panel, _ = open_eda(open_panel, model, 'binary', eda=model('eda', ev))
    page = panel.page
    options = dict(page.locator('#eda-variable option').evaluate_all('os => os.map(o => [o.value, o.textContent])'))
    assert options['duration'] == 'duration (feature, not available at prediction time)'
    assert options['age'] == 'age (feature)'
    assert page.locator('[data-not-at-prediction]').count() == 0
    page.locator('#eda-variable').select_option('duration')
    hint = page.locator('[data-not-at-prediction]')
    assert hint.inner_text() == ('duration is not available at prediction time (your availability decision), so the models '
                                 'do not use it. The chart describes the training rows only.')
    assert page.locator('#eda-run').is_enabled(), 'still runnable, on training rows'
    page.locator('#eda-run').click()
    assert panel.posted()[-1]['type'] == 'run_eda' and panel.posted()[-1]['column'] == 'duration'
    assert panel.clean()
    # Regression: an uncertain, excluded feature is not "not available"; nothing is added.
    reg, _ = open_eda(open_panel, model, 'regression')
    texts = reg.page.locator('#eda-variable option').evaluate_all('os => os.map(o => o.textContent)')
    assert not any('prediction time' in t for t in texts)
