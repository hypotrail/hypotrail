"""Context-bound references to immutable registry values (reliability roadmap J5).

The reference repeats context for reviewability, but registry lineage remains authoritative:
caller-supplied labels never manufacture evidence.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import cite, records as rec
from .errors import StudyError

SCHEMA = 'hypotrail.evidence_ref/1'
KEYS = ('schema', 'result_id', 'path', 'dataset_sha256', 'partition',
        'population_digest', 'metric', 'model', 'rule', 'unit')
OPTIONAL_KEYS = ('source_result_ids',)
FRACTION_METRICS = frozenset({'precision', 'recall', 'specificity', 'rate', 'roc_auc',
                              'average_precision', 'brier_score'})


def _error(code: str, message: str, **details) -> StudyError:
    return StudyError(code, message, details=details)


def _entry(study, result_id: str) -> dict:
    try:
        return study.result(result_id)
    except StudyError as exc:
        if exc.code in ('unknown_result', 'result_not_found'):
            raise _error('unknown_evidence_result', f'Unknown evidence result {result_id}.',
                         result_id=result_id) from None
        raise _error('evidence_integrity_error',
                     f'Evidence result {result_id} failed its integrity check.',
                     result_id=result_id, cause=exc.code) from None


def _population_digest(study, entry: Mapping) -> str | None:
    values = entry['output']['values']
    if isinstance(values, Mapping) and isinstance(values.get('population_digest'), str):
        return values['population_digest']
    exposure_id = entry.get('exposure_id')
    record = next((x for x in study.exposure_records()
                   if x.get('exposure_id') == exposure_id), None)
    if record and isinstance(record.get('row_keys'), str):
        keys = rec.parse_row_keys(study.blob(record['row_keys']))
        return rec.sha256_hex(rec.canonical(keys))
    return None


def _path_context(entry: Mapping, path: str) -> dict:
    segments = cite.parse_path(path)
    metric = segments[-1] if segments and not segments[-1].startswith('@') else None
    rule = None
    model = None
    for index, segment in enumerate(segments[:-1]):
        if segment == 'rules' and index + 1 < len(segments):
            rule = rec.canonical_rule(segments[index + 1]) or segments[index + 1]
        if segment in ('models', 'comparisons') and index + 1 < len(segments):
            model = segments[index + 1]
    params = entry.get('params') or {}
    if model is None and isinstance(params.get('model'), str):
        model = params['model']
    if rule is None and isinstance(params.get('rule'), str):
        rule = rec.canonical_rule(params['rule']) or params['rule']
    values = entry['output']['values']
    unit = (values.get('unit') if isinstance(values, Mapping) else None)
    if metric in FRACTION_METRICS or metric in ('low', 'high', 'delta'):
        unit = 'fraction'
    elif metric in ('n', 'n_rows', 'n_positive', 'selected', 'true_positive'):
        unit = 'count'
    return {'metric': metric, 'model': model, 'rule': rule, 'unit': unit}


def make(study, result_id: str, path: str, *, historical: bool = False,
         metric: str | None = None, model: str | None = None, rule: str | None = None,
         unit: str | None = None, source_result_ids: list[str] | None = None) -> dict:
    """Create and verify a reference bound to ``result_id`` (never to a mutable slot)."""
    entry = _entry(study, result_id)
    current = study.currency(result_id)
    if not current['current'] and not historical:
        raise _error('evidence_not_current', 'Evidence is unavailable as current evidence.',
                     result_id=result_id, reason=current['reason'])
    try:
        cite.resolve(entry['output']['values'], cite.parse_path(path), n_rows=entry['n_rows'])
    except (KeyError, StudyError):
        raise _error('invalid_evidence_path', f'Result {result_id} has no value at {path!r}.',
                     result_id=result_id, path=path) from None
    derived = _path_context(entry, path)
    assertions = {'metric': metric, 'model': model, 'rule': rule, 'unit': unit}
    for key, supplied in assertions.items():
        if supplied is not None and supplied != derived[key]:
            raise _error('evidence_context_mismatch',
                         f'{key} does not match registry lineage.', field=key,
                         supplied=supplied, derived=derived[key], result_id=result_id)
    ref = {
        'schema': SCHEMA, 'result_id': result_id, 'path': path,
        'dataset_sha256': study.state['dataset']['sha256'],
        'partition': entry['partition'],
        'population_digest': _population_digest(study, entry),
        **derived,
    }
    if source_result_ids is not None:
        lineage = set((entry.get('inputs') or {}).get('results', {}).values())
        if set(source_result_ids) != lineage:
            raise _error('evidence_context_mismatch',
                         'Comparison source result IDs do not match registry lineage.',
                         field='source_result_ids', supplied=source_result_ids,
                         derived=sorted(lineage))
        ref['source_result_ids'] = list(source_result_ids)
    return ref


def resolve(study, reference: Mapping, *, historical: bool = False,
            context: Mapping[str, Any] | None = None) -> Any:
    """Validate ``reference`` against registry lineage and return its exact value."""
    if not isinstance(reference, Mapping) or reference.get('schema') != SCHEMA \
            or set(reference) - set(KEYS + OPTIONAL_KEYS) or any(k not in reference for k in KEYS):
        raise _error('invalid_evidence_ref', f'Evidence reference must follow {SCHEMA}.')
    rebuilt = make(study, reference['result_id'], reference['path'], historical=historical,
                   source_result_ids=reference.get('source_result_ids'))
    for key in KEYS[2:]:
        if reference[key] != rebuilt[key]:
            raise _error('evidence_context_mismatch',
                         f'{key} does not match registry lineage.', field=key,
                         supplied=reference[key], derived=rebuilt[key],
                         result_id=reference['result_id'])
    for key, expected in (context or {}).items():
        if key not in reference or reference[key] != expected:
            raise _error('evidence_context_mismatch',
                         f'{key} does not match the statement context.', field=key,
                         supplied=reference.get(key), expected=expected)
    entry = _entry(study, reference['result_id'])
    return cite.resolve(entry['output']['values'], cite.parse_path(reference['path']),
                        n_rows=entry['n_rows'])
