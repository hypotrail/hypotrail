"""``next_action`` never names an action the engine would refuse as given (review round 6,
area E, R6E-1 and R6E-2).

The view builds ``next_action`` from the state's plan (:func:`mlkit.study.state.next_action`)
and completes it (:mod:`mlkit.study.view`: the rules of a policy evaluation, the rule of a
policy proposal, the options of a capture, the results the opening of the final test rests
on). :func:`checked` is the last step, one check for every kind that writes:

* ``await_user_words``: the refusals of ``decide confirm`` that do not depend on the words,
  by the function the confirmation itself calls
  (:func:`mlkit.study.commands.confirmation_refusals`: the final test already opened, a hold,
  a stale proposal, an invalid value, the preconditions with the store, the capture of the
  final test included: its currency, its configuration, and whether it loads);
* ``propose`` and ``reconfirm``: the refusals the confirmation of the value it carries would
  meet (:func:`mlkit.study.commands.decision_refusals`), except, for a decision the plan
  takes before its own results (``decide_first``), those results;
* ``run``: the refusals of the reservation (the opening rule
  :func:`mlkit.study.preconditions.opening_missing` for the final evaluation) and of the
  activity's plan (:func:`mlkit.study.activities.plan`, which calls
  :func:`mlkit.study.preconditions.require_activity`), and, for the final evaluation, the
  loading of the captured predictor.

When the action would be refused, it is replaced by the first remedy of the first refusal
(the one the engine would raise), which is checked in turn, upstream first: the hold the
junior's words resolve (``resolve_hold``), the proposal made again when it is stale, the
decision to settle first, the configuration the final test opens, or the ``run`` of the
result that is missing, stale, not current, computed on rows it must leave out, or captured
for another configuration (``predictor.capture`` with the options of the capture it
replaces). Each remedy says, in the study language, what it comes before and why
(``junior_message``). An action with no remedy is left as it is.

The check reads the registry and the study's files; it never writes. It is not run in a
read-only process (``HYPOTRAIL_READ_ONLY=1``, a notebook kernel: the capture checks import the
runtime), nor while the study's sources changed (every write is refused then) or an
execution is interrupted (that comes first).
"""
from __future__ import annotations

import copy
import json
import os
from typing import Callable, Mapping

from . import audience
from . import records as rec
from . import state as st
from .errors import StudyError

READ_ONLY_ENV = 'HYPOTRAIL_READ_ONLY'
# Remedies chained at most (a result upstream of a result upstream of ...).
MAX_REMEDIES = 10
DECISION_KINDS = ('propose', 'reconfirm', 'await_user_words')
CAPTURE = 'predictor.capture'
POLICY_EVALUATION = 'policy.evaluation'
FINAL_EVALUATION = 'final_test.evaluation'
# Requirements of a refusal that a ``run`` of their ``slot`` (or ``slots``) meets.
RUN_REQUIREMENTS = ('result_current', 'development_diagnostics_current',
                    'final_evidence_current_for_configuration',
                    'computed_without_delayed_labels', 'capture_loadable', 'nothing_stale')
NOT_READ = {'en': 'No final-test row was read: the final test is still sealed.',
            'fr': "Aucune ligne de l'échantillon de test final n'a été lue : il reste scellé."}


def applies(study, state: Mapping, action: Mapping | None) -> bool:
    """Whether :func:`checked` checks ``action`` (see the module docstring)."""
    return bool(action) and action.get('kind') in DECISION_KINDS + ('run',) \
        and os.environ.get(READ_ONLY_ENV) != '1' \
        and not state['executions']['interrupted'] and not study.source_changes()


