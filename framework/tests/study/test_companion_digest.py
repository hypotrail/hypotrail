"""``status --summary --digest`` (CLI-CONTRACT-COMPANION §1, C1): moments, pauses, the
last-session boundary, and the digest kinds and sentences.

Unit tests on ``view.last_session`` and ``view.digest`` (the gap rule, the run kinds),
then the real code path (``cli.run``) on the synthetic binary case and on Auto MPG: each
confirmation, proposal, note and promoted run appears with its kind, a policy
reconfirmation names the decision, and a regression digest never uses the vocabulary of a
decision rule.
"""
from __future__ import annotations

import json
import re

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import cmd_session_report, read, texts, view

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
RULE_VOCABULARY = re.compile(r'threshold|capacity|precision|recall|policy|positive class', re.I)


def _record(revision, minute, action='decide.propose', **extra):
    return {'revision': revision, 'time': f'2026-10-18T09:{minute:02d}:00+00:00',
            'action': action, **extra}


# --- unit: the gap rule and the constants -------------------------------------------------

def test_constants_follow_the_contract():
    assert view.SESSION_GAP_MINUTES == cc.SESSION_GAP_MINUTES \
        == cmd_session_report.DEFAULT_GAP_MINUTES
    assert view.DIGEST_MAX_ITEMS == cc.DIGEST_MAX_ITEMS
    assert view.DIGEST_SUMMARY_KEYS == cc.DIGEST_SUMMARY_KEYS[len(cc.SUMMARY_KEYS):]
    assert view.DIGEST_ITEM_KEYS == cc.DIGEST_ITEM_KEYS
    assert view.DIGEST_KINDS == cc.DIGEST_KINDS
    assert view.DIGEST_COUNT_KEYS == cc.DIGEST_COUNT_KEYS
    assert view.DIGEST_INVALIDATION_KEYS == cc.DIGEST_INVALIDATION_KEYS
    for task in ('binary', 'regression'):
        # WP-A4: a new study's split pause also holds the success criterion and the
        # preprocessing; the session report's v0.1 table stays the table of an older study.
        pauses = {p: list(d) for p, d in cmd_session_report.TASK_PAUSES[task].items()}
        pauses[2] = ['split', 'success_criterion', 'preprocessing']
        # WP-B1: the third pause names the variant first and may open the final test.
        choice = pauses[3][0]
        pauses[3] = ['model_variant', choice, 'final_test', 'conclusion']
        assert view.pause_decisions(task) == pauses


def test_content_has_no_digits():
    raw = (fk.FRAMEWORK / 'mlkit/study/content/digest.yaml').read_text(encoding='utf-8')
    body = '\n'.join(line.split('#', 1)[0] for line in raw.splitlines())
    assert not re.search(r'\d', body.replace('digest/1', '')), body
    assert texts.load('digest')['schema'] == 'hypotrail.content.digest/1'


def test_last_session_is_the_latest_gap_of_more_than_twenty_minutes():
    one = [_record(1, 0), _record(2, 5), _record(3, 25)]       # 20 minutes is not a gap
    assert view.last_session(one) == {'boundary_revision': 1, 'boundary_time': one[0]['time'],
                                      'gap_minutes': None}
    two = [_record(1, 0), _record(2, 21), _record(3, 22), _record(4, 50), _record(5, 51)]
    assert view.last_session(two) == {'boundary_revision': 3, 'boundary_time': two[2]['time'],
                                      'gap_minutes': 28}
    across_hours = [_record(1, 0), {**_record(2, 0), 'time': '2026-10-18T10:20:30+00:00'}]
    assert view.last_session(across_hours)['gap_minutes'] == 80


class _Study:
    """The two members of ``read.Study`` that ``view.digest`` uses."""

    def __init__(self, records):
        self.records, self.revision = records, records[-1]['revision']

    def revisions(self, since=0):
        return [r for r in self.records if r['revision'] > since]


