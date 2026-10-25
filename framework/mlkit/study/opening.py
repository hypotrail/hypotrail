"""What the opening of the final test rests on, and whether it is current (review round 3,
E3-3).

The final test is opened once, on the configuration the study chose; the choice rests on the
split, the reference and candidate fits, the declared variants, the policy evaluation (binary)
or the model comparison (regression), under review-v1 the development diagnostics, and the
captured predictor when the study captured one. Each must be current by the rule ``status``
and ``evidence`` use (:meth:`mlkit.study.read.Study.currency`: the stale map, a code change
under the code attestations, a result computed with delayed-label rows, an upstream result
not current), not by the stale map alone, before the final test may be opened.

:func:`not_current` is read-side (a snapshot and a state, nothing written): the confirmation
of ``final_test`` (:func:`mlkit.study.preconditions.final_test_missing`), the reservation of
``final_test.evaluation`` (:mod:`mlkit.study.executions`) and ``next_action``
(:mod:`mlkit.study.view`) all use it.
"""
from __future__ import annotations

from typing import Mapping

from . import state as st
from . import trials

SPLIT = 'split'
POLICY_EVALUATION = 'policy.evaluation'
REGRESSION_EVALUATION = 'evaluate.regression'
VARIANT_FIT = 'fit.variant'
CAPTURE = 'predictor.capture'
FIT_SLOTS = {st.BINARY: ('fit.baseline', 'fit.logistic'),
             st.REGRESSION: ('fit.baseline', 'fit.linear')}
NOT_READ = {'en': 'No final-test row was read: the final test is still sealed.',
            'fr': "Aucune ligne de l'échantillon de test final n'a été lue : il reste scellé."}


def selection_slots(state: Mapping) -> list[str]:
    """The slots whose results the opening rests on, upstream first: the split, the reference
    and the candidate fits, the declared variants, the policy evaluation (binary) or the model
    comparison (regression), and under review-v1 the development diagnostics."""
    from . import assurance
    task = st.task_of(state)
    slots = ([SPLIT] + list(FIT_SLOTS[task]) + (trials.declared_slots(state) or [VARIANT_FIT])
             + [POLICY_EVALUATION if task == st.BINARY else REGRESSION_EVALUATION])
    if assurance.profile(state) == 'review-v1':
        slots.append(st.DIAG_SLOT[task])
    return slots


def not_current(snapshot, state: Mapping, *, capture: bool = False) -> list[dict]:
    """The results of :func:`selection_slots` (and the capture when ``capture`` and the study
    holds one) that the stale map calls current but ``snapshot.currency`` does not. A slot
    without a result or marked stale is left to the other requirements (``result_current``,
    ``nothing_stale``).

    Each item is ``{requirement: "result_current", slot, result_id, reason, code_changed,
    upstream_not_current, delayed_labels_included, detail, junior_message}``; every item
    carries the same junior message, which names every slot, so a refusal relays it once."""
    slots = selection_slots(state)
    if capture and state['current'].get(CAPTURE):
        slots.append(CAPTURE)
    out = []
    for slot in slots:
        rid = state['current'].get(slot)
        if rid is None or not st.is_current(state, slot):
            continue
        currency = snapshot.currency(rid)
        if currency['current']:
            continue
        reason = currency['reason'] or {}
        text = str(reason.get('reason') or 'it is no longer current')
        out.append({'requirement': 'result_current', 'slot': slot, 'result_id': rid,
                    'reason': text,
                    'code_changed': list(reason.get('code_changed') or []),
                    'upstream_not_current': list(reason.get('upstream_not_current') or []),
                    'delayed_labels_included': bool(reason.get('delayed_labels_included')),
                    'detail': f'{slot} is not current ({text}): run it again before opening '
                              'the final test. No final-test row was read.'})
    if out:
        junior = message(state, out)
        for item in out:
            item['junior_message'] = junior
    return out


def message(state: Mapping, items: list[dict]) -> str:
    """The junior message of :func:`not_current` in the study language: what is not current
    and why, what to do, and that the final test is still sealed."""
    from . import audience
    lang = st.language_of(state)
    fr = lang == 'fr'
    words = audience.join([audience.activity_words(m['slot'], lang) for m in items], lang)
    why = []
    if any(m['delayed_labels_included'] for m in items):
        why.append("elles ont été calculées avec des lignes de développement dont l'étiquette "
                   "n'était pas encore connue au moment de la décision (des étiquettes "
                   "tardives)" if fr else
                   'they were computed with development rows whose label was not known yet at '
                   'the decision time (delayed labels)')
    if any(m['code_changed'] for m in items):
        why.append('le code du moteur qui les a calculées a changé depuis' if fr else
                   "the engine's code that computed them changed since")
    if not why:
        why.append('elles ont été calculées à partir de résultats qui ne sont plus à jour'
                   if fr else 'they were computed from results that are no longer current')
    if fr:
        return (f"Le test final s'ouvre seulement sur des résultats à jour, et ceux-ci ne le "
                f"sont pas : {words}. Raison : {' ; '.join(why)}. Relancez-les d'abord, puis "
                f"ouvrez le test final. {NOT_READ['fr']}")
    return (f'The final test is opened on current results only, and these are not current: '
            f'{words}. Why: {"; ".join(why)}. Run them again first, then open the final test. '
            f'{NOT_READ["en"]}')


