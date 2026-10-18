"""``hypotrail preview proposal DECISION --value V``: the engine's draft of a proposal.

CLI-CONTRACT-COMPANION §4 (C4), payload ``hypotrail.proposal_draft/1``. Read-only
(R1-R5). Dispatched by :mod:`mlkit.study.cmd_preview`. The draft texts come from
``content/drafts.yaml``; a client never writes a restatement itself.

A draft exists for the decisions of :data:`DRAFT_DECISIONS` only: the policy rule of a
binary study and the model choice of a regression study. It is **proposable only from
recorded evidence**: a current, verified ``policy.evaluation`` that evaluated the rule, or
a current, verified ``evaluate.regression`` that compared the model. Otherwise the draft
says what is missing and carries no text (the companion may not run the evaluation: that
records ``validation_policy_selection``; decision CA.7).

The texts cite the evaluation's figures at their displayed precision, so ``decide
propose`` traces every number they contain to a current result
(``literal_number_in_text``). They never state a recommended default, so a delegation can
never confirm them (``restatement_not_default``).

It reads the state and one registry entry; it writes nothing, takes no lock, records no
exposure, reads no dataset row, and imports neither pandas, scikit-learn, nor scipy.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

SCHEMA = 'hypotrail.proposal_draft/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'decision_id', 'value', 'proposable',
                'missing', 'restatement', 'rationale', 'evidence', 'supersedes_proposal',
                'recorded', 'note')
DRAFT_DECISIONS = {'binary': ('policy',), 'regression': ('model_choice',)}
NOTE = 'Draft only: nothing was recorded. Proposing creates a proposal, not a decision.'
# The evaluation slot each draft rests on, and the requirement named when it is missing.
EVIDENCE_SLOTS = {'policy': 'policy.evaluation', 'model_choice': 'evaluate.regression'}
REQUIREMENTS = {'policy': 'evaluated_rule', 'model_choice': 'evaluated_model'}
NOT_DEFINED = 'not defined'
SHORT_ID = 8
_FIGURE = re.compile(r'\{\{(\w+)\}\}')
_PARAMETER = re.compile(r'(?<!\{)\{(\w+)\}(?!\})')


def short_id(rid: str) -> str:
    """The first eight characters of ``rid``, or more when those are all digits: an
    identifier with a letter is never read as a number by ``decide propose``."""
    for n in range(SHORT_ID, len(rid) + 1):
        if not rid[:n].isdigit():
            return rid[:n]
    return rid


def _refuse(code: str, message: str, **details):
    from .errors import StudyError
    return StudyError(code, message, details=details)


def _evaluated(study, decision_id: str, value: str) -> dict | None:
    """The current, verified evaluation entry that evaluated ``value``, or None."""
    from . import state as st
    from .errors import StudyError

    slot = EVIDENCE_SLOTS[decision_id]
    state = study.state
    rid = state['current'].get(slot)
    if rid is None or not st.is_current(state, slot) or not study.currency(rid)['current']:
        return None
    try:
        entry = study.result(rid)
    except StudyError as exc:
        if exc.code == 'integrity_error':
            raise
        return None
    params = entry.get('params') or {}
    listed = params.get('rules' if decision_id == 'policy' else 'models') or []
    return entry if value in [str(v) for v in listed] else None


def _texts(decision_id: str, value: str, entry: Mapping) -> tuple[str, str, list[dict]]:
    """``(restatement, rationale, figures)`` of a draft resting on ``entry``."""
    from . import cite, texts

    content = texts.load('drafts')
    values = entry['output']['values']
    if decision_id == 'policy':
        kind, _, amount = value.partition(':')      # the canonical spelling, as written
        templates = content['drafts']['policy'][kind]
        parameters = {'k' if kind == 'capacity' else 't': amount, 'rule': value}
    else:
        templates = content['drafts']['model_choice'][value]
        parameters = {'unit': values.get('unit') or ''}
    specs = content['figures'][decision_id]
    figures, shown = [], {}

    def figure(match):
        name = match.group(1)
        if name == 'rid8':
            return short_id(entry['result_id'])
        if name not in shown:
            spec = specs[name]
            segments = [str(s).format(**parameters) for s in spec['path']]
            try:
                raw = cite.resolve(values, segments)
            except KeyError:
                raw = None
            text = (cite.fmt_number(raw, spec['fmt']) if cite.is_number(raw)
                    else spec.get('undefined', NOT_DEFINED))
            shown[name] = text
            figures.append({'path': cite.format_path(segments), 'value': raw, 'shown': text})
        return shown[name]

    def fill(template: str) -> str:
        text = _FIGURE.sub(figure, template)
        text = _PARAMETER.sub(lambda m: str(parameters.get(m.group(1), m.group(0))), text)
        return re.sub(r'\s+', ' ', text).replace(' )', ')').strip()

    restatement = fill(templates['restatement'])
    rationale = fill(templates['rationale'])
    return restatement, rationale, figures


def preview_proposal(study_dir, decision_id: str, value: str) -> dict:
    """The ``hypotrail.proposal_draft/1`` payload (CLI-CONTRACT-COMPANION §4)."""
    from . import commands, read
    from . import records as rec
    from . import state as st

    study = read.open(study_dir)
    state = study.state
    task = st.task_of(state)
    if decision_id not in st.decision_ids(state):
        raise _refuse('unknown_decision', f'Decision {decision_id!r} is not part of a {task} '
                                          f'study.',
                      decisions=list(st.decision_ids(state)), task=task)
    supported = DRAFT_DECISIONS[task]
    if decision_id not in supported:
        raise _refuse('unsupported_capability',
                      f'There is no proposal draft for {decision_id}: the companion proposes '
                      f'{" or ".join(supported)} only.',
                      capability=f'a proposal draft for {decision_id}',
                      decisions=list(supported))
    commands.validate_value(state, decision_id, value)        # invalid_value
    if decision_id == 'policy':
        value = rec.canonical_rule(value) or value
    entry = _evaluated(study, decision_id, value)
    open_ids = [p['proposal_id'] for p in sorted(st.open_proposals(state),
                                                 key=lambda p: (p['revision'],
                                                                p['proposal_id']))
                if p['decision_id'] == decision_id]
    restatement = rationale = evidence = None
    missing: list[dict] = []
    if entry is None:
        missing.append({'requirement': REQUIREMENTS[decision_id], 'value': value})
    else:
        restatement, rationale, figures = _texts(decision_id, value, entry)
        evidence = {'result_id': entry['result_id'], 'activity': entry['activity'],
                    'figures': figures}
    payload: dict[str, Any] = {
        'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir), 'revision': study.revision,
        'decision_id': decision_id, 'value': value, 'proposable': entry is not None,
        'missing': missing, 'restatement': restatement, 'rationale': rationale,
        'evidence': evidence, 'supersedes_proposal': open_ids[-1] if open_ids else None,
        'recorded': False, 'note': NOTE}
    assert tuple(payload) == PAYLOAD_KEYS
    return payload
