"""The three pauses as preconditions of the decision graph (plan §4).

* Pause 1: ``feature_availability`` needs ``prediction_time``; the split decision needs
  both.
* Pause 2: the ``split`` activity needs the split decision, and every EDA and fit
  needs a current split result.
* Pause 3: confirming ``policy`` needs a current policy evaluation of that rule;
  the conclusion ``adopt_policy`` needs an adopted policy; ``keep_baseline`` and
  ``inconclusive`` need none (post-v0.1 fixes, D6: "inconclusive" is the honest verdict
  while the policy is on hold, and ``not_yet_defensible`` names it). In a regression study
  the third decision is ``model_choice``: confirming it needs a current
  ``evaluate.regression`` result that compared the chosen model; the conclusion
  ``adopt_model`` needs the candidate model chosen, and ``keep_baseline`` and
  ``inconclusive`` need no model choice.

``missing_for_decision`` and ``missing_for_activity`` return the unmet requirements
(empty when met); the ``require_*`` functions raise
:class:`mlkit.reliability.CommandRefused` with code ``precondition_missing``. Phase 2
activities call :func:`require_activity` before reserving an execution, and again
when promoting a result.

Pure: only state is read, plus, when ``store`` is given, the registry entry of the
current policy evaluation (to check that it evaluated the proposed rule) and (review round
3, E3-3) the currency of the results the final-test opening rests on, by the rule of
``status`` (:mod:`mlkit.study.opening`).
"""
from __future__ import annotations

from typing import Any, Mapping

from mlkit.reliability import CommandRefused

from . import records as rec
from . import state as st
from . import trials

POLICY_EVALUATION = 'policy.evaluation'
REGRESSION_EVALUATION = 'evaluate.regression'
SPLIT_SLOT = 'split'
CONCLUSION_VERDICTS = ('adopt_policy', 'keep_baseline', 'inconclusive')
# A regression study adopts a model, not a decision rule.
REGRESSION_CONCLUSION_VERDICTS = ('adopt_model', 'keep_baseline', 'inconclusive')
CONCLUSION_VERDICTS_BY_TASK = {st.BINARY: CONCLUSION_VERDICTS,
                               st.REGRESSION: REGRESSION_CONCLUSION_VERDICTS}
# Model slots of a regression study: the reference (training mean) and the candidate.
REGRESSION_BASELINE, REGRESSION_CANDIDATE = 'fit.baseline', 'fit.linear'
BINARY_BASELINE, BINARY_CANDIDATE = 'fit.baseline', 'fit.logistic'
MODEL_CHOICES = (REGRESSION_CANDIDATE, REGRESSION_BASELINE)
FIT_SLOTS = {st.BINARY: (BINARY_BASELINE, BINARY_CANDIDATE),
             st.REGRESSION: (REGRESSION_BASELINE, REGRESSION_CANDIDATE)}

DECISION_REQUIRES = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': ('prediction_time', 'feature_availability'),
    'policy': ('prediction_time', 'feature_availability', 'split'),
    'model_choice': ('prediction_time', 'feature_availability', 'split'),
    'conclusion': ('prediction_time', 'feature_availability', 'split'),
}
# v0.2a (WP-A4): in a study with the WP-A4 decisions, the success criterion and the
# preprocessing are confirmed after the split decision; the choice and the conclusion need
# both (the success criterion is fixed before any model is seen, and the conclusion is
# judged against it).
WP_A4_REQUIRES = {
    st.SUCCESS_CRITERION: ('prediction_time', 'feature_availability', 'split'),
    st.PREPROCESSING: ('prediction_time', 'feature_availability', 'split'),
    'policy': (st.SUCCESS_CRITERION, st.PREPROCESSING),
    'model_choice': (st.SUCCESS_CRITERION, st.PREPROCESSING),
    'conclusion': (st.SUCCESS_CRITERION, st.PREPROCESSING),
}


