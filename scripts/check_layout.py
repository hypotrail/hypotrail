"""Read-only check of canonical paths, public datasets."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'AGENTS.md', '.github/copilot-instructions.md', 'docs/START-HERE.md',
    'docs/specs/JUNIOR-WORKFLOW.md', 'docs/handoff/IMPLEMENTATION.md',
    'framework/mlkit/pilot.py', 'framework/mlkit/reliability.py',
    'framework/tests/fixtures/legacy-project/frame.yaml',
    'experimental/companion/feature.json',
]
LINKS = {
    'experimental/companion/runtime/bank-tutorial.html': 'use-cases/bank-marketing/bank-tutorial.html',
    'experimental/companion/runtime/tutorial-results.json': 'use-cases/bank-marketing/tutorial-results.json',
    'experimental/companion/runtime/projects': 'use-cases',
    'experimental/companion/runtime/data': 'use-cases/bank-marketing/data',
    'experimental/companion/runtime/prepare_bank.py': 'use-cases/bank-marketing/prepare_bank.py',
    'experimental/companion/runtime/prepare_auto_mpg.py': 'use-cases/auto-mpg/prepare_auto_mpg.py',
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

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
    print(json.dumps({'ok': not errors, 'use_cases': 2, 'compatibility_links': len(LINKS),
                      'errors': errors}, ensure_ascii=False, indent=2))
    return bool(errors)

if __name__ == '__main__':
    sys.exit(main())
