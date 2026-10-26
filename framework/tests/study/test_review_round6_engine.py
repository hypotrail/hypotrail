"""Review round 6 of the study engine (area E): R6E-1..R6E-4.

Every study is a temporary synthetic one (the reviewer's probes, ported).

* R6E-1 and R6E-2, one root cause: ``next_action`` proposed or awaited actions without the
  preconditions the engine applies when it executes them, so it could point forever at a
  refused confirmation or run (a final test whose capture is another configuration, or was
  made stale by a policy adopted again; a policy proposal whose basis changed). The fix is one
  shared check (:mod:`mlkit.study.feasibility`): before naming an action, the view evaluates
  the refusals the engine would raise (the confirmation's own
  :func:`mlkit.study.commands.confirmation_refusals`, the reservation's and the plan's rules
  for a run) and names the first remedy instead. The property test follows ``next_action``
  from many states, executing every action exactly as given, and asserts that no action is
  refused, that no state repeats without progress, and that the walk reaches ``done``.
* R6E-3: a rule named for the study's policy evaluation is not called the engine's default.
* R6E-4: "12 percent", "12 pour cent", "1.5 per mille", "12 pour mille" are percentages and
  per milles; "trillion" is 10^12; the French "billion" is 10^12 (long scale).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import flowkit as fk
from mlkit.study import (audience, feasibility, governance, junior, numtrace,
                         records as rec, state as st, view as view_mod)
from test_review_round2_training_exclusions import OPEN, ReviewFlow
from test_review_round3_engine import ADOPT, CHOOSE, REG_WORDS, _changed

sys.path.insert(0, str(Path(__file__).resolve().parent / 'libraries'))

ACK = ("Understood, the quality overview was interrupted and its outcome is unknown; don't "
       'restart it.')
HOLD = "Wait for my manager's figure before we settle this decision."
RESOLVE = "My manager's figure is here, so the condition is met."
CONCLUSION = ('The development evidence is all the study can cite: the final test was opened '
              'once.')
WORDS = {'model_choice': CHOOSE, 'policy': ADOPT, 'final_test': OPEN}
OTHER_VARIANT = {'variants': [{'kind': 'regularisation', 'strength': 'weak',
                               'question': 'Does a weaker penalty fit the rows better?'}]}
REVIEW_VARIANT_KEYS = {'origin': 'planned', 'diagnostic_result_id': None}


# --- the studies ------------------------------------------------------------------------------

class Study:
    """A study driven in-process, and what the walker needs to know about it."""

    def __init__(self, flow: fk.Flow, task: str, review: bool):
        self.f, self.task, self.review = flow, task, review

    def __getattr__(self, name):
        return getattr(self.f, name)


def _legacy(base: Path, task: str, language: str) -> Study:
    case_dir = fk.make_case(base / f'case-{task}', n_rows=300, task=task)['case'].parent
    f = fk.Flow(base / f'study-{task}', case_dir, prefix=task[:3])
    f.call('init', '--case', case_dir, '--study', f.study, '--lang', language)
    return Study(f, task, False)


def _review(base: Path, task: str, language: str, monkeypatch, delay: int = 0) -> Study:
    if task == 'binary':
        f = ReviewFlow(base, outcome_delay=delay, language=language)
        f.init()
        return Study(f, task, True)
    mod = fk._module
    original = mod.make_case
    with monkeypatch.context() as m:
        m.setattr(mod, 'make_case', lambda out_dir, n_rows=300, **kw:
                  original(out_dir, task='regression', n_rows=n_rows))
        paths = mod.make_review_case(base / 'case-reg', future=True, outcome_delay=delay,
                                     n_rows=300)
    f = fk.Flow(base / 'reg', paths['case'].parent, prefix='reg')
    f.call('init', '--case', paths['case'], '--study', f.study, '--reliability-profile',
           'review-v1', '--lang', language)
    return Study(f, task, True)


def _previous(base: Path, task: str, language: str) -> Study:
    """Owner session 2026-10-26 (L5): a study of the generation before the structural-first
    plan (no ``exploration_order``): it explores the target before the preparation and keeps
    the earlier drafts."""
    s = _legacy(base, task, language)
    fk.previous_generation(s.study)
    return s


BASES = {'legacy-binary-en': lambda b, m: _legacy(b, 'binary', 'en'),
         'legacy-binary-fr': lambda b, m: _legacy(b, 'binary', 'fr'),
         'legacy-regression-fr': lambda b, m: _legacy(b, 'regression', 'fr'),
         'review-binary-fr': lambda b, m: _review(b, 'binary', 'fr', m, delay=2),
         'review-binary-en': lambda b, m: _review(b, 'binary', 'en', m),
         'review-regression-en': lambda b, m: _review(b, 'regression', 'en', m),
         # L5: every base above is structural-first (``init`` writes it); these two are not.
         'previous-binary-en': lambda b, m: _previous(b, 'binary', 'en'),
         'previous-regression-fr': lambda b, m: _previous(b, 'regression', 'fr')}


# --- the walker: every next_action executed exactly as given --------------------------------

def _run(s, *args, expect=None):
    return s.call('run', *args, '--request-id', s.rid(), '--expected-revision', s.rev(),
                  '--study', s.study, expect=expect)


def _words(s: Study, decision: str) -> str:
    if decision == 'model_choice' and s.task == 'regression':
        return REG_WORDS
    return WORDS.get(decision) or fk.default_words(decision)


def _junior_value(s: Study, decision: str, nxt: dict):
    """The value the junior states where the engine drafts none (the prediction moment of a
    legacy study, the model choice, the conclusion's verdict and text)."""
    if decision == 'prediction_time':
        return ('Predict using information available at the planted decision time' if s.review
                else 'when the record is created, before the outcome')
    if decision == 'model_choice':
        return 'fit.linear' if s.task == 'regression' else 'fit.logistic'
    if decision == 'conclusion':
        return {'verdict': (nxt.get('verdicts') or ['inconclusive'])[0], 'text': CONCLUSION}
    raise AssertionError(f'the engine asks the junior for no value of {decision}: {nxt}')


def _propose(s: Study, decision: str, value) -> dict:
    return s.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                  '--restatement', f'You decide the {decision} as stated.', '--rationale',
                  'It fits the scenario.', '--request-id', s.rid(), '--expected-revision',
                  s.rev(), '--study', s.study, expect=None)


