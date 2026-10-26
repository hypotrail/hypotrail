"""Journey check J-PANEL, panel part (owner session 2026-10-26, plan §5.3; R1b, R16, R11).

The engine's walkthrough (``framework/tests/study/test_journey_walkthrough.py``, ``walk``)
drives a study from ``init`` to ``done`` with the panel on at stage v3. After every write, the
panel's own reads (``status --summary --digest``, ``decisions``, ``evidence``, ``data``, with
``--json``) are taken and projected by the real panel models (``lib/models/*.js``, in Node);
the section that ``next_action.panel.shown`` names must hold at least one item in them: the
line never points at an empty section. This is not a VS Code session and not a Copilot
session.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'study'))

import test_journey_walkthrough as journey  # noqa: E402
from conftest import NODE  # noqa: E402
from mlkit.study import companion_env as ce  # noqa: E402

PROJECT = """
let s = '';
process.stdin.on('data', d => s += d).on('end', () => {
  const { toSummaryModel } = require('./lib/models/summary');
  const { toDecisionsModel } = require('./lib/models/decisions');
  const { toEvidenceModel } = require('./lib/models/evidence');
  const { toEdaModel } = require('./lib/models/eda');
  const { toDataModel } = require('./lib/models/data');
  const out = JSON.parse(s).map(r => ({ label: r.label, shown: r.shown,
    summary: toSummaryModel(r.summary), decisions: toDecisionsModel(r.decisions),
    evidence: toEvidenceModel(r.evidence), eda: toEdaModel(r.evidence), data: toDataModel(r.data) }));
  process.stdout.write(JSON.stringify(out));
});
"""


def _items(section: str, m: dict) -> int:
    """How many items the panel model shows in ``section`` (the J-PANEL count)."""
    ev, summary = m['evidence'], m['summary']
    if section == 'data_card':
        return sum(len(g['variables']) for g in m['data']['groups'])
    if section == 'quality':
        return sum(1 for c in m['eda']['cards'] if c['kind'] == 'quality' and c['current'])
    if section.startswith('eda.'):
        return sum(1 for c in m['eda']['cards'] if c['slot'] == section and c['current'])
    if section == 'waiting':
        return len(summary['proposals'])
    if section == 'choice':
        return len(summary['nextAction']['choiceOptions'])
    if section == 'holds':
        return len(summary['holds'])
    if section == 'history':
        return len(m['decisions']['history'])
    if section == 'mode':
        return 1 if summary['mode'] else 0
    if section == 'development':
        cv = ev['crossValidation']
        fits = cv['fits'] if cv else []
        split = [r for r in ev['results'] if r['slot'] == 'split' and r['current']]
        return len(fits) + len(split) + (1 if ev['variant'] else 0) + len(ev['variantCards'])
    if section == 'diagnostics':
        return sum(1 for d in ev['diagnostics'] if d['evidence'] == 'development')
    if section == 'final_test':
        final = ev['finalEvaluation']
        return (1 if final and final['current'] else 0) + sum(
            1 for d in ev['diagnostics'] if d['evidence'] == 'final')
    raise AssertionError(section)


@pytest.mark.parametrize('case, lang', [('synthetic', 'fr'), ('auto-mpg', 'en')])
def test_j_panel_the_named_section_shows_at_least_one_item(tmp_path, monkeypatch, case, lang):
    """J-PANEL: for every write of the walkthrough, the section ``panel.shown`` names is
    rendered by the panel model with at least one item (R1b), the choice card included
    (R16), and every compared variant has its card in the Evidence model (R11)."""
    if NODE is None:  # pragma: no cover
        pytest.skip('Node.js is not installed')
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    f, task, _ = journey.journey_flow(tmp_path, case, lang)
    reads, captures = [], []

    def read(*args):
        return f.call(*args, '--json', '--study', f.study)

    def on_write(label, payload):
        if label == 'run:predictor.capture':
            # Third session of 2026-10-26: the capture before the opening shows nothing in
            # the panel (``shown`` null, no panel line), as test_journey_walkthrough checks.
            assert payload['next_action']['panel']['shown'] is None
            captures.append(label)
            return
        reads.append({'label': label, 'shown': payload['next_action']['panel']['shown'],
                      'summary': read('status', '--summary', '--digest'),
                      'decisions': read('decisions'), 'evidence': read('evidence'),
                      'data': read('data')})

    journey.walk(f, task, on_write=on_write)
    assert len(captures) == 1, captures
    models = json.loads(subprocess.run([NODE, '-e', PROJECT], input=json.dumps(reads),
                                       capture_output=True, text=True, check=True, cwd=CLIENT,
                                       timeout=300).stdout)
    assert len(models) == len(reads) > 15
    empty = [(m['label'], m['shown']['section']) for m in models
             if _items(m['shown']['section'], m) < 1]
    assert empty == []
    last = models[-1]['evidence']
    fitted = [r['slot'] for r in last['results'] if r['current'] and r['promoted']
              and str(r['slot']).startswith('fit.variant')]
    assert [v['slot'] for v in last['variantCards']] == sorted(fitted)
