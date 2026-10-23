"""Fine-grained invalidation after a confirmed change (plan §3.7).

:data:`MUTATIONS` is the dependency table. :func:`effects` classifies one change and
returns what must be recomputed, re-explained, or reconfirmed; :func:`apply_effects`
applies it to state in memory (inside an ``apply_command`` handler) and records the
invalidation with its reason. Downstream results are found through registry lineage:
a current result computed from a stale one is stale too.

Effect keys (all lists of names, so renderers can iterate):

* ``refit``: model slots to fit again (``fit.*``);
* ``re_eda``: EDA slots to recompute (``eda.*``);
* ``re_policy``: policy slots to evaluate again (``policy.*``);
* ``recompute``: other activity slots to run again (``split``);
* ``re_chart``: slots whose charts change (union of the above);
* ``re_explain``: plan steps whose explanation must be rewritten;
* ``reconfirm``: confirmed decisions that need the user's words again.

Plus ``mutation`` (table id), ``row`` (table row), ``reason``, ``blocked_until``
(decisions to reconfirm before the listed refits can run), ``scope``, and ``notes``.

An unknown mutation invalidates everything that is current and asks for every
confirmed decision again, with its reason recorded. Facts are never reconfirmed: a
``documented_fact`` stays as documented, and no fact is ever "confirmed".

A changed dataset or case (row 12) is not an invalidation but a refusal:
``dataset_changed``.

This module imports neither pandas, numpy, nor scikit-learn.
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from . import records as rec
from . import state as st
from . import trials
from .errors import StudyError

EFFECT_KEYS = ('refit', 're_eda', 're_policy', 're_chart', 're_explain', 'reconfirm')
META_KEYS = ('mutation', 'row', 'reason', 'recompute', 'blocked_until', 'scope', 'notes')
USABLE_AVAILABILITY = ('available_at_prediction', 'uncertain_included')
POLICY_RULES = ('threshold', 'capacity', 'share')

# Plan §3.7. ``refit``/``re_eda``/``re_policy``/``recompute`` name slots; the special
# value ``'*'`` means every current slot of that kind.
MUTATIONS: tuple[dict, ...] = (
    {'row': 1, 'mutation': 'prediction_time', 'refit': ('fit.logistic',), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (),
     'reconfirm': ('feature_availability', 'policy', 'conclusion'),
     'blocked_until': ('feature_availability',),
     'notes': ('The logistic refit waits until feature availability is confirmed again.',)},
    {'row': 2, 'mutation': 'feature_availability.feature_set', 'refit': ('fit.logistic',),
     're_eda': (), 're_policy': ('policy.evaluation',), 'recompute': (),
     'reconfirm': ('policy', 'conclusion'), 'blocked_until': (),
     'notes': ('The constant baseline uses no feature and stays current.',)},
    {'row': 3, 'mutation': 'feature_availability.wording', 'refit': (), 're_eda': (),
     're_policy': (), 'recompute': (), 'reconfirm': (), 'blocked_until': (),
     're_explain': ('feature_availability',),
     'notes': ('The feature set is unchanged; only the dictionary text changes.',)},
    {'row': 4, 'mutation': 'split', 'refit': ('fit.baseline', 'fit.logistic'),
     're_eda': ('*',), 're_policy': ('policy.evaluation',), 'recompute': ('split',),
     'reconfirm': ('policy', 'conclusion'), 'blocked_until': (),
     'notes': ('Exposure is retained: rows explored under the old split are not unseen. '
               'The split activity reports the overlap (exposure.overlap) when it runs.',)},
    {'row': 5, 'mutation': 'policy.parameter', 'refit': (), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (), 'reconfirm': ('policy', 'conclusion'),
     'blocked_until': (),
     'notes': ('No refit: predictions are reused. The previous policy confirmation is '
               'superseded.',)},
    {'row': 6, 'mutation': 'policy.rule_type', 'refit': (), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (), 'reconfirm': ('policy', 'conclusion'),
     'blocked_until': (), 'notes': ('No refit: predictions are reused.',)},
    {'row': 7, 'mutation': 'settings.bootstrap', 'refit': (), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (), 'reconfirm': ('conclusion',),
     'blocked_until': (), 'scope': 'intervals',
     'notes': ('Only the intervals are recomputed; point estimates do not change.',)},
    {'row': 8, 'mutation': 'usage_label', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': ('conclusion',), 'blocked_until': (),
     're_explain': ('conclusion',), 'notes': ('The conclusion is explained again.',)},
    {'row': 9, 'mutation': 'eda_added', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': (), 'blocked_until': (), 'scope': 'addition',
     'notes': ('A new EDA result is added; nothing existing changes.',)},
    {'row': 10, 'mutation': 'conclusion', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': (), 'blocked_until': (), 're_explain': ('conclusion',),
     'notes': ('Nothing depends on the conclusion text.',)},
    {'row': 11, 'mutation': 'code_fingerprint', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': (), 'blocked_until': (),
     'notes': ('The affected activity and everything downstream of it (registry lineage) '
               'are stale; no decision changes.',)},
    {'row': 12, 'mutation': 'dataset', 'refusal': 'dataset_changed'},
    # WP-B2. Changing the selected binary model reuses the stored predictions and the
    # comparison, but the rule must be adopted again for that model.
    {'row': 13, 'mutation': 'model_choice', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': ('policy', 'conclusion'), 'blocked_until': (),
     'notes': ('No refit and no new evaluation: the stored predictions and the current '
               'comparison are reused. The decision rule must be confirmed for the newly '
               'selected model.',)},
    # v0.2a (WP-A4). Row 14: the preprocessing parameters changed; the candidate model is
    # fitted again with them, its evaluation follows, and the choice and conclusion are asked
    # again. The EDA is unchanged (it never applies the preprocessing). Row 15: only the
    # motivating results changed; nothing is recomputed. Row 16: the success criterion
    # changed; the conclusion is judged against it, so it is asked again.
    {'row': 14, 'mutation': 'preprocessing', 'refit': ('fit.logistic',), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (), 'reconfirm': ('policy', 'conclusion'),
     'blocked_until': (),
     'notes': ('The constant baseline uses no feature and stays current; the exploration is '
               'unchanged.',)},
    {'row': 15, 'mutation': 'preprocessing.motivation', 'refit': (), 're_eda': (),
     're_policy': (), 'recompute': (), 'reconfirm': (), 'blocked_until': (),
     're_explain': ('preprocessing',),
     'notes': ('The parameters are unchanged; only the analyses cited as motivation changed.',)},
    {'row': 16, 'mutation': 'success_criterion', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': ('conclusion',), 'blocked_until': (),
     'notes': ('No result changes; the conclusion is judged against the new criterion.',)},
    # v0.2b (WP-B1). Row 17: the variant changed; the variant is fitted again, the evaluation
    # follows, and the choice and the conclusion are asked again. The candidate and the
    # baseline stay current.
    {'row': 17, 'mutation': 'model_variant', 'refit': ('fit.variant',), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (), 'reconfirm': ('policy', 'conclusion'),
     'blocked_until': (),
     'notes': ('The baseline and the candidate stay current; only the variant is fitted again. '
               'The trial count grows by one configuration.',)},
    {'row': 18, 'mutation': 'success_criterion.selection', 'refit': (), 're_eda': (),
     're_policy': ('policy.evaluation',), 'recompute': (),
     'reconfirm': ('policy', 'conclusion'), 'blocked_until': (),
     'notes': ('Fixed predictions are reused. Selection-dependent evaluations and tuned '
               'variants are recomputed on development rows.',)},
    {'row': '*', 'mutation': 'unknown', 'refit': ('*',), 're_eda': ('*',), 're_policy': ('*',),
     'recompute': ('*',), 'reconfirm': ('*',), 'blocked_until': (),
     'notes': ('Unknown mutation: every current result is stale and every confirmed '
               'decision needs reconfirmation. Facts are kept as documented.',)},
)
BY_MUTATION = {m['mutation']: m for m in MUTATIONS}
DATASET_MUTATIONS = ('dataset', 'case')

# The table of a regression study (same row numbers for the same mutations). Its third
# decision is ``model_choice`` and its evaluation slot is ``evaluate.regression``, listed
# under ``re_policy`` (the effect key of evaluations computed from stored predictions).
# Row 13 is new: changing the model choice reuses the evaluation and refits nothing.
# Rows 5 and 6 (policy rules) do not exist in a regression study.
REGRESSION_MUTATIONS: tuple[dict, ...] = (
    {'row': 1, 'mutation': 'prediction_time', 'refit': ('fit.linear',), 're_eda': (),
     're_policy': ('evaluate.regression',), 'recompute': (),
     'reconfirm': ('feature_availability', 'model_choice', 'conclusion'),
     'blocked_until': ('feature_availability',),
     'notes': ('The linear refit waits until feature availability is confirmed again.',)},
    {'row': 2, 'mutation': 'feature_availability.feature_set', 'refit': ('fit.linear',),
     're_eda': (), 're_policy': ('evaluate.regression',), 'recompute': (),
     'reconfirm': ('model_choice', 'conclusion'), 'blocked_until': (),
     'notes': ('The mean baseline uses no feature and stays current.',)},
    MUTATIONS[2],
    {'row': 4, 'mutation': 'split', 'refit': ('fit.baseline', 'fit.linear'),
     're_eda': ('*',), 're_policy': ('evaluate.regression',), 'recompute': ('split',),
     'reconfirm': ('model_choice', 'conclusion'), 'blocked_until': (),
     'notes': ('Exposure is retained: rows explored under the old split are not unseen. '
               'The split activity reports the overlap (exposure.overlap) when it runs.',)},
    {'row': 7, 'mutation': 'settings.bootstrap', 'refit': (), 're_eda': (),
     're_policy': ('evaluate.regression',), 'recompute': (),
     'reconfirm': ('model_choice', 'conclusion'), 'blocked_until': (), 'scope': 'intervals',
     'notes': ('Only the intervals are recomputed; point estimates do not change.',)},
    MUTATIONS[7], MUTATIONS[8], MUTATIONS[9], MUTATIONS[10], MUTATIONS[11],
    {'row': 13, 'mutation': 'model_choice', 'refit': (), 're_eda': (), 're_policy': (),
     'recompute': (), 'reconfirm': ('conclusion',), 'blocked_until': (),
     'notes': ('No refit and no new evaluation: the stored predictions and the current '
               'evaluation are reused. The previous model choice is superseded.',)},
    {'row': 14, 'mutation': 'preprocessing', 'refit': ('fit.linear',), 're_eda': (),
     're_policy': ('evaluate.regression',), 'recompute': (),
     'reconfirm': ('model_choice', 'conclusion'), 'blocked_until': (),
     'notes': ('The mean baseline uses no feature and stays current; the exploration is '
               'unchanged.',)},
    BY_MUTATION['preprocessing.motivation'], BY_MUTATION['success_criterion'],
    {'row': 18, 'mutation': 'success_criterion.selection', 'refit': (), 're_eda': (),
     're_policy': ('evaluate.regression',), 'recompute': (),
     'reconfirm': ('model_choice', 'conclusion'), 'blocked_until': (),
     'notes': BY_MUTATION['success_criterion.selection']['notes']},
    {'row': 17, 'mutation': 'model_variant', 'refit': ('fit.variant',), 're_eda': (),
     're_policy': ('evaluate.regression',), 'recompute': (),
     'reconfirm': ('model_choice', 'conclusion'), 'blocked_until': (),
     'notes': BY_MUTATION['model_variant']['notes']},
    BY_MUTATION['unknown'],
)
REGRESSION_BY_MUTATION = {m['mutation']: m for m in REGRESSION_MUTATIONS}
MUTATIONS_BY_TASK = {st.BINARY: MUTATIONS, st.REGRESSION: REGRESSION_MUTATIONS}
BY_MUTATION_BY_TASK = {st.BINARY: BY_MUTATION, st.REGRESSION: REGRESSION_BY_MUTATION}


def mutations(state: Mapping | str | None = None) -> tuple[dict, ...]:
    """The dependency table of a study's task (plan §3.7)."""
    return MUTATIONS_BY_TASK[st.task_of(state)]