def _key(nxt: dict) -> str:
    return json.dumps({k: nxt.get(k) for k in ('kind', 'activity', 'decision', 'proposal_id',
                                               'rules', 'options', 'default_value',
                                               'execution_id', 'note_id')},
                      sort_keys=True, default=str)


def execute(s: Study, nxt: dict) -> dict:
    """Execute one ``next_action`` exactly as given; the engine's answer. The junior's words
    are supplied only where the engine asks for them (a confirmation, a hold, an
    acknowledgement) and a value only where it drafts none."""
    kind = nxt['kind']
    if kind == 'show_data_card':
        # Informational; its message says to propose the prediction moment next.
        nxt = {'kind': 'propose', 'decision': 'prediction_time'}
        kind = 'propose'
    if kind == 'run':
        args = [nxt['activity']]
        for rule in nxt.get('rules') or []:
            args += ['--rule', rule]
        for option, value in (nxt.get('options') or {}).items():
            args += [f'--{option}', str(value)]
        return _run(s, *args)
    if kind == 'await_user_words':
        return s.call('decide', 'confirm', nxt['proposal_id'], '--user-words',
                      _words(s, nxt['decision']), '--request-id', s.rid(),
                      '--expected-revision', s.rev(), '--study', s.study, expect=None)
    if kind in ('propose', 'reconfirm'):
        decision = nxt['decision']
        value = nxt.get('default_value')
        if value is None:
            value = (nxt.get('recommended') or {}).get('value')
        if value is None or decision == 'conclusion':
            value = _junior_value(s, decision, nxt)
        return _propose(s, decision, value)
    if kind == 'resolve_hold':
        return s.call('decide', 'note', '--resolve', nxt['note_id'], '--text', RESOLVE,
                      '--request-id', s.rid(), '--expected-revision', s.rev(), '--study',
                      s.study, expect=None)
    if kind in ('acknowledge_interruption', 'outcome_unknown'):
        return s.call('run', '--acknowledge-interruption', nxt['execution_id'], '--user-words',
                      ACK, '--request-id', s.rid(), '--expected-revision', s.rev(), '--study',
                      s.study, expect=None)
    raise AssertionError(f'unknown next_action: {nxt}')


def walk(s: Study, *, limit: int = 120, hooks=(), log=None,
         choices: Path | None = None) -> tuple[list, dict]:
    """Follow ``next_action`` until ``done``; each hook ``(when, apply)`` fires once, the first
    time ``when(next_action, study)`` holds, before that action is executed (the junior or the
    team change something there). Asserts the property: every action accepted, no state seen
    twice (a state is the revision and the action: an action that changes nothing would be
    named again at the same revision), and ``done`` reached.

    Owner session 2026-10-26 (L1, J-PICK): every pause with options labels each of them, and
    with ``choices`` (a scratch folder) every ``choice_options`` entry is confirmed on a clone
    of the study, and every other value of that decision is refused there
    (:func:`check_choice_options`)."""
    log = [] if log is None else log
    seen: set[tuple[int, str]] = set()
    pending = list(hooks)
    for _ in range(limit):
        view = s.view()
        nxt = view['next_action']
        for hook in list(pending):
            if hook[0](nxt, s):
                pending.remove(hook)
                hook[1](s)
                view = s.view()
                nxt = view['next_action']
        assert nxt.get('junior_message') and nxt.get('audience') in audience.AUDIENCES, nxt
        pause = nxt['pause']
        assert list(pause['option_labels']) == pause['options'], pause
        assert all(isinstance(t, str) and t.strip() for t in pause['option_labels'].values())
        if nxt.get('choice_options'):
            assert pause['kind'] == 'choice' and pause['recommended_option'] is None, pause
            if choices is not None:
                check_choice_options(s, nxt, choices / f'r{view["revision"]}')
        state_key = (view['revision'], _key(nxt))
        assert state_key not in seen, ('a state repeats without progress', nxt, log[-6:])
        seen.add(state_key)
        log.append((nxt['kind'], nxt.get('activity') or nxt.get('decision')))
        if nxt['kind'] == 'done':
            assert not pending, ('a hook never fired', [h[2] for h in pending], log)
            return log, nxt
        assert nxt['kind'] != 'blocked', (nxt, log[-6:])
        out = execute(s, nxt)
        assert out.get('ok'), ('refused as given', nxt, out.get('error'), log[-6:])
        if nxt['kind'] == 'run':
            assert out['status'] == 'promoted', (nxt, out['status'], log[-6:])
    raise AssertionError(f'next_action did not settle: {log[-10:]}')


