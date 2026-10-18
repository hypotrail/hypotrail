"""HTML report renderer (plan WP3.1, §6; ADR 0001 decision 2)."""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from mlkit.study import cite, render_html, texts, view
from mlkit.study.errors import StudyError

import phase3_study as fx


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def all(self, tag):
        return [a for t, a in self.tags if t == tag]


def parse(page: str) -> Tags:
    p = Tags()
    p.feed(page)
    return p


@pytest.fixture
def full_view(full_study):
    return view.build(full_study)


def test_report_is_deterministic_and_cites_only_current_results(full_view):
    page, consumed = render_html.build(full_view)
    again, _ = render_html.build(full_view)
    assert page == again
    current = {r['result_id'] for r in full_view['results'].values() if r['current']}
    data = parse(page).all('data')
    assert len(data) > 50
    assert all(d.get('data-result-id') in current and d.get('data-path') and 'value' in d
               and d.get('title', '').startswith('result ') for d in data)
    assert set(consumed) == {d['data-result-id'] for d in data} == current


def test_every_cited_value_equals_the_registry_value(full_view):
    page, _ = render_html.build(full_view)
    by_id = {r['result_id']: r for r in full_view['results'].values()}
    for m in re.finditer(r'<data value="([^"]+)" data-result-id="([0-9a-f]+)" data-path="([^"]+)"'
                         r'[^>]*>([^<]+)</data>', page):
        raw, rid, path, shown = m.groups()
        item = by_id[rid]
        value = cite.resolve(item['values'], cite.parse_path(path.replace('&quot;', '"')),
                             n_rows=item['n_rows'])
        assert float(raw) == float(value)
        assert cite.shown_matches(cite.parse_numbers(shown)[0], value), (shown, value)


def test_no_fake_decision_controls_and_offline(full_view):
    page, _ = render_html.build(full_view)
    tags = parse(page)
    buttons = tags.all('button')
    assert len(buttons) == 1 and 'data-theme-toggle' in buttons[0]
    for forbidden in ('input', 'form', 'select', 'textarea', 'option', 'iframe', 'link', 'img',
                      'object', 'embed'):
        assert tags.all(forbidden) == [], forbidden
    assert not re.search(r'(src|href)\s*=\s*"(https?:)?//', page)
    assert not re.search(r'url\(\s*["\']?(https?:)?//', page)
    assert 'https://' not in page and 'http://' not in page
    assert render_html.BANNER_START + render_html.BANNER_END in page


