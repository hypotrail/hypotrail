"""Capture the step-card digests of the lot 2026-10-28 from the real engine (integration).

    uv run --project framework python clients/vscode-companion/test/fixtures/stepcards/capture.py [automatic]

replaces the hand-made fixtures the panel package wrote from the spec's example (the former
``build.py``). Two temporary French Auto MPG studies, driven through the ``hypotrail`` CLI code
path (``mlkit.study.cli.run``) with the companion on at stage v3:

* a guided study walked by the engine tests' journey walker (``test_journey_walkthrough.walk``,
  the test junior's words, not a Copilot session): ``status --summary --digest`` at the first
  read of every plan step (``summary.<state>.json``), at the pause after the exploration
  (``summary.exploration.json``) and at the end (``summary.done.json``), plus the views the
  panel reads at the end (``evidence``, ``status``, ``decisions``, ``data``);
* a study created with ``init --automation full_demo`` and ``automation run`` to the end
  (``summary.done.automatic.json``): every decision has the basis ``automatic``.

Each file is ``{"about": {...}, "payload": {...}}`` with ``about.source == "captured"``. Nothing
under ``use-cases/`` is written; the studies live in a temporary directory removed at the end.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / 'framework'))
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'study'))
os.environ.update({'HYPOTRAIL_COMPANION': '1', 'HYPOTRAIL_COMPANION_STAGE': 'v3'})

import flowkit as fk  # noqa: E402
import test_journey_walkthrough as jw  # noqa: E402

# The state names the tests use, by plan step (the first read of that step).
STATES = {'discover_data': 'data', 'prediction_time': 'moment', 'feature_availability': 'variables', 'split': 'split',
          'error_metric': 'metric', 'success_criterion': 'criterion', 'structural_eda': 'quality',
          'preprocessing': 'preparation', 'train_eda': 'exploration', 'models': 'models', 'model_variant': 'variants',
          'model_choice': 'choice', 'final_test': 'final', 'conclusion': 'conclusion'}
PLACEHOLDER = '/studies/auto mpg fr'


def save(root: Path, name: str, argv, payload: dict, note: str) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    for sub in ('guided', 'automatic'):
        text = text.replace(json.dumps(str(root / sub), ensure_ascii=False)[1:-1], PLACEHOLDER)
    text = text.replace(json.dumps(str(REPO))[1:-1], '/hypotrail')
    about = {'schema': payload.get('schema'), 'task': 'regression', 'exit_code': 0, 'source': 'captured',
             'argv': [str(a) for a in argv if str(root) not in str(a)], 'note': note}
    (HERE / f'{name}.json').write_text(json.dumps({'about': about, 'payload': json.loads(text)}, ensure_ascii=False, indent=1)
                                       + '\n', encoding='utf-8')


def digest(f: fk.Flow) -> dict:
    return f.call('status', '--summary', '--digest', '--study', f.study)


def guided(root: Path) -> None:
    f = fk.Flow(root / 'guided', jw.AUTO_MPG, prefix='g')
    f.call('init', '--case', jw.AUTO_MPG, '--study', f.study, '--lang', 'fr')
    seen: set[str] = set()

    def on_read(label, action):
        d = digest(f)
        step = d.get('current_step')
        if action.get('kind') == 'read_exploration':
            save(root, 'summary.exploration', ['status', '--summary', '--digest', '--json'], d,
                 'Guided French Auto MPG study at the pause after the exploration (read_exploration).')
            seen.add('train_eda')
        elif step in STATES and step not in seen:
            seen.add(step)
            save(root, f'summary.{STATES[step]}', ['status', '--summary', '--digest', '--json'], d,
                 f'Guided French Auto MPG study, first read of the step {step} ({action.get("kind")}).')

    def on_write(label, payload):
        # The data card leads straight to the moment's proposal (no read in between): the moment
        # step is captured right after its proposal is written.
        if label.startswith('propose:'):
            d = digest(f)
            step = d.get('current_step')
            if step in STATES and step not in seen:
                seen.add(step)
                save(root, f'summary.{STATES[step]}', ['status', '--summary', '--digest', '--json'], d,
                     f'Guided French Auto MPG study at the step {step}, its proposal open.')

    jw.walk(f, 'regression', on_read=on_read, on_write=on_write)
    d = digest(f)
    assert d['next_action']['kind'] == 'done', d['next_action']
    save(root, 'summary.done', ['status', '--summary', '--digest', '--json'], d, 'Guided French Auto MPG study at the end.')
    for name in ('evidence', 'status', 'decisions', 'data'):
        save(root, f'{name}.done', [name, '--json'], f.call(name, '--study', f.study),
             f'Guided French Auto MPG study at the end: `{name}`.')


def automatic(root: Path) -> None:
    f = fk.Flow(root / 'automatic', jw.AUTO_MPG, prefix='d')
    f.call('init', '--case', jw.AUTO_MPG, '--study', f.study, '--lang', 'fr', '--automation', 'full_demo')
    f.call('automation', 'run', '--study', f.study, '--json', '--request-id', 'auto', '--expected-revision', f.rev())
    d = digest(f)
    # Every step is done; the automatic decisions wait in the review queue (`reconfirm`).
    position = d['next_action']['pause']['position']
    assert position['completed'] == position['total'] == 14, d['next_action']
    save(root, 'summary.done.automatic', ['status', '--summary', '--digest', '--json'], d,
         'French Auto MPG study created with `init --automation full_demo`, run to the end by `automation run`: '
         'every step done, the automatic decisions in the review queue.')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='hypotrail stepcards ') as tmp:
        if 'automatic' not in sys.argv[1:]:
            guided(Path(tmp))
        automatic(Path(tmp))
    print('captured into', HERE)
    return 0


if __name__ == '__main__':
    sys.exit(main())
