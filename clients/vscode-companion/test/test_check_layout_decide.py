"""The ``scripts/check_layout.py`` rule of the v0.3 narrowing (WP-E1; ADR 0004 decision 8,
owner decision R23, integrator decision I2), scope U: the real client sources invoke no
``decide confirm``, ``decide withdraw``, or ``decide propose``; each way of bringing one
back (an argv array, a command string, in any source file) fails.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / 'clients' / 'vscode-companion'


@pytest.fixture(scope='module')
def layout():
    spec = importlib.util.spec_from_file_location('check_layout', ROOT / 'scripts' / 'check_layout.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def sources():
    return {p.relative_to(CLIENT).as_posix(): p.read_text(encoding='utf-8')
            for p in CLIENT.rglob('*.js') if 'test' not in p.relative_to(CLIENT).parts}


def test_the_real_sources_invoke_no_decide_write(layout, sources):
    assert layout.companion_decide_errors(sources) == []
    assert "'decide'" not in sources['lib/cli.js']


@pytest.mark.parametrize('snippet', [
    "return [...agent.argv, 'decide', 'confirm', pid, ...tail(agent)];",
    'const argv = [...a, "decide", "withdraw", pid];',
    "args.push(`decide`, `propose`, decisionId);",
    "const command = 'decide confirm';",
    "// runs decide propose from the panel",
])
def test_bringing_back_a_decide_write_fails(layout, sources, snippet):
    changed = {**sources, 'lib/handlers/decisions.js': sources['lib/handlers/decisions.js'] + '\n' + snippet + '\n'}
    errors = layout.companion_decide_errors(changed)
    assert errors == ['Companion client source invokes a withdrawn decide write (W1-W3): lib/handlers/decisions.js']


def test_other_decide_words_pass(layout, sources):
    changed = {**sources, 'lib/models/effects.js': sources['lib/models/effects.js']
               + "\n// The engine's dry run of a confirmation; the junior decides in the chat.\n"}
    assert layout.companion_decide_errors(changed) == []