def accepted_on_a_clone(s: Study, folder: Path, decision: str, value) -> bool:
    """Whether the engine adopts ``value`` for ``decision`` on a copy of the study: proposed,
    then confirmed with the junior's words, both through the CLI."""
    import shutil
    shutil.copytree(s.study, folder)
    f = fk.Flow(folder, s.case_dir, prefix='clone')
    if decision == 'conclusion':
        value = {**value, 'text': CONCLUSION}
    p = f.call('decide', 'propose', decision, '--value-json', json.dumps(value),
               '--restatement', f'You decide the {decision} as stated.', '--rationale',
               'It fits the scenario.', '--request-id', f.rid(), '--expected-revision',
               f.rev(), '--study', f.study, expect=None)
    if not p.get('ok'):
        return False
    out = f.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                 _words(s, decision), '--request-id', f.rid(), '--expected-revision', f.rev(),
                 '--study', f.study, expect=None)
    return bool(out.get('ok'))


def candidate_values(state, decision: str) -> list:
    """Every value of a free choice the engine knows: each verdict of the task; each model
    slot the study may name, the binary baseline and an undeclared variant slot included."""
    from mlkit.study import commands as cmd, preconditions, trials
    if decision == 'conclusion':
        return [{'verdict': v} for v in preconditions.conclusion_verdicts(state)]
    slots = list(cmd.model_choices(state))
    extra = ['fit.baseline'] + [v for v in trials.VARIANT_SLOTS if v not in slots][:1]
    return slots + [v for v in extra if v not in slots]


def check_choice_options(s: Study, nxt: dict, folder: Path) -> None:
    """J-PICK (L1, R2c): ``choice_options`` lists exactly the values the engine accepts now:
    each one is adopted on a clone, every other value of the decision is refused there."""
    decision = nxt['decision']
    offered = [o['value'] for o in nxt['choice_options']]
    assert [o['id'] for o in nxt['choice_options']] == nxt['pause']['options']
    for i, value in enumerate(candidate_values(s.state(), decision)):
        accepted = accepted_on_a_clone(s, folder / str(i), decision, value)
        assert accepted == (value in offered), (decision, value, offered)


# --- the changes made along the way (the hooks) ---------------------------------------------

def _decide(s: Study, decision: str, value, words: str | None = None) -> None:
    p = _propose(s, decision, value)
    assert p.get('ok'), p
    out = s.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                 words or _words(s, decision), '--request-id', s.rid(), '--expected-revision',
                 s.rev(), '--study', s.study, expect=None)
    assert out.get('ok'), out


def _note(s: Study, decision: str) -> None:
    out = s.call('decide', 'note', '--about', decision, '--text', HOLD, '--request-id', s.rid(),
                 '--expected-revision', s.rev(), '--study', s.study, expect=None)
    assert out.get('ok'), out


def _interrupt(s: Study) -> None:
    """A real process killed right after its reservation: an execution whose outcome is
    unknown (``eda.correlation`` needs no decision; owner session 2026-10-26, L5: not
    ``eda.quality``, which a structural-first study has already run as a plan step, so its
    run would be ``already_current`` and reserve nothing)."""
    env = fk.env(HYPOTRAIL_TEST_HOOKS='1', HYPOTRAIL_FAULT='run_after_reserve')
    subprocess.run([sys.executable, '-m', 'mlkit.study.cli', 'run', 'eda.correlation',
                    '--request-id', f'kill{s.rev()}', '--expected-revision', str(s.rev()),
                    '--study', str(s.study)], env=env, capture_output=True, text=True,
                   timeout=600)
    assert s.state()['executions']['active'] or s.state()['executions']['interrupted']


def change_preprocessing(s: Study) -> None:
    _decide(s, 'preprocessing', {**governance.DEFAULT_PREPROCESSING, 'rare_category_min_rows': 5})


