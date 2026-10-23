"""``hypotrail preview effects PROPOSAL``: the dry run of ``decide confirm``.

CLI-CONTRACT-COMPANION §3 (C3), payload ``hypotrail.preview_effects/1``. Read-only
(R1-R5). Dispatched by :mod:`mlkit.study.cmd_preview`.

It answers one question: if this open proposal were confirmed now, by words the engine
accepts, what would change? It calls the same :func:`mlkit.study.commands.confirmation_plan`
as ``decide confirm``, on the state read without the lock (a deep copy); the plan applies
the dependency-table effects to its own copy, with the store used for lineage reads only,
and the copy is discarded. So the preview cannot drift from the confirmation: at one
revision, a preview with empty ``blocked`` and an accepted confirmation give the same
``{mutation, row, reason, stale_results, stale_slots, reconfirm_required}``.

It never predicts the refusals that depend on the words or on the basis
(``missing_user_words``, ``negative_reply``, ``bare_acknowledgement``, ``unrelated_reply``,
``delegation_needs_basis``, ``not_a_delegation``, ``restatement_not_default``,
``delegation_not_given_at_this_pause``), nor ``stale_revision``. The preview assumes an
explicit confirmation.
"""
from __future__ import annotations

import copy

SCHEMA = 'hypotrail.preview_effects/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'proposal_id', 'decision_id', 'value',
                'previous', 'mutation', 'row', 'reason', 'stale_results', 'stale_slots',
                'kept_slots', 'refit', 're_eda', 're_policy', 'recompute', 'reconfirm_required',
                'supersedes_proposal', 'blocked', 'artifacts_after', 'notes', 'recorded', 'note')
PREVIOUS_KEYS = ('value', 'user_words', 'basis', 'channel', 'revision', 'proposal_id')
BLOCKED_KEYS = ('code', 'reason', 'message', 'details')
# The renders that ``after_commit`` performs; the workbench is never written.
ARTIFACTS_AFTER = {'report': 'regenerated', 'notebook': 'regenerated',
                   'editable': 'synced_if_unedited', 'workbench': 'unchanged'}
NOTE = ('Preview of a confirmation: nothing was recorded. The engine still checks the words '
        'when you confirm.')
EFFECT_LISTS = ('refit', 're_eda', 're_policy', 'recompute')


def _slot_order(state: dict):
    from . import state as st

    order = {slot: i for i, slot in enumerate(st.activity_slots(state))}
    # A per-column EDA slot follows the plan's EDA slots (it is shown with that step).
    after_eda = max((i for s, i in order.items() if s.startswith('eda.')), default=-1) + 0.5

    def key(slot: str):
        base = slot.split(':', 1)[0]
        if base in order and ':' not in slot:
            return (order[base], slot)
        return (after_eda if base.startswith('eda.') else len(order), slot)
    return key


def preview_effects(study_dir, proposal_id: str) -> dict:
    """The ``hypotrail.preview_effects/1`` payload."""
    from mlkit.reliability import CommandRefused

    from . import commands as cmd
    from . import read
    from .store import StudyStore

    study = read.open(study_dir)
    state = study.state
    proposal = state['proposals'].get(proposal_id)
    if proposal is None:
        raise CommandRefused('unknown_proposal', f'There is no proposal {proposal_id}.',
                             details={'proposal_id': proposal_id,
                                      'open_proposals': sorted(
                                          p['proposal_id'] for p in state['proposals'].values()
                                          if p['status'] == 'open')})
    if proposal['status'] != 'open':
        raise CommandRefused('proposal_not_open',
                             f'Proposal {proposal_id} is {proposal["status"]}; only an open '
                             f'proposal can be confirmed.',
                             details={'proposal_id': proposal_id, 'status': proposal['status']})
    # A store for lineage reads only (registry entries and blobs): nothing is written.
    plan = cmd.confirmation_plan(copy.deepcopy(state), StudyStore(study.study_dir), proposal_id)
    inv = plan['invalidation'] or {}
    eff = plan['effects'] or {}
    previous = None
    if plan['previous'] is not None:
        conf = plan['previous']['confirmation'] or {}
        previous = {'value': copy.deepcopy(plan['previous']['value']),
                    'user_words': conf.get('user_words'),
                    'basis': conf.get('basis') or 'explicit', 'channel': conf.get('channel'),
                    'revision': conf.get('revision'),
                    'proposal_id': plan['previous']['proposal_id']}
    stale_slots = list(inv.get('stale_slots') or [])
    kept = sorted((slot for slot in state['current']
                   if study.is_current(slot) and slot not in stale_slots),
                  key=_slot_order(state))
    return {'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir),
            'revision': study.revision, 'proposal_id': proposal_id,
            'decision_id': plan['decision_id'], 'value': copy.deepcopy(plan['value']),
            'previous': previous, 'mutation': inv.get('mutation', eff.get('mutation')),
            'row': inv.get('row', eff.get('row')), 'reason': inv.get('reason', eff.get('reason')),
            'stale_results': list(inv.get('stale_results') or []), 'stale_slots': stale_slots,
            'kept_slots': kept,
            **{k: list(eff.get(k) or []) for k in EFFECT_LISTS},
            'reconfirm_required': list(inv.get('reconfirm_required') or []),
            'supersedes_proposal': plan['supersedes_proposal'],
            'blocked': [{k: b[k] for k in BLOCKED_KEYS} for b in plan['blocked']],
            'artifacts_after': dict(ARTIFACTS_AFTER), 'notes': list(eff.get('notes') or []),
            'recorded': False, 'note': NOTE}
