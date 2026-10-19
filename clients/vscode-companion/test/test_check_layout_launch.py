"""The ``scripts/check_layout.py`` rule of the two Marimo launches (WP-A5; ADR 0004
amendment "local launch"), scope U: the real client sources pass; each way of widening the
launch (another file, another command, a shell string, typed text, a second call) fails.
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


def test_the_real_sources_pass(layout, sources):
    assert layout.companion_terminal_errors(sources) == []
    assert 'createTerminal(' in sources['extension.js'], 'the rule is exercised by the real call'


def test_check_layout_main_is_clean(layout, capsys):
    assert layout.main() is False
    assert '"errors": []' in capsys.readouterr().out


@pytest.mark.parametrize('change, message', [
    (lambda s: {**s, 'lib/controller.js': s['lib/controller.js'] + '\nvscode.window.createTerminal({ name: "x" });\n'},
     'outside extension.js'),
    (lambda s: {**s, 'extension.js': s['extension.js'] + '\nfunction more() { vscode.window.createTerminal({ name: "y" }); }\n'},
     'more than one terminal call'),
    (lambda s: {**s, 'extension.js': s['extension.js'].replace('terminal.show();\n  return false;',
                                                               "terminal.sendText('marimo run x');\n  terminal.show();\n  return false;")},
     'types into or builds a shell terminal'),
    (lambda s: {**s, 'extension.js': s['extension.js'].replace('shellPath: spec.argv[0],', "shellPath: '/bin/sh',")},
     'types into or builds a shell terminal'),
    (lambda s: {**s, 'extension.js': s['extension.js'].replace('launch.isMarimoLaunch(', 'Boolean(')},
     'without lib/launch.js accepting'),
    (lambda s: {**s, 'lib/launch.js': s['lib/launch.js'].replace(
        "workbench: Object.freeze({ path: 'notebooks/workbench.py', mode: 'edit' }),",
        "workbench: Object.freeze({ path: 'notebooks/workbench.py', mode: 'edit' }),\n"
        "  report: Object.freeze({ path: 'reports/study.html', mode: 'export' }),")},
     'launches other than marimo run'),
    (lambda s: {**s, 'lib/launch.js': s['lib/launch.js'].replace("mode: 'run' })", "mode: 'edit' })")},
     'launches other than marimo run'),
    (lambda s: {**s, 'lib/launch.js': s['lib/launch.js'].replace("tail[0] !== 'marimo'", "tail[0] === ''")},
     'does not require the marimo command'),
    (lambda s: {k: v for k, v in s.items() if k != 'lib/launch.js'}, 'has no lib/launch.js'),
])
def test_each_widening_is_refused(layout, sources, change, message):
    changed = change(sources)
    assert changed != sources, 'the change applies to the real source'
    errors = layout.companion_terminal_errors(changed)
    assert any(message in e for e in errors), errors


def test_child_process_and_exec_stay_forbidden(layout):
    for text in ["require('child_process').spawn('marimo')", 'childProcess.exec("marimo run x")', 'execSync("x")']:
        assert layout.COMPANION_FORBIDDEN.search(text), text
