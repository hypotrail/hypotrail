"""``hypotrail decisions``: every decision, proposal, confirmation, and reconfirmation.

    hypotrail decisions --study DIR [--json]

CLI-CONTRACT-COMPANION §2 (C2), payload ``hypotrail.decisions/1``. Read-only (R1-R5): it
reads the state and ``revisions.jsonl`` through :mod:`mlkit.study.read`, takes no lock,
writes nothing, reads no dataset row and no clock, and imports neither pandas nor numpy.

* ``decisions``: one item per decision of the task, in plan order, with the title and
  pause of its plan step and the confirmation it holds now.
* ``proposals``: every proposal, whatever its status, oldest first, with its ``origin``
  (C9; ``null`` for a proposal recorded before C9).
* ``history``: one item per committed ``decide.confirm`` record, oldest first; ``current``
  marks the confirmation the decision holds now, ``superseded_at`` the revision of the
  next confirmation of the same decision.
* ``reconfirm_queue``: the decisions whose status is ``reconfirm_required``, with the
  confirmation they still show and the revision of the invalidation that set the status.
* ``notes``: the junior's notes, as ``view.notes``.
"""
from __future__ import annotations

import argparse
import copy

from . import commands as cmd

SCHEMA = 'hypotrail.decisions/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'task', 'decisions', 'proposals', 'history',
                'reconfirm_queue', 'notes')
DECISION_KEYS = ('decision_id', 'title', 'pause', 'step', 'status', 'value', 'depends_on',
                 'reason', 'confirmation', 'open_proposals')
PROPOSAL_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale', 'status',
                 'revision', 'created', 'closed_revision', 'closed_reason', 'origin')
HISTORY_KEYS = ('revision', 'time', 'decision_id', 'proposal_id', 'value', 'user_words', 'basis',
                'delegation_scope', 'channel', 'actor', 'current', 'superseded_at')
RECONFIRM_KEYS = ('decision_id', 'reason', 'since_revision', 'previous', 'open_proposal')
RECONFIRM_PREVIOUS_KEYS = ('value', 'user_words', 'basis', 'channel')
CONFIRM_ACTION = 'decide.confirm'


def configure(parser: argparse.ArgumentParser) -> None:
    """No arguments besides ``--study`` and ``--format``/``--json``."""
    parser.description = ('Read-only list of the decisions, proposals, confirmation history, '
                          'and reconfirmation queue (hypotrail.decisions/1).')


def _proposal_order(p: dict):
    number = str(p['proposal_id']).rsplit('_', 1)[-1]
    return (p['revision'], int(number) if number.isdigit() else 0, p['proposal_id'])


def _history(records: list[dict], state: dict) -> list[dict]:
    out = []
    for r in records:
        if r.get('action') != CONFIRM_ACTION:
            continue
        params, result = r.get('params') or {}, r.get('result') or {}
        decision_id = result.get('decision_id')
        conf = (state['decisions'].get(decision_id) or {}).get('confirmation')
        out.append({'revision': r['revision'], 'time': r.get('time'), 'decision_id': decision_id,
                    'proposal_id': result.get('proposal_id') or params.get('proposal_id'),
                    'value': copy.deepcopy(result.get('value')),
                    'user_words': result.get('user_words', params.get('user_words')),
                    'basis': result.get('basis') or params.get('basis') or 'explicit',
                    'delegation_scope': result.get('delegation_scope',
                                                   params.get('delegation_scope')),
                    'channel': result.get('channel') or params.get('channel') or 'chat',
                    'actor': result.get('actor') or params.get('actor'),
                    'current': isinstance(conf, dict) and conf.get('revision') == r['revision'],
                    'superseded_at': None})
    for i, item in enumerate(out):
        later = next((h for h in out[i + 1:] if h['decision_id'] == item['decision_id']), None)
        item['superseded_at'] = later['revision'] if later else None
    return out


def _reconfirm_queue(state: dict, view: dict, ids) -> list[dict]:
    from . import state as st

    out = []
    for d in ids:
        dec = state['decisions'][d]
        if dec['status'] != 'reconfirm_required':
            continue
        since = None
        for inv in state['invalidations']:
            if d in (inv.get('reconfirm_required') or []):
                since = inv['revision']
        conf = dec['confirmation'] or {}
        opened = sorted((p for p in st.open_proposals(state) if p['decision_id'] == d),
                        key=_proposal_order)
        out.append({'decision_id': d, 'reason': dec['reason'], 'since_revision': since,
                    'previous': {'value': copy.deepcopy(dec['value']),
                                 'user_words': conf.get('user_words'),
                                 'basis': st.confirmation_basis(conf) if conf else None,
                                 'channel': conf.get('channel')},
                    'open_proposal': opened[-1]['proposal_id'] if opened else None})
    return out


def decisions(study_dir) -> dict:
    """The ``hypotrail.decisions/1`` payload."""
    from . import read
    from . import junior
    from . import state as st
    from . import view as vw

    study = read.open(study_dir)
    state = study.state
    language = st.language_of(state)
    ids = st.decision_ids(state)
    steps = {s['decision']: s for s in st.steps(state) if s.get('decision')}
    view_decisions = vw._decisions(state)
    items = []
    for d in ids:
        v = view_decisions[d]
        step = steps.get(d) or {}
        title = step.get('title')
        items.append({'decision_id': d,
                      'title': junior.step_text(title, language) if title else title,
                      'pause': step.get('pause'),
                      'step': step.get('id'), 'status': v['status'], 'value': v['value'],
                      'depends_on': v['depends_on'], 'reason': v['reason'],
                      'confirmation': v['confirmation'], 'open_proposals': v['open_proposals']})
    proposals = [{'proposal_id': p['proposal_id'], 'decision_id': p['decision_id'],
                  'value': copy.deepcopy(p['value']),
                  'restatement': st.label_of(p, language),
                  'rationale': p['rationale'], 'status': p['status'], 'revision': p['revision'],
                  'created': p['created'], 'closed_revision': p.get('closed_revision'),
                  'closed_reason': p.get('closed_reason'),
                  'origin': copy.deepcopy(p.get('origin'))}
                 for p in sorted(state['proposals'].values(), key=_proposal_order)]
    notes = [{k: n[k] for k in vw.NOTE_VIEW_KEYS} for n in st.notes(state)]
    return {'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir),
            'revision': study.revision, 'task': st.task_of(state), 'decisions': items,
            'proposals': proposals, 'history': _history(study.revisions(0), state),
            'reconfirm_queue': _reconfirm_queue(state, view_decisions, ids), 'notes': notes}


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(decisions(args.study))