def checked(study, state: Mapping, action: dict | None,
            finish: Callable[[dict], dict] = lambda a: a) -> dict | None:
    """``action`` when the engine would accept it as given; otherwise its first remedy that
    the engine would accept (completed by ``finish``, the view's own completion of an
    action). ``action`` unchanged when nothing applies or no remedy exists."""
    if not applies(study, state, action):
        return action
    from .store import StudyStore
    store = StudyStore(study.study_dir)
    seen: list[str] = []
    current = action
    try:
        for _ in range(MAX_REMEDIES):
            found = refusals(state, store, current)
            if not found:
                return current
            nxt = remedy(study, state, current, found[0], action)
            if nxt is None:
                break
            nxt = finish(nxt)
            key = _key(nxt)
            if key in seen or key == _key(current):
                break
            seen.append(key)
            current = nxt
    except Exception:          # noqa: BLE001 - the view never fails on its own check;
        return action          # the command executed reports what it refuses
    return action


def _key(action: Mapping) -> str:
    return json.dumps({k: action.get(k) for k in ('kind', 'activity', 'decision',
                                                  'proposal_id', 'rules', 'options',
                                                  'default_value')},
                      sort_keys=True, default=str)


# --- the refusals --------------------------------------------------------------------------

def refusals(state: Mapping, store, action: Mapping) -> list[dict]:
    """The refusals (``{code, reason, message, details}``, in the order the engine raises
    them) of ``action`` executed as given; empty when it would be accepted."""
    from . import commands as cmd
    kind = action.get('kind')
    if kind == 'await_user_words':
        proposal = state['proposals'].get(action.get('proposal_id')) or {}
        if proposal.get('status') != 'open':
            return []
        found, _ = cmd.confirmation_refusals(state, store, proposal['proposal_id'],
                                             sources=False)
        return [cmd.refusal_dict(e) for e in found]
    if kind in ('propose', 'reconfirm'):
        decision = action.get('decision')
        if decision not in state['decisions']:
            return []
        value = action.get('default_value')
        found, _ = cmd.decision_refusals(state, store, decision, value,
                                         validate=value is not None)
        return _own_results_left_out(state, action, [cmd.refusal_dict(e) for e in found])
    if kind == 'run':
        return run_refusals(state, store, action)
    return []


def run_options(action: Mapping) -> dict:
    """The options of a ``run`` action as ``hypotrail run`` passes them."""
    options = dict(action.get('options') or {})
    if action.get('rules'):
        options['rules'] = list(action['rules'])
    return options


def run_refusals(state: Mapping, store, action: Mapping) -> list[dict]:
    """The refusals of ``hypotrail run`` on ``action`` before anything is computed: the
    reservation's rule for the final evaluation, then the activity's plan, then the loading of
    the captured predictor the final evaluation would read."""
    from mlkit.reliability import CommandRefused

    from . import activities as act
    from . import assurance, commands as cmd, preconditions
    try:
        activity, options = act.resolve(action.get('activity'), run_options(action))
        activity = act.canonical(activity)
        options = act.normalize_options(activity, options)
        if activity == act.FINAL:
            if st.final_test_opened(state):
                raise cmd.final_test_opened_refusal(state)
            assurance.require_activity(state, activity)
            preconditions.refuse_missing(preconditions.opening_missing(state, store),
                                         'Opening the final test')
        plan = act.plan(store, state, activity, options)
        if activity == act.FINAL and plan['inputs'].get('predictor'):
            from mlkit.contracts import capture
            capture.require_loadable(store, state, plan['inputs']['predictor'])
    except (CommandRefused, StudyError) as exc:
        return [cmd.refusal_dict(exc)]
    return []


def _own_results_left_out(state: Mapping, action: Mapping, found: list[dict]) -> list[dict]:
    """A decision the plan takes before its own results (``decide_first``) is proposed
    before them: the results of its own step are not a reason to delay the proposal (its
    confirmation is checked when the words are awaited)."""
    step = next((s for s in st.steps(state) if s['id'] == action.get('step')), None)
    if action.get('kind') != 'propose' or step is None or not step.get('decide_first', True):
        return found
    own = set(step['activities'])
    out = []
    for refusal in found:
        missing = (refusal.get('details') or {}).get('missing')
        if refusal['code'] != 'precondition_missing' or not isinstance(missing, list):
            out.append(refusal)
            continue
        kept = [m for m in missing if not (m.get('slot') in own
                                           or (m.get('slots') and set(m['slots']) <= own))]
        if kept:
            out.append({**refusal, 'details': {**refusal['details'], 'missing': kept}})
    return out