def test_decisions_facts_and_assumptions_have_distinct_text_labels(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models')
    b.apply('decide.propose', {'decision_id': 'policy', 'value': 'capacity:20',
                               'restatement': 'Call the 20 highest-scored members.',
                               'rationale': 'Desk capacity.'})
    v = view.build(b.study)
    page, _ = render_html.build(v, variables=[{'name': 'holds_open', 'role': 'feature',
                                               'availability': {'value': 'unknown',
                                                                'status': 'unknown',
                                                                'source': 'x'}}])
    labels = texts.report()
    for text in (labels['decision_status']['confirmed'], labels['decision_status']['proposed'],
                 labels['decision_status']['open'], labels['fact_status']['documented_fact'],
                 labels['fact_status']['scenario_assumption'], labels['proposal_waiting']):
        assert text in page, text
    words = v['decisions']['prediction_time']['confirmation']['user_words']
    assert f'<q data-literal="user_words">{words}' in page.replace('&#x27;', "'")
    assert labels['not_authenticated'] in page
    assert 'data-decision="policy" data-status="proposed"' in page
    assert 'data-decision="conclusion" data-status="open"' in page
    # facts keep their status; nothing in the case is shown as a decision
    assert 'data-status="scenario_assumption"' in page
    assert 'data-status="documented_fact"' in page


def test_not_yet_defensible_lists_every_view_item(full_view):
    page, _ = render_html.build(full_view)
    ids = [x['id'] for x in full_view['not_yet_defensible']]
    assert 'uncertain_features_included' in ids and 'no_causality' in ids
    for nid in ids:
        assert f'data-nyd="{nid}"' in page
    assert fx.UNCERTAIN_INCLUDED in page.split('id="not-yet-defensible"')[1]


def test_policy_comparison_has_intervals_ties_paired_and_adopted_rule(full_view):
    page, _ = render_html.build(full_view)
    section = page.split('id="policy"')[1].split('id="not-yet-defensible"')[0]
    labels = texts.report()
    assert 'data-rule="capacity:20" data-model="fit.logistic"' in section
    assert 'data-rule="threshold:0.3" data-model="fit.logistic"' in section
    assert labels['adopted'] in section and labels['tied_yes'] in section
    assert labels['tied_none'] in section and labels['policy_note'] in section
    assert 'rules.capacity:20.intervals.[fit.logistic].precision.low' in section
    assert 'rules.capacity:20.deltas.[fit.logistic].precision.point' in section
    assert 'rules.capacity:20.models.[fit.baseline].cut.fraction_selected' in section


def test_steps_without_results_say_not_executed_yet(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='split')
    page, consumed = render_html.build(view.build(b.study))
    pending = texts.load('steps')['pending']
    for slot in ('eda.target_rate', 'fit.logistic', 'policy.evaluation'):
        block = page.split(f'data-slot="{slot}" data-state="pending"')
        assert len(block) == 2 and pending in block[1][:300], slot
    assert len(consumed) == 1                       # only the split result is cited


def test_stale_results_are_shown_but_never_cited(full_study):
    v = view.build(full_study)
    stale_rid = v['results']['fit.logistic']['result_id']
    v['results']['fit.logistic']['current'] = False
    v['results']['fit.logistic']['stale_reason'] = {'reason': 'split changed', 'since': 99}
    page, consumed = render_html.build(v)
    assert stale_rid not in consumed
    assert f'data-result-id="{stale_rid}"' not in page
    assert 'data-slot="fit.logistic" data-state="stale"' in page


def test_an_untraceable_number_is_refused():
    citer = cite.Citer({'a' * 64: cite.Cited('a' * 64, 'x', {'rate': 0.5, 'label': 'z'}, 10,
                                             True, 'ok'),
                        'b' * 64: cite.Cited('b' * 64, 'y', {'rate': 0.4}, 10, False, 'ok')})
    assert 'data-result-id="' + 'a' * 64 in citer.num('a' * 64, 'rate', 'pct1')
    for rid, path in (('0' * 64, 'rate'), ('a' * 64, 'missing'), ('a' * 64, 'label'),
                      ('b' * 64, 'rate')):
        with pytest.raises(StudyError) as err:
            citer.num(rid, path)
        assert err.value.code == 'untraceable_number'
    for template in ('{{slot:none:rate}}', '{{r:' + '0' * 64 + '.rate}}', '{{slot:x:rate|bogus}}'):
        with pytest.raises(StudyError) as err:
            citer.expand(template)
        assert err.value.code == 'untraceable_number'
    assert citer.expand('Rate {{slot:x:rate|pct0}} <b>') .endswith('&lt;b&gt;')


def test_unknown_number_in_a_content_template_fails_the_render(full_view, monkeypatch):
    steps = texts.load('steps')
    bad = dict(steps['steps']['split'], context='Rows: {{r:' + 'f' * 64 + '.rows|int}}.')
    monkeypatch.setitem(steps['steps'], 'split', bad)
    with pytest.raises(StudyError) as err:
        render_html.build(full_view)
    assert err.value.code == 'untraceable_number'


def test_paths_formats_and_number_parsing():
    assert cite.parse_path('rules.capacity:20.models.[fit.logistic].precision') == [
        'rules', 'capacity:20', 'models', 'fit.logistic', 'precision']
    assert cite.format_path(['rules', 'capacity:20', 'models', 'fit.logistic', 'x']) == \
        'rules.capacity:20.models.[fit.logistic].x'
    assert cite.resolve({'rules': [{'rule': 'k:1', 'v': 3}]}, ['rules', 'k:1', 'v']) == 3
    assert cite.fmt_number(3164, 'int') == '3,164'
    assert cite.fmt_number(0.11534, 'pct1') == '11.5%'
    toks = cite.parse_numbers('3,164 rows; 11.5 %; 0,115; pct1 x_2 3f9a 1357')
    assert [(t.value, t.decimals, t.percent) for t in toks] == [
        (3164.0, 0, False), (11.5, 1, True), (0.115, 3, False), (1357.0, 0, False)]
    assert cite.shown_matches(cite.parse_numbers('11.5%')[0], 0.11534)
    assert not cite.shown_matches(cite.parse_numbers('11.6%')[0], 0.11534)


def test_teaching_texts_are_data_without_digits():
    for name in texts.CONTENT_FILES:
        data = texts.load(name)
        assert data['schema'].startswith(f'hypotrail.content.{name}/')
    import yaml
    from importlib import resources
    for name in texts.CONTENT_FILES:
        raw = (resources.files('mlkit.study') / 'content' / f'{name}.yaml').read_text()
        prose = [line for line in raw.splitlines() if not line.lstrip().startswith('#')
                 and 'schema:' not in line]
        loaded = yaml.safe_load(raw)
        for line in prose:
            stripped = re.sub(r'\{\{[^}]*\}\}', '', line)
            stripped = re.sub(r'\b(pct\d|f\d)\b', '', stripped)
            assert not re.search(r'(?<![\w.])\d', stripped), (name, line)
        assert loaded
    steps = texts.load('steps')['steps']
    from mlkit.study import state as st
    assert set(steps) == set(st.STEP_IDS)
    for s in steps.values():
        assert texts.glossary(s['concept']), s['concept']
    for slot, spec in texts.load('activities')['activities'].items():
        assert texts.glossary(spec['glossary']), slot


def test_a_delegated_decision_is_shown_as_delegated(tmp_path, synthetic_case_dir):
    """D1: the report, the notebook and the view show a delegation distinctly from the
    junior's own decision, and the check still finds nothing to report."""
    from mlkit.study import cmd_check, cmd_render, notebook_view, read

    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='prediction_time')
    words = 'Use your recommended default and tell me what you assumed.'
    out = b.decide('feature_availability',
                   {f: 'available_at_prediction' for f in fx.features_of(synthetic_case_dir)},
                   'My recommended default: every variable is known at expiry.', words,
                   basis='delegated_default')
    assert out.exit_code == 0, out.payload
    cmd_render.render_all(b.study)
    v = view.build(b.study)
    assert v['decisions']['feature_availability']['confirmation']['basis'] == 'delegated_default'
    assert v['decisions']['prediction_time']['confirmation']['basis'] == 'explicit'
    page = (b.study / 'reports' / 'study.html').read_text()
    article = page[page.index('data-decision="feature_availability"'):]
    article = article[:article.index('</article>')]
    import html as h
    labels = {k: h.escape(v) for k, v in texts.report().items() if isinstance(v, str)}
    assert 'data-basis="delegated_default"' in article and labels['delegated'] in article
    assert labels['delegated_note'] in article
    explicit = page[page.index('data-decision="prediction_time"'):]
    assert 'data-basis="explicit"' in explicit[:explicit.index('</article>')]
    assert 'data-nyd="delegated_decisions"' in page
    html = notebook_view.decision_html(read.open(b.study), 'feature_availability')
    assert labels['delegated_words'] in html and 'data-basis="delegated_default"' in html
    assert labels['user_words'] in notebook_view.decision_html(read.open(b.study),
                                                               'prediction_time')
    errors = [f for f in cmd_check.run_check(b.study)['findings'] if f['severity'] == 'error']
    assert errors == []
