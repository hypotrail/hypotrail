"""Journey check J-PANEL, panel part (owner session 2026-10-26, plan §5.3; R1b, R16, R11; the
one page, ADR 0004 d13, CLI-CONTRACT §17.1).

The engine's walkthrough (``framework/tests/study/test_journey_walkthrough.py``, ``walk``)
drives a study from ``init`` to ``done`` with the panel on at stage v3. After every write, the
panel's own read (``status --summary --digest --json``) is projected by the real panel models
(``lib/models/summary.js`` and ``lib/models/page.js``, in Node), with ``evidence`` for the
variant cards: the place ``next_action.panel.shown.anchor`` names must be one of the page's
anchors at that stage (the line never points at a place the page does not have), and Now is
never empty when it is named; ``where.anchor`` likewise. This is not a VS Code session and
not a Copilot session.
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
  const { toPageModel } = require('./lib/models/page');
  const { toEvidenceModel } = require('./lib/models/evidence');
  const out = JSON.parse(s).map(r => {
    const pm = toPageModel(toSummaryModel(r.summary), { stage: 'v3', lang: r.lang });
    return { label: r.label, shown: r.shown, where: r.where, anchors: pm.anchors, now: pm.now.kind,
      nowStep: pm.now.step, evidence: r.evidence ? toEvidenceModel(r.evidence) : null };
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def _missing(m: dict) -> list:
    """The anchors of the line that the page does not have (J-PANEL)."""
    out = []
    for key in ('shown', 'where'):
        place = m[key]
        if place is None:
            continue
        anchor = place['anchor']
        assert ce.ANCHOR_RE.fullmatch(anchor), (m['label'], key, anchor)
        if anchor not in m['anchors']:
            out.append((m['label'], key, anchor))
        if anchor == 'now' and not m['now']:
            out.append((m['label'], key, 'now (empty)'))
    return out


@pytest.mark.parametrize('case, lang', [('synthetic', 'fr'), ('auto-mpg', 'en')])
def test_j_panel_the_named_place_exists_on_the_page(tmp_path, monkeypatch, case, lang):
    """J-PANEL: for every write of the walkthrough, the anchor ``panel.shown`` names, and the
    one ``panel.where`` names, are anchors of the page model at stage v3 (R1b, CLI-CONTRACT
    §17.1), a choice shown in Now (R16); every compared variant has its card in the Evidence
    model (R11)."""
    if NODE is None:  # pragma: no cover
        pytest.skip('Node.js is not installed')
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    f, task, _ = journey.journey_flow(tmp_path, case, lang)
    reads, captures = [], []

    def read(*args):
        return f.call(*args, '--json', '--study', f.study)

    def on_write(label, payload):
        panel = payload['next_action']['panel']
        assert panel['version'] == ce.PANEL_CONTRACT and panel['stage'] == 'v3'
        if label == 'run:predictor.capture':
            # Third session of 2026-10-26: the capture before the opening shows nothing in
            # the panel (``shown`` null), as test_journey_walkthrough checks.
            assert panel['shown'] is None
            captures.append(label)
            return
        reads.append({'label': label, 'lang': lang, 'shown': panel['shown'], 'where': panel['where'],
                      'summary': read('status', '--summary', '--digest'), 'evidence': None})

    journey.walk(f, task, on_write=on_write)
    assert len(captures) == 1, captures
    reads[-1]['evidence'] = read('evidence')
    models = json.loads(subprocess.run([NODE, '-e', PROJECT], input=json.dumps(reads),
                                       capture_output=True, text=True, check=True, cwd=CLIENT,
                                       timeout=300).stdout)
    assert len(models) == len(reads) > 15
    assert sum(m['shown'] is not None for m in models) > 15
    missing = [x for m in models for x in _missing(m)]
    assert missing == []
    # A figure the engine names under a step is filed under that step by the page too.
    figures = [m['shown']['anchor'] for m in models if m['shown'] and '/' in m['shown']['anchor']]
    assert figures, 'the walkthrough names figures in the path'
    last = models[-1]['evidence']
    fitted = [r['slot'] for r in last['results'] if r['current'] and r['promoted']
              and str(r['slot']).startswith('fit.variant')]
    assert [v['slot'] for v in last['variantCards']] == sorted(fitted)
