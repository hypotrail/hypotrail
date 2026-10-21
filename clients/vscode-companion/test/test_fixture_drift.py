"""Fixture drift (WP-I): the companion's fixtures have the shape of real engine payloads.

``test/fixtures/captured/`` holds payloads captured from temporary Bank Marketing and Auto
MPG studies by ``test/fixtures/capture.py``. Two checks:

* every hand-written fixture of ``test/fixtures/`` has, at every path it shares with a
  captured payload of the same schema (and command, refusal code, or run action), the same
  keys (``fixture_shapes.drift``); scope U, no process;
* the committed captures still have the shape of what the engine of this checkout emits:
  the test captures again into a temporary directory and compares (scope S, the CLI code
  path in-process, plus one fault-injected CLI process). An engine change that drifts
  fails here; re-run ``capture.py``, then fix the fixtures the first check names.

Neither is a VS Code session.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import fixture_shapes as shapes

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
CAPTURED = FIXTURES / 'captured'
# A hand-written fixture with no captured counterpart, and why.
NO_CAPTURE = {
    'error.not_implemented': 'the WP-0 stub refusal (CC §13); no command answers it any more, and '
                             'test_contract_keys.py checks it against errors.not_implemented()',
}


def _load(directory: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in sorted(directory.glob('*.json'))
            if p.stem not in ('index', 'contract-keys')}


def group(item: dict) -> str:
    """Payloads of one group have one shape: the schema, refined by what changes it."""
    p = item['payload']
    schema = str(p.get('schema'))
    if schema == 'hypotrail.summary/1' and 'digest' in p:
        return schema + '+digest'
    if schema == 'hypotrail.error/1':
        return f"{schema}:{p['error']['code']}"
    if schema == 'hypotrail.decide/1':
        return f"{schema}:{p.get('action')}"
    if schema == 'hypotrail.run/1':
        activity = '' if p.get('action') == 'run.acknowledge' else (p.get('result') or {}).get('activity') or p.get('activity')
        return f"{schema}:{p.get('action')}:{activity}"
    return schema


def _counterparts(item: dict, captured: dict[str, dict]) -> list[dict]:
    same = [c for c in captured.values() if group(c) == group(item)]
    by_task = [c for c in same if c['about']['task'] == item['about']['task']]
    return by_task or same


def test_the_captures_are_committed():
    captured = _load(CAPTURED)
    assert len(captured) >= 35, sorted(captured)
    for name, item in captured.items():
        assert item['about']['source'] == 'captured', name
        assert item['about']['schema'] == item['payload']['schema'], name
    # Every group of the hand-written fixtures has a capture, except the reasoned ones.
    hand = _load(FIXTURES)
    missing = sorted(n for n, item in hand.items() if not _counterparts(item, captured))
    assert missing == sorted(NO_CAPTURE), missing


def test_every_hand_written_fixture_has_the_shape_of_the_real_payloads():
    captured = _load(CAPTURED)
    problems = []
    for name, item in _load(FIXTURES).items():
        same = _counterparts(item, captured)
        if not same:
            continue
        for path, missing, extra in shapes.drift(item['payload'], [c['payload'] for c in same]):
            problems.append(f'{name} {path or "(top)"}: missing {missing}, not emitted {extra}')
    assert not problems, '\n'.join(problems)


def test_the_drift_check_sees_a_renamed_or_dropped_key():
    captured = _load(CAPTURED)
    item = json.loads(json.dumps(captured['evidence.binary']))
    item['payload']['results'][0]['stale_reasons'] = item['payload']['results'][0].pop('stale_reason')
    del item['payload']['exposure']['ledger'][0]['rows']
    found = {path for path, _, _ in shapes.drift(item['payload'], [captured['evidence.binary']['payload']])}
    assert any(p.startswith('results[]') for p in found) and 'exposure.ledger[]' in found, found


def _capture_module():
    spec = importlib.util.spec_from_file_location('companion_capture', FIXTURES / 'capture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_captures_have_the_shape_of_the_live_engine(tmp_path):
    try:
        capture = _capture_module()
    except ImportError as exc:  # pragma: no cover - the gate runs in framework/.venv
        pytest.skip(f'the engine is not importable here: {exc}')
    live = capture.capture(tmp_path / 'studies "q"')
    committed = _load(CAPTURED)
    assert sorted(live) == sorted(committed), 'run capture.py: the scenarios changed'
    problems = []
    for name, item in live.items():
        for a, b, label in ((committed[name], item, 'committed vs live'), (item, committed[name], 'live vs committed')):
            for path, missing, extra in shapes.drift(a['payload'], [b['payload']]):
                problems.append(f'{name} {path or "(top)"} ({label}): missing {missing}, extra {extra}')
        assert item['about']['exit_code'] == committed[name]['about']['exit_code'], name
    assert not problems, 'the engine drifted from test/fixtures/captured (run capture.py):\n' + '\n'.join(problems)
