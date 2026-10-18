"""The distribution of one column in the deliverables (CLI-CONTRACT-COMPANION §8, C8; WP-E3).

The HTML report and the generated notebook show ``eda.distribution:<column>`` with the
other training EDA results: a table of bins or groups, every number cited with its result
id, and ``check`` traces them (it is clean). Real cases: Bank (binary) and Auto MPG
(regression, whose report never uses the vocabulary of a decision rule). Studies live in
``tmp_path``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from mlkit.study import cmd_check, manifest as mf, notebook_view as nv, read

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flowkit as fk  # noqa: E402

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
BINARY_VOCABULARY = re.compile(r'threshold|positive class|precision|recall|capacity', re.I)


@pytest.fixture(scope='module')
def bank(tmp_path_factory):
    flow = fk.Flow(fk.prepare(fk.BANK, tmp_path_factory.mktemp('bank') / 'study', upto='split'),
                   fk.BANK, prefix='h')
    for column in ('age', 'pdays', 'job'):
        flow.run('eda.distribution', '--column', column)
    flow.call('render', '--study', flow.study)
    return flow


@pytest.fixture(scope='module')
def auto(tmp_path_factory):
    flow = fk.Flow(tmp_path_factory.mktemp('auto') / 'study', AUTO, prefix='m')
    flow.init()
    flow.pauses(split=False)
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.run('split')
    for column in ('mpg', 'model_year'):
        flow.run('eda.distribution', '--column', column)
    flow.call('render', '--study', flow.study)
    return flow


def _block(html: str, slot: str) -> str:
    start = html.index(f'<div data-slot="{slot}" data-state="current">')
    return html[start:html.index('</div></div>', start)]


def _cited(block: str) -> list[tuple[str, str]]:
    return re.findall(r'<data value="[^"]*" data-result-id="([0-9a-f]{64})" '
                      r'data-path="([^"]*)"', block)


def test_report_shows_bins_and_groups_with_cited_numbers(bank):
    html = (bank.study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')
    study = read.open(bank.study)
    for column, rows_path in (('age', 'numeric.bins'), ('pdays', 'numeric.bins'),
                              ('job', 'groups')):
        slot = f'eda.distribution:{column}'
        rid = study.state['current'][slot]
        block = _block(html, slot)
        assert 'Distribution of one column on training rows: ' + column in block
        cited = _cited(block)
        assert cited and {r for r, _ in cited} == {rid}
        values = study.result(rid)['output']['values']
        rows = values['numeric']['bins'] if rows_path == 'numeric.bins' else values['groups']
        paths = {p for _, p in cited}
        for i in range(len(rows)):
            assert f'{rows_path}.{i}.n_rows' in paths, (slot, i)
        assert f'id="r-{rid}"' in html
    pdays = _block(html, 'eda.distribution:pdays')
    assert 'special_values.0.n_rows' in {p for _, p in _cited(pdays)}
    assert 'step-train_eda' in html[:html.index('data-slot="eda.distribution:age"')]


def test_check_traces_the_distribution_numbers(bank, tmp_path):
    report = cmd_check.run_check(bank.study)
    assert report['clean'], report['findings']
    # a distribution number edited by hand in the report no longer traces
    copy = fk.clone(bank.study, tmp_path / 'edited')
    page = copy / mf.ARTIFACTS['report']
    html = page.read_text(encoding='utf-8')
    block = _block(html, 'eda.distribution:age')
    data = re.search(r'(<data [^>]*data-path="numeric\.bins\.1\.n_rows"[^>]*>)([^<]*)</data>',
                     block)
    edited = block.replace(data.group(0), f'{data.group(1)}{int(data.group(2)) + 1}</data>')
    page.write_text(html.replace(block, edited), encoding='utf-8')
    findings = cmd_check.run_check(copy)['findings']
    assert any('numeric.bins.1.n_rows' in str(f) for f in findings), findings


def test_generated_notebook_shows_the_distribution(bank):
    source = (bank.study / mf.ARTIFACTS['notebook']).read_text(encoding='utf-8')
    assert '"eda.distribution:age"' in source
    study = nv.open_study(bank.study)
    ids = {s: r for s, r in study.state['current'].items() if s.startswith('eda.distribution:')}
    html = nv.step_html(nv.citer(study, ids), ids, sorted(ids), '', '')
    for slot, rid in ids.items():
        assert f'data-result-id="{rid}"' in html, slot
    assert 'numeric.bins.9.n_rows' in html and 'groups.0.n_rows' in html


def test_regression_report_shows_the_distribution_without_binary_vocabulary(auto):
    html = (auto.study / mf.ARTIFACTS['report']).read_text(encoding='utf-8')
    for slot in ('eda.distribution:mpg', 'eda.distribution:model_year'):
        block = _block(html, slot)
        assert _cited(block)
        assert not BINARY_VOCABULARY.search(re.sub(r'<[^>]+>', ' ', block)), slot
    assert cmd_check.run_check(auto.study)['clean']
