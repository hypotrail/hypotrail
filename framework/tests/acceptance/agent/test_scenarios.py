"""Agent acceptance scenarios S1-S9 (plan WP0.7). Claude Code acceptance, not Copilot.

Skipped by default (conftest.py) and, until Phase 4, skipped because the `hypotrail` CLI
does not exist: every scenario declares ``requires: [hypotrail_cli]``. The scenario
driver (setup through the walkthrough, interruption, and the checks named in
scenarios.yaml) is to be completed in WP4.3 against the real CLI; until then the test
documents and validates the contract instead of pretending to run it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
SCENARIOS = yaml.safe_load((HERE / 'scenarios.yaml').read_text(encoding='utf-8'))


def _capabilities() -> set[str]:
    caps = set()
    if shutil.which('hypotrail'):
        caps.add('hypotrail_cli')
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
def test_scenario(scenario, case, lang):
    required = set(scenario.get('requires', SCENARIOS['defaults']['requires'])) | {'claude_cli'}
    missing = required - _capabilities()
    if missing:
        pytest.skip(f"{scenario['id']} requires {', '.join(sorted(missing))} (plan Phase 4)")
    pytest.fail(f"{scenario['id']}: scenario driver not implemented yet (WP4.3); the CLI now "
                f"exists, so implement the setup and checks before claiming acceptance")
