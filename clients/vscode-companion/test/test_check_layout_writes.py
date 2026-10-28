"""The ``scripts/check_layout.py`` write whitelist of ADR 0004 decision 14 (owner request R49,
2026-10-28), scope U: the panel's writes are exactly W4, W5, W7 and W8; W8 is the Azure ML
export with ``--out``, outside the study state, and never ``--plan`` (the plan is a read); only
``lib/cli.js`` builds an ``export azureml`` argv; no client source starts an Azure job. Each
way of widening the whitelist fails.
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


def test_the_real_sources_keep_the_whitelist(layout, sources):
    assert layout.companion_write_errors(sources) == []
    assert layout.COMPANION_WRITES == ('W4', 'W5', 'W7', 'W8')


def test_a_fifth_write_fails(layout, sources):
    cli = sources['lib/cli.js'].replace('W8: exportAzuremlArgv,', 'W8: exportAzuremlArgv, W9: renderArgv,')
    assert cli != sources['lib/cli.js']
    errors = layout.companion_write_errors({**sources, 'lib/cli.js': cli})
    assert errors == ['Companion client lib/cli.js WRITES is not exactly W4, W5, W7, W8: W4, W5, W7, W8, W9']


def test_w8_with_plan_fails(layout, sources):
    cli = sources['lib/cli.js'].replace("'export', 'azureml', `--out=${out}`,", "'export', 'azureml', `--out=${out}`, '--plan',")
    assert cli != sources['lib/cli.js']
    assert layout.companion_write_errors({**sources, 'lib/cli.js': cli}) == [
        'Companion client lib/cli.js W8 must write with --out and never carry --plan']


@pytest.mark.parametrize('snippet, error', [
    ("return [...agent.argv, 'export', 'azureml', '--out=/x'];",
     'Companion client source builds an export azureml argv outside lib/cli.js: lib/handlers/after.js'),
    ("const argv = ['az', 'ml', 'job', 'create', '--file', 'job.yml'];",
     'Companion client source starts an Azure job or calls the Azure CLI: lib/handlers/after.js'),
    ('// then run az ml job create from here',
     'Companion client source starts an Azure job or calls the Azure CLI: lib/handlers/after.js'),
])
def test_bringing_azure_outside_w8_fails(layout, sources, snippet, error):
    changed = {**sources, 'lib/handlers/after.js': sources['lib/handlers/after.js'] + '\n' + snippet + '\n'}
    assert layout.companion_write_errors(changed) == [error]