canonical_rule = rec.canonical_rule


def parse_policy(value: Any) -> tuple[str, float] | None:
    """``("threshold", t)`` or ``("capacity", k)`` from ``"threshold:0.3"`` /
    ``"capacity:100"`` (WP-B1: or ``"capacity:100@fit.variant"``, the rule of the variant);
    None when the value is not a policy (:func:`mlkit.study.records.canonical_rule` is the
    grammar of the rule)."""
    return rec.parse_rule(rec.policy_rule(value))


def feature_set(value: Any) -> frozenset | None:
    """Features used by a model under an availability decision (None if not a mapping)."""
    if not isinstance(value, Mapping):
        return None
    return frozenset(f for f, v in value.items() if v in USABLE_AVAILABILITY)


def _kind(slot: str) -> str:
    if slot.startswith('fit.'):
        return 'refit'
    if slot.startswith('eda.'):
        return 're_eda'
    if slot.startswith('policy.') or slot.startswith('evaluate.'):
        return 're_policy'
    return 'recompute'


def classify(decision_id: str, old: Any, new: Any) -> str:
    """The :data:`MUTATIONS` id of a change of ``decision_id`` from ``old`` to ``new``."""
    if decision_id in DATASET_MUTATIONS:
        return 'dataset'
    if decision_id == 'prediction_time':
        return 'prediction_time'
    if decision_id == 'feature_availability':
        before, after = feature_set(old), feature_set(new)
        if before is None or after is None:
            return 'unknown'
        return ('feature_availability.feature_set' if before != after
                else 'feature_availability.wording')
    if decision_id == 'split':
        return 'split'
    if decision_id == 'policy':
        before, after = parse_policy(old), parse_policy(new)
        if before is None or after is None:
            return 'unknown'
        if rec.policy_model(old) != rec.policy_model(new):
            # WP-B1: the rule moves to the other model (candidate or variant): no refit, the
            # stored predictions of both are reused, as for a new rule type.
            return 'policy.rule_type'
        return 'policy.parameter' if before[0] == after[0] else 'policy.rule_type'
    if decision_id == 'model_choice':
        return 'model_choice' if isinstance(old, str) and isinstance(new, str) else 'unknown'
    if decision_id == 'preprocessing':
        from . import governance
        before, after = governance.parameters(old), governance.parameters(new)
        if before is None or after is None:
            return 'unknown'
        return ('preprocessing' if rec.canonical(before) != rec.canonical(after)
                else 'preprocessing.motivation')
    if decision_id == 'success_criterion':
        if not isinstance(old, Mapping) or not isinstance(new, Mapping):
            return 'unknown'
        return ('success_criterion.selection'
                if rec.canonical(old.get('selection')) != rec.canonical(new.get('selection'))
                or old.get('metric') != new.get('metric') else 'success_criterion')
    if decision_id == 'model_variant':
        return 'model_variant' if isinstance(old, Mapping) and isinstance(new, Mapping) \
            else 'unknown'
    if decision_id in ('settings.bootstrap', 'usage_label', 'eda_added', 'conclusion',
                       'code_fingerprint'):
        return decision_id
    return 'unknown'


