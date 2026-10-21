"""v0.3 WP-J: the HTML report draws what the study panel draws (R17, R28).

* the distribution of a skewed column shows its exact zeros as their own bar and its
  positive values on logarithmic bins, every edge and count cited;
* the predictor correlation matrix shows one cell per pair in the engine's order, the
  flagged pairs outlined and listed with their cited value;
* ``check`` traces every number of the report (it stays clean).

Bank Marketing (committed, only read); the study lives in ``tmp_path``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from mlkit.study import read

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flowkit as fk  # noqa: E402


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    flow = fk.Flow(fk.prepare(fk.BANK, tmp_path_factory.mktemp('bank') / 'study', upto='split'),
                   fk.BANK, prefix='j')
    flow.run('eda.distribution', '--column', 'previous')
    flow.run('eda.correlation')
    flow.call('render', '--study', flow.study)
    html = (flow.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    return flow, html


def _figure(html: str, chart: str) -> str:
    start = html.index(f'<figure data-chart="{chart}">')
    return html[start:html.index('</figure>', start)]


def test_a_skewed_distribution_shows_its_zeros_apart_on_log_bins(bank):
    flow, html = bank
    values = read.open(flow.study).current('eda.distribution:previous')['output']['values']
    numeric = values['numeric']
    assert numeric['skewed'] and numeric['zeros']['n_rows'] > 0
    fig = _figure(html, 'distribution:previous')
    assert 'Exactly zero' in fig and 'Exact zeros, apart' in fig
    assert 'data-path="numeric.zeros.n_rows"' in fig
    for i in range(len(numeric['log_bins'])):
        for key in ('low', 'high', 'n_rows'):
            assert f'data-path="numeric.log_bins.{i}.{key}"' in fig, (i, key)
    assert 'logarithmic scale' in fig


def test_the_correlation_matrix_outlines_and_lists_the_flagged_pairs(bank):
    flow, html = bank
    values = read.open(flow.study).current('eda.correlation')['output']['values']
    fig = _figure(html, 'correlation')
    k = len(values['order'])
    assert fig.count('<rect class="b"') == k                      # the diagonal
    measured = sum(1 for p in values['pairs'] if p['value'] is not None)
    assert len(re.findall(r'<rect class="c(?:pos|neg)', fig)) == 2 * measured
    flagged = [p for p in values['pairs'] if p['flag']]
    assert len(re.findall(r'class="c(?:pos|neg) cflag"', fig)) == 2 * len(flagged)
    if flagged:
        assert 'Pairs at or above' in fig
    else:
        assert 'No pair reaches' in fig
    assert 'data-path="level"' in fig


def test_check_traces_every_number_of_the_report(bank):
    flow, _ = bank
    out = flow.call('check', '--study', flow.study)
    assert out['findings'] == [], out['findings']


def test_a_french_report_gives_the_glossary_definitions_in_french(tmp_path, bank):
    from mlkit.study import texts
    _, english = bank
    flow = fk.Flow(tmp_path / 'study', fk.BANK, prefix='f')
    flow.call('init', '--case', fk.BANK, '--lang', 'fr', '--study', flow.study)
    flow.pauses(split=False)
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.run('split')
    flow.call('render', '--study', flow.study)
    html = (flow.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    with texts.task_context('binary'), texts.scheme_context(texts.CROSS_VALIDATION):
        entry = texts.glossary('development_rows')
    # The cross-validation variant of the term, in French, marked as French.
    fr = entry['definition_fr']
    assert 'découper en plis' in fr
    assert f'<p lang="fr"><strong class="term">{entry["term_fr"]}.</strong> ' in html
    assert entry['definition'] not in html
    assert 'lang="fr"' not in english
    assert flow.call('check', '--study', flow.study)['findings'] == []


def test_every_definition_the_report_shows_has_a_french_translation():
    """The report's terms (steps, activities, diagnostics, statuses), in every variant a
    study can have (task, cross-validation), carry ``definition_fr``."""
    import re as _re
    from mlkit.study import texts
    root = Path(texts.__file__).parent
    ids = set()
    for name in ('render_html.py', 'render_diagnostics.py'):
        ids |= set(_re.findall(r'_concept\("([a-z_]+)"\)', (root / name).read_text()))
    for spec in (texts.load('activities'), texts.load('steps')):
        ids |= set(_re.findall(r"'(?:glossary|concept)': '([a-z_]+)'", repr(spec)))
    ids |= {'documented_fact', 'scenario_assumption'}
    for task in ('binary', 'regression'):
        for scheme in (texts.VALIDATION, texts.CROSS_VALIDATION):
            with texts.task_context(task), texts.scheme_context(scheme):
                terms = texts.glossary_terms()
                missing = sorted(i for i in ids if i in terms
                                 and not terms[i].get('definition_fr'))
            assert missing == [], (task, scheme, missing)
