"""A test plan must never turn missing evidence into success."""
import json
import sys
from pathlib import Path

import pytest

from mlkit import quality


@pytest.fixture
def project(tmp_path):
    policy = {'context_paths': ['test-policy.json', 'ticket.json', 'src'], 'suites': [
        {'id': 'unit', 'title': 'Contract', 'changes': ['model', 'refactor'], 'phases': ['pr', 'release'],
         'command': ['{python}', '-c', 'print("ok")']},
        {'id': 'cloud', 'title': 'Recette cloud', 'changes': ['deployment'], 'phases': ['release'],
         'command': None, 'unavailable': 'Authorized acceptance testing required'}]}
    (tmp_path / 'test-policy.json').write_text(json.dumps(policy))
    (tmp_path / 'ticket.json').write_text(json.dumps({'id': 'T-1', 'changes': ['model'], 'task': 'regression', 'interpretability': False}))
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/main.py').write_text('value=1')
    return tmp_path


def test_paths_cannot_weaken_declared_scope(project):
    report = quality.plan(project, project / 'ticket.json', changed=['.ci/pipeline.yml'])
    assert set(report['changes']) == {'model', 'deployment'}
    assert 'unit' in [s['id'] for s in report['suites'] if s['required']]


def test_unknown_path_selects_conservative_scope(project):
    report = quality.plan(project, project / 'ticket.json', changed=['mystery.txt'])
    assert 'deployment' in report['changes'] and 'data' in report['changes']


def test_missing_release_check_is_incomplete(project):
    report = quality.plan(project, project / 'ticket.json', 'release', ['.ci/pipeline.yml'])
    assert quality.execute(project, report, project / '.quality/run', 10) == 2
    assert report['suites'][1]['status'] == 'NOT_RUN'


def test_code_change_perishes_previous_success(project):
    report = quality.plan(project, project / 'ticket.json')
    assert quality.execute(project, report, project / '.quality/run', 10) == 0
    (project / 'src/main.py').write_text('value=2')
    assert quality.plan(project, project / 'ticket.json')['context'] != report['context']


def test_timeout_and_failure_are_not_success(project):
    for command in [['{python}', '-c', 'raise SystemExit(9)'], ['{python}', '-c', 'import time;time.sleep(5)']]:
        report = quality.plan(project, project / 'ticket.json')
        report['suites'][0].update(command=command, timeout=.05)
        folder = project / '.quality' / ('failure' if '9' in command[-1] else 'timeout')
        assert quality.execute(project, report, folder, 5) == 2
        assert report['suites'][0]['status'] == 'FAILED'


def test_skipped_pytest_is_not_green(project):
    p = project / 'src/test_skipped.py'
    p.write_text('import pytest\n@pytest.mark.skip(reason="missing runtime")\ndef test_missing(): pass\n')
    report = quality.plan(project, project / 'ticket.json')
    report['suites'][0]['command'] = [sys.executable, '-m', 'pytest', str(p), '-q']
    assert quality.execute(project, report, project / '.quality/run', 20) == 2
    assert report['suites'][0]['status'] == 'NOT_RUN'


def test_report_escapes_untrusted_ticket(project):
    report = quality.plan(project, project / 'ticket.json')
    report['ticket']['id'] = '<script>alert(1)</script>'
    quality.render(report, project / '.quality/plan')
    assert '<script>alert(1)</script>' not in (project / '.quality/plan/index.html').read_text()