def configuration_words(config, lang: str) -> str:
    """A ``final_test`` value (``{model, rule}``) in words, in ``lang``."""
    from . import audience
    if not isinstance(config, Mapping):
        return audience.model_words(config, lang) if config else ''
    model = audience.model_words(config.get('model'), lang)
    rule = config.get('rule')
    if not rule:
        return model
    return (f'{model} avec la règle « {audience.rule_words(rule, lang)} »' if lang == 'fr'
            else f'{model} with the rule "{audience.rule_words(rule, lang)}"')


def reservation_message(state: Mapping, missing: list[dict]) -> str:
    """Review round 4 (E4-1): the junior message of a refused opening of a confirmed final
    test (:func:`mlkit.study.preconditions.opening_missing`), in the study language: what
    changed since the confirmation, what to do first (confirm a decision again, run results
    again), that the final test is then confirmed again in the junior's own words, and that
    no final-test row was read."""
    from . import audience
    lang = st.language_of(state)
    fr = lang == 'fr'
    final = st.FINAL_TEST
    again: list[str] = []
    stale: list[str] = []
    confirm_final = False
    chosen = None
    not_current_items = []
    for m in missing:
        need = m.get('requirement')
        if need == 'decision_confirmed':
            if m.get('decision') == final:
                confirm_final = True
            else:
                again.append(m['decision'])
        elif need == 'nothing_to_reconfirm':
            again += [d for d in m.get('decisions') or [] if d != final]
            if final in (m.get('decisions') or []):
                confirm_final = True
        elif need == 'chosen_configuration':
            chosen = m
            confirm_final = True
        elif need == 'nothing_stale':
            stale += list(m.get('slots') or [])
        elif need in ('result_current', 'development_diagnostics_current') and m.get('slot'):
            if 'reason' in m and 'code_changed' in m:
                not_current_items.append(m)
            else:
                stale.append(m['slot'])
        elif need == 'final_test_sealed':
            return ("Cette étude n'a pas de test final à ouvrir." if fr else
                    'This study has no final test to open.')
    again = list(dict.fromkeys(again))
    stale = [s for s in dict.fromkeys(stale) if s not in {m['slot'] for m in not_current_items}]
    parts = []
    if fr:
        parts.append("Le test final ne peut pas s'ouvrir maintenant : ce sur quoi reposait sa "
                     "confirmation n'est plus à jour.")
        if chosen is not None:
            before = configuration_words(chosen.get('value'), lang)
            now = configuration_words(chosen.get('chosen'), lang)
            parts.append(f"Vous l'avez confirmé pour {before}, et l'étude choisit maintenant "
                         f'{now}.')
        if stale:
            words = audience.join([audience.activity_words(s, lang) for s in stale], lang)
            parts.append(f"Relancez d'abord : {words}.")
        if not_current_items:
            parts.append(message(state, not_current_items).replace(' ' + NOT_READ['fr'], ''))
        if again:
            words = audience.join([audience.decision_words(d, lang) for d in again], lang)
            parts.append(f'Confirmez ensuite à nouveau : {words}.')
        parts.append('Ensuite, confirmez à nouveau le test final, avec vos propres mots, sur la '
                     "configuration que l'étude choisit alors." if confirm_final or again
                     else 'Ensuite, ouvrez le test final.')
        parts.append(NOT_READ['fr'])
        return ' '.join(parts)
    parts.append('The final test cannot be opened now: what its confirmation rested on is no '
                 'longer current.')
    if chosen is not None:
        before = configuration_words(chosen.get('value'), lang)
        now = configuration_words(chosen.get('chosen'), lang)
        parts.append(f'You confirmed it for {before}, and the study now chooses {now}.')
    if stale:
        words = audience.join([audience.activity_words(s) for s in stale])
        parts.append(f'First run again: {words}.')
    if not_current_items:
        parts.append(message(state, not_current_items).replace(' ' + NOT_READ['en'], ''))
    if again:
        parts.append('Then confirm again: '
                     f'{audience.join([audience.decision_words(d) for d in again])}.')
    parts.append('Then confirm the final test again, in your own words, on the configuration '
                 'the study then chooses.' if confirm_final or again
                 else 'Then open the final test.')
    parts.append(NOT_READ['en'])
    return ' '.join(parts)


BINARY_VERDICTS = ('adopt_policy', 'keep_baseline', 'inconclusive')
REGRESSION_VERDICTS = ('adopt_model', 'keep_baseline', 'inconclusive')


def conclusion_verdicts(state: Mapping) -> list[str]:
    """Review round 4 (E4-2): the verdicts a conclusion proposed now would be accepted with,
    read from state only (the rule of :func:`mlkit.study.preconditions.missing_for_decision`
    for the conclusion, on the read side): an adopted policy for ``adopt_policy``, the model
    choice confirmed as the candidate or a variant for ``adopt_model``, and under review-v1
    only ``inconclusive`` while the final evaluation is recorded without current final-test
    diagnostics."""
    from . import assurance
    task = st.task_of(state)
    decisions = state['decisions']
    if assurance.profile(state) == 'review-v1' and st.is_current(state, 'final_test.evaluation') \
            and not st.is_current(state, 'diag.final_test'):
        return ['inconclusive']
    out = []
    for verdict in (REGRESSION_VERDICTS if task == st.REGRESSION else BINARY_VERDICTS):
        if verdict == 'adopt_policy' and (decisions.get('policy') or {}).get('status') \
                != 'confirmed':
            continue
        if verdict == 'adopt_model':
            choice = decisions.get('model_choice') or {}
            if choice.get('status') != 'confirmed' or not (
                    choice.get('value') == 'fit.linear'
                    or trials.is_variant_slot(choice.get('value'))):
                continue
        out.append(verdict)
    return out