# --- the remedies --------------------------------------------------------------------------

def remedy(study, state: Mapping, action: Mapping, refusal: Mapping,
           goal: Mapping) -> dict | None:
    """The action that removes ``refusal`` of ``action`` (``goal`` is the action first
    named, which the remedy comes before), or None when there is none."""
    code, details = refusal.get('code'), refusal.get('details') or {}
    decision = action.get('decision')
    if code == 'decision_on_hold':
        held = st.hold_action(state, details.get('decision_id') or decision)
        return audience.next_action(held, st.language_of(state)) if held else None
    if code == 'ambiguous_confirmation' and refusal.get('reason') == 'proposal_stale':
        return _propose_again(state, action)
    if code == 'invalid_value':
        diag = st.DIAG_SLOT[st.task_of(state)]
        if details.get('reason') == 'diagnostic_not_current' and not st.is_current(state, diag):
            # The diagnostic the variant must cite is computed again first.
            return _run(study, state, diag, goal, {'requirement': 'development_diagnostics_current',
                                                   'slot': diag})
        return _propose_valid(state, action, details)
    if code == 'model_not_captured':
        return _run(study, state, CAPTURE, goal, {'requirement': 'result_current',
                                                  'slot': CAPTURE,
                                                  'junior_message': details.get(
                                                      'junior_message')})
    if code != 'precondition_missing':
        return None
    return _first_requirement(study, state, action, details.get('missing') or [], goal)


def _first_requirement(study, state: Mapping, action: Mapping, missing: list,
                       goal: Mapping) -> dict | None:
    """The remedy of the most upstream unmet requirement: a decision first (in the study's
    order), then the configuration the final test opens, then a result (in the plan's order,
    the capture last)."""
    order = list(st.decision_ids(state))
    decisions, runs, choice = [], [], None
    for item in missing:
        need = item.get('requirement')
        if need == 'decision_confirmed':
            decisions.append(item.get('decision'))
        elif need == 'nothing_to_reconfirm':
            decisions += list(item.get('decisions') or [])
        elif need == 'chosen_configuration':
            choice = item
        elif need in RUN_REQUIREMENTS:
            for slot in ([item['slot']] if item.get('slot') else list(item.get('slots') or [])):
                runs.append((slot, item))
    own = action.get('decision') if action.get('kind') in DECISION_KINDS else None
    decisions = [d for d in dict.fromkeys(decisions) if d in order and d != own]
    for d in sorted(decisions, key=order.index):
        found = st.decision_action(dict(state), d)
        if found is not None:
            return _for_decision(state, found, d, goal)
    if choice is not None:
        return _final_test_on_choice(state, action, choice)
    slots = _slot_order(state)
    runs = [(s, i) for s, i in runs if s != FINAL_EVALUATION]
    runs.sort(key=lambda r: (r[0] == CAPTURE, slots.get(r[0].split(':', 1)[0], len(slots))))
    if runs:
        slot, item = runs[0]
        if slot == POLICY_EVALUATION and goal.get('kind') == 'await_user_words' \
                and goal.get('decision') == 'policy':
            from . import view
            found = view._unevaluated_policy_proposal(study, state, goal)
            if found is not None:
                return found
        return _run(study, state, slot, goal, item)
    return None


def _slot_order(state: Mapping) -> dict[str, int]:
    from . import opening
    order = list(opening.selection_slots(state)) + list(st.activity_slots(state))
    return {slot: i for i, slot in reversed(list(enumerate(order)))}


def _step_of(state: Mapping, slot: str, default=None):
    for step in st.derive_plan(dict(state)):
        if slot in step['activities']:
            return step['id']
    return default


