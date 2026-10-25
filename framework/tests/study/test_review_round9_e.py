"""Review round 9 of the study engine (area E): R9E-1..R9E-7.

Every study is a temporary synthetic one (the reviewer's probes, ported).

* R9E-1: a decimal without its leading zero (".99", ".5%", "-.3") was neither traced nor
  reported. English reads it as the number it is; French reports it (an odd form).
* R9E-2: "two thousand clients", "deux mille clients", "trois cents lignes" were read as the
  bare cardinal (2, 2, 3). A cardinal in words followed by a scale word is reported.
* R9E-3: the words that exempt the number after them ("row", "section", ...) matched inside
  other words ("grow 3", "intersection 4").
* R9E-4: an adopting conclusion could be confirmed while the final test was sealed (and,
  under review-v1, while no final evaluation existed). It now needs the final test opened
  with a current final evaluation; ``keep_baseline`` and ``inconclusive`` stay allowed at any
  time (J2.3, the optional final-test step), and ``next_action`` never names a refused action.
* R9E-5: a 179-200 character request id confirmed the final test and had its opening refused
  (the opening's request id was 22 characters longer).
* R9E-6: "1e999" raised an internal error and "1e-999" traced to 0.0.
* R9E-7: an en dash used as a minus ("–2.5") lost its sign.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

import flowkit as fk
from mlkit.reliability import MAX_REQUEST_ID_LENGTH
from mlkit.study import cite, executions, numtrace, preconditions, state as st, wordnum
from test_review_round6_engine import (ACK, BASES, CONCLUSION, OPEN, _decide, _propose, _run,
                                       at_await, at_conclusion, at_final, confirm_not_open,
                                       walk)

ADOPT_WORDS = 'Yes, I adopt that conclusion because the policy fits our desk'


def _pool(language='en', **values):
    results = {'eda.quality': {'result_id': 'a' * 64, 'current': True, 'integrity': 'ok',
                               'values': values, 'n_rows': None}}
    return numtrace.Pool({'results': results, 'decisions': {}, 'open_proposals': [],
                          'settings': {}, 'dataset': {}, 'facts': {'by_status': {}},
                          'plan': [], 'not_yet_defensible': [], 'language': language})


def _traced(pool, text, language=None):
    findings, traced = numtrace.trace_text(pool, text, 'draft', language=language)
    return ([(t.get('path') or t.get('id'), t.get('value')) for t in traced],
            [(f['details'].get('number'), f['details'].get('form')) for f in findings])


# --- R9E-1: a decimal without its leading zero -------------------------------------------------

@pytest.mark.parametrize('text,shown,key,value', [
    ('Its rate is .99.', '.99', 'rate', 0.99), ('About .5% of the rows.', '.5%', 'share', 0.005),
    ('A change of -.3 in the score.', '-.3', 'delta', -0.3),
    ('A change of −.3.', '−.3', 'delta', -0.3), ('A change of –.3 overall.', '–.3', 'delta', -0.3)])
def test_a_leading_dot_decimal_is_read_in_english(text, shown, key, value):
    assert _traced(_pool('en', **{key: value}), text) == ([(key, value)], [])
    # Its sign and precision count: neither 99 nor the opposite value traces it.
    traced, findings = _traced(_pool('en', other=99.0, opposite=-value), text)
    assert traced == [] and findings == [(shown, None)], findings


def test_a_made_up_leading_dot_decimal_is_reported():
    traced, findings = _traced(_pool('en', rate=0.5), 'Its AUC is .99.')
    assert traced == [] and findings == [('.99', None)]


@pytest.mark.parametrize('text', ['Son taux est de .99.', 'Une baisse de -.3.',
                                  'Environ .5 % des lignes.'])
def test_a_leading_dot_decimal_is_reported_in_french(text):
    """French writes a decimal with a comma and its leading zero: the odd form is reported,
    even when a registered value equals it."""
    for pool in (_pool('fr', rate=0.99, delta=-0.3, share=0.005, x=0.5), _pool('fr')):
        traced, findings = _traced(pool, text)
        assert traced == [] and len(findings) == 1, (text, traced, findings)
        assert findings[0][1] == 'decimal without its leading zero'


@pytest.mark.parametrize('text,values', [
    ('In 2024.', [2024.0]), ('See section 3.2 of the plan.', [3.2]), ('v.2 and No.5', []),
    ('1.2.3', [1.2]), ('It ends here. 5 rows', [5.0]), ('(.5)', [0.5])])
def test_sentence_ends_and_dotted_numbers_are_unchanged(text, values):
    assert [t.value for t in cite.parse_numbers(text)] == values


def test_a_restatement_with_a_leading_dot_decimal_is_refused(tmp_path):
    s = _initialised(tmp_path)
    for restatement in ('Its AUC is .99.', 'Its AUC is 0.99.'):
        out = _propose_with(s, restatement)
        assert out['error']['code'] == 'literal_number_in_text', out
    assert _propose_with(s, 'Its AUC is .99.')['error']['details']['numbers'] == ['.99']


# --- R9E-2: a cardinal in words with a scale word ----------------------------------------------

@pytest.mark.parametrize('text,bare', [
    ('We called two thousand clients.', 2), ('It covers two million rows.', 2),
    ('About five thousand calls.', 5), ('Nous avons appelé deux mille clients.', 2),
    ('Il reste trois cents lignes.', 3), ('We kept two hundred clients.', 2),
    ('About one hundred and five clients.', 5), ('Un million de clients.', 1),
    ('Roughly one in five hundred customers.', 5), ('A thousand clients answered.', 1),
    ('Twenty-one thousand calls.', 21)])
def test_a_cardinal_with_a_scale_word_is_reported_never_read_bare(text, bare):
    assert wordnum.parse(text) == []
    [(shown, _start, _end, form)] = wordnum.unread(text)
    assert form == wordnum.SCALED_FORM
    traced, findings = _traced(_pool('en', n=bare, rate=1 / bare), text)
    assert traced == [] and findings == [(shown, wordnum.SCALED_FORM)], (traced, findings)
    findings, _ = numtrace.trace_text(_pool('en', n=bare), text, 'draft')
    assert findings[0]['details']['in_words'] is True


@pytest.mark.parametrize('text,value', [('We called one hundred clients.', 100),
                                        ('We called a hundred clients.', 100),
                                        ('Nous avons appelé cent clients.', 100),
                                        ('Il y a cent clients.', 100),
                                        ('We called eleven clients.', 11),
                                        ('Vingt pour cent des lignes.', 0.2)])
def test_cardinals_up_to_a_hundred_are_still_read(text, value):
    assert wordnum.unread(text) == []
    key = 'rate' if value < 1 else 'n'
    assert _traced(_pool('en', **{key: value}), text) == ([(key, value)], [])


def test_a_scale_word_in_prose_is_not_a_figure():
    """Used without a count noun, a scale phrase is not read (nor reported), as "five" alone
    is not; no part of it is ever read."""
    assert wordnum.parse('two thousand and twenty') == []
    assert wordnum.unread('two thousand and twenty') == []


def test_a_restatement_with_a_scaled_word_number_is_refused(tmp_path):
    s = _initialised(tmp_path)
    out = _propose_with(s, 'We would call two thousand clients.')
    assert out['error']['code'] == 'literal_number_in_text', out
    assert out['error']['details']['numbers'] == ['two thousand']


# --- R9E-3: the exempting words start at a word boundary ---------------------------------------

@pytest.mark.parametrize('text', ['The base will grow 3 times.', 'A narrow 12 clients.',
                                  'Call them tomorrow 5 times.', 'They borrow 2 cars.',
                                  'At the intersection 4 cars.', 'Escrow 7 clients.',
                                  'Bystep 3 clients.', 'Tap_ 5 clients.', 'A§ 3 clients.'])
def test_a_word_that_ends_like_an_exempting_word_exempts_nothing(text):
    traced, findings = _traced(_pool('en'), text)
    assert traced == [] and len(findings) == 1, (text, findings)


@pytest.mark.parametrize('text', ['See row 12.', 'At step 3.', 'In section 4.', 'It ends with exit 2.',
                                  'At revision 7.', 'See § 3.', 'Proposal p_ 5.',
                                  'Request #4.', 'Exit code 2.', 'Rev. 9 holds.'])
def test_the_exempting_words_still_exempt(text):
    assert _traced(_pool('en'), text) == ([], [])


# --- R9E-6: exponents beyond ±300 ---------------------------------------------------------------

@pytest.mark.parametrize('text', ['A value of 1e999.', 'A value of 1e-999.', 'A value of -1e999.',
                                  'A value of 1.5×10^999.', 'A value of 1e9999.',
                                  'A value of 1e-9999.', 'A value of 2.5E+301.'])
@pytest.mark.parametrize('language', ['en', 'fr'])
def test_an_exponent_beyond_300_is_reported_not_an_internal_error(text, language):
    for pool in (_pool(language, zero=0.0, big=1e300), _pool(language)):
        traced, findings = _traced(pool, text, language)
        assert traced == [] and len(findings) == 1, (text, traced, findings)
        assert findings[0][1] == 'exponent beyond ±300'


def test_an_exponent_of_300_is_still_read():
    assert _traced(_pool('en', big=1e300), 'A value of 1e300.') == ([('big', 1e300)], [])
    assert _traced(_pool('en', tiny=1e-300), 'A value of 1e-300.') == ([('tiny', 1e-300)], [])


def test_shown_matches_never_overflows():
    for decimals in (-999, -301, 301, 999):
        token = cite.Token('x', 1.0, decimals, False, 0, 1)
        assert cite.shown_matches(token, 1.0) is False
    assert cite.shown_matches(cite.Token('x', float('inf'), 0, False, 0, 1), 1.0) is False


def test_a_restatement_with_a_huge_exponent_is_refused_not_an_internal_error(tmp_path):
    s = _initialised(tmp_path)
    for restatement in ('A value of 1e999.', 'A value of 1e-999.'):
        out = _propose_with(s, restatement)
        assert out['error']['code'] == 'literal_number_in_text', out


# --- R9E-7: an en dash as a minus ---------------------------------------------------------------

@pytest.mark.parametrize('language', ['en', 'fr'])
def test_an_en_dash_glued_to_a_number_is_a_minus(language):
    text = 'The gain is –2.5 points.' if language == 'en' else 'Le gain est de –2,5 points.'
    assert _traced(_pool(language, deltas=-0.025), text) == ([('deltas', -0.025)], [])
    traced, findings = _traced(_pool(language, deltas=0.025), text)
    assert traced == [] and findings


@pytest.mark.parametrize('text', ['from 2–5 calls', 'from 2 –5 calls', 'between 2 – 5 calls'])
def test_an_en_dash_after_a_number_is_a_range(text):
    assert [(t.text, t.value) for t in cite.parse_numbers(text)] == [('2', 2.0), ('5', 5.0)]


def test_an_en_dash_before_a_scaled_number_keeps_its_sign():
    [token] = numtrace.scaled_numbers('a drop of –1.5k rows')
    assert (token.text, token.value) == ('–1.5k', -1500.0)
    [token] = numtrace.scaled_numbers('from 2 –5k rows')
    assert (token.text, token.value) == ('5k', 5000.0)


# --- R9E-4: an adopting conclusion rests on the final test -------------------------------------

def _adopt(s):
    return {'verdict': 'adopt_model' if s.task == 'regression' else 'adopt_policy',
            'text': 'The policy improves precision on the validation rows, so we adopt it.'}


def _confirm(s, pid, words=ADOPT_WORDS):
    return s.call('decide', 'confirm', pid, '--user-words', words, '--request-id', s.rid(),
                  '--expected-revision', s.rev(), '--study', s.study, expect=None)


def _missing(out):
    assert not out.get('ok') and out['error']['code'] == 'precondition_missing', out
    return out['error']['details']['missing']


PROBES: dict = {}


def _early_adoption(s):
    """Before the final test is proposed, the junior proposes adopting, and confirms."""
    p = _propose(s, 'conclusion', _adopt(s))
    assert p.get('ok'), p
    PROBES['refused'] = _confirm(s, p['result']['proposal_id'])
    PROBES['next'] = s.view()['next_action']


@pytest.mark.parametrize('base', ['legacy-binary-en', 'review-binary-en', 'legacy-regression-fr'])
def test_an_adopting_conclusion_is_refused_while_the_final_test_is_sealed(tmp_path,
                                                                          monkeypatch, base):
    """The reviewer's probe, every profile: refused with the final test to confirm first;
    ``next_action`` then proposes the final test (never the refused confirmation), and the
    walk settles with the final test opened."""
    PROBES.clear()
    s = BASES[base](tmp_path, monkeypatch)
    log, last = walk(s, hooks=[(lambda n, s: n.get('decision') == st.FINAL_TEST
                                and n['kind'] == 'propose', _early_adoption, 'adopt')])
    [item] = _missing(PROBES['refused'])
    assert item['requirement'] == 'decision_confirmed' and item['decision'] == st.FINAL_TEST
    assert item['junior_message'] and PROBES['refused']['error']['details']['junior_message']
    assert PROBES['next']['decision'] == st.FINAL_TEST, PROBES['next']
    assert PROBES['next']['kind'] == 'propose' and PROBES['next']['junior_message']
    assert last['kind'] == 'done' and st.final_test_opened(s.state()), log


@pytest.mark.parametrize('verdict', ['keep_baseline', 'inconclusive'])
def test_keeping_the_baseline_or_inconclusive_needs_no_final_test(tmp_path, monkeypatch,
                                                                    verdict):
    """J2.3 and the optional final-test step: a study that keeps the baseline opens
    nothing."""
    s = BASES['legacy-binary-fr'](tmp_path, monkeypatch)

    def conclude(s):
        _decide(s, 'conclusion', {'verdict': verdict, 'text': CONCLUSION})
        PROBES['status'] = s.state()['decisions']['conclusion']['status']
        PROBES['opened'] = st.final_test_opened(s.state())
    PROBES.clear()
    walk(s, hooks=[(lambda n, s: n.get('decision') == st.FINAL_TEST and n['kind'] == 'propose',
                    conclude, 'conclude')])
    assert PROBES == {'status': 'confirmed', 'opened': False}


def test_an_adopting_conclusion_waits_for_a_confirmed_final_test_to_open(tmp_path,
                                                                         monkeypatch):
    PROBES.clear()
    s = BASES['legacy-binary-en'](tmp_path, monkeypatch)

    def confirmed_then_adopt(s):
        confirm_not_open(s)
        eid = sorted(s.state()['executions']['interrupted'])[0]
        out = s.call('run', '--acknowledge-interruption', eid, '--user-words', ACK,
                     '--request-id', s.rid(), '--expected-revision', s.rev(), '--study',
                     s.study, expect=None)
        assert out.get('ok'), out
        p = _propose(s, 'conclusion', _adopt(s))
        PROBES['refused'] = _confirm(s, p['result']['proposal_id'])
        PROBES['next'] = s.view()['next_action']
    log, last = walk(s, hooks=[(at_final, confirmed_then_adopt, 'confirm')])
    [item] = _missing(PROBES['refused'])
    assert item['requirement'] == 'final_test_opened', item
    assert PROBES['next']['kind'] == 'run', PROBES['next']
    assert PROBES['next']['activity'] == 'final_test.evaluation', PROBES['next']
    assert last['kind'] == 'done' and st.final_test_opened(s.state()), log


def _interrupted_final(s):
    """The final test confirmed and opened, its evaluation killed after it read the rows."""
    confirm_not_open(s)
    eid = sorted(s.state()['executions']['interrupted'])[0]
    out = s.call('run', '--acknowledge-interruption', eid, '--user-words', ACK,
                 '--request-id', s.rid(), '--expected-revision', s.rev(), '--study', s.study,
                 expect=None)
    assert out.get('ok'), out
    env = fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_before_promote')
    subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'final_test.evaluation',
                    '--request-id', f'killf{s.rev()}', '--expected-revision', str(s.rev()),
                    '--study', str(s.study)], env=env, capture_output=True, text=True,
                   timeout=600)
    assert st.final_test_opened(s.state())


def _adopt_without_final_evidence(s):
    """Once the walker has dealt with the killed run: the conclusion is what remains."""
    PROBES['verdicts'] = s.view()['next_action'].get('verdicts')
    p = _propose(s, 'conclusion', _adopt(s))
    PROBES['pid'] = p['result']['proposal_id']
    PROBES['refused'] = _confirm(s, p['result']['proposal_id'])
    PROBES['next'] = s.view()['next_action']


@pytest.mark.parametrize('base', ['legacy-binary-fr', 'legacy-regression-fr'])
def test_after_an_interrupted_opening_only_the_honest_verdicts_remain(tmp_path, monkeypatch,
                                                                       base):
    PROBES.clear()
    s = BASES[base](tmp_path, monkeypatch)
    log, last = walk(s, hooks=[(at_final, _interrupted_final, 'confirm'),
                               (at_conclusion, _adopt_without_final_evidence, 'adopt')])
    assert PROBES['verdicts'] == ['keep_baseline', 'inconclusive'], PROBES
    [item] = _missing(PROBES['refused'])
    assert item['requirement'] == 'final_evidence_required', item
    assert 'ne s' in item['junior_message']           # the study language (French)
    nxt = PROBES['next']
    assert (nxt['kind'], nxt['decision'], nxt['verdicts']) == (
        'propose', 'conclusion', ['keep_baseline', 'inconclusive']), nxt
    assert nxt['replaces'] == PROBES['pid'] and nxt['junior_message'], nxt
    assert last['kind'] == 'done', log
    conclusion = s.state()['decisions']['conclusion']
    assert conclusion['status'] == 'confirmed'
    assert conclusion['value']['verdict'] == 'keep_baseline'


@pytest.mark.parametrize('base', ['legacy-binary-en', 'legacy-regression-fr', 'review-binary-en'])
def test_an_adopting_conclusion_is_confirmed_on_current_final_evidence(tmp_path, monkeypatch,
                                                                       base):
    PROBES.clear()
    s = BASES[base](tmp_path, monkeypatch)

    def adopt(s):
        if s.review and not st.is_current(s.state(), 'diag.final_test'):
            # review-v1: the final diagnostics first (the rule of J2.3).
            p = _propose(s, 'conclusion', _adopt(s))
            [item] = _missing(_confirm(s, p['result']['proposal_id']))
            assert item['requirement'] == 'final_evidence_current_for_configuration'
            assert _run(s, 'diag.final_test').get('ok')
        p = _propose(s, 'conclusion', _adopt(s))
        PROBES['adopted'] = _confirm(s, p['result']['proposal_id'])
    walk(s, hooks=[(at_conclusion, adopt, 'adopt')])
    assert PROBES['adopted'].get('ok'), PROBES['adopted']
    assert s.state()['decisions']['conclusion']['value']['verdict'].startswith('adopt_')


def test_a_study_without_a_final_test_is_unchanged():
    """A study created before WP-B1 (no final test) or without a sealed final test adopts as
    before: no requirement is added."""
    state = {'decisions': {d: {'status': 'open', 'value': None}
                           for d in st.FULL_DECISION_IDS}, 'partition': None, 'current': {},
             'stale': {}}
    assert preconditions.adoption_missing(state) == []
    state = {'decisions': {d: {'status': 'open', 'value': None}
                           for d in st.B2_DECISION_IDS}, 'partition': None, 'current': {},
             'stale': {}}
    assert preconditions.adoption_missing(state) == []


# --- R9E-5: a long request id opens the final test ----------------------------------------------

def test_a_long_request_id_opens_the_final_test_and_replays(tmp_path, monkeypatch):
    s = BASES['legacy-binary-en'](tmp_path, monkeypatch)
    rid = 'x' * MAX_REQUEST_ID_LENGTH

    def long_confirm(s):
        pid = [p for p in s.state()['proposals'].values()
               if p['decision_id'] == st.FINAL_TEST and p['status'] == 'open'][-1]['proposal_id']
        args = ('decide', 'confirm', pid, '--user-words', OPEN, '--request-id', rid,
                '--expected-revision', s.rev(), '--study', s.study)
        PROBES['first'] = s.call(*args, expect=None)
        PROBES['replay'] = s.call(*args, expect=None)
    PROBES.clear()
    walk(s, hooks=[(at_await(st.FINAL_TEST), long_confirm, 'long')])
    first, replay = PROBES['first']['result']['opening'], PROBES['replay']['result']['opening']
    assert first['status'] == 'promoted', first
    assert PROBES['replay']['replayed'] and replay['status'] == 'opened', replay
    assert replay['execution_id'] == first['execution_id'], (first, replay)
    derived = executions.derived_request_id('final_test.evaluation', rid)
    assert len(derived) < MAX_REQUEST_ID_LENGTH
    assert s.state()['partition']['opening']['execution_id'] == executions.execution_id(derived)


def test_an_opening_recorded_under_the_old_key_is_reported_on_replay(tmp_path, monkeypatch):
    """A study opened by an earlier engine (``<request id>:final_test.evaluation``): the
    replayed confirmation reads the recorded opening from the state, whatever its key."""
    from mlkit.study import commands as cmd
    s = BASES['legacy-binary-en'](tmp_path, monkeypatch)

    def old_engine(store, payload, request_id):
        if payload['result'].get('decision_id') != st.FINAL_TEST or payload['replayed']:
            return original(store, payload, request_id)
        executions.run(store.study_dir, 'final_test.evaluation', {},
                       request_id=f'{request_id}:final_test.evaluation',
                       expected_revision=payload['revision'], render=False)
        return {'status': 'promoted'}
    original = cmd._opening

    def confirm_twice(s):
        pid = [p for p in s.state()['proposals'].values()
               if p['decision_id'] == st.FINAL_TEST and p['status'] == 'open'][-1]['proposal_id']
        args = ('decide', 'confirm', pid, '--user-words', OPEN, '--request-id', 'old-key',
                '--expected-revision', s.rev(), '--study', s.study)
        with monkeypatch.context() as m:
            m.setattr(cmd, '_opening', old_engine)
            assert s.call(*args, expect=None)['ok']
        PROBES['replay'] = s.call(*args, expect=None)
    PROBES.clear()
    walk(s, hooks=[(at_await(st.FINAL_TEST), confirm_twice, 'old')])
    replay = PROBES['replay']['result']['opening']
    assert PROBES['replay']['replayed'] and replay['status'] == 'opened', replay
    assert replay['execution_id'] == executions.execution_id('old-key:final_test.evaluation')


# --- helpers ------------------------------------------------------------------------------------

def _initialised(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300)['case'].parent
    flow = fk.Flow(tmp_path / 'study', case_dir, prefix='n')
    flow.call('init', '--case', case_dir, '--study', flow.study)
    return flow


def _propose_with(s, restatement):
    return s.call('decide', 'propose', 'prediction_time', '--value-json',
                  json.dumps('when the record is created, before the outcome'),
                  '--restatement', restatement, '--rationale', 'It fits the scenario.',
                  '--request-id', s.rid(), '--expected-revision', s.rev(), '--study', s.study,
                  expect=None)
