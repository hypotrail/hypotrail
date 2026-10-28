"""Journey check J-PANEL, engine part (owner session 2026-10-26, plan §5.3; R1b, R16;
contract P1, CLI-CONTRACT §17.1).

A scripted walkthrough drives a study from ``init`` to ``done`` through the CLI's own code path
(``cli.run``, as the agent's terminal does) with the study panel on (``HYPOTRAIL_COMPANION=1``,
stage v3), in English and in French, on the synthetic binary case and on Auto MPG (regression).
At every write, ``next_action.panel.shown`` names the anchor of the one page that shows what
the write produced; at every read after step 0 it is null. ``walk`` is shared with the panel
side of the check (``clients/vscode-companion/test/test_journey_panel.py``) and with
``test_l3_language.py``. This is not a Copilot session: the agent's words are a test script.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

import flowkit as fk
from mlkit.study import companion_env as ce

REPO = Path(__file__).resolve().parents[3]
AUTO_MPG = REPO / 'use-cases' / 'auto-mpg'
HOTEL = REPO / 'use-cases' / 'hotel-booking'
CONCLUSION = ('The development evidence is all the study can cite: the final test was opened '
              'once.')
# The words of a test junior (a test choice, as in the round-5 walker).
WORDS = {'model_choice': 'Yes, I choose that model because its error is smaller',
         'policy': 'Yes, I adopt that rule because the desk can act on that share',
         'final_test': 'Yes, I open the final test now, because the model and the rule are fixed'}
BINARY_MODEL_WORDS = 'Yes, I choose that model because it ranks the rows best for us'
PREDICTION_TIME = 'when the record is created, before the outcome'
HOLD = 'Wait until I check the fold count with my manager'
RESOLVE = 'My manager agrees with the fold count'


def _words(decision: str, task: str) -> str:
    if decision == 'model_choice' and task == 'binary':
        return BINARY_MODEL_WORDS
    return WORDS.get(decision) or fk.default_words(decision)


def _junior_value(decision: str, task: str):
    if decision == 'prediction_time':
        return PREDICTION_TIME
    return 'fit.linear' if task == 'regression' else 'fit.logistic'


def walk(f: fk.Flow, task: str, on_write: Callable[[str, dict], None] | None = None,
         on_read: Callable[[str, dict], None] | None = None, limit: int = 80,
         restatement_fr: bool = False) -> list:
    """Follow ``next_action`` from step 0 to ``done``; every write's payload goes to
    ``on_write(label, payload)`` and is returned as ``(label, payload)``. At the split, a hold
    is recorded and resolved before the confirmation, so a hold and its resolution are walked
    too. ``on_read(label, action)`` gets the ``status --summary`` next action between writes.
    ``restatement_fr`` (L3, J-LANG): each proposal also carries a French restatement."""
    writes = []
    held = False

    def wrote(label, payload):
        assert payload.get('ok'), (label, payload)
        writes.append((label, payload))
        if on_write:
            on_write(label, payload)
        return payload

    def call(*args):
        return f.call(*args, '--request-id', f.rid(), '--expected-revision', f.rev(),
                      '--study', f.study, expect=None)

    for _ in range(limit):
        summary = f.call('status', '--summary', '--study', f.study)
        nxt = summary['next_action']
        if on_read:
            on_read(f'status:{nxt["kind"]}', nxt)
        kind = nxt['kind']
        if kind in ('done', 'blocked'):
            return writes
        if kind == 'show_data_card':
            f.call('data', '--study', f.study)            # the data card: a read, no next action
            nxt, kind = {'kind': 'propose', 'decision': 'prediction_time'}, 'propose'
        if kind == 'run':
            args = [nxt['activity']]
            for rule in nxt.get('rules') or []:
                args += ['--rule', rule]
            for option, value in (nxt.get('options') or {}).items():
                args += [f'--{option}', str(value)]
            out = wrote(f'run:{nxt["activity"]}', call('run', *args))
            assert out['status'] in ce.SHOWN_RUN_STATUSES, out
            continue
        if kind == 'await_user_words':
            decision = nxt['decision']
            wrote(f'confirm:{decision}', call('decide', 'confirm', nxt['proposal_id'],
                                              '--user-words', _words(decision, task)))
            continue
        assert kind in ('propose', 'reconfirm'), nxt
        decision = nxt['decision']
        if decision == 'conclusion':
            # L1 (R2c): a conclusion option's value is ``{"verdict": ...}``; the text is the
            # junior's, written when it is proposed.
            options = nxt.get('choice_options') or []
            verdict = (options[0]['value']['verdict'] if options
                       else (nxt.get('verdicts') or ['inconclusive'])[0])
            value = {'verdict': verdict, 'text': CONCLUSION}
        else:
            value = nxt.get('default_value')
            if value is None:
                value = (nxt.get('recommended') or {}).get('value')
            if value is None and nxt.get('choice_options'):
                value = nxt['choice_options'][0]['value']
            if value is None:
                value = _junior_value(decision, task)
        # L3 (J-LANG): in a French study the agent also gives the restatement in French.
        french = ('--restatement-fr', f'Vous décidez : {decision}, comme indiqué.') \
            if restatement_fr else ()
        proposal = wrote(f'propose:{decision}', call(
            'decide', 'propose', decision, '--value-json', json.dumps(value), '--restatement',
            f'You decide the {decision} as stated.', *french,
            '--rationale', 'It fits the scenario.'))
        if decision == 'split' and not held:
            held = True
            note = wrote('note:hold', call('decide', 'note', '--about', 'split', '--text', HOLD))
            wrote('note:resolve', call('decide', 'note', '--resolve', note['result']['note_id'],
                                       '--text', RESOLVE))
        wrote(f'confirm:{decision}', call('decide', 'confirm', proposal['result']['proposal_id'],
                                          '--user-words', _words(decision, task)))
    raise AssertionError(f'next_action did not settle: {[w for w, _ in writes[-8:]]}')


def journey_flow(base: Path, case: str, lang: str) -> tuple[fk.Flow, str, dict]:
    """A new study on ``case`` (``synthetic`` binary, ``auto-mpg``, or ``hotel-booking``, the
    heavy opt-in one) in ``lang``; its init."""
    if case == 'synthetic':
        case_dir = fk.make_case(base / 'case', n_rows=300, task='binary')['case'].parent
        task = 'binary'
    elif case == 'hotel-booking':
        case_dir, task = HOTEL, 'binary'
    else:
        case_dir, task = AUTO_MPG, 'regression'
    f = fk.Flow(base / f'study-{case}-{lang}', case_dir, prefix='j')
    init = f.call('init', '--case', case_dir, '--study', f.study, '--lang', lang)
    return f, task, init


def _plan(f: fk.Flow) -> list[dict]:
    return f.call('plan', '--study', f.study)['steps']


@pytest.mark.parametrize('case', ['synthetic', 'auto-mpg'])
@pytest.mark.parametrize('lang', ['en', 'fr'])
def test_j_panel_every_write_names_its_place_and_every_read_none(tmp_path, monkeypatch, case,
                                                                 lang):
    """J-PANEL (engine), contract P1 (CLI-CONTRACT §17.1; rewritten from the tab form, whose
    sections no longer exist): along the walkthrough at stage v3, the next step is always in
    Now (``where``); after every write ``shown`` names the place of the one page that shows
    what it produced, in the study language: a proposal or a held condition in Now, a
    confirmation its step in the path, the opening the final test result, a chart in Now when
    its step is the current one and in its step's detail otherwise; after every read past
    step 0, nothing (or the choice the chat asks)."""
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    f, task, init = journey_flow(tmp_path, case, lang)
    assert init['next_action']['panel']['shown']['anchor'] == 'now'          # the data card
    prefix = ce.LINE_MARK[lang]
    seen, choices, captures = [], [], []

    def place_ok(found):
        # R35 (owner decision 2026-10-28; rewritten from "every place has its line"): within
        # the session the walkthrough runs in, a place at Now has no line, except the
        # end-of-study block; every other place has its line, the marker then its label.
        assert list(found) == list(ce.SHOWN_KEYS) and ce.ANCHOR_RE.fullmatch(found['anchor'])
        if found['anchor'] == 'now' and not found['label'].endswith(
                ce.CONTENT_LABELS[lang]['done']):
            assert found['line'] is None, found
        else:
            assert found['line'] == prefix + found['label'], found

    def on_write(label, payload):
        plan = _plan(f)                                 # the plan as the write left it
        action = payload['next_action']
        panel = action['panel']
        assert panel['version'] == 2 and list(action)[-1] == 'panel'
        assert panel['where']['anchor'] == 'now', (label, panel['where'])
        shown = panel['shown']
        head, _, rest = label.partition(':')
        if label == 'run:predictor.capture':
            assert shown is None, shown                     # a capture draws nothing
            captures.append(label)
            return
        place_ok(shown)
        anchor = shown['anchor']
        if head in ('propose', 'note'):
            assert anchor == 'now', (label, shown)
        elif label == 'confirm:final_test':
            assert anchor == 'path:final_test/final_test.evaluation', shown
        elif head == 'confirm':
            assert anchor == f'path:{ce.decision_step(rest, plan)}', (label, shown)
        else:
            from mlkit.study import executions
            slot = payload['result']['slot']
            step = ce.step_of(payload['activity'], slot, plan,
                              executions._target_read(payload))
            if anchor == 'now':
                assert step == ce.current_step(action, plan), (label, shown)
            else:
                assert anchor == f'path:{step}/{slot}', (label, shown)
        seen.append(anchor)

    def on_read(label, action):
        shown = action['panel']['shown']
        if action['kind'] == 'show_data_card':
            assert shown['anchor'] == 'now'
        elif action.get('choice_options'):
            assert shown['anchor'] == 'now' and shown['label'].endswith(
                ce.CONTENT_LABELS[lang]['choice'])
            choices.append(action['decision'])
        else:
            assert shown is None, (label, shown)

    writes = walk(f, task, on_write=on_write, on_read=on_read)
    assert len(writes) > 15
    # W1 integration (L1 + L2, D3): the opening's confirmation is followed by the conclusion, a
    # choice the chat asks; the write names the final test result it produced.
    opening = [p for label, p in writes if label == 'confirm:final_test']
    assert len(opening) == 1
    action = opening[0]['next_action']
    assert action['decision'] == 'conclusion' and action['choice_options'], action
    assert action['recommended'] is None and action['pause']['kind'] == 'choice'
    for anchor in ('now', 'path:split', 'path:prediction_time',
                   'path:final_test/final_test.evaluation'):
        assert anchor in seen, (anchor, seen)
    assert any(a.startswith('path:') and '/' in a and 'final_test' not in a for a in seen), seen
    assert {'model_choice', 'conclusion'} <= set(choices), choices
    assert len(captures) == 1, captures
