"""Every requirement id of COMPANION-ADVANCED.md is named by a test, and the checklist's
coverage table is the generated one (scope U, WP-I; ``scripts/companion_coverage.py``).

A test names an id in its title, docstring, or a comment next to its assertion
(``test_ev3_...`` counts as EV-3). The table lists files, not proofs: a reviewer reads the
named tests. Regenerate it with ``python3 scripts/companion_coverage.py --write``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _coverage():
    spec = importlib.util.spec_from_file_location('companion_coverage', REPO / 'scripts' / 'companion_coverage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_requirement_id_is_named_by_a_test():
    cov = _coverage()
    ids = cov.requirement_ids()
    assert len(ids) >= 60, ids
    missing = [rid for rid, files in cov.coverage().items() if not files]
    assert missing == [], missing


def test_the_checklist_table_is_the_generated_one():
    cov = _coverage()
    text = cov.CHECKLIST.read_text(encoding='utf-8')
    assert cov.START in text and cov.END in text
    current = text.split(cov.START, 1)[1].split(cov.END, 1)[0].strip()
    assert current == cov.table(), 'run python3 scripts/companion_coverage.py --write'
