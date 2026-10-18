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
from .errors import StudyError

EFFECT_KEYS = ('refit', 're_eda', 're_policy', 're_chart', 're_explain', 'reconfirm')
META_KEYS = ('mutation', 'row', 'reason', 'recompute', 'blocked_until', 'scope', 'notes')
USABLE_AVAILABILITY = ('available_at_prediction', 'uncertain_included')
POLICY_RULES = ('threshold', 'capacity')

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
    {'row': '*', 'mutation': 'unknown', 'refit': ('*',), 're_eda': ('*',), 're_policy': ('*',),
     'recompute': ('*',), 'reconfirm': ('*',), 'blocked_until': (),
     'notes': ('Unknown mutation: every current result is stale and every confirmed '
               'decision needs reconfirmation. Facts are kept as documented.',)},
)
BY_MUTATION = {m['mutation']: m for m in MUTATIONS}
DATASET_MUTATIONS = ('dataset', 'case')


def parse_policy(value: Any) -> tuple[str, float] | None:
    """``("threshold", t)`` or ``("capacity", k)`` from ``"threshold:0.3"`` /
    ``"capacity:100"``; None when the value is not a policy rule."""
    if not isinstance(value, str) or value.count(':') != 1:
        return None
    kind, _, number = value.partition(':')
    if kind not in POLICY_RULES:
        return None
    try:
        amount = float(number) if kind == 'threshold' else int(number)
    except ValueError:
        return None
    if kind == 'threshold' and not 0.0 <= amount <= 1.0:
        return None
    if kind == 'capacity' and amount < 1:
        return None
    return kind, amount


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
    if slot.startswith('policy.'):
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
        return 'policy.parameter' if before[0] == after[0] else 'policy.rule_type'
    if decision_id in ('settings.bootstrap', 'usage_label', 'eda_added', 'conclusion',
                       'code_fingerprint'):
        return decision_id
    return 'unknown'


def _expand(names, kind: str, old_state: Mapping) -> list[str]:
    out: list[str] = []
    for name in names:
        if name == '*':
            pool = list(old_state['current']) + list(st.ACTIVITY_SLOTS)
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
    if old is None and decision_id in st.DECISION_IDS:
        return no_effects('first_confirmation', f'{decision_id} confirmed for the first time')
    if decision_id in st.DECISION_IDS and rec.canonical(old) == rec.canonical(new):
        return no_effects('unchanged_value', f'{decision_id} confirmed again with the same value')
    mutation = classify(decision_id, old, new)
    spec = BY_MUTATION[mutation]
    if spec.get('refusal'):
        raise StudyError(spec['refusal'], 'The dataset or case changed: recorded row keys and '
                                          'results no longer refer to these bytes. Start a new '
                                          'study on the new data.',
                         details={'mutation': decision_id, 'old': old, 'new': new})
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
        out[_kind(activity)] = [activity]
        reason = f'code of activity {activity} changed (§3.7 row 11)'
    if spec['reconfirm'] == ('*',):
        reconfirm = [d for d in st.DECISION_IDS if d != decision_id]
    else:
        reconfirm = [d for d in spec['reconfirm'] if d != decision_id]
    explain = list(spec.get('re_explain', ())) + reconfirm
    if decision_id in st.DECISION_IDS and decision_id not in explain:
        explain.insert(0, decision_id)
    out.update(
        re_chart=sorted(set(out['refit'] + out['re_eda'] + out['re_policy'] + out['recompute'])),
        re_explain=list(dict.fromkeys(explain)), reconfirm=reconfirm, mutation=mutation,
        row=spec['row'], reason=reason, blocked_until=list(spec['blocked_until']),
        scope=spec.get('scope'), notes=list(spec['notes']))
    return out


def _lineage_map(store, rids) -> dict[str, set]:
    """Ancestors of each id (an unreadable entry gets ``None``: treated as stale)."""
    from . import registry   # writer-side module; never imported by read.py or view.py
    out = {}
    for rid in rids:
        try:
            out[rid] = set(registry.lineage(store, rid))
        except StudyError:
            out[rid] = None
    return out


def apply_effects(state: dict, eff: Mapping, *, revision: int, decision_id: str,
                  store=None, previous: Mapping | None = None) -> dict:
    """Apply ``eff`` to ``state`` in memory and append the invalidation record.

    * The current results of every listed slot become stale with the reason.
    * With ``store``, every other current result whose registry lineage includes a
      stale result becomes stale too (downstream propagation).
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
    if store is not None and stale:
        others = [r for r in set(state['current'].values())
                  if r not in stale and r not in state['stale']]
        ancestors = _lineage_map(store, others)
        changed = True
        while changed:
            changed = False
            for rid in others:
                if rid in stale:
                    continue
                parents = ancestors[rid]
                if parents is None or parents & set(stale):
                    stale.append(rid)
                    changed = True
    for rid in stale:
        state['stale'][rid] = {'reason': reason, 'since': revision}
    reconfirmed = []
    for d in eff['reconfirm']:
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
    if eff['mutation'] not in ('first_confirmation', 'unchanged_value') or stale or reconfirmed:
        state['invalidations'].append(record)
    return record