def _goal_words(goal: Mapping, lang: str) -> str:
    """What a remedy comes before, in words: the opening of the final test, the junior's
    answer on a decision, or a run."""
    fr = lang == audience.FR
    decision, activity = goal.get('decision'), goal.get('activity')
    if decision == st.FINAL_TEST or activity == FINAL_EVALUATION:
        return ('avant que le test final puisse être ouvert' if fr
                else 'before the final test can be opened')
    if decision and goal.get('kind') in DECISION_KINDS:
        return (f"avant qu'on vous demande votre réponse sur "
                f'{audience.decision_words(decision, lang)}' if fr else
                f'before you are asked about {audience.decision_words(decision)}')
    if activity:
        return (f'avant que {audience.activity_words(activity, lang)} puisse être lancé' if fr
                else f'before {audience.activity_words(activity)} can run')
    return "avant l'étape suivante" if fr else 'before the next step'


def _why(state: Mapping, slot: str, item: Mapping, lang: str) -> str:
    """Why the result in ``slot`` is run, in words."""
    fr = lang == audience.FR
    rid = state['current'].get(slot)
    if slot == CAPTURE and item.get('captured') is not None:
        from . import opening
        chosen = st.choice_config(state)
        return (f'le modèle capturé est une autre configuration '
                f'({opening.configuration_words(item["captured"], lang)}) que celle que vous '
                f'avez choisie ({opening.configuration_words(chosen, lang)})' if fr else
                f'the captured model is another configuration '
                f'({opening.configuration_words(item["captured"], lang)}) than the one you '
                f'chose ({opening.configuration_words(chosen, lang)})')
    if slot == POLICY_EVALUATION and (item.get('rule') or item.get('model')):
        if item.get('rule'):
            words = audience.rule_words(rec.policy_rule(item['rule']) or item['rule'], lang)
            return (f"l'évaluation à jour n'a pas mesuré la règle « {words} »" if fr else
                    f'the current evaluation did not measure the rule "{words}"')
        words = audience.model_words(item['model'], lang)
        return (f"l'évaluation à jour n'a pas comparé {words}" if fr else
                f'the current evaluation did not compare {words}')
    if item.get('requirement') == 'computed_without_delayed_labels':
        return ("le résultat a été calculé avec des lignes dont l'issue n'est connue que plus "
                'tard' if fr else
                'the result was computed with rows whose outcome is known only later')
    if rid is None:
        return "aucun résultat n'existe encore" if fr else 'there is no result yet'
    if item.get('requirement') == 'capture_loadable':
        return ('le modèle capturé ne peut pas être chargé comme le test final le chargerait'
                if fr else 'the captured model cannot be loaded as the final test would load it')
    if rid in state['stale']:
        return ("le résultat n'est plus à jour : un élément dont il dépend a changé" if fr
                else 'the result is out of date: something it rests on changed')
    if item.get('code_changed'):
        return ('le code du moteur qui a calculé le résultat a changé depuis' if fr
                else "the engine's code that computed the result changed since")
    return ("le résultat n'est plus à jour" if fr else 'the result is no longer current')


def _run(study, state: Mapping, slot: str, goal: Mapping, item: Mapping) -> dict:
    """The ``run`` of ``slot`` before ``goal``, with its junior message."""
    from . import view
    lang = st.language_of(state)
    fr = lang == audience.FR
    words = audience.activity_words(slot, lang)
    if slot == CAPTURE and item.get('junior_message') and item.get('captured') is None:
        # The capture's own message (not current, not loadable): what to do, and that the
        # final test is still sealed.
        junior = item['junior_message']
    else:
        goal_words = _goal_words(goal, lang)
        if slot == CAPTURE:
            does = ("le moteur capture d'abord à nouveau le modèle choisi" if fr
                    else 'the engine first captures the chosen model again')
        else:
            does = (f"le moteur lance d'abord {words}" if fr
                    else f'the engine first runs {words}')
        junior = (f'{goal_words[:1].upper() + goal_words[1:]}, {does} : '
                  f'{_why(state, slot, item, lang)}. Cela ne vous demande rien.' if fr else
                  f'{goal_words[:1].upper() + goal_words[1:]}, {does}: '
                  f'{_why(state, slot, item, lang)}. It asks nothing of you.')
        if goal.get('decision') == st.FINAL_TEST or goal.get('activity') == FINAL_EVALUATION:
            junior += ' ' + NOT_READ['fr' if fr else 'en']
    out = {'kind': 'run', 'step': _step_of(state, slot, goal.get('step')), 'activity': slot,
           'message': (f'Run {slot} first: {_describe(goal)} would be refused as given '
                       f'({item.get("requirement")}: {item.get("detail") or slot}). Then '
                       'read next_action again.'),
           'audience': audience.AGENT, 'junior_message': junior}
    if goal.get('kind') == 'await_user_words':
        out['proposal_id'] = goal.get('proposal_id')
    elif goal.get('kind') == 'reconfirm':
        out['reconfirm'] = goal.get('decision')
    if slot == CAPTURE:
        out = view._with_capture_options(study, state, out)
    if slot == POLICY_EVALUATION:
        # The rule (or the model) the current evaluation did not cover first, then the rules
        # the study knows (the evaluation it runs again covers them too).
        first = [rec.canonical_rule(item['rule']) or rec.policy_rule(item['rule'])] \
            if isinstance(item.get('rule'), str) else []
        if goal.get('kind') in ('propose', 'reconfirm') and goal.get('decision') == 'policy':
            first.append(rec.policy_rule(goal.get('default_value')))
        out['rules'] = [r for r in dict.fromkeys(first + view._known_rules(study, state, goal))
                        if r]
    return out


