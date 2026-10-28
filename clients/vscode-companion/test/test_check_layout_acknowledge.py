"""The ``scripts/check_layout.py`` rule of owner decision R31 (2026-10-27; ADR 0004 amendment),
scope U: the panel takes no words of the junior and never acknowledges an interrupted
execution. The real client sources build no ``run --acknowledge-interruption`` and keep no
acknowledgement builder; each way of bringing one back (an argv array, a command string, a
builder, in any source file) fails. The acknowledgement is made in the chat.
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


def test_the_real_sources_build_no_acknowledgement(layout, sources):
    assert layout.companion_acknowledge_errors(sources) == []
    assert 'W6' not in sources['lib/cli.js'].split('const WRITES')[1].split('});')[0]


@pytest.mark.parametrize('snippet', [
    "return [...agent.argv, 'run', '--acknowledge-interruption', eid, `--user-words=${words}`];",
    'const argv = [...a, "run", "--acknowledge-interruption", id];',
    'function acknowledgeArgv(agent, { executionId, words }) { return []; }',
    'const W6 = acknowledgeInterruptionArgv;',
    "// runs hypotrail run --acknowledge-interruption from the panel",
])
def test_bringing_back_an_acknowledgement_fails(layout, sources, snippet):
    changed = {**sources, 'lib/handlers/overview.js': sources['lib/handlers/overview.js'] + '\n' + snippet + '\n'}
    errors = layout.companion_acknowledge_errors(changed)
    assert errors == ['Companion client source builds a withdrawn acknowledgement write (W6): lib/handlers/overview.js']


def test_the_words_of_the_copy_pass(layout, sources):
    # Saying, in the copy, that an interruption is acknowledged in the chat is no write.
    changed = {**sources, 'media/copy/overview.js': sources['media/copy/overview.js']
               + "\n// The acknowledgement of an interrupted run is made in the chat; nothing is recorded here.\n"}
    assert layout.companion_acknowledge_errors(changed) == []