def _expand(names, kind: str, old_state: Mapping) -> list[str]:
    out: list[str] = []
    for name in names:
        if name == '*':
            pool = list(old_state['current']) + list(st.activity_slots(old_state))
            out += [s for s in pool if _kind(s) == kind]
        else:
            out.append(name)
    return sorted(set(out))


def no_effects(mutation: str, reason: str) -> dict:
    return {**{k: [] for k in EFFECT_KEYS}, 'mutation': mutation, 'row': None,
            'reason': reason, 'recompute': [], 'blocked_until': [], 'scope': None,
            'notes': []}


def effects(old_state: Mapping, decision_id: str, old: Any, new: Any) -> dict:
    """What a confirmed change of ``decision_id`` from ``old`` to ``new`` invalidates.

    ``old`` is the previously confirmed value (``None`` for a first confirmation, which
    has no effect). For ``code_fingerprint``, ``old`` and ``new`` are
    ``{"activity", "fingerprint"}``. Pure: ``old_state`` is only read.
    """
    return effects_at(old_state, decision_id, old, new)


def effects_at(old_state: Mapping, decision_id: str, old: Any, new: Any,
               diag_rule: str | None = None) -> dict:
    """:func:`effects`, with ``diag_rule`` (v0.3, WP-A, R34): the rule the current binary
    diagnostics were computed at, when the caller read it from the registry. Pure."""
    out = _diagnostics_follow_the_rule(old_state, decision_id, old, new,
                                       _effects(old_state, decision_id, old, new),
                                       diag_rule=diag_rule)
    out = _diagnostics_follow_the_variants(old_state, decision_id, out)
    if out['mutation'] == 'success_criterion.selection':
        variants = trials.variants_of(trials.confirmed_value(old_state))
        tuned = [trials.variant_slot(i + 1) for i, variant in enumerate(variants)
                 if variant.get('kind') in ('tuned', 'family')]
        out['refit'] = sorted(set(out['refit']) | set(tuned))
        diagnostics = [s for s in DIAG_SLOTS if s in old_state.get('current', {})]
        out['recompute'] = sorted(set(out['recompute']) | set(diagnostics))
        out['re_chart'] = sorted(set(out['refit'] + out['re_policy'] + out['recompute']))
    return out


