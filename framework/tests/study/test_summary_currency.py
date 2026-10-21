"""Review fix H1: ``currency`` of ``status --summary --digest`` (CLI-CONTRACT-COMPANION §1.5).

A short hex digest of what a client shows that can change without a new revision: the
case and dataset bytes, the deliverables' effective statuses and file hashes, the alerts,
and the registry's current set. It changes when the dataset is edited, after a render
that changes a deliverable, and when a deliverable is edited or deleted; it is equal
otherwise (repeated reads, the junior's workbench, Marimo's restamp of the notebook).
Without ``--digest`` the summary has no ``currency`` (its golden is byte-for-byte frozen).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import currency, read, view

REPORT = 'reports/study.html'
NOTEBOOK = 'notebooks/study_generated.py'


def _study(root: Path, case_dir: Path) -> fk.Flow:
    """A binary study whose three pauses are confirmed and split run; every commit rendered it."""
    flow = fk.Flow(root / 'study', case_dir, prefix='c')
    flow.init()
    flow.pauses()
    flow.run('split')
    return flow


@pytest.fixture(scope='module')
def rendered(tmp_path_factory, synthetic_case_dir):
    case = fk.clone(synthetic_case_dir, tmp_path_factory.mktemp('h1-case') / 'case')
    return _study(tmp_path_factory.mktemp('h1'), case)


@pytest.fixture
def flow(rendered, tmp_path):
    return fk.Flow(fk.clone(rendered.study, tmp_path / 'study'), rendered.case_dir, prefix='d')


def _currency(flow):
    code, p = cc.run('status', '--summary', '--digest', '--study', flow.study)
    assert code == 0, p
    assert tuple(p) == cc.DIGEST_SUMMARY_KEYS
    assert re.fullmatch(r'[0-9a-f]{%d}' % cc.CURRENCY_HEX, p['currency']), p['currency']
    return p['currency']


def test_constants_and_no_currency_without_digest(flow):
    assert view.CURRENCY_HEX == cc.CURRENCY_HEX
    assert view.CURRENCY_INPUT_KEYS == cc.CURRENCY_INPUT_KEYS
    code, p = cc.run('status', '--summary', '--study', flow.study)
    assert code == 0 and 'currency' not in p and tuple(p) == cc.SUMMARY_KEYS
    study = read.open(flow.study)
    inputs = view.currency_inputs(study, view.build(study))
    assert tuple(inputs) == cc.CURRENCY_INPUT_KEYS
    assert str(flow.study) not in repr(inputs)                  # no absolute path


def test_equal_when_nothing_changes(flow):
    first = _currency(flow)
    assert all(_currency(flow) == first for _ in range(3))
    (flow.study / 'notebooks/workbench.py').write_text('# my own experiment\n')
    assert _currency(flow) == first                              # the junior's free space
    nb = flow.study / NOTEBOOK
    nb.write_bytes(currency.GENERATED_WITH.sub(b'__generated_with = "9.9.9"', nb.read_bytes()))
    assert _currency(flow) == first                              # a Marimo restamp


def test_equal_for_equal_content_in_another_folder(flow, rendered):
    assert _currency(flow) == _currency(rendered)


def test_changes_when_the_dataset_is_edited(tmp_path, synthetic_case_dir):
    """On its own study and its own copy of the case: the edit touches no shared fixture."""
    flow = _study(tmp_path, fk.clone(synthetic_case_dir, tmp_path / 'case'))
    before = _currency(flow)
    data = read.open(flow.study).state['dataset']['path']
    path = Path(data)
    lines = path.read_text(encoding='utf-8').split('\n')
    lines[3] = re.sub(r'\d', lambda m: str((int(m.group()) + 1) % 10), lines[3], count=1)
    path.write_text('\n'.join(lines), encoding='utf-8')
    edited = _currency(flow)
    assert edited != before
    lines[3] = re.sub(r'\d', lambda m: str((int(m.group()) + 1) % 10), lines[3], count=1)
    path.write_text('\n'.join(lines), encoding='utf-8')
    assert _currency(flow) not in (before, edited)               # a second edit, a new value


@pytest.mark.parametrize('change', ['delete', 'edit'])
def test_changes_when_a_deliverable_changes_and_after_render(flow, change):
    before = _currency(flow)
    for rel in (REPORT, NOTEBOOK):
        path = flow.study / rel
        if change == 'delete':
            path.unlink()
        else:
            path.write_bytes(path.read_bytes() + b'\n')
        changed = _currency(flow)
        assert changed != before, rel
        code, p = cc.run('render', '--study', flow.study)
        assert code == 0, p
        after = _currency(flow)
        assert after != changed, rel
        assert after == before, rel                              # the same bytes again


def test_changes_when_a_render_changes_a_status(flow, monkeypatch):
    before = _currency(flow)
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    cc.run('render', '--study', flow.study)
    failed = _currency(flow)
    assert failed != before
    monkeypatch.delenv('HYPOTRAIL_FAULT')
    code, p = cc.run('render', '--study', flow.study)
    assert code == 0, p
    assert _currency(flow) == before                             # current again, same bytes


def test_changes_with_a_new_revision(flow):
    before = _currency(flow)
    flow.run('eda.target_rate')
    assert _currency(flow) != before


def test_the_contract_document_names_the_inputs():
    doc = (fk.REPO / 'docs/specs/CLI-CONTRACT-COMPANION.md').read_text(encoding='utf-8')
    section = doc.split('### 1.5 `currency`', 1)[1].split('\n## ', 1)[0]
    for key in (*cc.CURRENCY_INPUT_KEYS, 'view.CURRENCY_HEX', 'view.currency_inputs',
                'view.CURRENCY_INPUT_KEYS', 'currency.file_fingerprint'):
        assert f'`{key}`' in section, key
    assert f'({cc.CURRENCY_HEX})' in section
    assert '`task`, and (review fix H1) `currency`' in doc
