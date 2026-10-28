"""The automatic mode, reviewed at the end (owner session 2026-10-26, lot L9, remark R20).

Both variants chosen at launch run on Auto MPG (fast: about a second per activity), end to end
through the CLI's own code path (``cli.run``): ``until_final_test`` stops before the final test
and the junior then adopts or changes each automatic decision and opens the final test
themselves; ``full_demo`` also opens the final test and concludes, with its banners, and its
review marks a change as made after the final test. ADR 0005 and ADR 0006 amendments of
2026-10-26; CLI-CONTRACT §5.5.

Owner session 2026-10-27 (R23, R24 of the fourth session of 2026-10-26): both module runs pass
``--progress``, and the tests below read what it tells on stderr (the header, one line per
decision with its value in words and why, each computation's key result with registered
figures, the closing summary), the readable summary ``--format text`` prints, and the review
pause (adopt, change, explain; nothing recommended; the reviewed decision's step).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import flowkit as fk
from mlkit.study import (automation, cite, cli, cmd_export, notebook_view, read,
                         state as st, view as view_mod)
from mlkit.study.errors import StudyError

REPO = Path(__file__).resolve().parents[3]
AUTO_MPG = REPO / 'use-cases' / 'auto-mpg'
WORDS = {'en': 'Yes, I confirm this.', 'fr': 'Oui, je confirme cela.'}


def _flow(study: Path) -> fk.Flow:
    return fk.Flow(study, AUTO_MPG, prefix=f'{study.name}-')


def _created(study: Path, *more) -> fk.Flow:
    f = _flow(study)
    f.call('init', '--case', AUTO_MPG, '--study', study, *more)
    return f


def _ran(base: Path, mode: str, lang: str) -> tuple[Path, dict, str]:
    """The run through the CLI's code path with ``--progress``: the study, the JSON
    document, and what the run told on stderr (R23)."""
    f = _created(base / mode, '--lang', lang, '--automation', mode)
    told = io.StringIO()
    with contextlib.redirect_stderr(told):
        out = f.call('automation', 'run', '--progress', '--request-id', 'auto',
                     '--expected-revision', f.rev(), '--study', f.study)
    return f.study, out, told.getvalue()


@pytest.fixture(scope='module')
def until(tmp_path_factory):
    return _ran(tmp_path_factory.mktemp('until'), 'until_final_test', 'en')


@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    return _ran(tmp_path_factory.mktemp('demo'), 'full_demo', 'fr')


def _copy(study: Path, tmp_path: Path) -> fk.Flow:
    target = tmp_path / study.name
    shutil.copytree(study, target)
    return _flow(target)


def _propose(f: fk.Flow, decision: str, value, expect=0) -> dict:
    return f.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                  '--restatement', f'You decide the {decision} as stated.', '--rationale',
                  'Reviewed with the junior.', '--request-id', f.rid(), '--expected-revision',
                  f.rev(), '--study', f.study, expect=expect)


def _confirm(f: fk.Flow, pid: str, *more, words: str | None = None, expect=0) -> dict:
    lang = st.language_of(f.state())
    return f.call('decide', 'confirm', pid, '--user-words', words or WORDS[lang], *more,
                  '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study,
                  expect=expect)


def _review(f: fk.Flow, change=None, stop_at_final=False, limit=80) -> list:
    """Follow ``next_action`` as the agent does with the junior: every review adopted in the
    junior's words, except the decisions ``change`` gives a new value for; a run as given;
    the final test opened and the conclusion written by the junior. Every action must be
    accepted."""
    log = []
    for _ in range(limit):
        nxt = f.view()['next_action']
        log.append((nxt['kind'], nxt.get('decision') or nxt.get('activity'), nxt.get('review')))
        if nxt['kind'] == 'done':
            return log
        if stop_at_final and nxt.get('decision') == 'final_test':
            return log
        if nxt['kind'] == 'run':
            args = [nxt['activity']]
            for rule in nxt.get('rules') or []:
                args += ['--rule', rule]
            for option, value in (nxt.get('options') or {}).items():
                args += [f'--{option}', str(value)]
            out = f.call('run', *args, '--request-id', f.rid(), '--expected-revision', f.rev(),
                         '--study', f.study, expect=None)
        elif nxt['kind'] in ('propose', 'reconfirm'):
            decision = nxt['decision']
            value = nxt.get('default_value')
            if value is None:
                value = (nxt.get('recommended') or {}).get('value')
            if change and decision in change and nxt.get('review'):
                value = change[decision](value)
            if decision == 'conclusion' and not nxt.get('review'):
                value = {'verdict': 'inconclusive',
                         'text': 'The study records its evidence and does not conclude yet.'}
            if value is None and decision == 'model_choice':
                value = nxt['choice_options'][0]['value']
            out = _propose(f, decision, value, expect=None)
        elif nxt['kind'] == 'await_user_words':
            out = _confirm(f, nxt['proposal_id'], expect=None)
        else:
            raise AssertionError(f'unexpected next action: {nxt}')
        assert out.get('ok'), ('refused as given', nxt, out.get('error'), log[-6:])
    raise AssertionError(f'the review did not settle: {log[-8:]}')


# --- launch, compatibility, refusals of the basis ------------------------------------------

def test_automation_is_set_at_init_only_and_existing_studies_are_unchanged(tmp_path):
    """Without ``--automation`` a study has no key, its view says ``automation: null`` and
    ``review_queue: []``, no ``auto_value``; the runner, ``automation stop`` and ``--basis
    automatic`` are refused there; nothing sets the mode after ``init``."""
    plain = _created(tmp_path / 'plain')
    assert 'automation' not in plain.state()
    v = plain.view()
    assert (v['automation'], v['review_queue']) == (None, [])
    assert 'auto_value' not in v['next_action'] and 'review' not in v['next_action']
    assert not {'automatic_decisions_to_review', 'final_test_opened_automatically'} & {
        x['id'] for x in v['not_yet_defensible']}
    out = plain.call('automation', 'run', '--request-id', 'a', '--expected-revision', plain.rev(),
                     '--study', plain.study)
    assert (out['status'], out['reason'], out['steps']) == ('stopped', 'automation_not_set', [])
    stop = plain.call('automation', 'stop', '--user-words', 'Stop the automatic mode now.',
                      '--request-id', plain.rid(), '--expected-revision', plain.rev(),
                      '--study', plain.study, expect=2)
    assert stop['error']['details']['reason'] == 'automation_not_set'
    p = _propose(plain, 'prediction_time', 'before the car is measured')['result']
    refused = plain.call('decide', 'confirm', p['proposal_id'], '--basis', 'automatic',
                         '--request-id', plain.rid(), '--expected-revision', plain.rev(),
                         '--study', plain.study, expect=2)
    assert refused['error']['code'] == 'ambiguous_confirmation'
    assert refused['error']['details']['reason'] == 'automation_not_set'
    missing = plain.call('decide', 'confirm', p['proposal_id'], '--request-id', plain.rid(),
                         '--expected-revision', plain.rev(), '--study', plain.study, expect=2)
    assert missing['error']['code'] == 'invalid_arguments'
    # The flag takes the two variants only; a mode change never touches it.
    bad = _flow(tmp_path / 'bad').call('init', '--case', AUTO_MPG, '--study', tmp_path / 'bad',
                                       '--automation', 'always', expect=2)
    assert bad['error']['code'] == 'invalid_arguments'
    auto = _created(tmp_path / 'auto', '--automation', 'until_final_test')
    record = auto.state()['automation']
    assert record == {'mode': 'until_final_test', 'status': 'running', 'started_revision': 1,
                      'ended': None}
    auto.call('mode', 'set', 'training', '--request-id', auto.rid(), '--expected-revision',
              auto.rev(), '--study', auto.study)
    assert auto.state()['automation'] == record
    # The demo variant's decisions are never covered by until_final_test.
    p = _propose(auto, 'conclusion', {'verdict': 'inconclusive',
                                      'text': 'The study does not conclude yet.'})['result']
    refused = auto.call('decide', 'confirm', p['proposal_id'], '--basis', 'automatic',
                        '--request-id', auto.rid(), '--expected-revision', auto.rev(),
                        '--study', auto.study, expect=2)
    assert refused['error']['details']['reason'] == 'automation_does_not_cover'
    p = _propose(auto, 'prediction_time', 'before the car is measured')['result']
    for extra, field in ((('--user-words', 'yes'), 'user_words'),
                         (('--channel', 'choice'), 'channel'),
                         (('--agent-concern', 'a point'), 'agent_concern')):
        out = auto.call('decide', 'confirm', p['proposal_id'], '--basis', 'automatic', *extra,
                        '--request-id', auto.rid(), '--expected-revision', auto.rev(),
                        '--study', auto.study, expect=2)
        assert (out['error']['code'], out['error']['details']['field']) == (
            'invalid_value', field), out


def test_automatic_basis_is_never_a_human_basis(until, tmp_path):
    """``until_final_test`` runs to the model choice: every decision before the final test is
    ``automatic`` (``actor: assistant``, no words), never the junior's own words nor a
    delegation; the final test stays sealed; the report, the notebook and the summary say the
    study is not defensible until reviewed."""
    study, out, _ = until
    assert (out['status'], out['reason'], out['refusal']) == ('ended', 'reached_end', None), out
    assert tuple(out) == automation.PAYLOAD_KEYS
    assert all(tuple(s) == automation.STEP_KEYS for s in out['steps'])
    assert out['stopped_at']['review'] is True and out['next_action']['review'] is True
    state = read.open(study).state
    assert state['partition']['status'] == 'sealed'
    before = [d for d in st.decision_ids(state) if d not in ('final_test', 'conclusion')]
    assert [q['decision_id'] for q in out['review_queue']] == before == st.review_queue(state)
    for d in before:
        conf = state['decisions'][d]['confirmation']
        assert (conf['basis'], conf['actor'], conf['user_words']) == ('automatic', 'assistant',
                                                                      None), d
        assert st.basis_class(conf['basis']) == 'automatic'
    for d in ('final_test', 'conclusion'):
        assert state['decisions'][d]['status'] != 'confirmed'
    assert st.delegated_decisions(state) == []
    assert state['automation']['status'] == 'ended'
    assert state['automation']['ended']['reason'] == 'reached_end'
    assert state['mode_history'][-1]['automation'] == {'previous': 'until_final_test',
                                                        'reason': 'reached_end'}
    v = view_mod.build(read.open(study))
    limits = {x['id']: x for x in v['not_yet_defensible']}
    assert limits['automatic_decisions_to_review']['decisions'] == before
    assert limits['automatic_decisions_to_review']['junior_text'].startswith(
        'Automatic study: not defensible until reviewed.')
    assert 'final_test_opened_automatically' not in limits
    summary = view_mod.summary(v)
    assert summary['not_yet_defensible']['top'][0]['id'] == 'automatic_decisions_to_review'
    report = (study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-automation-banner="review"' in report
    assert 'Automatic study: not defensible until reviewed.' in report
    assert 'data-automation-banner="opened"' not in report
    assert 'data-basis="automatic"' in report
    banner = notebook_view.banner_html(read.open(study), v['revision'], {})
    assert 'data-automation-banner="review"' in banner
    check = _flow(study).call('check', '--study', study)
    assert check['clean'] is True, check['findings']
    # Once ended, the mode records nothing more (one way).
    f = _copy(study, tmp_path)
    p = _propose(f, 'final_test', st.b1_default_value(f.state(), 'final_test'))['result']
    refused = f.call('decide', 'confirm', p['proposal_id'], '--basis', 'automatic',
                     '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study,
                     expect=2)
    assert refused['error']['details']['reason'] == 'automation_not_set'


def test_review_queue_adopt_and_change_then_the_junior_opens(until, tmp_path):
    """The junior cannot open the final test before the review; then each automatic decision
    is adopted in their own words (``adopted_from``, no invalidation) or changed (a normal
    confirmation that invalidates), and the junior opens the final test themselves."""
    f = _copy(until[0], tmp_path)
    p = _propose(f, 'final_test', st.b1_default_value(f.state(), 'final_test'))['result']
    refused = _confirm(f, p['proposal_id'], expect=2)
    assert refused['error']['code'] == 'precondition_missing'
    item = refused['error']['details']['missing'][0]
    assert item['requirement'] == 'automatic_decisions_reviewed'
    assert 'No final-test row was read' in item['junior_message']
    assert f.state()['partition']['status'] == 'sealed'
    # The review comes first: the open final-test proposal waits for it.
    assert f.view()['next_action']['review'] is True
    start = f.rev()
    log = _review(f, change={'success_criterion': lambda v: {**v, 'min_share': 0.05}},
                  stop_at_final=True)
    # After the review, the capture the engine names before the opening (third session of
    # 2026-10-26) is run as given, then the junior is asked about the final test.
    assert log[-2:] == [('run', 'predictor.capture', None), ('propose', 'final_test', None)], log
    reviewed = [d for k, d, r in log if r and k == 'await_user_words']
    state = f.state()
    assert reviewed == [d for d in st.decision_ids(state) if d not in ('final_test',
                                                                      'conclusion')]
    assert st.review_queue(state) == []
    for d in reviewed:
        conf = state['decisions'][d]['confirmation']
        assert conf['basis'] in st.OWN_WORDS_BASES and conf['user_words'], d
        assert bool(conf.get('adopted_from')) == (d != 'success_criterion'), d
    assert state['decisions']['success_criterion']['value']['min_share'] == 0.05
    # An adoption records no invalidation; the change does.
    later = [i for i in state['invalidations'] if i['revision'] > start]
    assert [i['decision_id'] for i in later] == ['success_criterion'], later
    ids = {x['id'] for x in f.view()['not_yet_defensible']}
    assert 'automatic_decisions_to_review' not in ids
    _review(f)
    state = f.state()
    assert st.final_test_opened(state)
    assert 'basis' not in state['partition']['opening']
    assert state['partition']['opening']['user_words'] == WORDS['en']


def test_full_demo_opens_once_and_banners(demo, tmp_path):
    """``full_demo`` opens the final test with ``basis: automatic`` and concludes from the
    criterion judged on the final test; the French banners say so; the opening is never
    redone."""
    study, out, _ = demo
    assert (out['status'], out['reason'], out['refusal']) == ('ended', 'reached_end', None), out
    state = read.open(study).state
    assert st.final_test_opened(state) and st.opened_automatically(state)
    opening = state['partition']['opening']
    assert (opening['basis'], opening['user_words']) == ('automatic', None)
    assert st.review_queue(state) == list(st.decision_ids(state))
    v = view_mod.build(read.open(study))
    conclusion = state['decisions']['conclusion']
    assert conclusion['value']['verdict'] == automation.verdict_of(v)
    assert conclusion['value']['text'].startswith('Conclusion automatique')
    ids = {x['id'] for x in v['not_yet_defensible']}
    assert {'automatic_decisions_to_review', 'final_test_opened_automatically'} <= ids
    report = (study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'Étude automatique : à relire, pas encore défendable.' in report
    assert 'Le test final a été ouvert automatiquement.' in report
    f = _copy(study, tmp_path)
    other = {**state['decisions']['final_test']['value'], 'model': 'fit.baseline'}
    again = _propose(f, 'final_test', other, expect=2)
    assert again['error']['code'] == 'final_test_already_opened'
    # The runner follows the capture the engine names before the opening (third session of
    # 2026-10-26), with its options as given, so the export carries the evaluated model.
    order = [(s['kind'], s['decision'] or s['activity']) for s in out['steps']]
    assert order.index(('run', 'predictor.capture')) < order.index(
        ('await_user_words', 'final_test')), order
    capture = v['results']['predictor.capture']
    assert capture['current'] and capture['params']['role'] == 'final_development_refit'
    from mlkit.contracts import capture as capture_mod
    try:
        capture_mod.require_packager(capture_mod.WORKSHOP_PACKAGER)
        expected = {'profile': 'workshop'}
    except StudyError:
        expected = {}
    assert view_mod.capture_options(capture['params']) == expected, capture['params']
    # R22: the French handoff names the automatic basis in French, with no words recorded,
    # and a French regression pack traces its figures ("pour la moyenne de référence").
    pack = tmp_path / 'pack'
    f.call('export', 'handoff', '--out', pack, '--study', f.study)
    md = (pack / 'handoff.md').read_text(encoding='utf-8')
    assert md.count(f'- Fondement : {cmd_export.BASIS_WORDS_FR[st.AUTOMATIC]}') == len(
        st.decision_ids(state))
    assert 'None' not in md and 'Basis:' not in md
    assert f.call('check', '--text', pack / 'handoff.md', '--study', f.study)['clean']


def test_delegation_still_never_opens(demo, tmp_path):
    """The demo's review accepts the opened configuration again, but a delegation never
    confirms the final test, in any automation (``delegation_not_allowed``)."""
    f = _copy(demo[0], tmp_path)
    p = _propose(f, 'final_test', f.state()['decisions']['final_test']['value'])['result']
    refused = _confirm(f, p['proposal_id'], '--basis', 'delegated_default', '--delegation-scope',
                       'this_decision', words='Prends ta recommandation, je te laisse choisir.',
                       expect=2)
    assert refused['error']['details']['reason'] == 'delegation_not_allowed'


def test_full_demo_review_adopts_the_opening_and_marks_changes_after(demo, tmp_path):
    """The demo's review: adoptions change nothing after the final test, the opening is
    adopted without a second evaluation, a changed decision is marked as made after the final
    test, and the opening's banner stays."""
    f = _copy(demo[0], tmp_path)
    opening = dict(f.state()['partition']['opening'])
    log = _review(f, change={'success_criterion': lambda v: {**v, 'min_share': 0.05}})
    assert ('await_user_words', 'final_test', True) in log
    state = f.state()
    assert state['partition']['opening'] == opening
    assert st.review_queue(state) == []
    conf = state['decisions']['final_test']['confirmation']
    assert conf['basis'] in st.OWN_WORDS_BASES and conf['adopted_from']['basis'] == 'automatic'
    v = f.view()
    assert v['final_test']['changed_after'] == ['success_criterion'], v['final_test']
    ids = {x['id'] for x in v['not_yet_defensible']}
    assert 'final_test_opened_automatically' in ids and 'changed_after_final_test' in ids
    assert 'automatic_decisions_to_review' not in ids
    assert v['results']['final_test.evaluation']['execution_id'] == opening['execution_id']