DIAG_SLOTS = ('diag.binary', 'diag.regression')


def _diagnostics_follow_the_variants(old_state: Mapping, decision_id: str, out: dict) -> dict:
    """v0.3 (WP-F1, R28): the development diagnostics describe the candidate and the
    variants the junior named; a confirmed variant decision that names other variants (its
    first confirmation included) makes them stale, so they are run again once the variants
    are fitted. A question reworded changes no variant and keeps them current."""
    if decision_id != st.MODEL_VARIANT or out['mutation'] == 'unchanged_value':
        return out
    slots = [s for s in DIAG_SLOTS if s in old_state.get('current', {})]
    if not slots:
        return out
    out['recompute'] = sorted(set(out['recompute']) | set(slots))
    out['re_chart'] = sorted(set(out['re_chart']) | set(slots))
    out['notes'] = list(out['notes']) + ['The diagnostics compare the candidate with the '
                                         'variants: they are run again once the variants are '
                                         'fitted.']
    return out


# WP-B4: the binary diagnostics are computed at one rule (the adopted one when there is one).
DIAG_BINARY_SLOT = 'diag.binary'


def _diagnostics_follow_the_rule(old_state: Mapping, decision_id: str, old: Any, new: Any,
                                 out: dict, *, diag_rule: str | None = None) -> dict:
    """A policy confirmed with another rule than the one the current binary diagnostics
    were computed at makes them stale. v0.3 (WP-A, R34): the diagnostics are keyed on the
    rule they were computed at (``diag_rule``): adopting that same rule, a first adoption
    included (the scenario's share, a proposed rule), keeps them current. Without
    ``diag_rule``, the rule is taken to be the previously adopted one."""
    if decision_id != 'policy' or DIAG_BINARY_SLOT not in old_state.get('current', {}):
        return out
    computed_at = rec.canonical_rule(diag_rule) if diag_rule is not None else (
        rec.policy_rule(old) if old is not None else None)
    if computed_at is not None and computed_at == rec.policy_rule(new):
        return out
    if DIAG_BINARY_SLOT not in out['recompute']:
        out['recompute'] = sorted(set(out['recompute']) | {DIAG_BINARY_SLOT})
        out['re_chart'] = sorted(set(out['re_chart']) | {DIAG_BINARY_SLOT})
        out['notes'] = list(out['notes']) + ['The diagnostics are computed at the adopted rule: '
                                             'they are run again at the new one.']
    return out


