"""Hypothesis state machine over the real engine operations (spec §15, A1).

Rules call the real CLI in-process (``cli.run``) and, for the crash rule, a real process
killed by the engine's fault hook. The oracle is a reduced model of rights and states,
written independently of the engine's code: it records what the "user" did (which proposals
were confirmed with which words, which requests were sent, which activity runs succeeded)
and checks properties that must hold whatever the engine decides to accept:

* a refused command (stale revision, unknown proposal, conflicting duplicate request,
  missing precondition) leaves every file of the study unchanged, except the writer lock's
  bookkeeping and the session log, which only ever grows by appending;
* a replayed request changes nothing and returns the same outcome;
* a confirmed decision always carries words this oracle sent for that very proposal;
  a proposal or a withdrawal never confirms anything, and a withdrawal never changes a
  confirmed value;
* revisions never decrease; exposure records only grow, even after a refusal, a failure or
  a crash; no final-test row is ever read before the final test is opened;
* after a decision change, a slot whose inputs changed is not reported current until it is
  computed again (the engine's own currency is read back and compared with the oracle's
  "last computed after last confirmation" ledger for the split);
* an interrupted execution blocks every run until it is acknowledged in the user's words.

Budget: derandomised, a fixed number of examples and steps (reproducible, a few minutes).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings, strategies as stg
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

import flowkit as fk
from mlkit.study import cli, read, state as st

CASE_ROOT = Path(tempfile.mkdtemp(prefix='hyp-case-'))
# Lock bookkeeping (who held the writer lock last) and the session log, which records every
# command, refused ones included (observation kit), by appending only (checked separately).
LOCK_FILES = ('writer.lock', 'events.jsonl')
SESSION_LOG = 'events.jsonl'
CASE_DIR = fk.make_case(CASE_ROOT, n_rows=200)['case'].parent
DECISIONS = ('prediction_time', 'feature_availability', 'split', 'success_criterion',
             'preprocessing')
ACTIVITIES = ('split', 'eda.quality', 'eda.target_rate', 'fit.baseline', 'fit.logistic')
WORDS = 'Yes, I want the {d} exactly as you stated it, number {n}'


def _digest(study):
    return {k: v for k, v in fk.tree_digest(study).items() if k not in LOCK_FILES}


def _call(*args):
    out = cli.run([str(a) for a in args])
    return out.exit_code, out.payload


class StudyMachine(RuleBasedStateMachine):
    @initialize(prepared=stg.booleans())
    def setup(self, prepared):
        self.root = Path(tempfile.mkdtemp(prefix='hyp-study-'))
        self.study = self.root / 'study'
        code, _ = _call('init', '--case', CASE_DIR, '--study', self.study)
        assert code == 0
        self.n = 0
        self.sent_words: dict[str, str] = {}        # proposal id -> words the oracle sent
        self.open_proposals: dict[str, str] = {}    # proposal id -> decision
        self.last_request = None                    # (args, payload)
        self.revision = self._state()['revision']
        self.exposure_ids: set[str] = set()
        self.final_keys = set(fk.partition_keys(self.study, 'final_test'))
        self.split_confirmed_at = None               # oracle ledger (revisions)
        self.split_run_at = None
        self.interrupted = False
        if prepared:
            # Half of the runs start at the model pauses (every framing decision confirmed in
            # the oracle's words, the split computed), so fits, changes and invalidations are
            # reachable within the step budget.
            for decision in DECISIONS:
                self.propose(decision, 0, True)
            self.run('split')

    def teardown(self):
        shutil.rmtree(getattr(self, 'root', CASE_ROOT / 'none'), ignore_errors=True)

    # -- helpers ---------------------------------------------------------------------------
    def _state(self):
        return read.open(self.study).state

    def _rid(self):
        self.n += 1
        return f'h{self.n}'

    def _value(self, decision, variant):
        state = self._state()
        if decision == 'prediction_time':
            return ['when the record is created, before the outcome',
                    'one week before the renewal date'][variant % 2]
        if decision == 'feature_availability':
            return fk.availability(CASE_DIR)
        if decision == 'split':
            value = dict(st.b1_default_value(state, 'split'))
            if 'seed' in value:
                value['seed'] = value['seed'] + variant % 2
            return value
        if decision == 'success_criterion':
            return fk.criterion(state)
        from mlkit.study import governance
        value = dict(governance.DEFAULT_PREPROCESSING)
        if variant % 2:
            value['missing'] = 'indicator'
        return value

    def _session_log(self):
        path = self.study / '.hypotrail' / SESSION_LOG
        return path.read_bytes() if path.exists() else b''

    def _refused_without_change(self, args):
        before = _digest(self.study)
        code, payload = _call(*args)
        assert code != 0, payload
        assert _digest(self.study) == before, payload['error']
        return payload['error']['code']

    # -- rules -----------------------------------------------------------------------------
    @rule(decision=stg.sampled_from(DECISIONS), variant=stg.integers(0, 3),
          confirm=stg.booleans())
    def propose(self, decision, variant, confirm):
        args = ('decide', 'propose', decision, '--value-json',
                json.dumps(self._value(decision, variant)), '--restatement',
                f'You decide the {decision} as stated.', '--rationale', 'It fits.',
                '--request-id', self._rid(), '--expected-revision', self._state()['revision'],
                '--study', self.study)
        before = _digest(self.study)
        code, payload = _call(*args)
        if code != 0:
            assert _digest(self.study) == before
            return
        self.last_request = (args, payload)
        pid = payload['result']['proposal_id']
        self.open_proposals[pid] = decision
        dec = self._state()['decisions'][decision]
        assert dec['proposal_id'] != pid or dec['status'] != 'confirmed' \
            or pid in self.sent_words                     # proposing never confirms
        if confirm:
            self.confirm(pid, variant)

    def confirm(self, pid, variant):
        words = WORDS.format(d=self.open_proposals[pid], n=variant)
        args = ('decide', 'confirm', pid, '--user-words', words, '--request-id', self._rid(),
                '--expected-revision', self._state()['revision'], '--study', self.study)
        before = _digest(self.study)
        code, payload = _call(*args)
        if code != 0:
            assert _digest(self.study) == before
            return
        self.sent_words[pid] = words
        self.last_request = (args, payload)
        if self.open_proposals[pid] == 'split':
            self.split_confirmed_at = self._state()['revision']
        self.open_proposals.pop(pid, None)

    @rule(data=stg.data())
    def withdraw(self, data):
        if not self.open_proposals:
            return
        pid = data.draw(stg.sampled_from(sorted(self.open_proposals)))
        decision = self.open_proposals[pid]
        before = self._state()['decisions'][decision]
        code, payload = _call('decide', 'withdraw', pid, '--request-id', self._rid(),
                              '--expected-revision', self._state()['revision'],
                              '--study', self.study)
        if code == 0:
            self.open_proposals.pop(pid)
            after = self._state()['decisions'][decision]
            if before['status'] == 'confirmed':
                assert (after['status'], after['value'], after['proposal_id']) == \
                    (before['status'], before['value'], before['proposal_id'])
            else:
                assert after['status'] != 'confirmed'

    @rule(activity=stg.sampled_from(ACTIVITIES))
    def run(self, activity):
        args = ('run', activity, '--request-id', self._rid(), '--expected-revision',
                self._state()['revision'], '--study', self.study)
        before = _digest(self.study)
        code, payload = _call(*args)
        if self.interrupted:
            assert code != 0 and payload['error']['code'] == 'interrupted_execution_pending'
            return
        if code != 0:
            # A refusal before the reservation writes nothing.
            assert _digest(self.study) == before, payload['error']
            return
        self.last_request = (args, payload)
        state = self._state()
        if payload['status'] in ('promoted', 'already_current'):
            assert state['current'].get(activity) == payload['result_id']
        if activity == 'split' and payload['status'] == 'promoted':
            self.split_run_at = state['revision']

    @rule()
    def stale_revision(self):
        rev = self._state()['revision']
        if rev == 0:
            return
        code = self._refused_without_change(('run', 'eda.quality', '--request-id', self._rid(),
                                             '--expected-revision', rev - 1, '--study',
                                             self.study))
        assert code in ('stale_revision', 'interrupted_execution_pending')

    @rule()
    def replay_last_request(self):
        if self.last_request is None:
            return
        args, payload = self.last_request
        before = _digest(self.study)
        code, again = _call(*args)
        assert _digest(self.study) == before
        if code == 0:
            if payload.get('status') == 'already_current':
                # No reservation, no receipt: answered from current state again.
                assert again.get('status') == 'already_current'
                assert again.get('result_id') == payload.get('result_id')
            else:
                assert again.get('replayed') is True
                assert again.get('result') == payload.get('result') or \
                    again.get('result_id') == payload.get('result_id')

    @rule()
    def conflicting_duplicate(self):
        if self.last_request is None:
            return
        args = list(self.last_request[0])
        rid = args[args.index('--request-id') + 1]
        conflicting = ['decide', 'propose', 'prediction_time', '--value-json',
                       json.dumps('another moment entirely'), '--restatement', 'x',
                       '--rationale', 'y', '--request-id', rid, '--expected-revision',
                       self._state()['revision'], '--study', self.study]
        code = self._refused_without_change(conflicting)
        assert code in ('idempotency_conflict', 'interrupted_execution_pending',
                        'invalid_request')

    @rule()
    def unknown_proposal(self):
        code = self._refused_without_change(
            ('decide', 'confirm', 'p-does-not-exist', '--user-words', 'yes I confirm',
             '--request-id', self._rid(), '--expected-revision', self._state()['revision'],
             '--study', self.study))
        assert code in ('unknown_proposal', 'ambiguous_confirmation',
                        'interrupted_execution_pending')

    @rule()
    def crash_during_a_run(self):
        if self.interrupted or 'split' not in self._state()['current']:
            return
        rev = self._state()['revision']
        env = fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_before_promote')
        proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'eda.quality',
                               '--request-id', self._rid(), '--expected-revision', str(rev),
                               '--study', str(self.study)], capture_output=True, text=True,
                              env=env, timeout=300)
        if proc.returncode == 70:                    # killed after its reservation
            self.interrupted = True
            # The next command records the interruption (run.recover) with the reads it had
            # planned, then refuses: from here on every refusal writes nothing.
            code, payload = _call('run', 'eda.quality', '--request-id', self._rid(),
                                  '--expected-revision', self._state()['revision'],
                                  '--study', self.study)
            assert code != 0 and payload['error']['code'] == 'interrupted_execution_pending'
            pending = self._state()['executions']['interrupted']
            assert pending
            unknown = [r for r in fk.exposure_records(self.study)
                       if r['execution_id'] in pending]
            assert unknown and all(r['result_id'] is None for r in unknown)

    @rule()
    def acknowledge(self):
        if not self.interrupted:
            return
        pending = self._state()['executions']['interrupted']
        assert pending
        eid = sorted(pending)[0]
        code, payload = _call('run', '--acknowledge-interruption', eid, '--user-words',
                              'I understand the outcome is unknown, go on', '--request-id',
                              self._rid(), '--expected-revision', self._state()['revision'],
                              '--study', self.study)
        assert code == 0, payload
        self.interrupted = bool(self._state()['executions']['interrupted'])

    # -- invariants ------------------------------------------------------------------------
    @invariant()
    def revisions_never_decrease_and_state_is_valid(self):
        if not hasattr(self, 'study'):
            return
        state = self._state()
        assert state['revision'] >= self.revision
        self.revision = state['revision']
        assert st.validate_state(state) == []

    @invariant()
    def the_session_log_only_appends(self):
        if not hasattr(self, 'study'):
            return
        log = self._session_log()
        previous = getattr(self, 'log', b'')
        assert log.startswith(previous)
        self.log = log

    @invariant()
    def confirmations_carry_the_users_words(self):
        if not hasattr(self, 'study'):
            return
        for did, dec in self._state()['decisions'].items():
            if dec['status'] == 'confirmed' and dec['confirmation']:
                pid = dec['proposal_id']
                assert self.sent_words.get(pid) == dec['confirmation'].get('user_words'), did

    @invariant()
    def exposure_only_grows_and_the_final_test_stays_unread(self):
        if not hasattr(self, 'study'):
            return
        records = fk.exposure_records(self.study)
        ids = {r['exposure_id'] for r in records}
        assert self.exposure_ids <= ids
        self.exposure_ids = ids
        assert not st.final_test_opened(self._state())
        for r in records:
            if r['purpose'] == 'sealed':
                continue
            assert r['partition'] != 'final_test'

    @invariant()
    def a_split_changed_after_its_run_is_not_current(self):
        if not hasattr(self, 'study') or self.split_confirmed_at is None:
            return
        study = read.open(self.study)
        if self.split_run_at is not None and self.split_run_at < self.split_confirmed_at \
                and 'split' in study.state['current']:
            current = study.currency(study.state['current']['split'])['current']
            entry = study.result(study.state['current']['split'])
            value = study.state['decisions']['split']['value']
            if entry['inputs'].get('decision') != value:
                assert not current


StudyMachine.TestCase.settings = settings(
    max_examples=int(os.environ.get('HYPOTRAIL_HYPOTHESIS_EXAMPLES', '12')),
    stateful_step_count=int(os.environ.get('HYPOTRAIL_HYPOTHESIS_STEPS', '20')),
    deadline=None, derandomize=True, suppress_health_check=list(HealthCheck),
    database=None)
TestStudyMachine = StudyMachine.TestCase
