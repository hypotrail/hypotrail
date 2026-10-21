"""``HYPOTRAIL_READ_ONLY=1`` refuses every mutating command (review finding H3).

A notebook kernel sets the variable; a CLI process started from it must not decide,
acknowledge, initialise, run, or render. Each command runs as a real subprocess
(the reviewer's ``t4.py``), is refused with ``read_only`` (exit 2), and leaves every file
under ``.hypotrail/`` unchanged. Studies live in ``tmp_path``.
"""
from __future__ import annotations

import pytest

from mlkit.study import commands as cmd, executions as ex
from mlkit.study.errors import StudyError

import flowkit as fk
from flowkit import Flow

RO = {'HYPOTRAIL_READ_ONLY': '1'}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory, synthetic_case_dir):
    """Pauses confirmed, an open proposal, and an interrupted execution."""
    study = fk.prepare(synthetic_case_dir, tmp_path_factory.mktemp('ro') / 'study', upto='pauses')
    work = tmp_path_factory.mktemp('rocwd')
    flow = Flow(study, synthetic_case_dir, prefix='ro')
    proc = fk.spawn('run', 'split', '--request-id', 'dying', '--expected-revision', flow.rev(),
                    '--study', study, cwd=work,
                    extra_env={'HYPOTRAIL_TEST_HOOKS': '1', 'HYPOTRAIL_FAULT': 'run_after_reserve'})
    proc.communicate(timeout=300)
    flow.run('split', expect=4)            # detects the interruption
    flow.call('decide', 'propose', 'prediction_time', '--value', 'At signup', '--restatement',
              'You predict at signup.', '--rationale', 'Earliest.', '--request-id', 'pp',
              '--expected-revision', flow.rev(), '--study', study)
    return study


def _commands(study, pid, rev):
    mut = ('--expected-revision', rev, '--study', study)
    return {
        'decide propose': ('decide', 'propose', 'prediction_time', '--value', 'At signup',
                           '--restatement', 'At signup.', '--rationale', 'x',
                           '--request-id', 'ro1', *mut),
        'decide confirm': ('decide', 'confirm', pid, '--user-words',
                           'we predict at signup time', '--request-id', 'ro2', *mut),
        'decide withdraw': ('decide', 'withdraw', pid, '--request-id', 'ro3', *mut),
        'run': ('run', 'split', '--request-id', 'ro4', *mut),
        'run --acknowledge-interruption': (
            'run', '--acknowledge-interruption', ex.execution_id('dying'), '--user-words',
            'the split was interrupted, record it', '--request-id', 'ro5', *mut),
        'render': ('render', '--study', study),
    }


@pytest.mark.parametrize('name', ['decide propose', 'decide confirm', 'decide withdraw', 'run',
                                  'run --acknowledge-interruption', 'render'])
def test_every_mutating_command_is_refused_read_only(prepared, tmp_path, synthetic_case_dir, name):
    study = fk.clone(prepared, tmp_path / 'study')
    flow = Flow(study, synthetic_case_dir)
    [pid] = [p for p, v in flow.state()['proposals'].items() if v['status'] == 'open']
    before = fk.tree_digest(study)
    argv = _commands(study, pid, flow.rev())[name]
    code, out = fk.hyp(*argv, cwd=tmp_path, extra_env=RO)
    assert (code, out['error']['code']) == (2, 'read_only'), out
    assert fk.tree_digest(study) == before


def test_init_is_refused_read_only(tmp_path, synthetic_case_dir):
    target = tmp_path / 'new'
    code, out = fk.hyp('init', '--case', synthetic_case_dir, '--study', target, cwd=tmp_path,
                       extra_env=RO)
    assert (code, out['error']['code']) == (2, 'read_only'), out
    assert not target.exists()


def test_the_writer_entry_points_refuse_in_process(prepared, tmp_path, monkeypatch):
    study = fk.clone(prepared, tmp_path / 'study')
    before = fk.tree_digest(study)
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    from mlkit.study.store import StudyStore
    calls = (lambda: cmd.apply(study, action=cmd.ACTION_WITHDRAW,
                               params={'proposal_id': 'p_4', 'reason': None},
                               request_id='x', expected_revision=0),
             lambda: StudyStore(study).execute({}, {}),
             lambda: ex.acknowledge(study, 'e_x', request_id='y', expected_revision=0,
                                    user_words='the split was interrupted'),
             lambda: cmd.init(tmp_path / 'case-missing', tmp_path / 'other'))
    for call in calls:
        with pytest.raises(StudyError) as err:
            call()
        assert err.value.code == 'read_only'
    assert fk.tree_digest(study) == before
