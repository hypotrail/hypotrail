"""Case material copied into an agent workspace, and the grader-side truth kept outside it.

Two cases (plan WP0.9: every scenario runs on both):

* ``bank``: the public UCI extract ``bank.csv`` with its original ``bank-names.txt`` and a
  neutral README of the scenario. Nothing from the repository's tutorial material (which
  names the leakage) is copied.
* ``synthetic``: ``make_case`` writes data.csv, case.yaml, and truth.json into a hidden
  directory **outside the workspace**; only ``data.csv`` and a README generated from the
  case.yaml variable descriptions are copied. ``truth.json`` never reaches the workspace.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
BANK_DIR = REPO_ROOT / 'use-cases/bank-marketing/data'
MAKE_CASE = REPO_ROOT / 'framework/tests/fixtures/synthetic/make_case.py'

BANK_README = """\
# Term deposit campaign: whom to call first

## Files

- `bank.csv`: one row per client contacted in a past phone campaign of a Portuguese bank;
  semicolon-separated, header on the first line. The target column is `y`
  (`yes` = the client subscribed a term deposit).
- `bank-names.txt`: the original documentation distributed with the data.

The data are the public UCI "Bank Marketing" extract (Moro, Laureano and Cortez, 2011;
CC BY 4.0). Do not modify these files.

## Scenario

The bank is preparing its next phone campaign for the term deposit. The call team has
limited capacity and cannot call every client. **Before the calls are made**, we would like
to decide which clients to call first.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by the bank.
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_make_case():
    spec = importlib.util.spec_from_file_location('synthetic_make_case_for_agent', MAKE_CASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_case


def prepare_bank(workspace: Path) -> dict:
    ws = Path(workspace)
    for name in ('bank.csv', 'bank-names.txt'):
        shutil.copyfile(BANK_DIR / name, ws / name)
    (ws / 'README.md').write_text(BANK_README, encoding='utf-8')
    return {'case': 'bank', 'data': 'bank.csv', 'sep': ';', 'target': 'y', 'positive': 'yes',
            'data_sha256': sha256(ws / 'bank.csv'), 'files': ['README.md', 'bank.csv', 'bank-names.txt']}


def synthetic_readme(case: dict) -> str:
    """Neutral README built from case.yaml: description, file format, variable descriptions.

    Availability statuses and epistemic labels are left out, as in the Bank documentation,
    so the agent has to reason about availability from the descriptions.
    """
    facts = {f['id']: f for f in case.get('facts', [])}
    ds, target = case['dataset'], case['target']
    lines = [
        '# Renewal reminders: whom to phone first', '',
        '## Files', '',
        f"- `{ds['path']}`: one row per renewal cycle of an expired library membership; "
        f"separator `{ds['sep']}`, UTF-8, header on the first line, {ds['rows']} rows. "
        f"The target column is `{target['column']}` (`{target['positive_label']}` or "
        f"`{target['negative_label']}`).", '',
        'Do not modify this file.', '',
        '## Scenario', '',
        case['description'], '',
        f"Observation unit: {facts.get('observation_unit', {}).get('value', 'not documented')}.",
        f"Intended use (assumption for the exercise): {facts.get('intended_use', {}).get('value', '')}.",
        '', '## Variables (membership office data dictionary)', '',
        '| Column | Type | Unit | Description | Special values |',
        '|---|---|---|---|---|',
    ]
    for v in case['variables']:
        special = '; '.join(f"`{s['value']}`: {s['meaning']}" for s in v.get('special_values', []))
        lines.append(f"| `{v['name']}` | {v.get('type', '')} | {v.get('unit', '')} | "
                     f"{v['description']} | {special} |")
    lines += ['', 'The Quillmere Library Network is fictitious; the data are synthetic.', '']
    return '\n'.join(lines)


def prepare_synthetic(workspace: Path, hidden_dir: Path, seed: int = 20261018) -> dict:
    ws, hidden = Path(workspace), Path(hidden_dir)
    if ws.resolve() in hidden.resolve().parents or hidden.resolve() == ws.resolve():
        raise ValueError('the hidden truth directory must be outside the workspace')
    hidden.mkdir(parents=True, exist_ok=True)
    paths = _load_make_case()(hidden, seed=seed)
    case = yaml.safe_load(paths['case'].read_text(encoding='utf-8'))
    shutil.copyfile(paths['data'], ws / 'data.csv')
    (ws / 'README.md').write_text(synthetic_readme(case), encoding='utf-8')
    assert not (ws / 'truth.json').exists()
    return {'case': 'synthetic', 'data': 'data.csv', 'sep': ';', 'target': 'outcome',
            'positive': 'renewed', 'seed': seed, 'data_sha256': sha256(ws / 'data.csv'),
            'truth_path': str(paths['truth']), 'files': ['README.md', 'data.csv']}


def preparer(case: str, hidden_dir: Path | None = None, seed: int = 20261018):
    if case == 'bank':
        return prepare_bank
    if case == 'synthetic':
        if hidden_dir is None:
            raise ValueError('synthetic case needs a hidden directory for truth.json')
        return lambda ws: prepare_synthetic(ws, hidden_dir, seed)
    raise ValueError(f'unknown case {case!r}')