# v0.2b (WP-B1): the variant is named after the success criterion and the preprocessing
# (it is fitted with them); the choice needs it (it compares it); the opening of the final
# test needs the choice and the success criterion (it judges the choice against it).
WP_B1_REQUIRES = {
    st.MODEL_VARIANT: ('prediction_time', 'feature_availability', 'split', st.SUCCESS_CRITERION,
                       st.PREPROCESSING),
    'policy': (st.MODEL_VARIANT,),
    'model_choice': (st.MODEL_VARIANT,),
    st.FINAL_TEST: ('prediction_time', 'feature_availability', 'split', st.SUCCESS_CRITERION,
                    st.PREPROCESSING, st.MODEL_VARIANT),
}
FINAL_TEST_EVALUATION = 'final_test.evaluation'
CAPTURE = 'predictor.capture'
VARIANT_FIT = 'fit.variant'
# WP-B4: the diagnostics of the final test.
FINAL_DIAGNOSTICS = 'diag.final_test'


def decision_requires(state: Mapping, decision_id: str) -> tuple[str, ...]:
    """The decisions that must be confirmed before ``decision_id`` can be."""
    base = DECISION_REQUIRES.get(decision_id, ())
    if st.has_wp_a4_decisions(state):
        extra = WP_A4_REQUIRES.get(decision_id, ())
        if decision_id in st.WP_A4_DECISIONS:
            base = ()
        base = tuple(dict.fromkeys(base + extra))
    if st.has_wp_b1_decisions(state):
        extra = WP_B1_REQUIRES.get(decision_id, ())
        if decision_id == 'policy' and st.has_explicit_binary_model_choice(state):
            extra = extra + ('model_choice',)
        if decision_id == st.FINAL_TEST:
            extra = extra + (st.choice_decision(state),)
            if st.has_explicit_binary_model_choice(state):
                extra = extra + ('model_choice',)
        base = tuple(dict.fromkeys(base + extra))
    return base


def conclusion_verdicts(state: Mapping | str | None) -> tuple[str, ...]:
    return CONCLUSION_VERDICTS_BY_TASK[st.task_of(state)]


def _confirmed(state: Mapping, decision_id: str) -> bool:
    return state['decisions'][decision_id]['status'] == 'confirmed'


def _need_decision(state: Mapping, decision_id: str) -> dict:
    return {'requirement': 'decision_confirmed', 'decision': decision_id,
            'status': state['decisions'][decision_id]['status']}


def evaluated_rules(entry: Mapping) -> list[str]:
    """Rules a policy evaluation entry covers: ``params.rules`` or ``params.rule``."""
    params = entry.get('params', {})
    if isinstance(params.get('rules'), list):
        rules = [str(r) for r in params['rules']]
    else:
        rules = [str(params['rule'])] if params.get('rule') is not None else []
    return [rec.canonical_rule(r) or r for r in rules]