def change_variant(s: Study) -> None:
    value = json.loads(json.dumps(OTHER_VARIANT))
    if s.review:
        value['variants'][0].update(REVIEW_VARIANT_KEYS)
    _decide(s, 'model_variant', value)


def change_model(s: Study) -> None:
    """The model choice moves to the variant (fitted first when it is not current)."""
    state = s.state()
    for slot in ('fit.variant',):
        if not st.is_current(state, slot):
            assert _run(s, slot).get('ok')
    if s.task == 'regression' and not st.is_current(s.state(), 'evaluate.regression'):
        assert _run(s, 'evaluate.regression').get('ok')
    _decide(s, 'model_choice', 'fit.variant')


def change_policy(s: Study) -> None:
    """A legacy binary study adopts another rule (evaluated first)."""
    assert _run(s, 'policy.evaluate', '--rule', 'capacity:40', '--rule', 'share:0.1').get('ok')
    model = (s.state()['decisions'].get('model_choice') or {}).get('value')
    rule = 'capacity:40' if model in (None, 'fit.logistic') else f'capacity:40@{model}'
    _decide(s, 'policy', rule)


def readopt_policy(s: Study) -> None:
    """The adopted rule is adopted again after an evaluation on more rules (the capture
    becomes stale): the reviewer's ``rechoose2 policy``."""
    assert _run(s, 'policy.evaluate', '--rule', 'capacity:40', '--rule', 'share:0.1').get('ok')
    decision = s.state()['decisions']['policy']
    rule = rec.policy_rule(decision['value'])
    new = 'share:0.1' if rule != 'share:0.1' else 'capacity:40'
    model = (s.state()['decisions'].get('model_choice') or {}).get('value')
    _decide(s, 'policy', new if model in (None, 'fit.logistic') else f'{new}@{model}')


def capture(s: Study) -> None:
    out = _run(s, 'predictor.capture')
    assert out.get('ok'), out


def capture_then(change):
    def apply(s: Study) -> None:
        capture(s)
        change(s)
    return apply


def unloadable(monkeypatch, tmp_path):
    """The installed runtime now differs from the one the capture's bundle binds (an engine
    update), so the capture cannot be loaded as the final evaluation loads it."""
    def apply(s: Study) -> None:
        capture(s)
        from test_review_round5_engine import _changed_runtime
        _changed_runtime(tmp_path, monkeypatch, 'errors.py')
    return apply


def code_change(monkeypatch, module='mlkit.study.policy'):
    def apply(s: Study) -> None:
        _changed(monkeypatch, module)
    return apply


def confirm_not_open(s: Study) -> None:
    """The final test confirmed while an execution is interrupted: the opening that follows
    the confirmation is refused; the final test is confirmed and sealed."""
    _interrupt(s)
    value = st.b1_default_value(s.state(), 'final_test')
    p = _propose(s, 'final_test', value)
    assert p.get('ok'), p
    out = s.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', OPEN,
                 '--request-id', s.rid(), '--expected-revision', s.rev(), '--study', s.study,
                 expect=None)
    assert out.get('ok') and out['result']['opening']['status'] == 'refused', out
    assert not st.final_test_opened(s.state())


def then(*steps):
    def apply(s: Study) -> None:
        for step in steps:
            step(s)
    return apply


# When a hook fires.
def at_propose(decision):
    return lambda nxt, s: nxt['kind'] == 'propose' and nxt.get('decision') == decision


def at_await(decision):
    return lambda nxt, s: nxt['kind'] == 'await_user_words' and nxt.get('decision') == decision


def at_final(nxt, s) -> bool:
    return nxt.get('decision') == st.FINAL_TEST or nxt.get('activity') in (
        'predictor.capture', 'final_test.evaluation')


def at_conclusion(nxt, s) -> bool:
    return nxt.get('decision') == 'conclusion'


# Every decision of a binary study, in the plan's order (a regression study has no policy:
# its hook is dropped by ``_hooks``).
DECISIONS = ('prediction_time', 'feature_availability', 'split', 'success_criterion',
             'preprocessing', 'model_variant', 'model_choice', 'policy', 'final_test',
             'conclusion')


def proposing(decision):
    return lambda nxt, s: (nxt.get('decision') == decision
                           and nxt['kind'] in ('propose', 'reconfirm')) or (
        decision == 'prediction_time' and nxt['kind'] == 'show_data_card')


def confirmed(decision):
    return lambda nxt, s: s.state()['decisions'][decision]['status'] == 'confirmed'


def at_run(nxt, s) -> bool:
    return nxt['kind'] == 'run' and nxt.get('activity') in ('fit.logistic', 'fit.linear')


def choice_of(s: Study) -> str:
    return st.choice_decision(s.state())


# --- the property ---------------------------------------------------------------------------

