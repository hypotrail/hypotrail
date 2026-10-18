"""Ticket-specific test policy, bounded execution, and local evidence; no certification."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

CHANGES = {'data', 'features', 'model', 'refactor', 'dependencies', 'deployment', 'interface', 'pilot', 'docs'}
TASKS = {'classification', 'regression', 'ranking', 'clustering', 'unspecified'}
IGNORED = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', 'reports', 'examples',
           'data', 'dist', 'build', '.pilot', '.quality', '.local', 'htmlcov', 'node_modules'}


def fingerprint(root, policy):
    """Code, tests, contracts, and ticket; actual data excluded from synthetic software tests."""
    hashes = {}
    for name in policy['context_paths']:
        base = root / name
        paths = base.rglob('*') if base.is_dir() else [base]
        for p in paths:
            if p.is_file() and not p.is_symlink() and not (set(p.relative_to(root).parts) & IGNORED):
                if p.suffix in {'.py', '.json', '.yaml', '.yml', '.toml', '.txt', '.in', '.lock', '.js', '.html', '.md'}:
                    hashes[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def infer_changes(paths):
    changes = set()
    for path in paths:
        p = path.lower().replace('\\', '/')
        if '..' in Path(p).parts or Path(p).is_absolute():
            raise ValueError('Changed paths must be project-relative')
        if p.endswith('.md') or p.startswith('docs/'):
            changes.add('docs')
        elif any(x in p for x in ['requirements', 'uv.lock', 'pyproject', 'environment', 'conda']):
            changes.add('dependencies')
        elif any(x in p for x in ['.ci/', '.github/', 'azure', 'deploy', 'docker']):
            changes.add('deployment')
        elif any(x in p for x in ['bridge', 'interface', 'tutorial', 'tutoriel']) or p.endswith(('.html', '.js')):
            changes.add('interface')
        elif any(x in p for x in ['pilot', 'quality', 'test-policy', 'ticket']):
            changes.add('pilot')
        elif any(x in p for x in ['prepar', 'split', 'schema', 'feature', 'data/']):
            changes.update(['data', 'features'])
        elif any(x in p for x in ['train', 'model', 'evaluat', 'decision', 'classical']):
            changes.add('model')
        else:
            changes.update(CHANGES - {'docs'})  # unknown: do not optimistically exclude checks
    return changes


def plan(root, ticket_path, phase='pr', changed=()):
    root = Path(root).resolve()
    policy = json.loads((root / 'test-policy.json').read_text())
    ticket_path = Path(ticket_path).resolve()
    if not ticket_path.is_relative_to(root):
        raise ValueError('Ticket must be inside the project')
    ticket = json.loads(ticket_path.read_text())
    if set(ticket) != {'id', 'changes', 'task', 'interpretability'}:
        raise ValueError('Ticket requires id, changes, task, and interpretability, with no extra fields')
    if not isinstance(ticket['id'], str) or not ticket['id'].strip():
        raise ValueError('Identifiant de ticket required')
    if not isinstance(ticket['changes'], list) or not ticket['changes'] or any(x not in CHANGES for x in ticket['changes']):
        raise ValueError('Nature de changement unknown ou missing')
    if ticket['task'] not in TASKS or not isinstance(ticket['interpretability'], bool):
        raise ValueError('Type ML ou contrainte invalid')
    if phase not in {'pr', 'release'}:
        raise ValueError('Phase unknown')
    selected = set(ticket['changes']) | infer_changes(changed)
    suites = []
    for item in policy['suites']:
        selected_by = selected & set(item['changes'])
        required = bool(selected_by) and phase in item['phases']
        if item.get('interpretability_only'):
            required = required and ticket['interpretability']
        suites.append({**item, 'required': required, 'status': 'NOT_RUN' if required else 'NOT_APPLICABLE',
                       'reason': 'Changements : ' + ', '.join(sorted(selected_by)) if required else 'Outside ticket or phase scope'})
    context = hashlib.sha256((fingerprint(root, policy) + json.dumps(ticket, sort_keys=True) +
                              json.dumps(sorted(selected)) + phase).encode()).hexdigest()
    return {'schema_version': 1, 'ticket': ticket, 'ticket_path': str(ticket_path.relative_to(root)),
            'changes': sorted(selected), 'changed_paths': list(changed), 'phase': phase, 'context': context,
            'policy_sha256': hashlib.sha256((root / 'test-policy.json').read_bytes()).hexdigest(),
            'approval': 'NOT_APPROVED', 'scope': 'synthetic_software_checks_and_explicit_release_requirements',
            'suites': suites}


def render(report, folder):
    def e(value):
        return html.escape(str(value), quote=True)
    labels = {'PASSED': 'Passed', 'FAILED': 'Failed', 'NOT_RUN': 'Not executed',
              'NOT_APPLICABLE': 'No applicable', 'STALE': 'Stale'}
    rows = ''
    for suite in report['suites']:
        log = '<a href="' + e(suite['log']) + '">Evidence</a>' if suite.get('log') else '—'
        rows += f'<tr><td>{e(suite["title"])}</td><td class="{suite["status"]}">{labels[suite["status"]]}</td><td>{e(suite["reason"])}</td><td>{e(suite.get("seconds", "—"))}</td><td>{log}</td></tr>'
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tests · {e(report['ticket']['id'])}</title>
    <style>:root{{--bg:#f2f5f1;--paper:#fff;--ink:#193c32;--line:#d7e1da}}body{{font:16px/1.65 system-ui;margin:0;background:var(--bg);color:var(--ink)}}main{{max-width:1100px;margin:auto;padding:32px 22px}}h1{{font-size:38px;line-height:1.2}}section{{background:var(--paper);padding:24px;border-radius:16px;margin:20px 0}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:14px;border-bottom:1px solid var(--line)}}.scroll{{overflow:auto}}.PASSED{{color:#16724c}}.FAILED,.STALE{{color:#b33c33}}.NOT_RUN{{color:#926000}}a{{color:inherit}}button{{padding:10px;border-radius:8px;cursor:pointer}}body.dark{{--bg:#132820;--paper:#203c31;--ink:#e6efe9;--line:#496052}}body.dark .PASSED{{color:#8be0ac}}body.dark .FAILED,body.dark .STALE{{color:#ffb5aa}}body.dark .NOT_RUN{{color:#ffd185}}</style>
    <main><button onclick="document.body.classList.toggle('dark')">Light / dark</button><p>OPEN SPEC · PREUVES DU TICKET · {e(report['phase'])}</p><h1>{e(report['ticket']['id'])}: useful checks</h1>
    <section><b>{e(report.get('outcome', 'PLAN NOT EXECUTED'))}</b><p>Changements : {e(', '.join(report['changes']))}. Type ML : {e(report['ticket']['task'])}.</p><p>Synthetic tests check software. They establish neither candidate business value nor production suitability. This policy performs no holdout reading or cloud submission.</p></section>
    <section class="scroll"><table><tr><th>Check</th><th>State</th><th>Reason / next action</th><th>Seconds</th><th>Evidence</th></tr>{rows}</table></section><p><a href="report.json">Structured results</a> · Fingerprint {e(report['context'][:16])}</p><p>Changes to code, tests, contracts, policy, or ticket make this summary stale. A skipped test is not a success. Protect critical policies and criteria through review and CI.</p></main></html>'''
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    from .presentation import polish
    (folder / 'index.html').write_text(polish(page,quality=True))


def execute(root, report, folder, budget=480):
    if not 1 <= budget <= 540:
        raise ValueError('Total budget entre 1 et 540 seconds')
    root, folder = Path(root).resolve(), Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    render(report, folder)
    for suite in report['suites']:
        if not suite['required']:
            continue
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0 or not suite.get('command'):
            suite['reason'] = 'Budget exhausted' if remaining <= 0 else suite.get('unavailable', 'Configure a project-specific command')
            continue
        command = [sys.executable if x == '{python}' else x for x in suite['command']]
        junit = folder / (suite['id'] + '.xml')
        if command[1:3] == ['-m', 'pytest']:
            command += ['--junitxml=' + str(junit)]
        suite['command_executed'] = command
        log = folder / (suite['id'] + '.txt')
        begin = time.monotonic()
        env = {k: v for k, v in os.environ.items() if not k.startswith('OSML_')}
        env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MLFLOW_DISABLE_AGENT_HINT='1')
        with log.open('w') as stream:
            process = subprocess.Popen(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=(os.name == 'posix'))
            try:
                code = process.wait(timeout=min(remaining, suite.get('timeout', 120)))
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
                code = 124
        suite.update(status='PASSED' if code == 0 else 'FAILED', returncode=code,
                     seconds=round(time.monotonic() - begin, 3), log=log.name,
                     log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        if code == 0 and command[1:3] == ['-m', 'pytest']:
            tree = ET.parse(junit).getroot()
            cases = list(tree.iter('testcase'))
            if not cases or any(case.find('skipped') is not None for case in cases):
                suite.update(status='NOT_RUN', reason='Missing or skipped tests: check dependencies and scope')
        if code != 0:
            suite['reason'] = 'Timeout' if code == 124 else 'Command failed: inspect evidence and fix without weakening the criterion'
        render(report, folder)
    current = plan(root, root / report['ticket_path'], report['phase'], report['changed_paths'])
    if current['context'] != report['context']:
        for suite in report['suites']:
            if suite['status'] == 'PASSED':
                suite.update(status='STALE', reason='Context changed during tests')
    required = [s for s in report['suites'] if s['required']]
    complete = bool(required) and all(s['status'] == 'PASSED' for s in required)
    report.update(outcome='SOFTWARE_CHECKS_PASSED' if complete else 'INCOMPLETE_OR_FAILED',
                  seconds=round(time.monotonic() - started, 3))
    render(report, folder)
    return 0 if complete else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'run', 'status'])
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--ticket', type=Path, default=Path('ticket.json'))
    parser.add_argument('--phase', choices=['pr', 'release'], default='pr')
    parser.add_argument('--changed', action='append', default=[])
    parser.add_argument('--budget', type=int, default=480)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        report = plan(root, root / args.ticket, args.phase, args.changed)
        if args.action == 'status':
            latest = root / '.quality/latest.json'
            old = json.loads(latest.read_text())
            saved = json.loads((root / old['report']).read_text())
            fresh = saved['context'] == report['context']
            print(json.dumps({'fresh': fresh, 'outcome': saved['outcome'] if fresh else 'STALE', 'report': old['report']}))
            return 0 if fresh and saved['outcome'] == 'SOFTWARE_CHECKS_PASSED' else 2
        folder = root / '.quality/results' / ('run-' + uuid.uuid4().hex[:12])
        if args.action == 'plan':
            report['outcome'] = 'PLAN_NOT_EXECUTED'
            render(report, folder)
            code = 0
        else:
            code = execute(root, report, folder, args.budget)
        (root / '.quality/latest.json').write_text(json.dumps({'report': str((folder / 'report.json').relative_to(root))}))
        print(json.dumps({'outcome': report['outcome'], 'report': str(folder / 'index.html'),
                          'required': [s['id'] for s in report['suites'] if s['required']]}, ensure_ascii=False))
        return code
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        print('TESTS : ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
