"""Capture real engine payloads for the companion's fixtures (WP-I).

    uv run --project framework python clients/vscode-companion/test/fixtures/capture.py [OUT]

builds temporary studies outside the repository, Bank Marketing (binary; WP-B5 adds a
cross-validated Bank study whose final test is opened once, then changed after) and Auto MPG
(regression, and since L3 a French Auto MPG study), drives them through the ``hypotrail``
CLI code path (``mlkit.study.cli.run``, the code a CLI process runs; fault-injected runs are
real processes), and writes one file
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
case's own baseline, logistic, and linear fits on the public data, as the engine tests do, and
(v0.3, WP-K) the three variants of ADR 0007 (a stronger penalty, an Explainable Boosting
Machine, histogram gradient boosting) on the public Bank rows, for the selection and family
cards of the Evidence tab.
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
SHOPPERS = REPO / 'use-cases' / 'online-shoppers'
# The path the captured payloads show instead of the temporary study directory.
STUDY_PLACEHOLDER = {'binary': '/studies/bank marketing "demo"', 'regression': '/studies/auto mpg',
                     # L3 (owner session 2026-10-26): a French Auto MPG study.
                     'french': '/studies/auto mpg fr'}
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
    # v0.3 (WP-E2): a skewed column (zeros apart, log bins) and the predictor matrix (R17, R28).
    flow.run('eda.distribution', '--column=previous')
    cap.save('run.eda_correlation.binary', 'binary', ['run', 'eda.correlation'], 0, flow.run('eda.correlation'))
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.run('policy.evaluate', '--rule', 'threshold:0.2')
    flow.decide('policy', 'threshold:0.2', words='Yes, call everyone scored at 0.2 or more')
    # v0.3 (WP-F1, R28): the plan runs the development diagnostics at the adopted rule
    # before it moves on, so the captured study follows it (it stays at the final test).
    cap.save('run.diag.binary', 'binary', ['run', 'diag.binary'], 0, flow.run('diag.binary'))
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
    # v0.3 (WP-K): the full view at the same point (the trial budget and the family shortlist).
    cap.read('status.binary', 'binary', study, 'status', '--json')
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
    # WP-B4: the development diagnostics are captured above, where the plan runs them.
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


def _killed_run(study: Path, rev: int, column: str = 'balance') -> None:
    """``run`` killed after its reservation (``HYPOTRAIL_FAULT=run_after_reserve``)."""
    import subprocess

    subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'eda.distribution', f'--column={column}',
                    '--request-id', 'b-fault', '--expected-revision', str(rev), '--json', '--study', str(study)],
                   cwd=study, env=fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_after_reserve'),
                   capture_output=True, text=True, timeout=300, check=False)


OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'
CONCLUSION_TEXT = ('The development evidence and the final test, opened once, are what the study '
                   'can cite; it does not show future performance or a causal effect.')


def _run_pending(flow) -> dict:
    """Run the activities ``next_action`` asks for, as given, until it asks something else;
    that next action."""
    for _ in range(10):
        nxt = flow.view()['next_action']
        if nxt['kind'] != 'run':
            return nxt
        flow.run(nxt['activity'])
    raise AssertionError(nxt)


def cross_validated(cap: Capture) -> None:
    """WP-B5: a Bank study with the engine's cross-validation (5 stratified folds), the
    default variant, ``share:p`` rules, the final test opened once in the junior's words,
    then a calling rule changed after the opening (``post_final_test``)."""
    from mlkit.study import state as st

    study = cap.root / 'binary-cv'
    flow = fk.Flow(study, BANK, prefix='v')
    flow.init()
    flow.decide('prediction_time', 'before the first contact of the campaign, from the client file')
    flow.decide('feature_availability', fk.availability(BANK, duration='not_available', day='not_available',
                                                         month='not_available', campaign='not_available',
                                                         contact='uncertain_included'))
    flow.decide('split', st.b1_default_value(flow.state(), 'split'))
    flow.model_decisions()
    for activity in ('split', 'eda.target_rate'):
        flow.run(activity)
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'share:0.1', '--rule', 'capacity:100')
    flow.decide('policy', 'share:0.1', words='Yes, I adopt calling the top tenth, because the team can make that many calls')
    value = st.b1_default_value(flow.state(), 'final_test')
    code, out = run('decide', 'propose', 'final_test', '--value-json', json.dumps(value), '--restatement',
                    'You open the sealed final test once, for the chosen configuration.', '--rationale',
                    'The model and the rule are chosen.', '--request-id', 'v-open', '--expected-revision',
                    flow.rev(), '--study', study)
    assert code == 0, out
    pid = out['result']['proposal_id']
    # WP-B5 (with WP-B4): the development diagnostics before the opening.
    cap.save('run.diag.binary.cv', 'binary', ['run', 'diag.binary'], 0, flow.run('diag.binary'))
    cap.read('summary.binary.cv.opening', 'binary', study, 'status', '--summary', '--digest', '--json',
             note='Bank, cross-validation, final test sealed, its opening proposed (waits for the junior).')
    cap.read('evidence.binary.cv.sealed', 'binary', study, 'evidence', '--json',
             note='Bank, cross-validation, variant compared, share rules, final test still sealed.')
    out = flow.call('decide', 'confirm', pid, '--user-words', OPEN_WORDS, '--request-id', flow.rid(),
                    '--expected-revision', flow.rev(), '--study', study)
    assert out['result']['opening']['status'] == 'promoted', out
    # The final diagnostics, once the final test is opened (WP-B4).
    cap.save('run.diag.final_test', 'binary', ['run', 'diag.final_test'], 0, flow.run('diag.final_test'))
    # A later rule, chosen after the opening: "after the final test".
    flow.run('policy.evaluate', '--rule', 'share:0.1', '--rule', 'share:0.2')
    cap.read('proposal_draft.binary.share', 'binary', study, 'preview', 'proposal', 'policy', '--value=share:0.2',
             '--json')
    cap.read('preview.binary.share', 'binary', study, 'preview', 'policy', '--rule', 'share:0.2', '--intervals',
             '--json')
    flow.decide('policy', 'share:0.2', words='Yes, I adopt the top fifth now, because the team grew')
    # The new rule makes the development diagnostics stale; computed again, after the opening.
    flow.run('diag.binary')
    cap.read('summary.binary.cv', 'binary', study, 'status', '--summary', '--digest', '--json',
             note='Bank, cross-validation, final test opened, then the calling rule changed after it.')
    cap.read('evidence.binary.cv', 'binary', study, 'evidence', '--json',
             note='Bank, cross-validation, final test opened, then the calling rule changed after it.')
    cap.read('status.binary.cv', 'binary', study, 'status', '--json',
             note='Bank, cross-validation, final test opened, then the calling rule changed after it.')
    cap.read('decisions.binary.cv', 'binary', study, 'decisions', '--json')
    cap.read('error.final_test_already_opened', 'binary', study, 'decide', 'propose', 'final_test', '--value-json',
             json.dumps(st.b1_default_value(flow.state(), 'final_test')), '--restatement',
             'You open the final test again.', '--rationale', 'x', '--request-id', 'v-again',
             '--expected-revision', flow.rev(), '--json', expect=(2,))
    # Owner session 2026-10-26, captured last so the payloads above keep their state. L1 (R2c),
    # L2 (R16): once the pending activities have run, the conclusion is a choice the chat asks
    # before any proposal: the summary carries the engine's options (``choice_options``).
    nxt = _run_pending(flow)
    assert nxt['kind'] == 'propose' and nxt['decision'] == 'conclusion', nxt
    conclusion = cap.read('summary.binary.cv.conclusion', 'binary', study, 'status', '--summary', '--digest',
                          '--json', note='Bank, cross-validation, final test opened, rule changed after it: the '
                                         'conclusion is a choice the chat asks (next_action.choice_options).')
    assert conclusion['next_action'].get('choice_options'), conclusion['next_action']
    # L7 (D15): the conclusion adopted from the engine's options; at ``done`` the summary says
    # what comes after the study (``next_action.after_study``).
    option = nxt['choice_options'][0]
    flow.decide('conclusion', {**option['value'], 'text': CONCLUSION_TEXT})
    done = cap.read('summary.binary.cv.done', 'binary', study, 'status', '--summary', '--digest', '--json',
                    note='Bank, cross-validation, the conclusion adopted: every step is done '
                         '(next_action.after_study).')
    assert done['next_action']['kind'] == 'done' and done['next_action'].get('after_study'), done['next_action']


FAMILY_VARIANTS = {'variants': [
    {'kind': 'regularisation', 'strength': 'strong', 'question': 'Does a stronger penalty rank the clients as well?'},
    {'kind': 'family', 'family': 'ebm',
     'question': 'Does an explainable boosting machine follow age and balance more closely?'},
    {'kind': 'family', 'family': 'hgb', 'question': 'Does gradient boosting rank the clients better?'}]}


def families(cap: Capture) -> None:
    """v0.3 (WP-F1, WP-K): a cross-validated Bank study whose variant decision names three
    variants (a stronger penalty, an Explainable Boosting Machine, histogram gradient
    boosting), so the budget is used, all fitted and compared by one evaluation, with the
    development diagnostics before and after the variants. The evidence carries the stored
    ``model_selection`` and each family's own diagnostics; the full view carries the live
    ``model_selection`` (with the budget) and the shortlist ``model_families``."""
    from mlkit.study import state as st

    study = cap.root / 'binary-families'
    flow = fk.Flow(study, BANK, prefix='m')
    flow.init()
    flow.decide('prediction_time', 'before the first contact of the campaign, from the client file')
    flow.decide('feature_availability', fk.availability(BANK, duration='not_available', day='not_available',
                                                         month='not_available', campaign='not_available',
                                                         contact='uncertain_included'))
    flow.decide('split', st.b1_default_value(flow.state(), 'split'))
    flow.model_decisions()
    for activity in ('split', 'eda.target_rate', 'fit.baseline', 'fit.logistic', 'diag.binary'):
        flow.run(activity)
    # The variant proposal waits for the junior: the Decisions card shows the budget it spends.
    code, out = run('decide', 'propose', 'model_variant', '--value-json', json.dumps(FAMILY_VARIANTS),
                    '--restatement', 'You compare three variants of the candidate, each with its question.',
                    '--rationale', 'One penalty change and two model families, inside the budget of three.',
                    '--request-id', 'm-variants', '--expected-revision', flow.rev(), '--study', study)
    assert code == 0, out
    pid = out['result']['proposal_id']
    cap.read('summary.binary.families.proposal', 'binary', study, 'status', '--summary', '--digest', '--json',
             note='Bank, cross-validation, the three-variant proposal waits for the junior.')
    cap.read('status.binary.families.proposal', 'binary', study, 'status', '--json',
             note='The full view while the three-variant proposal waits: nothing of the budget used yet.')
    flow.call('decide', 'confirm', pid, '--user-words', fk.default_words('model_variant'),
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study', study)
    for slot in ('fit.variant', 'fit.variant:2', 'fit.variant:3'):
        flow.run(slot)
    flow.run('policy.evaluate', '--rule', 'share:0.1', '--rule', 'capacity:100')
    flow.run('diag.binary')
    cap.read('summary.binary.families', 'binary', study, 'status', '--summary', '--digest', '--json',
             note='Bank, cross-validation, three variants (penalty, EBM, boosting) compared, budget used.')
    cap.read('evidence.binary.families', 'binary', study, 'evidence', '--json',
             note='Bank, cross-validation, three variants (penalty, EBM, boosting) compared, budget used.')
    cap.read('decisions.binary.families', 'binary', study, 'decisions', '--json')
    cap.read('status.binary.families', 'binary', study, 'status', '--json',
             note='The full view of the same study: the live model selection and the family shortlist.')


def scenario(cap: Capture) -> None:
    """WP-B5: the full view of a new Online Shoppers study, for its teaching scenario's
    default share (``view.scenario_defaults``), which the What if? tab labels."""
    study = cap.root / 'shoppers'
    flow = fk.Flow(study, SHOPPERS, prefix='s')
    flow.init()
    cap.read('status.shoppers', 'binary', study, 'status', '--json',
             note='Online Shoppers right after init: the scenario default share of the case.')


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
    flow.run('eda.correlation')       # v0.3 (WP-E2, R28)
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
    cap.read('status.regression', 'regression', study, 'status', '--json')
    cap.read('explain.regression', 'regression', study, 'explain', '--json')
    cap.read('session_report.regression', 'regression', study, 'session-report', '--json')
    # WP-B4: the development diagnostics.
    cap.save('run.diag.regression', 'regression', ['run', 'diag.regression'], 0,
             flow.run('diag.regression'))
    # WP-B5: the evidence with the development diagnostics of a regression study.
    cap.read('evidence.regression.diag', 'regression', study, 'evidence', '--json',
             note='Auto MPG with its development diagnostics (diag.regression).')


def french(cap: Capture) -> None:
    """L3 (owner session 2026-10-26, R4, D4b): a French Auto MPG study, its case translated by
    ``case.l10n.yaml``: the summary with ``texts`` in both languages, the data card with the
    case's statements in both languages, the evidence with the EDA results' ``texts`` and
    ``question_junior``, the Learn tab in French, and an open proposal restated in French and
    in English."""
    study = cap.root / 'french'
    flow = fk.Flow(study, AUTO, prefix='f')
    code, out = run('init', '--case', AUTO, '--lang', 'fr', '--study', study)
    assert code == 0, out
    flow.decide('prediction_time', 'quand les caractéristiques techniques sont fixées')
    flow.decide('feature_availability', fk.availability(AUTO, acceleration='uncertain_excluded'))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'eda.quality'):
        flow.run(activity)
    flow.run('eda.mean_by', '--column=model_year')
    flow.run('fit.baseline')
    flow.run('fit.linear')
    flow.run('evaluate.regression')
    code, out = run('decide', 'propose', 'model_choice', '--value', 'fit.linear', '--restatement',
                    'Adopt the linear model.', '--restatement-fr', 'Adopter le modèle linéaire.',
                    '--rationale', 'Erreur plus faible sur les années récentes.', '--request-id',
                    'f-prop', '--expected-revision', flow.rev(), '--study', study)
    assert code == 0, out
    note = 'A French Auto MPG study (L3): the engine texts in both languages.'
    cap.read('summary.regression.fr', 'regression', study, 'status', '--summary', '--digest',
             '--json', note=note)
    cap.read('data.regression.fr', 'regression', study, 'data', '--json', note=note)
    cap.read('evidence.regression.fr', 'regression', study, 'evidence', '--json', note=note)
    cap.read('explain.regression.fr', 'regression', study, 'explain', '--json', note=note)
    cap.read('decisions.regression.fr', 'regression', study, 'decisions', '--json', note=note)
    cap.read('status.regression.fr', 'regression', study, 'status', '--json', note=note)


# The five states of the approved one-page mockup (ADR 0004 d13, PANEL-ONE-PAGE-PLAN E-8) on
# an English Auto MPG study, read with the panel on at stage v3, so ``next_action.panel`` is
# the engine's line (contract P1, CLI-CONTRACT §17.1).
PANEL_ON = {'HYPOTRAIL_COMPANION': '1', 'HYPOTRAIL_COMPANION_STAGE': 'v3'}
HOLD_WORDS = 'Wait: I want to check how the six missing horsepower values are handled before I keep this preparation'
RESOLVE_WORDS = 'The team confirmed how horsepower is prepared, so the hold is over'
PREPARATION_WORDS = 'Yes, add an indicator for the missing horsepower values, because they may carry information'
CHOICE_WORDS = 'Yes, I keep the linear model, because its error is the lowest and it is the simplest'
AUTO_REVIEW_WORDS = 'Yes, I adopt this as it stands, because I read it and it fits my study'


def _summary(cap: Capture, name: str, study: Path, note: str) -> dict:
    with environment(**PANEL_ON):
        return cap.read(name, 'regression', study, 'status', '--summary', '--digest', '--json', note=note)


def one_page(cap: Capture) -> None:
    """E-8: step 1 (the data card and its seeded sample), the model choice asked as a choice
    (R16) with a chart requested from the panel (W4), the preparation to confirm again (then,
    on the same study, a run interrupted), the review of an ``init --automation
    until_final_test`` study, and the end (the final test opened once, the conclusion
    adopted)."""
    from mlkit.study import governance, state as st

    study = cap.root / 'regression-onepage'
    flow = fk.Flow(study, AUTO, prefix='o')
    flow.init()
    # The agent regenerates the deliverables after every change, the creation included.
    code, out = run('render', '--json', '--study', study)
    assert code == 0, out
    _summary(cap, 'summary.regression.step1', study, 'Auto MPG at step 1: the data card and its seeded sample.')
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed, '
                                   'before its fuel efficiency is measured')
    flow.decide('feature_availability', fk.availability(AUTO, acceleration='uncertain_excluded'))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()
    _run_pending(flow)
    flow.variant()
    nxt = _run_pending(flow)
    assert nxt['kind'] == 'propose' and nxt['decision'] == 'model_choice' and nxt.get('choice_options'), nxt
    # W4: a chart requested from the panel, filed under its step like any other.
    code, out = run('run', 'eda.mean_by', '--column=model_year', '--channel', 'webview', '--request-id', 'o-w4',
                    '--expected-revision', flow.rev(), '--study', study)
    assert code == 0, out
    _summary(cap, 'summary.regression.choice', study,
             'Auto MPG at the model choice, asked as a choice (R16); a chart requested from the panel.')
    # The panel's other reads of this study at the choice, for every one-page state (the same
    # result ids as the summaries).
    note = 'The one-page Auto MPG study at the model choice (the reads behind the five states).'
    cap.read('data.regression.onepage', 'regression', study, 'data', '--json',
             note=note + ' The seeded sample and the special-value rows (CLI-CONTRACT §17.3, §17.4).')
    for name, argv in (('evidence', ['evidence']), ('decisions', ['decisions']), ('explain', ['explain']),
                       ('status', ['status'])):
        cap.read(f'{name}.regression.onepage', 'regression', study, *argv, '--json', note=note)
    # The preparation changed after the models (an indicator for the missing horsepower
    # values: the linear model and its evaluation are stale), then put on hold in the junior's
    # words and the hold resolved: the preparation is to confirm again (``reconfirm``).
    reopened = fk.clone(study, cap.root / 'regression-reopened')
    held = fk.Flow(reopened, AUTO, prefix='r')
    held.decide('preprocessing', {**dict(governance.DEFAULT_PREPROCESSING), 'missing': 'indicator'},
                words=PREPARATION_WORDS)
    note_id = held.call('decide', 'note', '--about', 'preprocessing', '--text', HOLD_WORDS, '--request-id',
                        held.rid(), '--expected-revision', held.rev(), '--study', reopened)['result']['note_id']
    held.call('decide', 'note', '--resolve', note_id, '--text', RESOLVE_WORDS, '--request-id', held.rid(),
              '--expected-revision', held.rev(), '--study', reopened)
    summary = _summary(cap, 'summary.regression.reopened', reopened,
                       'Auto MPG: the preparation changed after the models, then to confirm again after a resolved '
                       'hold; the linear model and its evaluation are stale.')
    assert summary['next_action']['kind'] == 'reconfirm', summary['next_action']
    assert summary['next_action']['decision'] == 'preprocessing', summary['next_action']
    # The same study after a chart run was killed after its reservation: the interruption
    # comes first in the engine's next action (CLI-CONTRACT §8, F1), the preparation stays
    # to confirm again in the path.
    _killed_run(reopened, held.rev(), column='horsepower')
    summary = _summary(cap, 'summary.regression.interrupted', reopened,
                       'The reopened Auto MPG study after a chart run was interrupted: the interruption is the next '
                       'action; the preparation stays to confirm again.')
    assert summary['next_action']['kind'] in ('outcome_unknown', 'acknowledge_interruption'), summary['next_action']
    assert summary['decisions']['preprocessing']['status'] == 'reconfirm_required', summary['decisions']
    # The end: the model chosen, the final test opened once, the conclusion adopted.
    flow.decide('model_choice', 'fit.linear', words=CHOICE_WORDS)
    nxt = _run_pending(flow)
    if nxt.get('decision') == 'final_test':
        value = st.b1_default_value(flow.state(), 'final_test')
        code, out = run('decide', 'propose', 'final_test', '--value-json', json.dumps(value), '--restatement',
                        'You open the sealed final test once, for the chosen model.', '--rationale',
                        'The model is chosen.', '--request-id', 'o-open', '--expected-revision', flow.rev(),
                        '--study', study)
        assert code == 0, out
        flow.call('decide', 'confirm', out['result']['proposal_id'], '--user-words', OPEN_WORDS,
                  '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study', study)
        nxt = _run_pending(flow)
    assert nxt['kind'] == 'propose' and nxt['decision'] == 'conclusion', nxt
    flow.decide('conclusion', {**nxt['choice_options'][0]['value'], 'text': CONCLUSION_TEXT})
    done = _summary(cap, 'summary.regression.done', study,
                    'Auto MPG at the end: the final test opened once, the conclusion adopted.')
    assert done['next_action']['kind'] == 'done', done['next_action']
    # The review of an automatic study: every decision waits for the junior's own words.
    auto = cap.root / 'regression-automatic'
    code, out = run('init', '--case', AUTO, '--automation', 'until_final_test', '--study', auto)
    assert code == 0, out
    code, out = run('automation', 'run', '--request-id', 'o-auto', '--expected-revision',
                    run('status', '--study', auto)[1]['revision'], '--study', auto)
    assert code == 0, out
    review = fk.Flow(auto, AUTO, prefix='u')
    nxt = review.view()['next_action']
    if nxt['kind'] == 'await_user_words' and nxt.get('review'):
        review.call('decide', 'confirm', nxt['proposal_id'], '--user-words', AUTO_REVIEW_WORDS,
                    '--request-id', review.rid(), '--expected-revision', review.rev(), '--study', auto)
    summary = _summary(cap, 'summary.regression.review', auto,
                       'Auto MPG created with --automation until_final_test: the review of its automatic decisions.')
    assert summary['review_queue'] and summary['review_queue']['items'], summary['review_queue']


def capture(root: Path) -> dict[str, dict]:
    """Every captured scenario: ``{name: {about, payload}}`` (the studies live in ``root``)."""
    cap = Capture(root)
    with environment(HYPOTRAIL_SESSION_LOG='1'):
        binary(cap)
        cross_validated(cap)
        families(cap)
        scenario(cap)
        regression(cap)
        french(cap)
        one_page(cap)
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