def missing_for_decision(state: Mapping, decision_id: str, value: Any = None, *,
                         store=None) -> list[dict]:
    """Unmet requirements to confirm ``decision_id`` with ``value``."""
    missing = [_need_decision(state, d) for d in decision_requires(state, decision_id)
               if not _confirmed(state, d)]
    from . import assurance
    if decision_id == st.MODEL_VARIANT and assurance.profile(state) == 'review-v1':
        for slot in FIT_SLOTS[st.task_of(state)]:
            if not st.is_current(state, slot):
                missing.append({'requirement': 'result_current', 'slot': slot,
                                'detail': 'Fit the candidate and its reference before adopting '
                                          'a challenger.'})
        diag_slot = st.DIAG_SLOT[st.task_of(state)]
        if not st.is_current(state, diag_slot):
            missing.append({'requirement': 'development_diagnostics_current',
                            'slot': diag_slot,
                            'detail': 'Current candidate development diagnostics are required '
                                      'before the challenger discussion.'})
    if decision_id == st.FINAL_TEST and state['current'].get(CAPTURE):
        # Library integration v1: a study that captured its predictor opens the final test
        # only on a current capture of the configuration it opens. Review round 2 (E2-1, A
        # F1): current by the rule ``status`` and ``evidence`` use (stale map, code changed
        # under the attestations, upstream), and loadable as the final evaluation loads it
        # (bundle verification, environment, parity rows), checked here, before the
        # confirmation commits and so before anything is marked opened.
        from mlkit.contracts import capture
        if store is not None:
            problem = capture.currency_problem(store, state)
        elif not st.is_current(state, CAPTURE):
            problem = {'requirement': 'result_current', 'slot': CAPTURE,
                       'detail': 'Capture the chosen model again before opening the final '
                                 'test: the capture is no longer current.'}
        else:
            problem = None
        if problem is not None:
            missing.append(problem)
        elif store is not None:
            from . import registry
            entry = registry.get(store, state['current'][CAPTURE])
            if value is not None and entry['inputs'].get('configuration') != value:
                # Review round 6 (area E, R6E-1): with the junior's message, as every other
                # refusal of the opening.
                captured = entry['inputs'].get('configuration')
                missing.append({'requirement': 'result_current', 'slot': CAPTURE,
                                'captured': captured,
                                'detail': 'The captured predictor is another configuration; '
                                          'capture the one the final test would open.',
                                'junior_message': other_configuration_message(
                                    state, captured, value)})
            else:
                loading = capture.loading_problem(store, state, capture.predictor_of(entry))
                if loading is not None:
                    missing.append(loading)
    if decision_id == 'policy':
        if not st.is_current(state, POLICY_EVALUATION):
            missing.append({'requirement': 'result_current', 'slot': POLICY_EVALUATION,
                            'detail': 'Evaluate the policy before adopting it.'})
        elif store is not None:
            from . import registry   # read of one entry; registry is a writer-side module
            entry = registry.get(store, state['current'][POLICY_EVALUATION])
            rule = rec.policy_rule(value) if value is not None else None
            if value is not None and (rule or str(value)) not in evaluated_rules(entry):
                missing.append({'requirement': 'result_current', 'slot': POLICY_EVALUATION,
                                'rule': value, 'evaluated': evaluated_rules(entry),
                                'detail': 'The current evaluation did not evaluate this rule.'})
            elif value is not None:
                model = rec.policy_model(value)
                compared = [str(m) for m in entry.get('params', {}).get('models', [])]
                if model not in compared:
                    missing.append({'requirement': 'result_current', 'slot': POLICY_EVALUATION,
                                    'model': model, 'evaluated': compared,
                                    'detail': 'The current evaluation did not evaluate this '
                                              'model.'})
    if decision_id == 'model_choice':
        if st.task_of(state) == st.BINARY:
            required = ['fit.logistic']
            if isinstance(value, str) and trials.is_variant_slot(value):
                required.append(value)
            for slot in required:
                if not st.is_current(state, slot):
                    missing.append({'requirement': 'result_current', 'slot': slot,
                                    'detail': 'Fit every compared model on development rows '
                                              'before selecting one.'})
        elif not st.is_current(state, REGRESSION_EVALUATION):
            missing.append({'requirement': 'result_current', 'slot': REGRESSION_EVALUATION,
                            'detail': 'Evaluate the models on validation before choosing one.'})
        elif store is not None and value is not None:
            from . import registry   # read of one entry; registry is a writer-side module
            entry = registry.get(store, state['current'][REGRESSION_EVALUATION])
            compared = [str(m) for m in entry.get('params', {}).get('models', [])]
            if value not in compared:
                missing.append({'requirement': 'result_current', 'slot': REGRESSION_EVALUATION,
                                'model': value, 'evaluated': compared,
                                'detail': 'The current evaluation did not compare this model.'})
    if decision_id == st.FINAL_TEST:
        missing += final_test_missing(state, value, store=store)
    if decision_id == 'conclusion':
        verdict = value.get('verdict') if isinstance(value, Mapping) else None
        if st.task_of(state) == st.REGRESSION:
            choice = state['decisions']['model_choice']
            # v0.3 (WP-F1): a chosen variant is a model too.
            if verdict == 'adopt_model' and not (
                    _confirmed(state, 'model_choice')
                    and (choice['value'] == REGRESSION_CANDIDATE
                         or trials.is_variant_slot(choice['value']))):
                missing.append({**_need_decision(state, 'model_choice'),
                                'detail': f'Concluding adopt_model needs model_choice confirmed '
                                          f'as {REGRESSION_CANDIDATE} or a variant; otherwise '
                                          f'conclude keep_baseline.'})
        elif verdict == 'adopt_policy' and not _confirmed(state, 'policy'):
            missing.append({**_need_decision(state, 'policy'),
                            'detail': 'Adopt a policy first, or conclude keep_baseline or '
                                      'inconclusive.'})
        if assurance.profile(state) == 'review-v1' and verdict != 'inconclusive' \
                and st.is_current(state, FINAL_TEST_EVALUATION) \
                and not st.is_current(state, FINAL_DIAGNOSTICS):
            missing.append({'requirement': 'final_evidence_current_for_configuration',
                            'slot': FINAL_DIAGNOSTICS,
                            'detail': 'Compute the final diagnostic summary from the stored '
                                      'final predictions before drawing an empirical conclusion.'})
    return missing