def _scenarios():
    """(id, base, hooks factory). A factory takes (monkeypatch, tmp_path) and returns the
    hooks ``(when, apply, name)``."""
    out = []

    def add(name, bases, factory):
        for base in bases:
            out.append(pytest.param(base, factory, id=f'{base}:{name}'))

    every = list(BASES)
    binary_legacy = ['legacy-binary-en', 'legacy-binary-fr']
    add('init', every, lambda m, t: [])
    add('interrupted-early', ['legacy-binary-en', 'review-regression-en'],
        lambda m, t: [(at_run, _interrupt, 'interrupt')])
    for decision in ('split', 'preprocessing', 'model_variant'):
        add(f'held-before-{decision}', ['legacy-binary-fr', 'review-regression-en'],
            lambda m, t, d=decision: [(at_propose(d), lambda s, d=d: _note(s, d), 'hold')])
    add('every-decision-held-when-proposed', ['legacy-binary-en', 'review-binary-fr'],
        lambda m, t: [(proposing(d), lambda s, d=d: _note(s, d), f'hold {d}')
                      for d in DECISIONS])
    add('every-decision-held-once-confirmed', ['legacy-regression-fr', 'review-binary-en'],
        lambda m, t: [(confirmed(d), lambda s, d=d: _note(s, d), f'hold {d}')
                      for d in DECISIONS])
    add('held-after-confirming-success-criterion', ['legacy-regression-fr', 'review-binary-en'],
        lambda m, t: [(confirmed('success_criterion'),
                       lambda s: _note(s, 'success_criterion'), 'hold')])
    add('held-policy-proposal', binary_legacy,
        lambda m, t: [(at_await('policy'), lambda s: _note(s, 'policy'), 'hold')])
    # A proposal whose basis changes before it is confirmed (R6E-2).
    add('policy-proposal-then-model', binary_legacy,
        lambda m, t: [(at_await('policy'), change_model, 'model')])
    add('policy-proposal-then-preprocessing', binary_legacy,
        lambda m, t: [(at_await('policy'), change_preprocessing, 'preprocessing')])
    add('model-proposal-then-variant', ['legacy-regression-fr', 'legacy-binary-en'],
        lambda m, t: [(at_await('model_choice'), change_variant, 'variant')])
    add('final-proposal-then-model', ['legacy-binary-en', 'legacy-regression-fr'],
        lambda m, t: [(at_await(st.FINAL_TEST), change_model, 'model')])
    # The capture made, then the choice changes under it (R6E-1).
    for name, change, bases in (
            ('model', change_model, ['legacy-binary-en', 'legacy-regression-fr',
                                     'review-binary-en']),
            ('policy', readopt_policy, binary_legacy),
            ('preprocessing', change_preprocessing, ['legacy-binary-fr',
                                                     'review-regression-en']),
            ('variant', change_variant, ['legacy-binary-en', 'review-binary-fr'])):
        add(f'capture-then-{name}', bases,
            lambda m, t, c=change: [(at_final, capture_then(c), 'capture')])
    add('variant-before-capture', ['legacy-regression-fr'],
        lambda m, t: [(at_final, change_variant, 'variant')])
    add('capture-unloadable', ['legacy-binary-en', 'review-regression-en'],
        lambda m, t: [(at_final, unloadable(m, t), 'unloadable')])
    add('capture-code-changed', ['legacy-binary-fr'],
        lambda m, t: [(at_final, then(capture, code_change(m, 'mlkit.study.policy')),
                       'code')])
    # The final test confirmed but not opened, then something changes (or not).
    add('confirmed-not-opened', ['review-binary-fr', 'legacy-regression-fr'],
        lambda m, t: [(at_final, confirm_not_open, 'confirm')])
    add('confirmed-not-opened-then-model', ['legacy-binary-en'],
        lambda m, t: [(at_final, then(confirm_not_open, change_model), 'confirm')])
    # After the opening.
    add('opened-then-code', ['review-binary-en', 'legacy-regression-fr'],
        lambda m, t: [(at_conclusion, code_change(m), 'code')])
    add('opened-then-model', ['legacy-binary-fr'],
        lambda m, t: [(at_conclusion, change_model, 'model')])
    add('opened-then-hold', ['review-regression-en'],
        lambda m, t: [(at_conclusion, lambda s: _note(s, 'conclusion'), 'hold')])
    # Owner session 2026-10-26 (L5): the structural-first plan and its drafts. A look at the
    # target before the drafted preparation (the stamp, not a refusal); a hold on the
    # preparation and a changed preparation under a policy proposal in the previous
    # generation too.
    add('target-look-before-preparation', ['legacy-binary-fr', 'review-regression-en'],
        lambda m, t: [(at_propose('preprocessing'), _look_at_target, 'look')])
    add('held-before-preprocessing', ['previous-binary-en'],
        lambda m, t: [(at_propose('preprocessing'), lambda s: _note(s, 'preprocessing'),
                       'hold')])
    add('policy-proposal-then-preprocessing', ['previous-binary-en'],
        lambda m, t: [(at_await('policy'), change_preprocessing, 'preprocessing')])
    return out