def _effects(old_state: Mapping, decision_id: str, old: Any, new: Any) -> dict:
    decisions = st.decision_ids(old_state)
    if old is None and decision_id in decisions:
        return no_effects('first_confirmation', f'{decision_id} confirmed for the first time')
    if decision_id in decisions and rec.canonical(old) == rec.canonical(new):
        return no_effects('unchanged_value', f'{decision_id} confirmed again with the same value')
    if decision_id == st.MODEL_VARIANT and isinstance(old, Mapping) \
            and isinstance(new, Mapping) \
            and [trials.spec_key(v) for v in trials.variants_of(old)] \
            == [trials.spec_key(v) for v in trials.variants_of(new)]:
        # v0.3 (WP-F1): the same variants (a v0.2b value restated as a list, or a question
        # reworded): no model changes.
        return no_effects('unchanged_value', 'model_variant confirmed again with the same '
                                             'variants')
    mutation = classify(decision_id, old, new)
    table = BY_MUTATION_BY_TASK[st.task_of(old_state)]
    spec = table.get(mutation, table['unknown'])
    if mutation not in table:
        mutation = 'unknown'
    if spec.get('refusal'):
        raise StudyError(spec['refusal'], 'The dataset or case changed: recorded row keys and '
                                          'results no longer refer to these bytes. Start a new '
                                          'study on the new data.',
                         details={'mutation': decision_id, 'old': old, 'new': new})
    out = _table_effects(old_state, decision_id, mutation, spec, new)
    if mutation == 'model_variant':
        # v0.3 (WP-F1): only the variants whose model changed (or that are no longer named)
        # are fitted again; a variant added is fitted for the first time.
        out['refit'] = trials.changed_slots(old, new)
        out['re_chart'] = sorted(set(out['refit'] + out['re_eda'] + out['re_policy']
                                     + out['recompute']))
    return out


def _table_effects(old_state: Mapping, decision_id: str, mutation: str, spec: Mapping,
                   new: Any = None) -> dict:
    """The effects of the table row ``spec`` (shared by :func:`effects` and
    :func:`effects_for_mutation`). ``new`` is read only for ``code_fingerprint``."""
    decisions = st.decision_ids(old_state)
    reason = (f'{decision_id} changed (§3.7 row {spec["row"]}: {mutation})'
              if mutation != 'unknown' else
              f'unknown mutation of {decision_id}: everything is stale')
    out = {'refit': _expand(spec['refit'], 'refit', old_state),
           're_eda': _expand(spec['re_eda'], 're_eda', old_state),
           're_policy': _expand(spec['re_policy'], 're_policy', old_state),
           'recompute': _expand(spec['recompute'], 'recompute', old_state)}
    if mutation == 'code_fingerprint':
        activity = (new or {}).get('activity') if isinstance(new, Mapping) else None
        if not activity:
            raise StudyError('invalid_value', 'A code_fingerprint change names its activity.')
        # Every slot holding a result of that activity (eda.rate_by has one per column).
        slots = sorted(s for s in old_state['current']
                       if s == activity or s.startswith(activity + ':'))
        out[_kind(activity)] = slots or [activity]
        reason = f'code of activity {activity} changed (§3.7 row 11)'
    if spec['reconfirm'] == ('*',):
        reconfirm = [d for d in decisions if d != decision_id]
    else:
        reconfirm = [d for d in spec['reconfirm'] if d != decision_id]
    # WP-B1: the opening of the final test is a one-time act; it is never asked again (a
    # later change is shown as made after the final test instead).
    reconfirm = [d for d in reconfirm if d != st.FINAL_TEST]
    if st.has_wp_b1_decisions(old_state) and mutation in VARIANT_REFITS:
        # The variant is the candidate with one change: what refits the candidate refits it
        # (v0.3, WP-F1: every variant).
        named = [s for s in trials.VARIANT_SLOTS[1:] if s in old_state.get('current', {})]
        out['refit'] = sorted(set(out['refit']) | {VARIANT_SLOT} | set(named))
    explain = list(spec.get('re_explain', ())) + reconfirm
    if decision_id in decisions and decision_id not in explain:
        explain.insert(0, decision_id)
    out.update(
        re_chart=sorted(set(out['refit'] + out['re_eda'] + out['re_policy'] + out['recompute'])),
        re_explain=list(dict.fromkeys(explain)), reconfirm=reconfirm, mutation=mutation,
        row=spec['row'], reason=reason, blocked_until=list(spec['blocked_until']),
        scope=spec.get('scope'), notes=list(spec['notes']))
    return out


