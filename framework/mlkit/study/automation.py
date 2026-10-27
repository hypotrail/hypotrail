"""The automatic mode, reviewed at the end (owner session 2026-10-26, lot L9, remark R20).

The owner asked for a mode where the assistant makes every choice and the junior reviews
them at the end, with two variants chosen at launch (``init --automation``):

* ``until_final_test`` (the default variant): every decision and computation up to the
  model and the rule is recorded with the engine's value, as ``automatic``; the junior then
  adopts or changes each one in their own words and opens the final test themselves.
* ``full_demo``: the same, and the automatic mode also opens the final test and concludes.
  A demonstration: the report says "Automatic study: not defensible until reviewed" until
  every decision is reviewed, and "The final test was opened automatically" for good.

This module holds what the engine decides on the automatic mode's behalf, and the runner
(``hypotrail automation run``, :func:`run`):

* :func:`auto_value` is the value the mode records for the decision a ``next_action``
  names (``next_action.auto_value``), from fixed rules and never from a free choice of the
  agent: the engine's drafted value (``default_value``), else its recommended value
  (``recommended.value``), else, where it recommends nothing, a documented rule
  (:data:`RULES`): the model choice by the selection advice (the one-standard-error pick,
  else the best configuration on the declared metric, else the candidate), the decision
  rule by the case's scenario share or the engine's recommended share, the conclusion from
  the success criterion as judged on the final test (``met`` adopts, ``not_met`` keeps the
  baseline, ``uncertain`` or ``not_assessed`` is inconclusive) with a text drafted in the
  study language. A value the engine would refuse is never offered: the rules only pick
  among the values the confirmation accepts (``choice_options``) when the engine lists them.
* :func:`run` follows ``next_action`` exactly as the engine gives it, through the same
  commands as the agent (``decide propose``, ``decide confirm --basis automatic``,
  ``run``): every refusal is honoured (the run stops and reports it, nothing is bypassed),
  every precondition holds as for the junior, the exposure, the trial budget and the sealing
  are unchanged. It stops where the mode stops covering the plan (the final test in
  ``until_final_test``; ``done`` in ``full_demo``), at anything only the junior can answer
  (a hold, an interrupted run, a value the engine cannot draft), or at the first refusal,
  and it then ends the mode when it reached what it covers (one way).

Nothing here is fingerprinted (``activities.MODULES``); the activities run as they always do.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, TextIO

from . import audience
from . import state as st

SCHEMA = 'hypotrail.automation/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'automation', 'status', 'stopped_at',
                'reason', 'refusal', 'steps', 'review_queue', 'next_action', 'artifacts')
STEP_KEYS = ('revision', 'kind', 'decision', 'activity', 'outcome')
# Why the runner stopped (``reason``).
STOP_REASONS = ('reached_end', 'needs_junior', 'no_automatic_value', 'refused',
                'not_promoted', 'automation_not_set', 'limit')
# The rules :func:`auto_value` applies when the engine drafts and recommends nothing.
RULES = {
    'model_choice': 'the one-standard-error pick of the model selection, else the best '
                    'configuration on the declared metric, else the candidate model',
    'policy': "the case's scenario share when it declares one, else the engine's "
              'recommended share',
    'conclusion': 'from the success criterion judged on the final test: met adopts, not_met '
                  'keeps the baseline, uncertain or not_assessed is inconclusive',
}
MAX_STEPS = 200
FR = audience.FR


def _t(lang: str, en: str, fr: str) -> str:
    return fr if lang == FR else en


# --- the automatic value --------------------------------------------------------------------

def _accepted(action: Mapping) -> list | None:
    """The values the confirmation accepts now when the engine lists them."""
    options = action.get('choice_options')
    return [o['value'] for o in options] if options else None


def _first_accepted(candidates: list, accepted: list | None):
    for value in candidates:
        if value is not None and (accepted is None or value in accepted):
            return value
    return accepted[0] if accepted else None


def _model_choice(view: Mapping, action: Mapping):
    selection = view.get('model_selection') or {}
    candidate = 'fit.linear' if view.get('task') == st.REGRESSION else 'fit.logistic'
    one_se = selection.get('one_se') if isinstance(selection.get('one_se'), Mapping) else {}
    return _first_accepted([one_se.get('pick'), selection.get('best'), candidate],
                           _accepted(action))


def _policy(view: Mapping, state: Mapping):
    from . import view as view_mod
    share = (((view.get('scenario_defaults') or {}).get('capacity_share') or {})
             .get('value'))
    rule = f'share:{share}' if share is not None else view_mod.RECOMMENDED_RULE
    from . import records as rec
    return view_mod._with_chosen_model(state, rec.canonical_rule(rule) or rule)


def verdict_of(view: Mapping) -> str:
    """The verdict the success criterion supports, judged on the final test once opened."""
    criterion = view.get('criterion') or {}
    status = criterion.get('judged_status') or criterion.get('status')
    adopt = 'adopt_model' if view.get('task') == st.REGRESSION else 'adopt_policy'
    return {'met': adopt, 'not_met': 'keep_baseline'}.get(status, 'inconclusive')


CONCLUSION_TEXTS = {
    'en': {'adopt': 'Automatic conclusion: the success criterion is met on the final test, so '
                    'the chosen configuration is adopted. Recorded by the demonstration mode, '
                    'not by the analyst: not defensible until reviewed.',
           'keep_baseline': 'Automatic conclusion: the success criterion is not met on the '
                            'final test, so the baseline is kept. Recorded by the '
                            'demonstration mode, not by the analyst: not defensible until '
                            'reviewed.',
           'inconclusive': 'Automatic conclusion: the success criterion cannot be settled on '
                           'the final test, so the study does not conclude. Recorded by the '
                           'demonstration mode, not by the analyst: not defensible until '
                           'reviewed.'},
    'fr': {'adopt': "Conclusion automatique : le critère de succès est atteint sur le test "
                    "final, la configuration choisie est donc adoptée. Enregistrée par le mode "
                    "démonstration, et non par l'analyste : pas défendable avant relecture.",
           'keep_baseline': "Conclusion automatique : le critère de succès n'est pas atteint "
                            'sur le test final, le modèle de référence est donc gardé. '
                            "Enregistrée par le mode démonstration, et non par l'analyste : "
                            'pas défendable avant relecture.',
           'inconclusive': "Conclusion automatique : le critère de succès ne peut pas être "
                           "tranché sur le test final, l'étude ne conclut donc pas. Enregistrée "
                           "par le mode démonstration, et non par l'analyste : pas défendable "
                           'avant relecture.'},
}


def _conclusion(view: Mapping, action: Mapping) -> dict | None:
    verdict = verdict_of(view)
    accepted = [v.get('verdict') for v in (_accepted(action) or []) if isinstance(v, Mapping)]
    if accepted and verdict not in accepted:
        verdict = 'inconclusive' if 'inconclusive' in accepted else accepted[0]
    lang = view.get('language') or 'en'
    key = 'adopt' if verdict.startswith('adopt') else verdict
    return {'verdict': verdict, 'text': CONCLUSION_TEXTS[lang if lang == FR else 'en'][key]}


def auto_value(view: Mapping, state: Mapping, action: Mapping) -> Any:
    """The value the automatic mode records for the decision ``action`` proposes, or None
    when the engine has none (the junior is then asked). See :data:`RULES`."""
    decision = action.get('decision')
    if action.get('kind') not in ('propose', 'reconfirm') or decision is None:
        return None
    if decision == 'conclusion':
        return _conclusion(view, action)
    value = action.get('default_value')
    if value is None:
        value = (action.get('recommended') or {}).get('value')
    if value is not None:
        return copy.deepcopy(value)
    if decision == 'model_choice':
        return _model_choice(view, action)
    if decision == 'policy':
        return _policy(view, state)
    return None


def annotate(view: dict, state: Mapping) -> None:
    """``next_action.auto_value`` (L9) while the automatic mode runs and covers the action:
    the value it records (``null`` when the engine has none). Absent otherwise, so a study
    without automation is unchanged."""
    action = view.get('next_action')
    if not isinstance(action, dict) or action.get('kind') not in ('propose', 'reconfirm') \
            or not st.action_covered(state, action):
        return
    action['auto_value'] = auto_value(view, state, action)


# --- texts ----------------------------------------------------------------------------------

def restatement(view: Mapping, decision: str) -> str:
    """The restatement of an automatic proposal, in the study language, without a number
    (the value says what it is; the junior reviews it at the end)."""
    lang = view.get('language') or 'en'
    words = audience.decision_words(decision, lang)
    return _t(lang, f'Automatic decision on {words}: the engine\'s value, recorded by the '
                    'automatic mode chosen at launch, to review in your own words at the end.',
              f'Décision automatique sur {words} : la valeur du moteur, enregistrée par le mode '
              'automatique choisi au lancement, à relire avec vos propres mots à la fin.')


def rationale(view: Mapping, decision: str) -> str:
    lang = view.get('language') or 'en'
    return _t(lang, 'Recorded by the automatic mode with the value the engine drafts or '
                    'recommends, or by its fixed rule where it recommends nothing; never the '
                    "junior's words.",
              "Enregistrée par le mode automatique avec la valeur que le moteur rédige ou "
              "recommande, ou par sa règle fixe là où il ne recommande rien ; jamais les mots "
              "de l'analyste.")


# --- the runner -----------------------------------------------------------------------------

def _step(revision: int, action: Mapping, outcome: str) -> dict:
    return {'revision': revision, 'kind': action.get('kind'),
            'decision': action.get('decision'), 'activity': action.get('activity'),
            'outcome': outcome}


def _view(study_dir: Path) -> dict:
    from . import lock, read, view as view_mod
    return view_mod.build(read.open(study_dir), leases=lock.probe_leases(study_dir))


def _stale(current: int, expected: int):
    from mlkit.reliability import CommandRefused
    return CommandRefused('stale_revision',
                          f'The study is at revision {current}, not {expected}: read status '
                          'again before running the automatic mode.',
                          details={'current_revision': current, 'expected_revision': expected})


def run(study_dir, *, request_id: str, expected_revision: int,
        progress: TextIO | None = None, progress_interval: float | None = None) -> dict:
    """Follow ``next_action`` with the automatic mode until it stops (module docstring);
    the ``hypotrail.automation/1`` payload. Every write goes through the engine's own
    commands with a request id derived from ``request_id`` and the revision it expects
    (``<request_id>-r<revision>``), so a rerun after an interruption continues where the
    study stands and never replays a different request."""
    from mlkit.reliability import CommandRefused

    from . import automation_words, commands as cmd, executions, guard, read
    from .errors import StudyError

    guard.assert_writable()
    study_dir = Path(study_dir).resolve()
    state = read.open(study_dir).state
    if state['revision'] != expected_revision:
        raise _stale(state['revision'], expected_revision)
    # Contract P1.9: a study created before the step-1 sample records its look on its first
    # write, before the runner's own work (once per seed).
    from . import exposure
    exposure.ensure_sample_locked(study_dir)
    steps: list[dict] = []
    status, reason, refusal, stopped_at = 'stopped', None, None, None
    # R23 (owner session 2026-10-27): what is going on, in the study language, on stderr.
    narrator = automation_words.Narrator(progress)
    if st.automation_of(state) is None or st.automation_in_force(state) is None:
        reason = 'automation_not_set'
        view = _view(study_dir)
        stopped_at = view['next_action']
        payload = _payload(study_dir, view, status, reason, None, stopped_at, steps, None)
        narrator.closing(view, payload)
        return payload
    for index in range(1, MAX_STEPS + 1):
        view = _view(study_dir)
        state = read.open(study_dir).state
        if index == 1:
            narrator.header(view, state)
        narrator.result(view)
        action = view['next_action']
        kind = action.get('kind')
        revision = view['revision']
        rid = f'{request_id}-r{revision}'
        if kind == 'show_data_card':
            # Informational: the data card is shown in the report; the next step is the
            # prediction moment, as the card's message says.
            recommended = junior_recommended(view, state)
            action = {**action, 'kind': 'propose', 'decision': 'prediction_time',
                      'recommended': recommended}
            action['auto_value'] = auto_value(view, state, {
                'kind': 'propose', 'decision': 'prediction_time',
                'recommended': recommended})
            kind = 'propose'
        if not st.action_covered(state, action):
            stopped_at = action
            reason = 'reached_end' if kind == 'done' or action.get('review') or (
                kind in ('propose', 'reconfirm', 'await_user_words')
                and not st.automation_covers(state, action.get('decision'))) \
                else 'needs_junior'
            break
        try:
            if kind == 'run':
                options = {**(action.get('options') or {})}
                if action.get('rules'):
                    options['rules'] = list(action['rules'])
                narrator.computing(view, action['activity'])
                kwargs = {}
                if progress_interval is not None:
                    kwargs['progress_interval'] = progress_interval
                # Contract P1.8 (CLI-CONTRACT §17.2.5): a computation of the automatic
                # runner is recorded as coming from the command line, as its decisions are.
                out = executions.run(study_dir, action['activity'], options, request_id=rid,
                                     expected_revision=revision, render=False,
                                     progress=narrator.activities, channel='cli',
                                     **kwargs).payload
                outcome = out.get('status')
                steps.append(_step(revision, action, outcome))
                if outcome not in ('promoted', 'already_current'):
                    status, reason, stopped_at = 'stopped', 'not_promoted', action
                    refusal = {'code': 'not_promoted', 'status': outcome,
                               'error': out.get('error')}
                    narrator.due = None
                    break
            elif kind in ('propose', 'reconfirm'):
                value = action.get('auto_value')
                if value is None:
                    reason, stopped_at = 'no_automatic_value', action
                    break
                decision = action['decision']
                lang = view.get('language') or 'en'
                text = restatement(view, decision)
                params = {'decision_id': decision, 'value': value, 'restatement': text,
                          'rationale': rationale(view, decision), 'channel': 'cli',
                          'labels': {lang: text}}
                cmd.apply(study_dir, action=cmd.ACTION_PROPOSE, params=params,
                          request_id=rid, expected_revision=revision, quiet=True)
                steps.append(_step(revision, action, 'proposed'))
                narrator.proposed(view, state, action, value)
            elif kind == 'await_user_words':
                params = {'proposal_id': action['proposal_id'], 'user_words': None,
                          'channel': 'cli', 'actor': st.AUTOMATIC_ACTOR,
                          'basis': st.AUTOMATIC, 'delegation_scope': None}
                out = cmd.apply(study_dir, action=cmd.ACTION_CONFIRM, params=params,
                                request_id=rid, expected_revision=revision, quiet=True).payload
                opening = (out.get('result') or {}).get('opening')
                outcome = 'confirmed' if not opening else f'confirmed, opening {opening["status"]}'
                steps.append(_step(revision, action, outcome))
                narrator.recorded(view, action)
                if opening:
                    narrator.opened()
                if opening and opening.get('status') not in ('promoted', 'opened'):
                    reason, stopped_at = 'not_promoted', action
                    refusal = {'code': 'opening_not_promoted', 'status': opening.get('status'),
                               'error': opening.get('error')}
                    break
            else:                                     # never reached: covered kinds only
                reason, stopped_at = 'needs_junior', action
                break
        except (CommandRefused, StudyError) as exc:
            # Every refusal is honoured: the run stops and says why; nothing is bypassed.
            steps.append(_step(revision, action, 'refused'))
            reason, stopped_at = 'refused', action
            refusal = cmd.refusal_dict(exc)
            break
    else:
        reason, stopped_at = 'limit', view['next_action']
    state = read.open(study_dir).state
    if reason == 'reached_end' and cmd.automation_reached_end(state):
        cmd.apply(study_dir, action=cmd.ACTION_END_AUTOMATION,
                  params={'reason': 'reached_end', 'user_words': None},
                  request_id=f'{request_id}-end-r{state["revision"]}',
                  expected_revision=state['revision'], quiet=True)
        status = 'ended'
    view = _view(study_dir)
    narrator.result(view)
    artifacts = _render(study_dir, view) if steps or status == 'ended' else None
    if artifacts is not None:
        view = _view(study_dir)
    payload = _payload(study_dir, view, status, reason, refusal, stopped_at, steps, artifacts)
    narrator.closing(view, payload)
    return payload


def junior_recommended(view: Mapping, state: Mapping) -> dict | None:
    """The recommended prediction moment the view gives at its ``propose`` (the case's)."""
    from . import junior
    return junior._recommended({'kind': 'propose', 'decision': 'prediction_time'}, view,
                               state, view.get('language') or 'en')


def _render(study_dir: Path, view: Mapping) -> dict | None:
    """The deliverables, rendered once at the end of the run (the runner's writes skip it)."""
    from . import commands as cmd
    try:
        return cmd.after_commit(study_dir, {'revision': view['revision'], 'action': 'automation'})
    except Exception as exc:                       # noqa: BLE001 - the run's writes stand
        return {'report': {'status': 'failed', 'message': f'{type(exc).__name__}: {exc}'}}


def _payload(study_dir: Path, view: Mapping, status: str, reason: str | None,
             refusal: Mapping | None, stopped_at: Mapping | None, steps: list,
             artifacts: Mapping | None) -> dict:
    from . import commands as cmd
    next_action = cmd.refreshed_next_action(study_dir, {'command': 'automation'})
    return {'schema': SCHEMA, 'ok': True, 'study': str(study_dir),
            'revision': view['revision'], 'automation': view.get('automation'),
            'status': status, 'stopped_at': ({k: stopped_at.get(k) for k in (
                'kind', 'decision', 'activity', 'proposal_id', 'review')}
                if stopped_at else None),
            'reason': reason, 'refusal': refusal, 'steps': steps,
            'review_queue': view.get('review_queue') or [],
            'next_action': next_action, 'artifacts': artifacts}


__all__ = ['auto_value', 'annotate', 'run', 'RULES', 'SCHEMA', 'PAYLOAD_KEYS', 'STOP_REASONS',
           'verdict_of', 'restatement']