def other_configuration_message(state: Mapping, captured: Any, value: Any) -> str:
    """Review round 6 (area E, R6E-1): the junior message of a final test that would open a
    configuration other than the captured one, in the study language."""
    from . import opening
    lang = st.language_of(state)
    if lang == 'fr':
        return ('Votre modèle capturé est une autre configuration '
                f'({opening.configuration_words(captured, lang)}) que celle que le test final '
                f'ouvrirait ({opening.configuration_words(value, lang)}) : le test final ne '
                "peut pas l'évaluer. Capturez d'abord à nouveau le modèle choisi, puis ouvrez "
                f"le test final. {opening.NOT_READ['fr']}")
    return ('Your captured model is another configuration '
            f'({opening.configuration_words(captured, lang)}) than the one the final test would '
            f'open ({opening.configuration_words(value, lang)}), so the final test cannot score '
            'it. Capture the chosen model again first, then open the final test. '
            f"{opening.NOT_READ['en']}")


def final_test_missing(state: Mapping, value: Any = None, *, store=None) -> list[dict]:
    """What the opening of the final test still needs (WP-B1), beyond the confirmed
    decisions: a sealed final test, the value naming the chosen configuration, no result
    stale, no decision to confirm again, and the current evaluations it is opened on."""
    missing: list[dict] = []
    part = state.get('partition')
    if part is None:
        missing.append({'requirement': 'final_test_sealed',
                        'detail': 'This study was created before the final test existed: it has '
                                  'no final test to open.'})
        return missing
    chosen = st.choice_config(state)
    if value is not None and chosen is not None and dict(value) != chosen:
        missing.append({'requirement': 'chosen_configuration', 'value': value,
                        'chosen': chosen,
                        'detail': 'The final test opens the configuration the study chose; '
                                  'propose it as chosen.'})
    # WP-B4: stale diagnostics describe the choice, they do not make it: they never block.
    # v0.3 (WP-F1): a variant the decision no longer names is not part of the choice.
    declared = trials.declared_slots(state)
    stale = sorted(slot for slot, rid in state['current'].items()
                   if rid in state['stale'] and not slot.startswith(('eda.', 'diag.'))
                   and slot != 'policy.inspection'
                   and not (trials.is_variant_slot(slot) and slot not in declared))
    if stale:
        missing.append({'requirement': 'nothing_stale', 'slots': stale,
                        'detail': 'Some results are stale: run them again before opening the '
                                  'final test.'})
    # Review round 4 (E4-1): the final test's own confirmation, asked again, is what this
    # rule is checked for.
    again = [d for d in st.decision_ids(state) if d != st.FINAL_TEST
             and state['decisions'][d]['status'] == 'reconfirm_required']
    if again:
        missing.append({'requirement': 'nothing_to_reconfirm', 'decisions': again,
                        'detail': 'Confirm these decisions again before opening the final test.'})
    task = st.task_of(state)
    slots = list(FIT_SLOTS[task]) + (declared or [VARIANT_FIT]) + [
        POLICY_EVALUATION if task == st.BINARY else REGRESSION_EVALUATION]
    for slot in slots:
        if not st.is_current(state, slot):
            missing.append({'requirement': 'result_current', 'slot': slot,
                            'detail': 'The final test is opened on current results only.'})
    if store is not None:
        # Review round 3 (E3-3): current by the rule ``status`` and ``evidence`` use, not by
        # the stale map alone (the capture is checked by ``missing_for_decision``).
        missing += selection_not_current(store, state)
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        diag_slot = st.DIAG_SLOT[task]
        diag_id = state.get('current', {}).get(diag_slot)
        if not st.is_current(state, diag_slot):
            missing.append({'requirement': 'development_diagnostics_current',
                            'slot': diag_slot,
                            'detail': 'Run current development diagnostics for the chosen '
                                      'configuration before opening the final test.'})
        elif store is not None and chosen is not None:
            from . import registry
            entry = registry.get(store, diag_id)
            params = entry.get('params') or {}
            model_ok = chosen['model'] in (params.get('models') or [])
            rule_ok = chosen.get('rule') is None or chosen.get('rule') == params.get('rule')
            if not model_ok or not rule_ok:
                missing.append({'requirement': 'development_diagnostics_current',
                                'slot': diag_slot, 'result_id': diag_id,
                                'chosen': chosen,
                                'diagnostic': {'models': params.get('models'),
                                               'rule': params.get('rule')},
                                'detail': 'The current diagnostic describes a different '
                                          'model or action rule.'})
    return missing