VARIANT_SLOT = 'fit.variant'
# The mutations that refit the candidate model, so the variant too (WP-B1).
VARIANT_REFITS = ('prediction_time', 'feature_availability.feature_set', 'preprocessing')


# The decision a row of the table changes (advanced companion, CLI-CONTRACT-COMPANION §5).
DECISION_OF_MUTATION = {'prediction_time': 'prediction_time',
                        'feature_availability.feature_set': 'feature_availability',
                        'feature_availability.wording': 'feature_availability',
                        'split': 'split', 'policy.parameter': 'policy',
                        'policy.rule_type': 'policy', 'model_choice': 'model_choice',
                        'preprocessing': 'preprocessing',
                        'success_criterion': 'success_criterion',
                        'success_criterion.selection': 'success_criterion',
                        # WP-B1.
                        'model_variant': 'model_variant'}
# The rows whose mutation can change a confirmed decision, by task (CC §5 ``impacts``):
# rows 1 to 6 for a binary study, rows 1 to 4 and 13 for a regression study.
DECISION_MUTATIONS = {
    st.BINARY: ('prediction_time', 'feature_availability.feature_set',
                'feature_availability.wording', 'split', 'policy.parameter',
                'policy.rule_type', 'model_choice', 'preprocessing', 'success_criterion',
                'model_variant'),
    st.REGRESSION: ('prediction_time', 'feature_availability.feature_set',
                    'feature_availability.wording', 'split', 'model_choice', 'preprocessing',
                    'success_criterion', 'model_variant'),
}


def effects_for_mutation(state: Mapping, mutation: str, store=None) -> dict:
    """What a confirmed change of the kind ``mutation`` would invalidate **now**, without
    old and new values (CLI-CONTRACT-COMPANION §5, the ``impacts`` of ``evidence``).

    Pure: the effects of the table row are applied, with lineage propagation when
    ``store`` is given (anything :func:`mlkit.study.registry.get` can read: ``home`` and
    ``read_blob``), to a deep copy of ``state``; ``state`` itself is never changed.

    Returns ``{mutation, row, decision_id, reason, stale_results, stale_slots, kept_slots,
    refit, reconfirm, notes, effects}``: ``stale_slots`` are the slots whose current result
    would become stale, ``kept_slots`` the slots holding a result that is current (not marked
    stale) and would stay so, ``reconfirm`` the confirmed decisions that would need the
    junior's words again. A mutation outside the study's table, or the dataset row (a
    refusal, not an invalidation), is ``invalid_arguments``.
    """
    table = BY_MUTATION_BY_TASK[st.task_of(state)]
    spec = table.get(mutation)
    if spec is None or mutation == 'unknown' or spec.get('refusal'):
        raise StudyError('invalid_arguments',
                         f'{mutation!r} is not a decision mutation of this study.',
                         details={'mutations': list(DECISION_MUTATIONS[st.task_of(state)])})
    decision_id = DECISION_OF_MUTATION[mutation]
    work = copy.deepcopy(dict(state))
    eff = _table_effects(work, decision_id, mutation, spec)
    record = apply_effects(work, eff, revision=state['revision'], decision_id=decision_id,
                           store=store)
    stale = set(record['stale_slots'])
    kept = [slot for slot, rid in sorted(state['current'].items())
            if rid not in state['stale'] and slot not in stale]
    return {'mutation': mutation, 'row': spec['row'], 'decision_id': decision_id,
            'reason': eff['reason'], 'stale_results': list(record['stale_results']),
            'stale_slots': list(record['stale_slots']), 'kept_slots': kept,
            'refit': list(eff['refit']), 'reconfirm': list(record['reconfirm_required']),
            'notes': list(eff['notes']), 'effects': eff}


