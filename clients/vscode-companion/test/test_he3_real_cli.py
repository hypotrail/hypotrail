"""HE-3 on the real CLI (review finding; COMPANION-ADVANCED §6.1.5, decision CR.1).

``he3_realcli.js`` walks a temporary Bank Marketing study to the fits, renders it, and
changes two copies behind the engine's back: one cited number of ``reports/study.html``
is edited (a stale citation), and the report is deleted. The real controller then reads
each copy after the junior's Refresh. Not a VS Code session; needs framework/.venv.

The cases on the engine's currency (review finding M4 of the engine: a deleted or edited
deliverable is not current, and ``summary.currency`` moves) run against the engine as it
is; the engine sends ``currency`` under ``status --summary --digest``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PYTHON = HERE.parents[2] / 'framework' / '.venv' / 'bin' / 'python'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None or not PYTHON.exists(), reason='needs Node.js and framework/.venv')


@pytest.fixture(scope='module')
def he3():
    out = subprocess.run([NODE, str(HERE / 'he3_realcli.js')], capture_output=True, text=True, timeout=600, cwd=HERE.parent)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


def engine_currency(he3):
    return he3['edited']['engineCurrency']


def test_he3_an_edited_cited_number_is_a_check_finding_after_refresh_with_a_working_open(he3):
    e = he3['edited']
    assert e['before']['clean'] is True, 'the rendered report checks clean first'
    assert e['detail']['from'] != e['detail']['to']
    assert 'value_mismatch' in e['after']['codes'], e['after']['codes']
    f = e['after']['finding']
    assert f['severity'] == 'error' and f['deliverable'] == 'report'
    assert e['detail']['to'] in f['message'], 'the engine message, verbatim, names the edited text'
    assert e['opened'] == [{'name': 'report', 'rel': 'reports/study.html', 'options': {}}], '"Open" opens the report'
    assert e['checkReads'] == 2, 'the Refresh read the checks again (same revision)'


def test_he3_an_edited_report_moves_the_engine_currency(he3):
    assert engine_currency(he3), 'the engine sends summary.currency'
    assert he3['edited']['after']['currencyMoved'] is True


def test_he3_a_deleted_report_is_not_current_and_regenerate_is_offered(he3):
    assert engine_currency(he3), 'the engine sends summary.currency'
    d = he3['deleted']
    assert d['before']['report'] == 'ok'
    assert d['after']['report'] != 'ok', 'a deleted report is not current'
    assert d['after']['regenerate'] is True
    assert d['after']['currencyMoved'] is True
    assert d['checkReads'] == 2
