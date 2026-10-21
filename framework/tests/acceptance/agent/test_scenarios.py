"""Agent acceptance scenarios S1-S9 (plan WP0.7, WP4.3). Claude Code acceptance, not Copilot.

Skipped by default (conftest.py): each test launches real ``claude -p`` sessions against a
real Hypotrail study (cost, non-determinism). Opt in with ``HYPOTRAIL_AGENT_ACCEPTANCE=1``
and select with ``-m agent_acceptance -k S1-bank-en``. Raw runs go to
``$HYPOTRAIL_AGENT_RUNS`` (a directory outside the repository) or to pytest's temporary
directory. The driver and the checks are in ``scenarios.py``; a failed check is an
invariant violation to analyse in the transcript, never a flaky test to rerun until green.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

import scenarios as sc

SCENARIOS = sc.SCENARIOS


def _capabilities() -> set[str]:
    caps = {'hypotrail_cli'} if sc.graders.hypotrail_available() else set()
    if shutil.which('claude'):
        caps.add('claude_cli')
    return caps


def _params():
    d = SCENARIOS['defaults']
    for s in SCENARIOS['scenarios']:
        for case in s.get('cases', d['cases']):
            for lang in s.get('languages', d['languages']):
                yield pytest.param(s, case, lang, id=f"{s['id']}-{case}-{lang}")


@pytest.mark.agent_acceptance
@pytest.mark.parametrize('scenario,case,lang', list(_params()))
def test_scenario(scenario, case, lang, tmp_path):
    missing = set(scenario.get('requires', SCENARIOS['defaults']['requires'])) - _capabilities()
    if missing:
        pytest.skip(f"{scenario['id']} requires {', '.join(sorted(missing))}")
    base = Path(os.environ.get('HYPOTRAIL_AGENT_RUNS') or tmp_path)
    out = base / f"{scenario['id']}-{case}-{lang}"
    sc.run_scenario(scenario['id'], case, lang, out, workspace_base=base / 'workspaces')
    result = sc.grade(out)
    failed = {c['check']: {k: v for k, v in c.items() if k not in ('check', 'ok')}
              for c in result['checks'] if not c['ok']}
    assert not failed, json.dumps(failed, indent=1, default=str)[:4000]