def test_run_kinds_and_truncation():
    state = {'task': 'binary', 'invalidations': [], 'notes': {}}
    eid = 'e_1'
    records = [
        _record(1, 0, 'init'),
        _record(2, 1, 'run.reserve', params={'activity': 'eda.rate_by', 'execution_id': eid,
                                             'options': {'column': 'job'}}),
        _record(3, 2, 'run.fail', params={'execution_id': eid, 'error': {}},
                result={'execution_id': eid, 'activity': 'eda.rate_by', 'status': 'failed'}),
        _record(4, 3, 'run.reserve', params={'activity': 'fit.logistic', 'execution_id': 'e_2',
                                             'options': {}}),
        _record(5, 4, 'run.recover', params={'execution_id': 'e_2'},
                result={'execution_id': 'e_2', 'activity': 'fit.logistic'}),
        _record(6, 5, 'run.acknowledge', params={'execution_id': 'e_2', 'user_words': 'ok'},
                result={'execution_id': 'e_2', 'activity': 'fit.logistic'}),
    ]
    d = view.digest(_Study(records), state, since=0)
    assert [i['kind'] for i in d['items']] == ['other', 'run_failed', 'run_interrupted',
                                               'interruption_acknowledged']
    failed = d['items'][1]
    assert failed['column'] == 'job' and failed['execution_id'] == eid
    assert failed['text'] == 'The target rate by group failed: no result was recorded.'
    assert d['counts']['runs_started'] == 2 and d['counts']['runs_failed'] == 1
    many = [_record(1, 0, 'init')] + [_record(r, 1, 'decide.withdraw',
                                              result={'proposal_id': f'p_{r}'})
                                      for r in range(2, 60)]
    d = view.digest(_Study(many), state, since=0)
    assert d['truncated'] is True and len(d['items']) == view.DIGEST_MAX_ITEMS
    assert d['items'][-1]['revision'] == 59 and d['counts']['withdrawn'] == 58


# --- the real code path on a binary study ---------------------------------------------------

@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    return cc.binary_study(synthetic_case_dir, tmp_path_factory.mktemp('digest') / 'study')


def _digest(flow, since=None):
    extra = () if since is None else ('--since', since)
    code, p = cc.run('status', '--summary', '--digest', *extra, '--study', flow.study)
    assert code == 0, p
    return p