def _look_at_target(s: Study) -> None:
    activity = 'eda.target_rate' if s.task == 'binary' else 'eda.target_summary'
    out = _run(s, activity, expect=0)
    assert out['status'] == 'promoted', out


@pytest.mark.parametrize('base,factory', _scenarios())
def test_next_action_is_never_refused_and_settles(tmp_path, monkeypatch, base, factory):
    """The required property (R6E-1, R6E-2): from many states, ``next_action`` followed
    exactly as given never meets a refusal, never repeats a state without progress, and
    reaches ``done``."""
    s = BASES[base](tmp_path, monkeypatch)
    made = factory(monkeypatch, tmp_path)
    hooks = [h for h in made
             if not h[2].startswith('hold ') or h[2][5:] in s.state()['decisions']]
    # L1 (J-PICK): the scenarios without a change check every free choice on clones.
    log, last = walk(s, hooks=[(w, a, n) for w, a, n in hooks],
                     choices=tmp_path / 'choices' if not made else None)
    assert last['kind'] == 'done', log[-6:]
    if any(n in ('confirm', 'capture', 'unloadable', 'code') for _, _, n in hooks) \
            or base == 'review-binary-fr':
        assert st.final_test_opened(s.state()), log


# --- the reviewer's probes, ported ----------------------------------------------------------

def _legacy_at_policy(tmp_path, language='en') -> Study:
    from test_review_round5_engine import _legacy_at_policy as at_policy
    return Study(at_policy(tmp_path, language), 'binary', False)


def _chosen(tmp_path) -> Study:
    import test_capture_final as tcf
    return Study(tcf._chosen(tmp_path, 'binary'), 'binary', False)


@pytest.mark.parametrize('mode', ['policy', 'model'])
def test_rechoose2_the_final_test_opens_after_the_choice_changed_under_its_capture(tmp_path,
                                                                                  mode):
    """``rechoose2.py``: a capture made, then the policy adopted again (the capture stale)
    or the model changed (the capture another configuration); the final test opened only
    after the capture is made again, never a refused confirmation in a loop."""
    s = _chosen(tmp_path)
    capture(s)
    if mode == 'policy':
        _run(s, 'policy.evaluate', '--rule', 'capacity:40', '--rule', 'share:0.1', expect=0)
        _decide(s, 'policy', 'share:0.1')
    else:
        _decide(s, 'model_choice', 'fit.variant')
    log, _ = walk(s)
    assert ('run', 'predictor.capture') in log, log
    assert st.final_test_opened(s.state())


def test_the_other_configuration_refusal_carries_a_junior_message(tmp_path):
    """R6E-1: confirming the final test on the configuration chosen now while the capture is
    of another one is refused with the junior's message, and ``next_action`` captures
    again first."""
    s = _chosen(tmp_path)
    capture(s)
    _decide(s, 'model_choice', 'fit.variant')
    for _ in range(10):
        nxt = s.view()['next_action']
        if nxt['activity' if nxt['kind'] == 'run' else 'kind'] == 'predictor.capture':
            break
        assert execute(s, nxt).get('ok'), nxt
    assert nxt['kind'] == 'run' and nxt['activity'] == 'predictor.capture', nxt
    assert 'another configuration' in nxt['junior_message'], nxt
    assert 'captures the chosen model again' in nxt['junior_message'], nxt
    assert 'still sealed' in nxt['junior_message']
    p = _propose(s, 'final_test', st.b1_default_value(s.state(), 'final_test'))
    out = s.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', OPEN,
                 '--request-id', s.rid(), '--expected-revision', s.rev(), '--study', s.study,
                 expect=2)
    details = out['error']['details']
    assert any(m.get('captured') for m in details['missing']), details
    assert 'another configuration' in details['junior_message']
    assert 'No final-test row was read' in details['junior_message']
    nxt = s.view()['next_action']
    assert (nxt['kind'], nxt['activity']) == ('run', 'predictor.capture'), nxt
    assert nxt['proposal_id'] == p['result']['proposal_id']


@pytest.mark.parametrize('mode', ['model', 'pre'])
def test_polmodel2_a_policy_proposal_whose_basis_changed_is_resolved(tmp_path, mode):
    """``polmodel2.py``: a policy proposal, then the model (``proposal_stale`` on every
    confirmation) or the preprocessing (the rerouted evaluation refused while the fits are
    not current) changes; ``next_action`` runs what is needed and proposes again, and the
    policy is adopted."""
    s = _legacy_at_policy(tmp_path)
    _run(s, 'policy.evaluate', '--rule', 'capacity:40', expect=0)
    p = _propose(s, 'policy', 'capacity:30' if mode == 'pre' else 'capacity:40')
    pid = p['result']['proposal_id']
    if mode == 'model':
        _decide(s, 'model_choice', 'fit.variant')
    else:
        change_preprocessing(s)
    nxt = s.view()['next_action']
    assert not (nxt['kind'] == 'await_user_words' and nxt['proposal_id'] == pid), nxt
    log, _ = walk(s)
    assert s.state()['proposals'][pid]['status'] != 'open'
    assert ('propose', 'policy') in log
    assert s.state()['decisions']['policy']['status'] == 'confirmed'
    if mode == 'model':
        assert rec.policy_model(s.state()['decisions']['policy']['value']) == 'fit.variant'


