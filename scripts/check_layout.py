"""Read-only check of canonical paths, public datasets."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'AGENTS.md', '.github/copilot-instructions.md', 'docs/START-HERE.md',
    'docs/specs/JUNIOR-WORKFLOW.md', 'docs/handoff/IMPLEMENTATION.md',
    'framework/mlkit/pilot.py', 'framework/mlkit/reliability.py',
    'framework/tests/fixtures/legacy-project/frame.yaml',
    'experimental/companion/feature.json',
    'clients/vscode-companion/package.json', 'clients/vscode-companion/extension.js',
    'clients/vscode-companion/README.md', 'docs/decisions/0003-companion-webview-v0.md',
    'clients/vscode-companion/ARCHITECTURE.md', 'docs/decisions/0004-companion-advanced.md',
]
LINKS = {
    'experimental/companion/runtime/bank-tutorial.html': 'use-cases/bank-marketing/bank-tutorial.html',
    'experimental/companion/runtime/tutorial-results.json': 'use-cases/bank-marketing/tutorial-results.json',
    'experimental/companion/runtime/projects': 'use-cases',
    'experimental/companion/runtime/data': 'use-cases/bank-marketing/data',
    'experimental/companion/runtime/prepare_bank.py': 'use-cases/bank-marketing/prepare_bank.py',
    'experimental/companion/runtime/prepare_auto_mpg.py': 'use-cases/auto-mpg/prepare_auto_mpg.py',
}

CONFIRMATION = re.compile(r'confirm(?:ed|ation)', re.IGNORECASE)
CASE_FILES = ('case.yaml', 'case-supplement.yaml')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dataset_fields(text):
    """The `dataset` mapping of a case file: PyYAML when available, else a plain scan."""
    try:
        import yaml
    except ImportError:
        fields, inside = {}, False
        for line in text.splitlines():
            if line.startswith('dataset:'):
                inside = True
            elif inside and line.startswith('  ') and not line.startswith('   '):
                key, _, value = line.strip().partition(':')
                fields[key] = value.strip().strip('\'"')
            elif inside and line and not line.startswith(' '):
                break
        return fields
    return (yaml.safe_load(text) or {}).get('dataset') or {}

# A use case whose data may not be redistributed commits a `prepare.py` that copies them
# from an installed package into an ignored path; until it runs, the dataset is absent.
MATERIALIZER = 'prepare.py'

def check_cases(errors, absent=None):
    """A case never declares a confirmation, and its dataset matches the declared sha256.

    A dataset materialized by the use case's `prepare.py` may be absent (listed in
    `absent`); when present, it must match like any other."""
    count, absent = 0, ([] if absent is None else absent)
    for folder in sorted(p for p in (ROOT / 'use-cases').iterdir() if p.is_dir()):
        for name in CASE_FILES:
            path = folder / name
            if path.is_file() and CONFIRMATION.search(path.read_text(encoding='utf-8')):
                errors.append(f'Case file declares a confirmation: {folder.name}/{name}')
        path = folder / 'case.yaml'
        if not path.is_file():
            continue
        count += 1
        dataset = dataset_fields(path.read_text(encoding='utf-8'))
        raw = (folder / str(dataset.get('path') or '')).resolve()
        if not dataset.get('path') or not raw.is_relative_to(folder.resolve()):
            errors.append(f'Case dataset outside its use case: {folder.name}')
        elif not raw.is_file() and (folder / MATERIALIZER).is_file():
            absent.append(f'{folder.name}/{dataset["path"]} (run {folder.name}/{MATERIALIZER})')
        elif not raw.is_file() or sha(raw) != dataset.get('sha256'):
            errors.append(f'Case dataset fingerprint mismatch: {folder.name}')
    return count

# The study companion (ADR 0003) is a client of the `hypotrail` CLI behind a flag that is
# off by default: no runtime dependency, no network module, no shell, no storage of its own.
COMPANION_CLIENT = 'clients/vscode-companion'
COMPANION_SETTING = 'hypotrail.companion.enabled'
# ADR 0004 and COMPANION-ADVANCED §3.1: the stage setting defaults to v0; chatInsert is not
# contributed (hidden until verified in a real VS Code, decision CA.8) or defaults to false.
COMPANION_STAGE = 'hypotrail.companion.stage'
COMPANION_CHAT_INSERT = 'hypotrail.companion.chatInsert'
COMPANION_ACTIVATION = ['onCommand:hypotrail.companion.open', 'onCommand:hypotrail.companion.openReviewer',
                        'onCommand:hypotrail.companion.goToResult', 'onUri']
COMPANION_FORBIDDEN = re.compile(
    r"require\(['\"](?:node:)?(?:https?|http2|net|tls|dgram|ws|sqlite3?|better-sqlite3)['\"]\)"
    r"|shell:\s*true|\bexecSync\b|\bspawn\(|childProcess\.exec\(|\bexec\("
    r"|vscode\.lm\b|WebSocket|localStorage|indexedDB|\bfetch\(|workspaceState")

# ADR 0004 amendment "local launch" (WP-A5): the panel may open a VS Code terminal for
# exactly two commands, Marimo's own server on the study's two notebooks (`marimo run` of
# the generated notebook, `marimo edit` of the workbench). The terminal is created once,
# in extension.js, with an argument list (shellPath and shellArgs), after lib/launch.js
# accepted the argv; nothing types into a terminal and no other file creates one.
COMPANION_LAUNCH_FILE = 'lib/launch.js'
COMPANION_TERMINAL_FILE = 'extension.js'
COMPANION_NOTEBOOKS = {"notebook: Object.freeze({ path: 'notebooks/study_generated.py', mode: 'run' })",
                       "workbench: Object.freeze({ path: 'notebooks/workbench.py', mode: 'edit' })"}
TERMINAL_CALL = re.compile(r'createTerminal\s*\(')
TERMINAL_FORBIDDEN = re.compile(r'\bsendText\b|\bcreateTerminal\s*\(\s*[\'"`]|\bshellPath\s*:\s*[\'"`]'
                                r'|ExtensionTerminalOptions|\bpty\s*:')


def companion_terminal_errors(sources):
    """Errors of the terminal rule over ``{relative path: text}`` of the client sources."""
    errors = []
    for rel, text in sorted(sources.items()):
        if TERMINAL_FORBIDDEN.search(text):
            errors.append(f'Companion client source types into or builds a shell terminal: {rel}')
        if rel != COMPANION_TERMINAL_FILE and TERMINAL_CALL.search(text):
            errors.append(f'Companion client creates a terminal outside {COMPANION_TERMINAL_FILE}: {rel}')
    main = sources.get(COMPANION_TERMINAL_FILE, '')
    calls = list(TERMINAL_CALL.finditer(main))
    if len(calls) > 1:
        errors.append(f'Companion client creates more than one terminal call in {COMPANION_TERMINAL_FILE}')
    if calls:
        start = calls[0].start()
        call = main[start:main.find('})', start) + 2]
        before = main[max(0, main.rfind('\nfunction ', 0, start)):start]
        if 'shellPath:' not in call or 'shellArgs:' not in call:
            errors.append('Companion client terminal is not created with an argument list (shellPath, shellArgs)')
        if 'launch.isMarimoLaunch(' not in before:
            errors.append('Companion client terminal is created without lib/launch.js accepting the Marimo argv')
        launch = sources.get(COMPANION_LAUNCH_FILE)
        if launch is None:
            errors.append(f'Companion client creates a terminal but has no {COMPANION_LAUNCH_FILE}')
        else:
            modes = re.findall(r"^\s*\w+: Object\.freeze\(\{ path: '[^']*', mode: '[^']*' \}\)", launch, re.M)
            if {m.strip() for m in modes} != COMPANION_NOTEBOOKS:
                errors.append(f'Companion client {COMPANION_LAUNCH_FILE} launches other than marimo run of the '
                              'generated notebook and marimo edit of the workbench')
            if "tail[0] !== 'marimo'" not in launch:
                errors.append(f'Companion client {COMPANION_LAUNCH_FILE} does not require the marimo command')
    return errors


def check_companion_client(errors):
    """The companion client stays default-off, dependency-free, and CLI-only."""
    folder = ROOT / COMPANION_CLIENT
    package = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
    properties = package.get('contributes', {}).get('configuration', {}).get('properties', {})
    setting = properties.get(COMPANION_SETTING, {})
    if setting.get('default') is not False:
        errors.append(f'Companion client flag {COMPANION_SETTING} is not default-off')
    if properties.get(COMPANION_STAGE, {}).get('default') != 'v0':
        errors.append(f'Companion client setting {COMPANION_STAGE} does not default to v0')
    if properties.get(COMPANION_CHAT_INSERT, {'default': False}).get('default') is not False:
        errors.append(f'Companion client setting {COMPANION_CHAT_INSERT} is not default-off')
    if package.get('activationEvents') != COMPANION_ACTIVATION:
        errors.append('Companion client activation events are not exactly its commands and onUri')
    if package.get('capabilities', {}).get('untrustedWorkspaces', {}).get('supported') is not False:
        errors.append('Companion client does not require a trusted workspace')
    if package.get('dependencies'):
        errors.append('Companion client has runtime dependencies')
    sources = sorted(p for p in folder.rglob('*.js')
                     if 'test' not in p.relative_to(folder).parts and 'node_modules' not in p.parts)
    # The webview's protocol copy is generated from lib/protocol.js and must not drift.
    generated = subprocess.run(['node', str(folder / 'lib' / 'protocol.js')], capture_output=True,
                               text=True, timeout=60) if shutil.which('node') else None
    if generated is not None and (generated.returncode != 0 or generated.stdout
                                  != (folder / 'media' / 'protocol.js').read_text(encoding='utf-8')):
        errors.append('Companion client media/protocol.js differs from lib/protocol.js --emit-webview')
    for path in sources:
        if COMPANION_FORBIDDEN.search(path.read_text(encoding='utf-8')):
            errors.append(f'Companion client source uses a forbidden API: {path.relative_to(ROOT)}')
    errors.extend(companion_terminal_errors(
        {p.relative_to(folder).as_posix(): p.read_text(encoding='utf-8') for p in sources}))
    return len(sources)

def main():
    errors = []
    for rel in REQUIRED:
        if not (ROOT / rel).is_file(): errors.append(f'Missing file: {rel}')
    for rel, target in LINKS.items():
        path = ROOT / rel
        if not path.is_symlink() or not path.exists() or path.resolve() != (ROOT / target).resolve():
            errors.append(f'Compatibility link mismatch: {rel}')
    feature = json.loads((ROOT / 'experimental/companion/feature.json').read_text())
    if feature['status'] != 'paused' or feature['default_enabled'] is not False:
        errors.append('Companion is no longer documented as paused/default-off')
    for entry in json.loads((ROOT / 'use-cases/registry.json').read_text())['projects']:
        folder = ROOT / 'use-cases' / entry['dir']
        project = json.loads((folder / 'project.json').read_text())
        results = json.loads((folder / 'results.json').read_text())
        raw = (folder / project['dataset']['path']).resolve()
        if not raw.is_relative_to(folder.resolve()):
            errors.append(f'Dataset outside its use case: {entry["dir"]}')
        elif not raw.is_file() or sha(raw) != project['dataset']['sha256']:
            errors.append(f'Dataset fingerprint mismatch: {entry["dir"]}')
        if results['dataset']['sha256'] != project['dataset']['sha256']:
            errors.append(f'Results do not reference the declared dataset: {entry["dir"]}')
    absent = []
    cases = check_cases(errors, absent)
    client_sources = check_companion_client(errors)
    print(json.dumps({'ok': not errors, 'use_cases': 2, 'cases': cases,
                      'not_materialized': absent,
                      'compatibility_links': len(LINKS),
                      'companion_client_sources': client_sources,
                      'errors': errors}, ensure_ascii=False, indent=2))
    return bool(errors)

if __name__ == '__main__':
    sys.exit(main())