def opening_missing(state: Mapping, store=None) -> list[dict]:
    """Review round 4 (E4-1): what the reservation of ``final_test.evaluation`` (every path
    that opens the final test: the opening right after the confirmation, and ``run
    final_test.evaluation`` on a confirmed final test whose opening did not run) still needs
    before anything is marked opened. It is the confirmation's own rule
    (:func:`final_test_missing` on the confirmed value: the stale map, the full currency of
    every result the opening rests on, the value equal to the configuration the study
    chooses now, nothing awaiting reconfirmation), plus the decisions it requires confirmed
    and the final test's own confirmation still holding (a change of what it rests on after
    the confirmation makes it ``reconfirm_required``, :mod:`mlkit.study.dependencies`). The
    capture's currency and loading are the plan's (E2-1, A F1). Every item carries the same
    junior message (:func:`mlkit.study.opening.reservation_message`); empty when the final
    test may open."""
    decision = state['decisions'].get(st.FINAL_TEST) or {}
    missing: list[dict] = []
    if decision.get('status') != 'confirmed':
        missing.append({**_need_decision(state, st.FINAL_TEST),
                        'reason': decision.get('reason'),
                        'detail': 'The final test opens only on its confirmation in the '
                                  "junior's words; confirm it again."})
    missing += [_need_decision(state, d) for d in decision_requires(state, st.FINAL_TEST)
                if not _confirmed(state, d)]
    missing += final_test_missing(state, decision.get('value'), store=store)
    if missing:
        from . import opening
        junior = opening.reservation_message(state, missing)
        missing = [{**m, 'junior_message': junior} for m in missing]
    return missing


def selection_not_current(store, state: Mapping, *, capture: bool = False) -> list[dict]:
    """Review round 3 (E3-3): :func:`mlkit.study.opening.not_current` on ``state`` (the
    writer's state, through :meth:`mlkit.study.read.Study.at_state`)."""
    from . import opening, read
    return opening.not_current(read.Study.at_state(store.study_dir, state), state,
                               capture=capture)


ACTIVITY_DECISIONS = ('prediction_time', 'feature_availability', 'split')
# v0.2a (WP-A4): the structural quality overview reads the development rows without the
# target, so it needs no decision and no split (it can run right after ``init``).
NO_REQUIREMENT_ACTIVITIES = ('eda.quality', 'eda.correlation')
# The fits (and what reads them) need the success criterion and the preprocessing when the
# study has them: the criterion is fixed before any model is seen, and the models apply the
# preprocessing.
MODEL_DECISIONS = (st.SUCCESS_CRITERION, st.PREPROCESSING)