def test_a_stale_policy_proposal_is_proposed_again_with_the_chosen_model(tmp_path):
    """The remedy of ``proposal_stale``: the same rule, on the model chosen now, said to the
    junior in words; the rule's source is the earlier proposal, not the engine."""
    s = _legacy_at_policy(tmp_path, 'fr')
    _run(s, 'policy.evaluate', '--rule', 'capacity:40', expect=0)
    pid = _propose(s, 'policy', 'capacity:40')['result']['proposal_id']
    _decide(s, 'model_choice', 'fit.variant')
    nxt = s.view()['next_action']
    assert (nxt['kind'], nxt['decision'], nxt['replaces']) == ('propose', 'policy', pid), nxt
    assert nxt['default_value'] == 'capacity:40@fit.variant'
    assert nxt['junior_message'].startswith('La proposition sur')
    assert nxt['recommended']['why'] == junior.POLICY_WHY['proposal'][1]
    assert 'Proposée à nouveau' in nxt['junior_digest']


def test_polstale_a_proposal_before_a_preprocessing_change_settles(tmp_path):
    """``polstale.py``: the walk from a policy proposal made before a preprocessing change."""
    s = _legacy_at_policy(tmp_path)
    _propose(s, 'policy', 'capacity:30')
    change_preprocessing(s)
    log, last = walk(s)
    assert last['kind'] == 'done'


def test_a_hold_is_asked_about_never_confirmed_over(tmp_path):
    """A held decision: ``next_action`` asks the junior whether the condition is met
    (``resolve_hold``), in the study language, never a confirmation the hold refuses."""
    s = _legacy_at_policy(tmp_path, 'fr')
    _note(s, 'policy')
    for _ in range(8):
        nxt = s.view()['next_action']
        if nxt['kind'] == 'resolve_hold':
            break
        assert execute(s, nxt).get('ok'), nxt
    assert nxt['kind'] == 'resolve_hold' and nxt['decision'] == 'policy', nxt
    assert nxt['note_id'] == 'n_1' and nxt['user_words'] == HOLD
    assert nxt['question'] == 'La condition que vous avez posée est-elle remplie maintenant ?'
    assert nxt['junior_message'].startswith('Vous avez mis la règle de décision en attente') \
        or 'en attente' in nxt['junior_message'], nxt['junior_message']
    assert HOLD in nxt['junior_message'] and 'decide note --resolve n_1' in nxt['message']
    assert execute(s, nxt).get('ok')
    assert s.view()['next_action']['kind'] == 'await_user_words'


# --- R6E-3 -----------------------------------------------------------------------------------

@pytest.mark.parametrize('language', ['en', 'fr'])
def test_polwhy_a_rule_named_for_the_evaluation_is_not_the_engine_s(tmp_path, language):
    """``polwhy.py``: the evaluation ran on a capacity the team named; the proposal carries
    it and says where it comes from (that rule), not that the engine chose it."""
    s = _legacy_at_policy(tmp_path, language)
    _run(s, 'policy.evaluate', '--rule', 'capacity:40', expect=0)
    for _ in range(4):
        nxt = s.view()['next_action']
        if nxt['kind'] == 'propose':
            break
        assert execute(s, nxt).get('ok')
    assert (nxt['decision'], nxt['default_value']) == ('policy', 'capacity:40')
    fr = language == 'fr'
    assert nxt['recommended']['why'] == junior.POLICY_WHY['evaluated'][fr]
    engine = junior.POLICY_WHY['engine'][fr]
    assert engine not in nxt['junior_digest']
    assert ('La règle nommée pour cette étude' if fr else 'The rule named for this study') \
        in nxt['junior_digest']
    assert ('Le moteur propose' if fr else 'The engine proposes') not in nxt['junior_digest']


def test_the_engine_s_own_shares_keep_the_engine_s_reason(tmp_path):
    s = _legacy_at_policy(tmp_path)
    _run(s, 'policy.evaluate', *[a for r in view_mod.RECOMMENDED_RULES for a in ('--rule', r)],
         expect=0)
    for _ in range(4):
        nxt = s.view()['next_action']
        if nxt['kind'] == 'propose':
            break
        assert execute(s, nxt).get('ok')
    assert nxt['default_value'] == view_mod.RECOMMENDED_RULE
    assert nxt['recommended']['why'] == junior.POLICY_WHY['engine'][0]


# --- R6E-4 -----------------------------------------------------------------------------------

def _pool(language='en', **values):
    results = {'eda.quality': {'result_id': 'a' * 64, 'current': True, 'integrity': 'ok',
                               'values': values, 'n_rows': None}}
    return numtrace.Pool({'results': results, 'decisions': {}, 'open_proposals': [],
                          'settings': {}, 'dataset': {}, 'facts': {'by_status': {}},
                          'plan': [], 'not_yet_defensible': [], 'language': language})