# --- the runner honours every refusal -------------------------------------------------------

def test_the_runner_honours_holds_and_refusals_and_stops_one_way(tmp_path, monkeypatch):
    """A hold stops the run (the junior answers it); a value the engine refuses stops it with
    the refusal, nothing bypassed; ``--progress`` writes lines on stderr only; the junior's
    words stop the mode for good and the decisions it recorded wait for their review."""
    f = _created(tmp_path / 'held', '--automation', 'until_final_test')
    f.call('decide', 'note', '--about', 'split', '--text', 'Wait for my manager before the split.',
           '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'automation', 'run',
                           '--progress', '--request-id', 'p', '--expected-revision',
                           str(f.rev()), '--study', str(f.study)],
                          capture_output=True, text=True, env=fk.env(), timeout=600)
    out = json.loads(proc.stdout)
    assert len(proc.stdout.strip().splitlines()) == 1
    # R23: the decisions recorded before the hold, each once, then why the run stopped.
    assert proc.stderr.startswith('Automatic mode · up to the final test · Auto MPG · UCI\n')
    assert '\n1 · Decision · The prediction moment: ' in proc.stderr
    assert '\n2 · Decision · The feature availability: keep ' in proc.stderr
    assert 'proposed' not in proc.stderr and 'recorded as automatic' not in proc.stderr
    assert 'Summary · I stopped: what comes next needs your answer.' in proc.stderr
    assert 'Decisions to review (2): the prediction moment and the feature availability.' \
        in proc.stderr
    assert (out['status'], out['reason']) == ('stopped', 'needs_junior'), out
    assert out['stopped_at']['kind'] == 'resolve_hold'
    state = f.state()
    assert state['automation']['status'] == 'running'
    assert state['decisions']['split']['status'] != 'confirmed'
    assert st.review_queue(state) == ['prediction_time', 'feature_availability']
    note = next(iter(state['notes']))
    f.call('decide', 'note', '--resolve', note, '--text', 'My manager agreed, so we can go on.',
           '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    real = automation.auto_value
    monkeypatch.setattr(automation, 'auto_value', lambda view, state, action: (
        {'metric': 'no_such_metric', 'min_share': 0.1}
        if action.get('decision') == 'success_criterion' else real(view, state, action)))
    out = f.call('automation', 'run', '--request-id', 'q', '--expected-revision', f.rev(),
                 '--study', f.study)
    assert (out['status'], out['reason']) == ('stopped', 'refused'), out
    assert out['refusal']['code'] == 'invalid_value'
    assert out['stopped_at']['decision'] == 'success_criterion'
    assert f.state()['decisions']['split']['confirmation']['basis'] == 'automatic'
    assert f.state()['decisions']['success_criterion']['status'] == 'open'
    assert f.state()['automation']['status'] == 'running'
    question = f.call('automation', 'stop', '--user-words', 'Can we stop?', '--request-id',
                      f.rid(), '--expected-revision', f.rev(), '--study', f.study, expect=2)
    assert question['error']['details']['reason'] == 'question_reply'
    stop = f.call('automation', 'stop', '--user-words', 'Stop the automatic mode, I decide now.',
                  '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    assert stop['result']['automation']['ended']['reason'] == 'stopped'
    state = f.state()
    assert state['mode_history'][-1]['automation'] == {'previous': 'until_final_test',
                                                        'reason': 'stopped'}
    assert state['mode_history'][-1]['user_words'] == 'Stop the automatic mode, I decide now.'
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['decision'], nxt['review']) == ('reconfirm', 'prediction_time',
                                                             True)
    assert 'auto_value' not in nxt
    out = f.call('automation', 'run', '--request-id', 'r', '--expected-revision', f.rev(),
                 '--study', f.study)
    assert (out['reason'], out['steps']) == ('automation_not_set', [])


def test_auto_value_rules():
    """The fixed rules where the engine recommends nothing: the one-standard-error pick among
    the accepted choices, else the best, else the candidate; the conclusion from the criterion
    judged on the final test."""
    state = {'decisions': {}, 'task': 'regression'}
    action = {'kind': 'propose', 'decision': 'model_choice', 'recommended': None,
              'choice_options': [{'value': v} for v in ('fit.linear', 'fit.variant',
                                                        'fit.baseline')]}
    view = {'task': 'regression', 'model_selection': {'one_se': {'pick': 'fit.variant'},
                                                      'best': 'fit.variant.2'}}
    assert automation.auto_value(view, state, action) == 'fit.variant'
    view['model_selection'] = {'one_se': {'available': False}, 'best': 'fit.variant.2'}
    assert automation.auto_value(view, state, action) == 'fit.linear'
    for status, verdict in (('met', 'adopt_model'), ('not_met', 'keep_baseline'),
                            ('uncertain', 'inconclusive'), ('not_assessed', 'inconclusive')):
        v = {'task': 'regression', 'language': 'en',
             'criterion': {'status': 'met', 'judged_status': status}}
        out = automation.auto_value(v, state, {'kind': 'propose', 'decision': 'conclusion'})
        assert out['verdict'] == verdict and not any(c.isdigit() for c in out['text'])
    assert automation.auto_value({}, state, {'kind': 'propose', 'decision': 'prediction_time',
                                             'recommended': None}) is None


# --- R23: what the run tells, and its readable summary ----------------------------------------

def _figure(view: dict, slot: str, lang: str) -> str:
    """The registered out-of-fold mean absolute error of ``slot``, as the study language
    writes it."""
    models = view['results']['evaluate.regression']['values']['models']
    return cite.format_value(models[slot]['mae'], 'f2', lang) + ' mpg'


@pytest.mark.parametrize('which', ['until', 'demo'])
def test_progress_tells_what_is_going_on(which, request, tmp_path):
    """R23: on stderr, in the study language, a header (mode, case, what is done, where it
    stops); one line per decision, once, with its value in words and why, never raw JSON, an
    id or the propose/confirm pair; after each computation its key result with registered
    figures formatted in the study language; a closing summary (the decisions to review, the
    model kept and its figure, what the junior does next)."""
    study, out, told = request.getfixturevalue(which)
    lang = 'en' if which == 'until' else 'fr'
    v = view_mod.build(read.open(study))
    lines = told.splitlines()
    T = (lambda en, fr: fr if lang == 'fr' else en)
    head = T('Automatic mode · up to the final test · Auto MPG · UCI',
             'Mode automatique · démonstration complète · Auto MPG · UCI')
    assert lines[0] == head, lines[:3]
    assert lines[1].startswith(T('What I do: I take each decision', 'Ce que je fais : je prends'))
    assert lines[3].startswith(T('Where I stop: before the final test, which stays sealed.',
                                 "Où je m'arrête : à la fin. Cette démonstration ouvre aussi"))
    # One line per decision recorded, numbered with the computations, each with its why.
    decision_lines = [x for x in lines if re.match(r'\d+ · ' + T('Decision', 'Décision') + ' · ',
                                                   x)]
    recorded = [s['decision'] for s in out['steps'] if s['kind'] == 'await_user_words']
    assert len(decision_lines) == len(recorded) == len(v['review_queue']), decision_lines
    for line, decision in zip(decision_lines, recorded):
        from mlkit.study import audience
        words = audience.decision_words(decision, lang)
        assert (words[:1].upper() + words[1:]) in line, (decision, line)
        assert T(' Why: ', ' Pourquoi : ') in line, line
        assert '{' not in line and '"' not in line and 'p_' not in line, line
        assert decision not in line or decision in words, line
    numbers = [int(x.split(' · ', 1)[0]) for x in lines if re.match(r'\d+ · ', x)]
    assert numbers == list(range(1, len(numbers) + 1))
    for noise in (' · proposed', ' · proposée', 'recorded as automatic', 'enregistrée comme '
                  'automatique', 'model_choice', 'feature_availability', 'fit.'):
        assert noise not in told, noise
    split = T('    Result: 5 folds in time order, ', '    Résultat : 5 plis dans l\'ordre du temps, ')
    assert any(x.startswith(split) for x in lines), told
    quality = next(x for x in lines if 'horsepower)' in x and x.lstrip().startswith(
        T('Result:', 'Résultat :')))
    assert T('6 of 318 rows with a missing value (horsepower)',
             '6 sur 318 lignes avec une valeur manquante (horsepower)') in quality
    assert T('rare categories in car_name', 'catégories rares dans car_name') in quality
    for slot in ('fit.baseline', 'fit.linear', 'fit.variant:2'):
        mae = _figure(v, slot, lang)
        assert T(f'    Result: mean absolute error out of fold {mae}',
                 f'    Résultat : erreur absolue moyenne hors pli {mae}') in told, (slot, mae)
    advice = v['model_selection']['advice']['texts'][lang]
    assert any(advice in x for x in lines if x.lstrip().startswith(T('Result:', 'Résultat :')))
    assert T('2 flags: a shape the linear model does not follow (horsepower and weight)',
             '2 signaux : une forme que le modèle linéaire ne suit pas (horsepower et weight)') \
        in told
    if lang == 'fr':
        final = v['results']['final_test.evaluation']['values']['models']['fit.linear']['mae']
        assert ('Résultat : le test final est ouvert, une fois, sur 80 lignes : erreur absolue '
                f'moyenne {cite.format_value(final, "f2", "fr")} mpg pour le modèle linéaire') \
            in told
        assert '7,16' in told and '7.16' not in told
        assert '· La conclusion : adopter le modèle choisi. Pourquoi : ' in told
    # The closing summary.
    start = next(i for i, x in enumerate(lines) if x.startswith(T('Summary · ', 'Bilan · ')))
    closing = '\n'.join(lines[start:])
    assert T('Summary · I stopped before the final test, as planned.',
             "Bilan · La démonstration est allée jusqu'au bout, comme prévu.") in closing
    queue = len(v['review_queue'])
    assert T(f'Decisions to review ({queue}): the prediction moment, ',
             f'Décisions à relire ({queue}) : le moment de la prédiction, ') in closing
    kept = v['decisions']['model_choice']['value']
    assert T(f'Model kept: the linear model (one-standard-error rule), mean absolute error out '
             f'of fold {_figure(v, kept, lang)}',
             f"Modèle retenu : le modèle linéaire (règle d'une erreur type), erreur absolue "
             f'moyenne hors pli {_figure(v, kept, lang)}') in closing
    assert T('The final test stays sealed', 'Le test final a été ouvert automatiquement') \
        in closing
    assert T('Next: review each decision in the chat, starting with the prediction moment',
             'Et maintenant : relisez chaque décision dans le chat, en commençant par le '
             'moment de la prédiction') in closing
    # Every figure the results and the summary cite is a registered value, written as the
    # study language writes it: the engine's own check traces each one.
    cited = tmp_path / 'cited.txt'
    cited.write_text('\n'.join(x.strip() for x in lines if x.lstrip().startswith(
        (T('Result:', 'Résultat :'), T('Model kept:', 'Modèle retenu :')))), encoding='utf-8')
    check = _flow(study).call('check', '--text', cited, '--study', study)
    assert check['clean'] is True, check['findings']


def test_the_text_summary_and_the_terminal_default(until, tmp_path):
    """R23: ``--format text`` prints a readable summary instead of the JSON document; on a
    terminal it is the default of ``automation run`` only, ``--json`` keeps the JSON there, and
    stdout that is not a terminal always gets the JSON document (CLI-CONTRACT §1)."""
    study, out, _ = until
    text = cli._text(out)
    assert text.startswith('Automatic mode · up to the final test · Auto MPG · UCI · revision '
                           f'{out["revision"]}\n')
    assert 'Recorded by the automatic mode, to review:' in text
    assert '  - The split: cross-validation on the development rows: 5 folds' in text
    assert '  - The feature availability: keep cylinders, ' in text
    assert 'Model kept: the linear model (one-standard-error rule)' in text
    assert 'The full JSON document: add --json.' in text
    assert '"schema"' not in text and '{' not in text

    class Terminal(io.StringIO):
        def isatty(self):
            return True
    run = ['automation', 'run', '--request-id', 'a', '--expected-revision', '1', '--study', 's']
    assert cli._wanted_format(run, Terminal()) == 'text'
    assert cli._wanted_format(run + ['--json'], Terminal()) == 'json'
    assert cli._wanted_format(run + ['--format', 'json'], Terminal()) == 'json'
    assert cli._wanted_format(run, io.StringIO()) == 'json'
    assert cli._wanted_format(run + ['--format', 'text'], io.StringIO()) == 'text'
    assert cli._wanted_format(['status', '--study', 's'], Terminal()) == 'json'
    assert cli.TEXT_ON_A_TERMINAL == (('automation', 'run'),)
    # In a real process on a terminal (a study without automation: nothing to do).
    import pty
    plain = _created(tmp_path / 'plain')
    for extra, readable in (((), True), (('--json',), False)):
        master, slave = pty.openpty()
        try:
            proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'automation', 'run',
                                   *extra, '--request-id', 'p', '--expected-revision',
                                   str(plain.rev()), '--study', str(plain.study)],
                                  stdout=slave, stderr=subprocess.PIPE, text=True,
                                  env=fk.env(), timeout=600)
            os.close(slave)
            shown = os.read(master, 1 << 16).decode('utf-8').replace('\r\n', '\n')
        finally:
            os.close(master)
        assert proc.returncode == 0 and proc.stderr == '', proc.stderr
        if readable:
            assert shown.startswith('Automatic mode · Auto MPG · UCI · revision 1\n'), shown
            assert 'Nothing was done: this study has no automatic mode in force.' in shown
        else:
            assert json.loads(shown)['reason'] == 'automation_not_set'


