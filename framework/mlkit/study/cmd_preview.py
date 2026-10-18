"""``hypotrail preview policy``: evaluate rules on persisted predictions, recording nothing.

    hypotrail preview policy --rule RULE [--rule RULE ...] [--intervals] --study DIR

The workbench slider (and later a webview) calls this to show what a threshold or a
capacity would select: "Experiment, not adopted". It reads the current fits'
validation predictions through the read-only API (:mod:`mlkit.study.read`) and
applies :func:`mlkit.study.policy.evaluate`. ``--intervals`` adds the paired
bootstrap with the study's settings.

It writes nothing: no state, registry entry, exposure record, or artefact, and it
takes no lock. In particular it records **no exposure**. The validation rows it reads
were already exposed under ``validation_model_evaluation`` when the fits scored them;
choosing a rule on them is recorded as ``validation_policy_selection`` only by
``hypotrail run policy.evaluate``, whose result is what a policy confirmation needs.
A preview is therefore never evidence and never a decision.

``warnings`` (post-v0.1 fixes, D4) holds the G.12 warnings that bear on the previewed
rules, as the view words them: ``capacity_exceeds_validation`` when a previewed capacity
is at least the number of validation rows (it selects every row), and
``small_validation_partition`` when the current split's validation partition is small.

Works under ``HYPOTRAIL_READ_ONLY=1``. Output: ``hypotrail.preview/1``.
"""
from __future__ import annotations

import argparse

from . import commands as cmd

SCHEMA = 'hypotrail.preview/1'
PAYLOAD_KEYS = ('schema', 'ok', 'study', 'revision', 'kind', 'rules', 'models', 'evaluations',
                'intervals', 'adopted', 'recorded', 'note',
                # Post-v0.1 fixes (D4): the small-data warnings that bear on these rules.
                'warnings')
FITS = ('fit.baseline', 'fit.logistic')
NOTE = ('Experiment, not adopted: nothing was recorded. To adopt a rule, run policy.evaluate '
        'with it (exposure validation_policy_selection), then propose and confirm the policy.')


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('kind', choices=('policy',))
    parser.add_argument('--rule', action='append', required=True,
                        help='threshold:t or capacity:k (repeatable)')
    parser.add_argument('--intervals', action='store_true',
                        help='add paired bootstrap intervals (study settings)')


def preview_policy(study_dir, rules, *, intervals: bool = False) -> dict:
    """The preview payload; pure reads only."""
    import gzip
    import io
    import csv

    import numpy as np

    from . import policy, read
    from .errors import StudyError

    for rule in rules:
        try:
            policy.parse_rule(rule)
        except ValueError as exc:
            raise StudyError('invalid_arguments', str(exc), details={'rule': rule}) from None
    from .records import canonical_rule
    rules = list(dict.fromkeys(canonical_rule(r) for r in rules))
    study = read.open(study_dir)
    state = study.state
    if state.get('task', 'binary') != 'binary':
        raise StudyError('unsupported_capability',
                         'preview policy applies to a binary study. A regression study compares '
                         'models by their error with run evaluate.regression.',
                         details={'command': 'preview policy', 'task': state['task']})
    missing = [{'requirement': 'result_present', 'slot': s} for s in FITS
               if state['current'].get(s) is None]
    if missing:
        raise StudyError('precondition_missing', 'Previewing a policy needs both fits.',
                         details={'missing': missing})
    models, scores, y, keys = {}, {}, None, None
    for slot in FITS:
        entry = study.current(slot)
        sha = entry['blobs'].get('predictions')
        if sha is None:
            raise StudyError('no_predictions', f'{slot} has no predictions blob.',
                             details={'result_id': entry['result_id']})
        reader = csv.reader(io.StringIO(gzip.decompress(study.blob(sha)).decode('utf-8')))
        next(reader)
        rows = list(reader)
        these = [r[0] for r in rows]
        labels = np.asarray([int(r[1]) for r in rows], dtype=float)
        if keys is not None and (these != keys or not (labels == y).all()):
            raise StudyError('integrity_error', 'The fits were not scored on the same rows.')
        keys, y = these, labels
        scores[slot] = np.asarray([float(r[2]) for r in rows])
        models[slot] = {'result_id': entry['result_id'], 'current': study.is_current(slot),
                        'stale_reason': study.stale_reason(entry['result_id'])}
    evaluations = {rule: {slot: policy.evaluate(y, scores[slot], rule) for slot in FITS}
                   for rule in rules}
    boot = None
    if intervals:
        settings = state['settings']['bootstrap']
        boot = {rule: policy.paired_bootstrap(y, scores, rule, int(settings['replicates']),
                                              int(settings['seed']),
                                              level=float(settings['level']),
                                              reference=FITS[0])
                for rule in rules}
    decision = state['decisions']['policy']
    from . import view
    warnings = []
    if study.is_current('split'):
        small = view.small_partition_warning(study.current('split')['output']['values'], True)
        if small:
            warnings.append(small)
    over = view.capacity_warning(rules, len(keys))
    if over:
        warnings.insert(0, over)
    return {'schema': SCHEMA, 'ok': True, 'study': str(study.study_dir),
            'revision': study.revision, 'kind': 'policy', 'rules': list(rules), 'models': models,
            'evaluations': evaluations, 'intervals': boot,
            'adopted': {'status': decision['status'], 'value': decision['value']},
            'recorded': False, 'note': NOTE, 'warnings': warnings}


def main(args: argparse.Namespace) -> cmd.Outcome:
    return cmd.Outcome(preview_policy(args.study, list(dict.fromkeys(args.rule)),
                                      intervals=args.intervals))
