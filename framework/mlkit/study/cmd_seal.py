"""``hypotrail seal``: write the case, set the final test aside, create the study (onboarding
Lots 2 and 3; ADR 0006 amendment of 2026-11-01; CLI-CONTRACT §20).

    hypotrail seal --expected-revision REV [--automation until_final_test|full_demo] --study DIR

Preconditions: the six answers recorded in the user's words, the ``final_test`` answer
naming the current plan, and a passing feasibility check (:func:`cmd_case.feasibility`).
Then, in this order:

1. ``case.yaml`` is written in the case folder from the profile and the answers
   (:func:`case_draft.build_case`) and loaded back (``load_case``);
2. the preparation instructions are removed (an edited file is kept and reported);
3. ``init`` runs on that case with the ``review-v1`` profile, without a ``data`` link, and
   records the deduction (the rule, its reason in both languages, the guard checks and the
   user's words accepting it) in the partition record as ``analysis_protocol.deduction``.
   The report's first chapter shows it as how the final test was set aside;
4. the brief or the context given to ``new`` is imported into the study (``brief import``).

``--automation`` (ADR 0005 amendment of 2026-10-26, R20) is the automatic mode, chosen at
the study's launch only: for a prepared study the launch is this ``seal`` (``new --data``
creates no study yet, so it refuses the flag and names this one). It is passed to ``init``
unchanged, with the same meaning and the same refusals as ``init --automation``; without it
the study has no automatic mode, and none can be added later.

There is no silent fallback: a refused ``init`` restores the preparation (its instructions
and its state) and answers with the refusal. Reliability profile ``review-v1`` is always
used: the case always holds an ``analysis_contract``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import case_draft as cd
from . import cmd_prepare as prep
from . import commands as cmd
from .errors import StudyError

SCHEMA = 'hypotrail.seal/1'


def seal(study, expected_revision: int, automation: str | None = None) -> cmd.Outcome:
    from . import case as c
    from . import cmd_brief, cmd_case, lock
    from . import state as st
    from .guard import assert_writable
    assert_writable()
    if automation is not None and automation not in st.AUTOMATION_MODES:
        raise StudyError('invalid_arguments', 'automation is one of '
                         + ', '.join(st.AUTOMATION_MODES) + '.')
    study, case_dir = prep.locate(study)
    with lock.writer_lock(study):
        record = prep.load(case_dir)
        if record['status'] != prep.PREPARING:
            raise StudyError('precondition_missing', f'The preparation is {record["status"]}.',
                             details={'reason': record['status']})
        if expected_revision != record['revision']:
            raise StudyError('stale_revision', 'The preparation changed since you read it: '
                                               'read prepare status again.',
                             details={'expected_revision': expected_revision,
                                      'current_revision': record['revision']})
        missing = [q for q in cd.QUESTIONS if q not in record['answers']]
        if missing:
            raise StudyError('precondition_missing', 'Seal once the six questions are answered '
                                                     "in the user's words.",
                             details={'reason': 'questions_missing', 'missing': missing})
        prof = prep.load_profile(case_dir)
        final = cmd_case.feasibility(case_dir, record, prof)
        if final['status'] != 'pass':
            raise StudyError('precondition_missing', 'The final test cannot be set aside: '
                                                     + '; '.join(final['problems']),
                             details={'reason': 'feasibility_failed', 'feasibility': final})
        accepted = record['answers']['final_test']
        if accepted['value']['plan'] != final['plan']:
            raise StudyError('stale_revision', 'The final test the user accepted is not the '
                                               'current one: show it again and ask.',
                             details={'reason': 'plan_changed', 'plan': final['plan']})
        document = cmd_case.case_document(case_dir, record, prof)
        case_file = case_dir / c.CASE_FILE
        case_file.write_text(cd.render(document), encoding='utf-8')
        c.load_case(case_file)
        record['status'] = prep.SEALING
        record['revision'] += 1
        record['history'].append({'revision': record['revision'], 'action': 'sealing',
                                  'time': st.now()})
        prep._write(case_dir, record)
    import json
    marker = prep._marker(study)
    written = json.loads(marker.read_text(encoding='utf-8')).get('agent_files') or {}
    agent = prep.remove_agent(study, written)
    deduction = {**final['deduction'], 'plan': final['plan'], 'words': final['words'],
                 'counts': {k: final['counts'][k] for k in
                            ('rows', 'final_rows', 'development_rows', 'fraction')},
                 'accepted': {'user_words': accepted['user_words'],
                              'time': accepted['time']}}
    try:
        out = cmd.init(case_dir, study, language=record['language'],
                       reliability_profile='review-v1', automation=automation,
                       data_link=False, deduction=deduction)
    except Exception:
        _restore(study, case_dir)
        raise
    if out.exit_code != 0:
        _restore(study, case_dir)
        return out
    marker.unlink()
    snapshot = out.payload
    revision = snapshot['revision']
    brief = record.get('brief')
    imported = None
    if brief:
        imported = cmd_brief.import_pdf(study, study / brief['file'],
                                        expected_revision=revision)
        revision = imported.payload['revision']
        snapshot['next_action'] = imported.payload['next_action']
        snapshot['brief'] = {k: imported.payload.get(k) for k in ('result', 'then')}
    with lock.writer_lock(study):
        record = prep.load(case_dir)
        record['status'] = prep.SEALED
        record['revision'] += 1
        record['sealed'] = {'time': st.now(), 'study_revision': revision,
                            'case_sha256': c.sha256_file(case_dir / c.CASE_FILE)}
        record['history'].append({'revision': record['revision'], 'action': 'sealed',
                                  'time': record['sealed']['time']})
        prep._write(case_dir, record)
    sealed = snapshot['final_test']
    if sealed.get('rows') != final['counts']['final_rows']:
        raise StudyError('integrity_error', 'The sealed final test differs from the plan the '
                                            'user accepted.',
                         details={'planned': final['counts']['final_rows'],
                                  'sealed': sealed.get('rows')})
    payload = dict(snapshot, schema=SCHEMA, command='seal', revision=revision,
                   case_file=str(case_file), deduction=deduction,
                   preparation_agent_files=agent)
    return cmd.Outcome(payload, out.exit_code)


def _restore(study: Path, case_dir: Path) -> None:
    """A refused ``init``: the preparation instructions and state come back."""
    import json
    from . import case as c
    from . import state as st
    written = prep.install_agent(study)
    marker = prep._marker(study)
    record = json.loads(marker.read_text(encoding='utf-8'))
    record['agent_files'] = written
    from .store import atomic_write_json
    atomic_write_json(marker, record)
    state = prep.load(case_dir)
    state['status'] = prep.PREPARING
    state['revision'] += 1
    state['history'].append({'revision': state['revision'], 'action': 'seal_refused',
                             'time': st.now()})
    prep._write(case_dir, state)
    (case_dir / c.CASE_FILE).unlink(missing_ok=True)


def configure(parser: argparse.ArgumentParser) -> None:
    from . import state as st
    parser.add_argument('--expected-revision', type=int, required=True,
                        help='the revision prepare status gave')
    parser.add_argument('--automation', choices=st.AUTOMATION_MODES, default=None,
                        help='the automatic mode, chosen now or never (ADR 0005): '
                             'until_final_test, or full_demo (also opens the final test, a '
                             'demonstration marked as such for good)')


def main(args: argparse.Namespace) -> cmd.Outcome:
    return seal(args.study, args.expected_revision, automation=args.automation)
