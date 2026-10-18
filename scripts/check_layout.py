"""Read-only check of canonical paths, public datasets."""
from pathlib import Path
import hashlib
import json
import re
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
COMPANION_FORBIDDEN = re.compile(
    r"require\(['\"](?:node:)?(?:https?|http2|net|tls|dgram|ws|sqlite3?|better-sqlite3)['\"]\)"
    r"|shell:\s*true|\bexecSync\b|\bspawn\(|childProcess\.exec\(|\bexec\("
    r"|vscode\.lm\b|WebSocket|localStorage|indexedDB|\bfetch\(")

def check_companion_client(errors):
    """The companion client stays default-off, dependency-free, and CLI-only."""
    folder = ROOT / COMPANION_CLIENT
    package = json.loads((folder / 'package.json').read_text(encoding='utf-8'))
    setting = (package.get('contributes', {}).get('configuration', {})
               .get('properties', {}).get(COMPANION_SETTING, {}))
    if setting.get('default') is not False:
        errors.append(f'Companion client flag {COMPANION_SETTING} is not default-off')
    if package.get('activationEvents') != ['onCommand:hypotrail.companion.open']:
        errors.append('Companion client activates on more than its command')
    if package.get('capabilities', {}).get('untrustedWorkspaces', {}).get('supported') is not False:
        errors.append('Companion client does not require a trusted workspace')
    if package.get('dependencies'):
        errors.append('Companion client has runtime dependencies')
    sources = sorted(p for p in folder.rglob('*.js')
                     if 'test' not in p.relative_to(folder).parts and 'node_modules' not in p.parts)
    for path in sources:
        if COMPANION_FORBIDDEN.search(path.read_text(encoding='utf-8')):
            errors.append(f'Companion client source uses a forbidden API: {path.relative_to(ROOT)}')
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
