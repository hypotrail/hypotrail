"""Capture real engine payloads for the companion's fixtures (WP-I).

    uv run --project framework python clients/vscode-companion/test/fixtures/capture.py [OUT]

builds two temporary studies outside the repository, Bank Marketing (binary) and Auto MPG
(regression), drives them through the ``hypotrail`` CLI code path (``mlkit.study.cli.run``,
the code a CLI process runs; fault-injected runs are real processes), and writes one file
per scenario to ``OUT`` (default ``test/fixtures/captured/``):
``{"about": {...}, "payload": {...}}``, the format of the hand-written fixtures, with
``about.source == "captured"``.

The hand-written fixtures next to this file carry the states the views need (holds,
stale results, an injected citation) with the values of the mockups. The test
``test_fixture_drift.py`` compares the *shape* of each of them (keys at every depth, by
schema) with these captured payloads, and with a fresh capture from the engine of the
checkout, so a drift between the fixtures and the real engine fails the gate. Re-run this
script after an engine change, then update the hand-written fixtures the test names.

Nothing under ``use-cases/`` is written: the committed cases are only read. The studies
live in a temporary directory, removed at the end. No business model is trained beyond the
case's own baseline, logistic, and linear fits on the public data, as the engine tests do.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / 'framework'))
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'study'))

import flowkit as fk  # noqa: E402
from mlkit.study import cli  # noqa: E402

BANK = REPO / 'use-cases' / 'bank-marketing'
AUTO = REPO / 'use-cases' / 'auto-mpg'
# The path the captured payloads show instead of the temporary study directory.
STUDY_PLACEHOLDER = {'binary': '/studies/bank marketing "demo"', 'regression': '/studies/auto mpg'}
OUT = HERE / 'captured'


@contextlib.contextmanager
def environment(**extra):
    saved = {k: os.environ.get(k) for k in extra}
    os.environ.update(extra)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run(*argv) -> tuple[int, dict]:
    outcome = cli.run([str(a) for a in argv])
    return outcome.exit_code, json.loads(json.dumps(outcome.payload))


class Capture:
    def __init__(self, root: Path):
        self.root = root
        self.items: dict[str, dict] = {}

    def save(self, name, task, argv, code, payload, note=''):
        text = json.dumps(payload)
        for t, placeholder in STUDY_PLACEHOLDER.items():
            text = text.replace(json.dumps(str(self.root / t))[1:-1], json.dumps(placeholder)[1:-1])
        text = text.replace(json.dumps(str(self.root))[1:-1], '/tmp/capture')
        # WP-A7: the engine's checkout (case files, the notebooks' launch commands) reads
        # the same in every checkout.
        text = text.replace(json.dumps(str(REPO))[1:-1], '/hypotrail')
        payload = json.loads(text)
        self.items[name] = {'about': {'schema': payload.get('schema'), 'task': task, 'exit_code': code,
                                      'source': 'captured', 'argv': [str(a) for a in argv
                                                                     if str(self.root) not in str(a)],
                                      'note': note}, 'payload': payload}
        return payload

    def read(self, name, task, study, *argv, note='', expect=(0,)):
        code, payload = run(*argv, '--study', study)
        assert code in expect, (name, code, payload)
        return self.save(name, task, argv, code, payload, note)


def binary(cap: Capture) -> None:
    study = cap.root / 'binary'
    flow = fk.Flow(study, BANK, prefix='b')
    flow.init()
    flow.decide('prediction_time', 'before the first contact of the campaign, from the client file')
    flow.decide('feature_availability', fk.availability(BANK, duration='not_available', day='not_available',
                                                         month='not_available', campaign='not_available',
                                                         contact='uncertain_included'))
    flow.decide('split', fk.SPLIT)
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    # WP-A7: the structural quality check and the single-feature signal (leakage detector).
    for activity in ('split', 'eda.target_rate', 'eda.special_values', 'eda.quality',
                     'eda.single_feature_signal'):
        flow.run(activity)
    cap.save('run.rate_by.binary', 'binary', ['run', 'eda.rate_by', '--column=job'], 0,
             flow.run('eda.rate_by', '--column=job'))
    cap.save('run.eda_distribution.binary', 'binary', ['run', 'eda.distribution', '--column=age'], 0,
             flow.run('eda.distribution', '--column=age'))
    flow.run('eda.distribution', '--column=job')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('policy.evaluate', '--rule', 'threshold:0.2')
    flow.decide('policy', 'threshold:0.2', words='Yes, call everyone scored at 0.2 or more')
    flow.run('policy.evaluate', '--rule', 'capacity:100')
    code, out = run('decide', 'propose', 'policy', '--value', 'capacity:100', '--restatement',
                    'Call the 100 clients with the highest scores.', '--rationale',
                    'The team can make 100 calls per wave.', '--request-id', 'b-prop',
                    '--expected-revision', flow.rev(), '--study', study)
    cap.save('decide.propose.binary', 'binary', ['decide', 'propose', 'policy'], code, out)
    pid = out['result']['proposal_id']
    cap.read('summary.v0.binary', 'binary', study, 'status', '--summary', '--json')
    # WP-A7: the data card (a read of the Data & EDA tab).
    cap.read('data.binary', 'binary', study, 'data', '--json')
    cap.read('summary.binary', 'binary', study, 'status', '--summary', '--digest', '--json')
    cap.read('decisions.binary', 'binary', study, 'decisions', '--json')
    cap.read('preview_effects.binary', 'binary', study, 'preview', 'effects', pid, '--json')
    cap.read('proposal_draft.binary', 'binary', study, 'preview', 'proposal', 'policy', '--value=capacity:100', '--json')
    cap.read('proposal_draft.binary.unevaluated', 'binary', study, 'preview', 'proposal', 'policy',
             '--value=capacity:150', '--json')
    cap.read('preview.binary', 'binary', study, 'preview', 'policy', '--rule', 'capacity:100', '--intervals', '--json')
    evidence = cap.read('evidence.binary', 'binary', study, 'evidence', '--json')
    logistic = next(r['result_id'] for r in evidence['results'] if r['slot'] == 'fit.logistic' and r['current'])
    cap.read('evidence.binary.detail', 'binary', study, 'evidence', '--result', logistic, '--json')
    cap.read('error.unknown_result', 'binary', study, 'evidence', '--result', 'a' * 64, '--json', expect=(2,))
    cap.read('explain.binary', 'binary', study, 'explain', '--json')
    cap.read('render.binary', 'binary', study, 'render', '--json', expect=(0, 3))
    cap.read('check.binary', 'binary', study, 'check', '--json', expect=(0, 2, 3))
    cap.read('session_report.binary', 'binary', study, 'session-report', '--json')
    rev = flow.rev()
    cap.read('error.stale_revision', 'binary', study, 'decide', 'confirm', pid, '--user-words=Yes, call the top 100',
             '--channel', 'webview', '--request-id', 'b-stale', '--expected-revision', rev - 1, '--json', expect=(2,))
    cap.read('error.bare_acknowledgement', 'binary', study, 'decide', 'confirm', pid, '--user-words=ok',
             '--channel', 'webview', '--request-id', 'b-ok', '--expected-revision', rev, '--json', expect=(2,))
    cap.read('error.delegation_needs_basis', 'binary', study, 'decide', 'confirm', pid,
             '--user-words=Use your recommended default', '--channel', 'webview', '--request-id', 'b-deleg',
             '--expected-revision', rev, '--json', expect=(2,))
    with environment(HYPOTRAIL_READ_ONLY='1'):
        cap.read('error.read_only', 'binary', study, 'decide', 'withdraw', pid, '--request-id', 'b-ro',
                 '--expected-revision', rev, '--json', expect=(2,))
    # The export pack (C7) and its refusal on a non-empty target.
    pack = cap.root / 'packs' / f'revision-{rev}'
    out = cap.read('export.binary', 'binary', study, 'export', 'handoff', f'--out={pack}', '--json', expect=(0, 3))
    cap.save('handoff.binary', 'binary', [], 0, json.loads((pack / 'handoff.json').read_text(encoding='utf-8')))
    cap.read('error.export_target_exists', 'binary', study, 'export', 'handoff', f'--out={pack}', '--json',
             expect=(2,))
    assert out['ok'] is True
    # A webview proposal (C9), then its withdrawal and a confirmation on clones.
    web = fk.clone(study, cap.root / 'binary-web')
    code, out = run('decide', 'propose', 'policy', '--value', 'capacity:100', '--restatement',
                    'Call the 100 clients with the highest scores.', '--rationale', 'Chosen in the panel.',
                    '--channel', 'webview', '--request-id', 'b-web', '--expected-revision', rev, '--study', web)
    cap.save('decide.propose.webview.binary', 'binary', ['decide', 'propose', 'policy', '--channel', 'webview'],
             code, out)
    web_pid = out['result']['proposal_id']
    confirmed = fk.clone(web, cap.root / 'binary-confirm')
    cap.read('decide.withdraw.binary', 'binary', web, 'decide', 'withdraw', web_pid, '--request-id', 'b-wd',
             '--expected-revision', rev + 1, '--json')
    cap.read('decide.confirm.binary', 'binary', confirmed, 'decide', 'confirm', web_pid,
             '--user-words=Yes, call the 100 best-scored clients in each wave', '--channel', 'webview',
             '--actor', 'user', '--request-id', 'b-conf', '--expected-revision', rev + 1, '--json')
    # A hold on the policy blocks the confirmation (P2) and the preview says so (C3).
    held = fk.clone(study, cap.root / 'binary-hold')
    run('decide', 'note', '--about', 'policy', '--text', 'Only if the call centre confirms the wave size',
        '--request-id', 'b-note', '--expected-revision', rev, '--study', held)
    cap.read('preview_effects.binary.blocked', 'binary', held, 'preview', 'effects', pid, '--json')
    cap.read('error.decision_on_hold', 'binary', held, 'decide', 'confirm', pid,
             '--user-words=Yes, call the 100 best-scored clients', '--channel', 'webview', '--request-id', 'b-held',
             '--expected-revision', rev + 1, '--json', expect=(2,))
    # An interrupted execution (a real process killed by the fault hook), then its
    # acknowledgement in the junior's words (W6).
    broken = fk.clone(study, cap.root / 'binary-broken')
    _killed_run(broken, rev)
    summary = cap.read('summary.binary.health', 'binary', broken, 'status', '--summary', '--digest', '--json')
    pending = [e['execution_id'] for e in summary['executions']['interrupted']
               + summary['executions']['suspected_interrupted']]
    if pending:
        cap.read('run.acknowledge.binary', 'binary', broken, 'run', '--acknowledge-interruption', pending[0],
                 '--user-words=I know this run stopped and its outcome is unknown', '--request-id', 'b-ack',
                 '--expected-revision', run('status', '--study', broken)[1]['revision'], '--json')


def _killed_run(study: Path, rev: int) -> None:
    """``run`` killed after its reservation (``HYPOTRAIL_FAULT=run_after_reserve``)."""
    import subprocess

    subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'eda.distribution', '--column=balance',
                    '--request-id', 'b-fault', '--expected-revision', str(rev), '--json', '--study', str(study)],
                   cwd=study, env=fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_after_reserve'),
                   capture_output=True, text=True, timeout=300, check=False)


def regression(cap: Capture) -> None:
    study = cap.root / 'regression'
    flow = fk.Flow(study, AUTO, prefix='a')
    flow.init()
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed, '
                                   'before its fuel efficiency is measured')
    flow.decide('feature_availability', fk.availability(AUTO, acceleration='uncertain_excluded'))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'eda.quality',
                     'eda.single_feature_signal'):
        flow.run(activity)
    flow.run('eda.mean_by', '--column=model_year')
    cap.save('run.eda_distribution.regression', 'regression', ['run', 'eda.distribution', '--column=weight'], 0,
             flow.run('eda.distribution', '--column=weight'))
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.run('evaluate.regression')
    code, out = run('decide', 'propose', 'model_choice', '--value', 'fit.linear', '--restatement',
                    'Adopt the linear model.', '--rationale', 'Lower error on later years.', '--request-id', 'a-prop',
                    '--expected-revision', flow.rev(), '--study', study)
    assert code == 0, out
    pid = out['result']['proposal_id']
    cap.read('summary.v0.regression', 'regression', study, 'status', '--summary', '--json')
    cap.read('data.regression', 'regression', study, 'data', '--json')
    cap.read('summary.regression', 'regression', study, 'status', '--summary', '--digest', '--json')
    cap.read('decisions.regression', 'regression', study, 'decisions', '--json')
    cap.read('preview_effects.regression', 'regression', study, 'preview', 'effects', pid, '--json')
    cap.read('proposal_draft.regression', 'regression', study, 'preview', 'proposal', 'model_choice',
             '--value=fit.linear', '--json')
    cap.read('evidence.regression', 'regression', study, 'evidence', '--json')
    cap.read('explain.regression', 'regression', study, 'explain', '--json')
    cap.read('session_report.regression', 'regression', study, 'session-report', '--json')


def capture(root: Path) -> dict[str, dict]:
    """Every captured scenario: ``{name: {about, payload}}`` (the studies live in ``root``)."""
    cap = Capture(root)
    with environment(HYPOTRAIL_SESSION_LOG='1'):
        binary(cap)
        regression(cap)
    return cap.items


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else OUT
    with tempfile.TemporaryDirectory(prefix='hypotrail capture "q" ') as tmp:
        items = capture(Path(tmp))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, item in sorted(items.items()):
        (out / f'{name}.json').write_text(json.dumps(item, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(items)} payloads written to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