def _lineage_map(store, rids) -> dict[str, set]:
    """Ancestors of each id (an unreadable entry gets ``None``: treated as stale)."""
    from . import registry   # writer-side module; never imported by read.py or view.py
    out = {}
    for rid in rids:
        try:
            # The inputs a result's values depend on: history roles (the split a new
            # split replaced) are not inputs, so they never make a result stale.
            seen: set = set()
            frontier = rec.upstream(registry.get(store, rid), history=False)
            while frontier:
                parent = frontier.pop()
                if parent not in seen:
                    seen.add(parent)
                    frontier += rec.upstream(registry.get(store, parent), history=False)
            out[rid] = seen
        except StudyError:
            out[rid] = None
    return out


def apply_effects(state: dict, eff: Mapping, *, revision: int, decision_id: str,
                  store=None, previous: Mapping | None = None, seeds=(), keep=()) -> dict:
    """Apply ``eff`` to ``state`` in memory and append the invalidation record.

    * The current results of every listed slot become stale with the reason.
    * With ``store``, every other current result whose registry lineage includes a
      stale result becomes stale too (downstream propagation).
    * ``seeds`` are result ids that no longer hold (a replaced result): every current
      result computed from one of them becomes stale too; ``keep`` (the result that
      replaced it) never does.
    * Each confirmed decision in ``reconfirm`` becomes ``reconfirm_required``; its
      previous value and confirmation stay visible.
    * A policy confirmation does not mark its own evaluation stale: a current
      evaluation of the new rule is a precondition of that confirmation.

    Returns the invalidation record (also appended to ``state['invalidations']``).
    """
    slots = list(eff['refit']) + list(eff['re_eda']) + list(eff['re_policy']) \
        + list(eff.get('recompute', []))
    if decision_id == 'policy':
        slots = [s for s in slots if not s.startswith('policy.')]
    reason = eff['reason']
    stale: list[str] = []
    for slot in slots:
        rid = state['current'].get(slot)
        if rid and rid not in state['stale'] and rid not in stale:
            stale.append(rid)
    seeds = [r for r in seeds if r]
    if store is not None and (stale or seeds):
        others = sorted(r for r in set(state['current'].values())
                        if r not in stale and r not in state['stale'] and r not in seeds
                        and r not in keep)
        ancestors = _lineage_map(store, others)
        changed = True
        while changed:
            changed = False
            for rid in others:
                if rid in stale:
                    continue
                parents = ancestors[rid]
                if parents is None or parents & (set(stale) | set(seeds)):
                    stale.append(rid)
                    changed = True
    for rid in stale:
        state['stale'][rid] = {'reason': reason, 'since': revision}
    reconfirmed = []
    for d in eff['reconfirm']:
        if d == st.FINAL_TEST:
            continue        # WP-B1: the opening is never asked again
        decision = state['decisions'][d]
        if decision['status'] == 'confirmed':
            decision.update(status='reconfirm_required', reason=reason)
            reconfirmed.append(d)
    record = {'revision': revision, 'decision_id': decision_id, 'mutation': eff['mutation'],
              'row': eff['row'], 'reason': reason, 'stale_results': stale,
              'stale_slots': sorted(s for s, r in state['current'].items() if r in stale),
              'reconfirm_required': reconfirmed,
              'effects': {k: copy.deepcopy(eff[k]) for k in (*EFFECT_KEYS, *META_KEYS) if k in eff},
              'previous': copy.deepcopy(previous) if previous is not None else None}
    if eff['mutation'] not in QUIET_MUTATIONS or stale or reconfirmed:
        state['invalidations'].append(record)
    return record


# Mutations recorded only when they invalidate something.
QUIET_MUTATIONS = ('first_confirmation', 'unchanged_value', 'result_replaced', 'hold_added')


def dependents(state: Mapping, decision_id: str) -> list[str]:
    """The decisions that rest on ``decision_id`` (its ``depends_on`` closure, reversed),
    in plan order: the conclusion rests on every other decision."""
    ids = st.decision_ids(state)
    out: set[str] = set()
    frontier = [decision_id]
    while frontier:
        current = frontier.pop()
        for d in ids:
            if d not in out and d != decision_id and current in st.depends_on(state, d):
                out.add(d)
                frontier.append(d)
    return [d for d in ids if d in out]


CONCLUSION = 'conclusion'