def _describe(action: Mapping) -> str:
    kind = action.get('kind')
    if kind == 'run':
        return f'run {action.get("activity")}'
    if kind == 'await_user_words':
        return f'confirming proposal {action.get("proposal_id")} ({action.get("decision")})'
    return f'{kind} {action.get("decision")}'


def _for_decision(state: Mapping, action: dict, decision: str, goal: Mapping) -> dict:
    """The action of a decision to settle before ``goal``, with its junior message."""
    lang = st.language_of(state)
    fr = lang == audience.FR
    out = audience.next_action(action, lang)
    words = audience.decision_words(decision, lang)
    goal_words = _goal_words(goal, lang)
    lead = (f"{goal_words[:1].upper() + goal_words[1:]}, {words} passe d'abord." if fr else
            f'{goal_words[:1].upper() + goal_words[1:]}, {words} comes first.')
    out['message'] = (f'Settle {decision} first: {_describe(goal)} would be refused as given '
                      f'(decision {decision} is not confirmed). {out["message"]}')
    out['audience'] = audience.AGENT
    out['junior_message'] = f'{lead} {out["junior_message"]}'
    return out


def _final_test_on_choice(state: Mapping, action: Mapping, item: Mapping) -> dict:
    """The final test proposed again on the configuration the study chooses now."""
    from . import opening
    chosen = st.choice_config(state)
    return {'kind': 'propose', 'step': st.FINAL_TEST, 'decision': st.FINAL_TEST,
            'default_value': chosen,
            'message': ('The final test would open another configuration than the one the '
                        'study chooses now: propose it again on the chosen configuration '
                        '(default_value) and record the junior\'s own words. The final test '
                        'stays sealed.'),
            'audience': audience.AGENT,
            'junior_message': opening.reservation_message(state, [item])}


def valid_value(state: Mapping, decision: str, value, details: Mapping):
    """A value the confirmation would accept in place of ``value``, refused as
    ``invalid_value`` with ``details``: a review-v1 variant informed by a development
    diagnostic that is no longer the current one cites the current one (the rule:
    ``diagnostic_not_current``); otherwise the engine's draft, or None."""
    from . import trials
    if decision == st.MODEL_VARIANT and details.get('reason') == 'diagnostic_not_current' \
            and isinstance(value, Mapping):
        current = (state.get('current') or {}).get(st.DIAG_SLOT[st.task_of(state)])
        if current is not None and st.is_current(state, st.DIAG_SLOT[st.task_of(state)]):
            out = copy.deepcopy(dict(value))
            for item in trials.variants_of(out):
                if item.get(trials.ORIGIN_KEY) == 'diagnostic_informed':
                    item[trials.DIAGNOSTIC_RESULT_KEY] = current
            return out
        return None
    return st.b1_default_value(state, decision)