# --- R24: the review pause is an adoption pause --------------------------------------------

@pytest.mark.parametrize('which', ['until', 'demo'])
def test_the_review_pause_offers_adopt_change_explain(which, request, tmp_path):
    """R24: after the run, the review pause offers adopt, change, explain with the engine's
    localized labels, recommends nothing, quotes the recorded value in words, and names the
    reviewed decision's step (never ``final_test``); once the value is proposed again, the
    pause holds the proposal, still without a recommendation."""
    study, out, _ = request.getfixturevalue(which)
    lang = 'en' if which == 'until' else 'fr'
    labels = {'en': ('I adopt this decision', 'Change something', 'Explain first'),
              'fr': ("J'adopte cette décision", 'Changer quelque chose', "Expliquer d'abord")}
    for nxt in (out['next_action'], view_mod.build(read.open(study))['next_action']):
        assert (nxt['kind'], nxt['decision'], nxt['review']) == ('reconfirm', 'prediction_time',
                                                                 True)
        pause = nxt['pause']
        assert pause['kind'] == 'decision' and pause['recommended_option'] is None
        assert pause['options'] == ['adopt', 'change', 'explain']
        assert tuple(pause['option_labels'].values()) == labels[lang]
        assert pause['position']['step_id'] == 'prediction_time'
        value = nxt['default_value']
        assert pause['proposal_text'] == (
            f'The prediction moment: {value} (value recorded by the automatic mode, not yet in '
            'your words).' if lang == 'en' else
            f'Le moment de la prédiction : {value} (valeur enregistrée par le mode automatique, '
            'pas encore avec vos mots).')
        closed = 'Do you adopt this decision?' if lang == 'en' else 'Adoptez-vous cette décision ?'
        # (A French surface writes a no-break space before the question mark.)
        assert pause['question'].replace('\xa0', ' ') == f'{pause["proposal_text"]}\n\n{closed}'
    # The value proposed again: the pause holds the open proposal, nothing recommended.
    f = _copy(study, tmp_path)
    p = _propose(f, 'prediction_time', out['next_action']['default_value'])['result']
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['review']) == ('await_user_words', True)
    pause = nxt['pause']
    assert (pause['kind'], pause['proposal_id'], pause['recommended_option']) == (
        'decision', p['proposal_id'], None)
    assert pause['position']['step_id'] == 'prediction_time'
    # The next review names its own step (the feature availability), not the current one.
    _confirm(f, p['proposal_id'])
    nxt = f.view()['next_action']
    assert nxt['review'] and nxt['pause']['position']['step_id'] == nxt['decision'] \
        == 'feature_availability'
    assert ('garder ' if lang == 'fr' else 'keep ') in nxt['pause']['proposal_text']
    assert '{' not in nxt['pause']['proposal_text']