def _traced(pool, text):
    findings, traced = numtrace.trace_text(pool, text, 'draft')
    return ([(t.get('path') or t.get('id'), t.get('value')) for t in traced],
            [f['details'].get('number') for f in findings])


@pytest.mark.parametrize('language', ['en', 'fr'])
@pytest.mark.parametrize('text', ['About 12 percent of bookings.', 'About 12 per cent of bookings.',
                                  'Environ 12 pour cent des réservations.', 'A 12-percent rate.',
                                  'About 12% of bookings.', 'About 12 PERCENT of bookings.'])
def test_num3_a_percentage_in_words_is_a_percentage(text, language):
    assert _traced(_pool(language, rate=0.12), text) == ([('rate', 0.12)], [])


@pytest.mark.parametrize('language', ['en', 'fr'])
@pytest.mark.parametrize('text', ['About 12 percent of bookings.', 'Environ 12 pour cent.',
                                  'About 12 per cent.', '12 pour mille', '12 per mille'])
def test_a_made_up_percentage_never_passes_as_a_count(text, language):
    """A count of 12 does not make "12 percent" (or "12 per mille") traced."""
    traced, findings = _traced(_pool(language, n_rows=12), text)
    assert traced == [] and findings, (traced, findings)


@pytest.mark.parametrize('language', ['en', 'fr'])
@pytest.mark.parametrize('text,value', [('1.5 per mille', 0.0015), ('12 pour mille', 0.012),
                                        ('12 per mil', 0.012), ('12 permille', 0.012),
                                        ('1.5‰', 0.0015)])
def test_a_per_mille_in_words_is_a_per_mille(text, value, language):
    if language == 'fr':
        text = text.replace('1.5', '1,5')
    assert _traced(_pool(language, rate=value), text) == ([('rate', value)], [])
    assert _traced(_pool(language, n_rows=12, other=1.5), text)[0] == []


@pytest.mark.parametrize('text,language,value', [
    ('1.5 trillion', 'en', 1.5e12), ('2 trillions', 'en', 2e12),
    ('1.5 billion', 'en', 1.5e9), ('1,5 billion', 'fr', 1.5e12), ('2 billions', 'fr', 2e12),
    ('2 billiards', 'fr', 2e15), ('1,5 milliard', 'fr', 1.5e9), ('3 trillions', 'fr', 3e18)])
def test_scale_words_of_both_scales(text, language, value):
    assert _traced(_pool(language, big=value), text) == ([('big', value)], [])
    # Never the bare number, nor the other scale.
    assert _traced(_pool(language, big=float(text.split()[0].replace(',', '.'))), text)[0] == []


def test_billiard_is_no_scale_in_english():
    traced, findings = _traced(_pool('en', big=2e15), '2 billiards')
    assert traced == [] and findings


def test_the_digit_words_agree_with_the_words_reader():
    """"12 percent" and "twelve percent" are read alike."""
    pool = _pool('en', rate=0.12)
    assert _traced(pool, 'About twelve percent of bookings.')[0] == [('rate', 0.12)]
    assert _traced(pool, 'About 12 percent of bookings.')[0] == [('rate', 0.12)]
    assert _traced(_pool('en', n_rows=12), 'About twelve percent of bookings.')[0] == []


# --- the shared check itself ------------------------------------------------------------------

def test_the_check_is_skipped_in_a_read_only_process(tmp_path, monkeypatch):
    s = _legacy_at_policy(tmp_path)
    _propose(s, 'policy', 'capacity:30')
    change_preprocessing(s)
    checked = s.view()['next_action']
    monkeypatch.setenv('HYPOTRAIL_READ_ONLY', '1')
    raw = s.view()['next_action']
    assert raw['kind'] == 'await_user_words' and checked['kind'] != 'await_user_words'


def test_the_confirmation_and_the_check_share_one_function(tmp_path):
    """``decide confirm`` and ``preview effects`` and ``next_action`` read the same
    refusals (``commands.confirmation_refusals``)."""
    from mlkit.study import commands as cmd, read
    from mlkit.study.store import StudyStore
    s = _legacy_at_policy(tmp_path)
    _run(s, 'policy.evaluate', '--rule', 'capacity:40', expect=0)
    pid = _propose(s, 'policy', 'capacity:40')['result']['proposal_id']
    _decide(s, 'model_choice', 'fit.variant')
    state = read.open(s.study).state
    store = StudyStore(s.study)
    plan = cmd.confirmation_plan(state, store, pid)
    found = feasibility.refusals(state, store, {'kind': 'await_user_words', 'proposal_id': pid,
                                                'decision': 'policy'})
    assert [r['code'] for r in found] == [b['code'] for b in plan['blocked']]
    assert found[0]['reason'] == 'proposal_stale'