def _propose_valid(state: Mapping, action: Mapping, details: Mapping) -> dict | None:
    """A value the confirmation refuses (``invalid_value``) is proposed again with one it
    accepts (:func:`valid_value`), the junior's words asked again."""
    proposal = state['proposals'].get(action.get('proposal_id')) or {}
    decision = proposal.get('decision_id') or action.get('decision')
    value = proposal.get('value') if proposal else action.get('default_value')
    fixed = valid_value(state, decision, value, details)
    if decision is None or fixed is None or fixed == value:
        return None
    out = _propose_again(state, {'kind': action.get('kind'), 'decision': decision,
                                 'proposal_id': action.get('proposal_id')})
    out['default_value'] = fixed
    lang = st.language_of(state)
    words = audience.decision_words(decision, lang)
    out['message'] = (f'The value of the {decision} would be refused as given '
                      f'(invalid_value: {details.get("reason") or "it no longer fits"}): '
                      'propose it again with default_value and ask the junior again.')
    out['junior_message'] = (
        f'La valeur de {words} ne convient plus en l\'état : elle vous est proposée à nouveau, '
        "mise à jour, puis vous dites si vous l'adoptez." if lang == audience.FR else
        f'The value of {words} no longer fits as it is: it is proposed to you again, updated, '
        'then you say whether you adopt it.')
    if decision == st.MODEL_VARIANT and details.get('reason') == 'diagnostic_not_current':
        out['junior_message'] = (
            f'{words[:1].upper() + words[1:]} cite un diagnostic de développement qui a été '
            "recalculé depuis : elle vous est proposée à nouveau en citant le diagnostic à "
            "jour, puis vous dites si vous l'adoptez." if lang == audience.FR else
            f'{words[:1].upper() + words[1:]} cites a development diagnostic that was computed '
            'again since: it is proposed to you again citing the current diagnostic, then you '
            'say whether you adopt it.')
    if not action.get('proposal_id'):
        out.pop('replaces', None)
    return out


def propose_again_value(state: Mapping, proposal: Mapping):
    """The value a stale proposal is proposed again with: the configuration the
    study chooses now for the final test; for a binary policy under an explicit model choice
    its rule (the view applies it to the model chosen now); the proposal's own value
    otherwise."""
    decision = proposal.get('decision_id')
    if decision == st.FINAL_TEST:
        return st.choice_config(state)
    if decision == 'policy':
        return rec.policy_rule(proposal.get('value')) or None
    return copy.deepcopy(proposal.get('value'))


def _propose_again(state: Mapping, action: Mapping) -> dict | None:
    """A stale proposal is proposed again (proposing replaces it), with the value it would be
    accepted with, and the junior's words asked again."""
    pid = action.get('proposal_id')
    proposal = state['proposals'].get(pid) or {}
    decision = proposal.get('decision_id') or action.get('decision')
    if decision is None:
        return None
    lang = st.language_of(state)
    fr = lang == audience.FR
    words = audience.decision_words(decision, lang)
    step = next((s['id'] for s in st.derive_plan(dict(state)) if s['decision'] == decision),
                decision)
    out = {'kind': 'propose', 'step': step, 'decision': decision, 'replaces': pid,
           'message': (f'Proposal {pid} on {decision} cannot be confirmed as it is (it rests '
                       'on decisions that changed since it was made, or its value no longer '
                       'fits): propose it again (default_value) and ask the junior again. '
                       'Proposing replaces it.'),
           'audience': audience.AGENT,
           'junior_message': (f'La proposition sur {words} a été faite avant un changement de '
                              "ce sur quoi elle repose : elle ne peut plus être adoptée telle "
                              'quelle. Elle vous est proposée à nouveau, puis vous dites si '
                              "vous l'adoptez." if fr else
                              f'The proposal on {words} was made before something it rests on '
                              'changed, so it can no longer be adopted as it is. It is proposed '
                              'to you again, then you say whether you adopt it.')}
    value = propose_again_value(state, proposal)
    if value is not None:
        out['default_value'] = value
    return out