def test_every_action_appears_with_its_kind(binary, tmp_path):
    flow = fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='d')
    start = flow.rev()
    pid = cc.open_proposal(flow, 'policy')
    flow.call('decide', 'confirm', pid, '--user-words', 'Yes, I want the policy exactly as '
              'you stated it, because it fits our situation', '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    flow.call('decide', 'note', '--about', 'policy', '--text', "wait for my manager's figure",
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study',
              flow.study)
    note = read.open(flow.study).state['notes']
    nid = next(iter(note))
    flow.call('decide', 'note', '--resolve', nid, '--text', 'my manager agrees with the policy',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study',
              flow.study)
    flow.run('policy.evaluate', '--rule', 'capacity:20', '--rule', 'capacity:30')
    flow.call('decide', 'propose', 'policy', '--value', 'capacity:30', '--restatement',
              'You decide the policy as stated.', '--rationale', 'It fits.', '--channel',
              'webview', '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    pid = cc.open_proposal(flow, 'policy')
    flow.call('decide', 'withdraw', pid, '--request-id', flow.rid(), '--expected-revision',
              flow.rev(), '--study', flow.study)
    p = _digest(flow, since=start)
    items = p['digest']['items']
    assert [(i['action'], i['kind']) for i in items] == [
        ('decide.confirm', 'confirmed'), ('decide.note', 'hold_recorded'),
        ('decide.resolve_note', 'hold_resolved'), ('run.promote', 'result_replaced'),
        ('decide.propose', 'proposed'), ('decide.withdraw', 'withdrawn')]
    confirmed, hold, resolved, replaced, proposed, withdrawn = items
    assert confirmed['text'] == "The policy was confirmed in the junior's words (channel chat)."
    assert confirmed['invalidation']['mutation'] == 'first_confirmation'
    assert (confirmed['channel'], confirmed['basis']) == ('chat', 'restated')  # ADR 0005: own words repeating the proposal are recorded as restated (was explicit)
    assert hold['text'] == ('Hold recorded on the policy: "wait for my manager\'s figure". The '
                            'policy needs confirmation again: the junior put the policy on hold.')
    assert hold['invalidation']['mutation'] == 'hold_added'
    assert hold['invalidation']['reconfirm_required'] == ['policy']
    assert hold['note_id'] == nid and hold['decision_id'] == 'policy'
    assert '"wait for my manager\'s figure"' in resolved['text']
    assert '"my manager agrees with the policy"' in resolved['text']
    assert replaced['rules'] == ['capacity:20', 'capacity:30']
    assert replaced['slot'] == 'policy.evaluation' and cc.is_hex64(replaced['result_id'])
    assert replaced['text'] == ('The policy evaluation was replaced: capacity:20, capacity:30 '
                                'evaluated. Models unchanged, nothing refitted.')
    assert proposed['text'] == 'The policy was proposed: capacity:30.'
    assert proposed['superseded'] == [] and proposed['channel'] is None
    assert withdrawn['text'] == 'The proposal for the policy was withdrawn.'
    counts = p['digest']['counts']
    assert (counts['confirmed'], counts['holds_recorded'], counts['holds_resolved'],
            counts['results_replaced'], counts['runs_started'], counts['proposed'],
            counts['withdrawn']) == (1, 1, 1, 1, 1, 1, 1)
    for item in items:            # P3: no revision number, no result id in a sentence
        assert str(item['revision']) not in re.sub(r'capacity:\d+', '', item['text'])
        assert not re.search(r'[0-9a-f]{8,}', item['text'])


def test_a_policy_reconfirmation_names_the_decision(binary, tmp_path):
    flow = fk.Flow(fk.clone(binary.study, tmp_path / 'study'), binary.case_dir, prefix='r')
    pid = cc.open_proposal(flow, 'policy')
    flow.call('decide', 'confirm', pid, '--user-words', 'Yes, I want the policy exactly as '
              'you stated it, because it fits our situation', '--request-id', flow.rid(), '--expected-revision', flow.rev(),
              '--study', flow.study)
    start = flow.rev()
    flow.run('policy.evaluate', '--rule', 'capacity:25')
    flow.decide('policy', 'capacity:25')
    items = _digest(flow, since=start)['digest']['items']
    again = [i for i in items if i['kind'] == 'confirmed']
    assert len(again) == 1
    assert again[0]['text'].startswith("The policy was confirmed again in the junior's words")
    assert 'Models unchanged, nothing refitted.' in again[0]['text']
    # WP-B1: the variant is a fit the evaluation compares; it is kept too.
    assert again[0]['invalidation']['kept_fits'] == ['fit.baseline', 'fit.logistic',
                                                     'fit.variant']
    assert again[0]['invalidation']['refit'] == []
    # a split change: the policy needs the junior's words again
    start = flow.rev()
    flow.decide('split', {**fk.SPLIT, 'seed': 3})
    [item] = [i for i in _digest(flow, since=start)['digest']['items']
              if i['kind'] == 'confirmed']
    assert 'the policy' in item['text'].lower() and 'confirmation again' in item['text']
    assert 'the split changed' in item['text']
    assert set(item['invalidation']['refit']) == {'fit.baseline', 'fit.logistic'}
    assert item['invalidation']['kept_fits'] == []


def test_since_the_current_revision_has_no_items_and_is_deterministic(binary):
    p = _digest(binary, since=binary.rev())
    assert p['digest']['items'] == [] and p['digest']['truncated'] is False
    assert set(p['digest']['counts'].values()) == {0}
    first, second = _digest(binary), _digest(binary)
    assert json.dumps(first) == json.dumps(second)


def test_digest_keeps_the_summary_and_appends_origin_last(binary):
    code, plain = cc.run('status', '--summary', '--study', binary.study)
    p = _digest(binary)
    assert {k: v for k, v in p.items() if k in cc.SUMMARY_KEYS and k != 'open_proposals'} == {
        k: v for k, v in plain.items() if k != 'open_proposals'}
    assert [{k: v for k, v in o.items() if k != 'origin'} for o in p['open_proposals']] == \
        plain['open_proposals']
    assert p['open_proposals'][0]['origin'] == {'channel': 'chat'}


# --- Auto MPG: the regression vocabulary scan -----------------------------------------------

def test_regression_digest_has_no_decision_rule_vocabulary(tmp_path):
    flow = fk.Flow(tmp_path / 'study', AUTO, prefix='m')
    flow.init()
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed')
    flow.decide('feature_availability', fk.availability(AUTO, acceleration='uncertain_excluded'))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'fit.baseline',
                     'fit.linear', 'evaluate.regression'):
        flow.run(activity)
    flow.run('eda.mean_by', '--column', 'model_year')
    flow.decide('model_choice', 'fit.linear')
    flow.call('decide', 'note', '--about', 'model_choice', '--text', 'wait for the new data',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study',
              flow.study)
    p = _digest(flow, since=0)
    assert p['task'] == 'regression'
    assert [tuple(m['steps']) for m in p['moments']] == list(cc.MOMENT_STEPS['regression'])
    # WP-B1: the variant before the model choice, the opening of the final test after it.
    assert p['pauses'][2]['decisions'] == ['model_variant', 'model_choice', 'final_test',
                                           'conclusion']
    kinds = {i['kind'] for i in p['digest']['items']}
    assert {'proposed', 'confirmed', 'result_added', 'hold_recorded'} <= kinds
    joined = ' '.join(i['text'] for i in p['digest']['items'])
    assert not RULE_VOCABULARY.search(joined), RULE_VOCABULARY.findall(joined)
    assert 'The model choice was proposed: fit.linear.' in joined
    assert 'The linear model was computed.' in joined