def missing_for_activity(state: Mapping, activity: str) -> list[dict]:
    """Unmet requirements to run ``activity`` (a slot name such as ``fit.logistic``)."""
    if activity in NO_REQUIREMENT_ACTIVITIES:
        return []
    if activity == CAPTURE:
        # Library integration v1: the chosen configuration, before the final test opens.
        from mlkit.contracts import capture
        return capture.missing(state)
    if activity == FINAL_TEST_EVALUATION:
        # WP-B1: only after the opening decision, once.
        missing = [] if _confirmed(state, st.FINAL_TEST) else [_need_decision(state,
                                                                              st.FINAL_TEST)]
        return missing
    if activity == FINAL_DIAGNOSTICS:
        # WP-B4: the final test's diagnostics read its rows, so only once it was opened and
        # its one evaluation is recorded; before that, nothing is read.
        if not st.final_test_opened(state):
            return [{'requirement': 'final_test_opened',
                     'detail': 'The final test is sealed: its diagnostics exist only after the '
                               'junior opened it and its one evaluation is recorded.'}]
        if FINAL_TEST_EVALUATION not in state['current']:
            return [{'requirement': 'result_current', 'slot': FINAL_TEST_EVALUATION,
                     'detail': 'The final test was opened without a recorded evaluation.'}]
        return []
    missing = [_need_decision(state, d) for d in ACTIVITY_DECISIONS if not _confirmed(state, d)]
    if activity.startswith(('fit.', 'policy.', 'evaluate.', 'diag.')) \
            and st.has_wp_a4_decisions(state):
        missing += [{**_need_decision(state, d),
                     'detail': 'Fix the success criterion and the preprocessing before fitting '
                               'any model.'}
                    for d in MODEL_DECISIONS if not _confirmed(state, d)]
    if activity == SPLIT_SLOT:
        return missing
    if not st.is_current(state, SPLIT_SLOT):
        missing.append({'requirement': 'result_current', 'slot': SPLIT_SLOT,
                        'detail': 'Split the data before exploring or fitting it.'})
    if trials.is_variant_slot(activity) and st.has_wp_b1_decisions(state):
        if not _confirmed(state, st.MODEL_VARIANT):
            missing.append({**_need_decision(state, st.MODEL_VARIANT),
                            'detail': 'Name the variant to compare before fitting it.'})
        elif activity not in trials.declared_slots(state):
            # v0.3 (WP-F1): variants 2 and 3 exist once the decision names them.
            missing.append({'requirement': 'variant_declared', 'slot': activity,
                            'declared': trials.declared_slots(state),
                            'detail': 'The variant decision does not name this variant.'})
    if activity.startswith(('policy.', 'evaluate.', 'diag.')):
        # WP-B4: the diagnostics read the predictions the evaluation reads.
        for slot in FIT_SLOTS[st.task_of(state)]:
            if not st.is_current(state, slot):
                missing.append({'requirement': 'result_current', 'slot': slot})
        if st.has_wp_b1_decisions(state):
            # WP-B1: the evaluation compares the variant the junior named with the candidate
            # (v0.3, WP-F1: every variant named). The diagnostics run after the first fit,
            # before any variant is named (R28), and compare the variants once they are.
            if not _confirmed(state, st.MODEL_VARIANT):
                if not activity.startswith('diag.'):
                    missing.append({**_need_decision(state, st.MODEL_VARIANT),
                                    'detail': 'Name the variant to compare before evaluating.'})
            else:
                for slot in trials.declared_slots(state) or [VARIANT_FIT]:
                    if not st.is_current(state, slot):
                        missing.append({'requirement': 'result_current', 'slot': slot})
    return missing



def refuse_missing(missing: list[dict], subject: str) -> None:
    """Raise ``precondition_missing`` for ``missing`` (with its junior message), if any."""
    _refuse(missing, subject)


def _refuse(missing: list[dict], subject: str) -> None:
    if missing:
        details: dict = {'missing': missing}
        # Review round 2 (E2-1): an unmet requirement written for the junior (the capture
        # of the final test) is relayed as the refusal's junior message.
        junior = [m['junior_message'] for m in missing if m.get('junior_message')]
        if junior:
            details['junior_message'] = ' '.join(dict.fromkeys(junior))
        raise CommandRefused('precondition_missing', f'{subject} is not possible yet.',
                             details=details)


def require_decision(state: Mapping, decision_id: str, value: Any = None, *, store=None) -> None:
    _refuse(missing_for_decision(state, decision_id, value, store=store),
            f'Confirming {decision_id}')


def require_activity(state: Mapping, activity: str) -> None:
    from . import assurance
    assurance.require_activity(state, activity)
    _refuse(missing_for_activity(state, activity), f'Running {activity}')
