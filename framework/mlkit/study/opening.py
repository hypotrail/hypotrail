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