def outdates_conclusion(state: Mapping, decision_id: str, *, was_confirmed: bool, old: Any,
                        new: Any, old_basis: str | None, new_basis: str) -> str | None:
    """Why confirming ``decision_id`` makes a confirmed conclusion outdated (D2), or None.

    The conclusion summarizes every decision it rests on (its ``depends_on``): their
    values and who decided them (its credit line). A confirmation made after the
    conclusion was confirmed outdates it when it changes the decision's status (a policy
    adopted later, a decision confirmed again after a reconfirmation request), its value,
    or its basis (a delegated default confirmed again in the junior's own words). The
    dependency table already covers most value changes; this rule also covers first
    confirmations and basis changes, which change no result."""
    if decision_id == CONCLUSION or CONCLUSION not in st.decision_ids(state) \
            or decision_id not in st.depends_on(state, CONCLUSION) \
            or state['decisions'][CONCLUSION]['status'] != 'confirmed':
        return None
    if not was_confirmed:
        what = 'it was confirmed after the conclusion'
    elif rec.canonical(old) != rec.canonical(new):
        what = 'its value changed after the conclusion was confirmed'
    elif st.basis_class(old_basis) != st.basis_class(new_basis):
        # ADR 0005: ``explicit``, ``endorsed`` and ``restated`` are all the junior's own
        # words; only a change between them and a delegation changes the credit line.
        what = (f'it was confirmed again with basis {new_basis} (was {old_basis}) after the '
                'conclusion was confirmed')
    else:
        return None
    return f'the {decision_id} the conclusion summarizes changed: {what}'


def apply_hold(state: dict, decision_id: str, note_id: str, *, revision: int) -> dict | None:
    """A hold added to an already confirmed decision (post-v0.1 fixes, D1).

    The junior's condition withdraws the agreement they gave: the decision becomes
    ``reconfirm_required`` (its value and confirmation stay visible), and so does every
    confirmed decision that rests on it (:func:`dependents`; the conclusion rests on all
    of them). No result is invalidated: the value did not change. The invalidation is
    recorded with mutation ``hold_added`` and ``row`` null. Returns the record, or None
    when the decision was not confirmed (a hold on an open decision changes no status)."""
    if state['decisions'][decision_id]['status'] != 'confirmed':
        return None
    reason = (f'the junior put the {decision_id} on hold in their own words (note {note_id}) '
              f'after it was confirmed')
    eff = {**no_effects('hold_added', reason),
           'reconfirm': [decision_id] + dependents(state, decision_id),
           're_explain': [decision_id], 'scope': 'hold',
           'notes': ['The value is kept; the decision and the decisions resting on it need the '
                     "junior's words again once the hold is resolved or withdrawn."]}
    return apply_effects(state, eff, revision=revision, decision_id=decision_id)
# Decisions resting on the figures of a slot's result: an adopted policy and the
# conclusion were confirmed on evaluations computed from the split and the fits.
RESTS_ON = {'split': ('policy', 'conclusion'), 'fit.baseline': ('policy', 'conclusion'),
            'fit.logistic': ('policy', 'conclusion'),
            # WP-B1: the choice compares the variant too (v0.3, WP-F1: every variant).
            'fit.variant': ('policy', 'conclusion'), 'fit.variant:2': ('policy', 'conclusion'),
            'fit.variant:3': ('policy', 'conclusion')}
# In a regression study the model choice and the conclusion rest on the split and the fits.
REGRESSION_RESTS_ON = {'split': ('model_choice', 'conclusion'),
                       'fit.baseline': ('model_choice', 'conclusion'),
                       'fit.linear': ('model_choice', 'conclusion'),
                       'fit.variant': ('model_choice', 'conclusion'),
                       'fit.variant:2': ('model_choice', 'conclusion'),
                       'fit.variant:3': ('model_choice', 'conclusion')}
RESTS_ON_BY_TASK = {st.BINARY: RESTS_ON, st.REGRESSION: REGRESSION_RESTS_ON}


def apply_replacement(state: dict, slot: str, previous: str, new: str, *, revision: int,
                      store, code_changed: bool = False) -> dict | None:
    """A new result replaced ``previous`` in ``slot`` (inside ``run.promote``).

    Every current result computed from ``previous`` (registry lineage) becomes stale,
    and the decisions that rest on the slot (:data:`RESTS_ON`) need reconfirmation:
    the evaluation an adopted policy was confirmed on no longer describes the current
    models. The invalidation is recorded with mutation ``result_replaced``,
    ``decision_id`` the slot, and row 11 when the activity's code changed (else
    ``None``). Returns the record, or None when ``previous`` is empty or equal to ``new``.
    """
    if not previous or previous == new:
        return None
    reason = (f'the result of {slot} was replaced ({previous[:12]} by {new[:12]})'
              + ('; its code changed (§3.7 row 11)' if code_changed else ''))
    eff = {**no_effects('result_replaced', reason),
           'row': 11 if code_changed else None,
           'reconfirm': list(RESTS_ON_BY_TASK[st.task_of(state)].get(slot, ())),
           'scope': 'downstream',
           'notes': ['Results computed from the replaced result are stale; decisions confirmed '
                     "on them need the junior's words again."]}
    return apply_effects(state, eff, revision=revision, decision_id=slot, store=store,
                         seeds=[previous], keep=[new])
