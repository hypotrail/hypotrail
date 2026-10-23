"""Task bank and rubrics of a case: ``<case dir>/understanding.yaml`` (SPEC §08).

The bank is case content, not engine code: the engine has no branch per case. It holds
versioned human rubrics (expected criteria, error signs, acceptable evidence, uncertain
cases, the conditions of ``demonstrated``, coaching hints) and contextualised tasks
(``hypotrail.understanding-task/1``) whose prompts cite the study through references
resolved in the snapshot (``{decision:split}``, ``{fact:observation_unit}``,
``{case:target}``); a reference that does not resolve is a missing prerequisite, never an
invented number.

The engine validates the structure and the provenance of a bank. It does not prove its
pedagogical quality: ``qualification.status`` says whether a person reviewed it
(``reviewed``) or not (``to_qualify``); a bank ``to_qualify`` never produces a
``required`` result. A qualification record marked ``simulated`` (test fixtures) says so
in every result built on it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from . import DIMENSIONS, canonical, refuse

SCHEMA = 'hypotrail.understanding-bank/1'
TASK_SCHEMA = 'hypotrail.understanding-task/1'
FILE = 'understanding.yaml'
KINDS = ('explain', 'predict_consequence', 'diagnose', 'transfer')
QUALIFICATION_STATUSES = ('to_qualify', 'reviewed')
BANK_KEYS = ('schema', 'bank_id', 'bank_version', 'case_id', 'case_contract_version',
             'locale', 'qualification', 'rubrics', 'tasks')
QUALIFICATION_KEYS = ('status', 'reviews')
REVIEW_KEYS = ('reviewer_declared_id', 'role', 'reviewed_on', 'simulated', 'note')
RUBRIC_KEYS = ('rubric_id', 'version', 'dimension_id', 'criteria', 'error_signs',
               'acceptable_evidence', 'uncertain_cases', 'demonstrated_when',
               'dependency_keys', 'hints')
CRITERION_KEYS = ('criterion_id', 'text', 'mandatory', 'not_applicable_allowed')
TASK_KEYS = ('task_id', 'task_version', 'case_contract_version', 'dimension_ids',
             'responsibility_tags', 'kind', 'prompt_template', 'prerequisite_refs',
             'source_refs', 'rubric_id', 'variant_family', 'variant_id', 'dependency_keys',
             'permitted_resources', 'prohibited_actions', 'locale')
ID = re.compile(r'[a-z0-9][a-z0-9_.-]{0,79}')
REF = re.compile(r'\{((?:decision|fact|case):[a-z0-9_]+)\}')
MAX_TASKS = 200
MAX_TEXT = 4000


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _invalid(message: str, **details):
    return refuse('unsupported_case', f'Task bank: {message}',
                  'Fix the case understanding.yaml (or use a case that has a valid bank).',
                  **details)


def _keys(doc: Any, keys: tuple, where: str) -> None:
    if not isinstance(doc, Mapping):
        raise _invalid(f'{where} must be a mapping.', field=where)
    missing = [k for k in keys if k not in doc]
    extra = sorted(str(k) for k in doc if k not in keys)
    if missing or extra:
        raise _invalid(f'{where} has missing or unknown keys.', field=where, missing=missing,
                       unknown=extra)


def _id(value, where: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise _invalid(f'{where} must be a lowercase identifier.', field=where)
    return value


def _text(value, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise _invalid(f'{where} must be a non-empty text of at most {MAX_TEXT} characters.',
                       field=where)
    return value


def _texts(value, where: str) -> list:
    if not isinstance(value, list):
        raise _invalid(f'{where} must be a list.', field=where)
    for i, v in enumerate(value):
        _text(v, f'{where}/{i}')
    return value


def validate(doc: Any, *, case_id: str | None = None) -> dict:
    """The bank when it is structurally valid (``unsupported_case`` otherwise)."""
    _keys(doc, BANK_KEYS, 'bank')
    if doc['schema'] != SCHEMA:
        raise _invalid(f'schema must be {SCHEMA}.', field='schema')
    _id(doc['bank_id'], 'bank_id')
    if not _is_int(doc['bank_version']) or doc['bank_version'] < 1:
        raise _invalid('bank_version must be a positive integer.', field='bank_version')
    if case_id is not None and doc['case_id'] != case_id:
        raise _invalid('the bank belongs to another case.', field='case_id',
                       bank_case=doc['case_id'], study_case=case_id)
    _keys(doc['qualification'], QUALIFICATION_KEYS, 'qualification')
    if doc['qualification']['status'] not in QUALIFICATION_STATUSES:
        raise _invalid('qualification/status must be to_qualify or reviewed.',
                       field='qualification/status')
    reviews = doc['qualification']['reviews']
    if not isinstance(reviews, list):
        raise _invalid('qualification/reviews must be a list.', field='qualification/reviews')
    for i, r in enumerate(reviews):
        _keys(r, REVIEW_KEYS, f'qualification/reviews/{i}')
        _id(r['reviewer_declared_id'], f'qualification/reviews/{i}/reviewer_declared_id')
        if not isinstance(r['simulated'], bool):
            raise _invalid('simulated must be true or false.',
                           field=f'qualification/reviews/{i}/simulated')
    if doc['qualification']['status'] == 'reviewed' and not reviews:
        raise _invalid('a reviewed bank lists its reviews.', field='qualification/reviews')
    rubrics = {}
    for i, r in enumerate(doc['rubrics'] if isinstance(doc['rubrics'], list) else []):
        _keys(r, RUBRIC_KEYS, f'rubrics/{i}')
        rid = _id(r['rubric_id'], f'rubrics/{i}/rubric_id')
        if rid in rubrics:
            raise _invalid('duplicate rubric id.', field=f'rubrics/{i}/rubric_id')
        if r['dimension_id'] not in DIMENSIONS:
            raise _invalid('unknown dimension.', field=f'rubrics/{i}/dimension_id')
        if not _is_int(r['version']) or r['version'] < 1:
            raise _invalid('rubric version must be a positive integer.',
                           field=f'rubrics/{i}/version')
        crit = r['criteria']
        if not isinstance(crit, list) or not crit:
            raise _invalid('a rubric has criteria.', field=f'rubrics/{i}/criteria')
        seen = set()
        for j, cr in enumerate(crit):
            _keys(cr, CRITERION_KEYS, f'rubrics/{i}/criteria/{j}')
            cid = _id(cr['criterion_id'], f'rubrics/{i}/criteria/{j}/criterion_id')
            if cid in seen:
                raise _invalid('duplicate criterion id.', field=f'rubrics/{i}/criteria/{j}')
            seen.add(cid)
            _text(cr['text'], f'rubrics/{i}/criteria/{j}/text')
            if not isinstance(cr['mandatory'], bool) \
                    or not isinstance(cr['not_applicable_allowed'], bool):
                raise _invalid('mandatory and not_applicable_allowed are booleans.',
                               field=f'rubrics/{i}/criteria/{j}')
        if not any(cr['mandatory'] for cr in crit):
            raise _invalid('a rubric has at least one mandatory criterion.',
                           field=f'rubrics/{i}/criteria')
        for k in ('error_signs', 'acceptable_evidence', 'uncertain_cases', 'hints'):
            _texts(r[k], f'rubrics/{i}/{k}')
        _text(r['demonstrated_when'], f'rubrics/{i}/demonstrated_when')
        _texts(r['dependency_keys'], f'rubrics/{i}/dependency_keys')
        if not r['dependency_keys']:
            raise _invalid('a rubric declares its dependency keys.',
                           field=f'rubrics/{i}/dependency_keys')
        rubrics[rid] = r
    if not rubrics:
        raise _invalid('the bank has no rubric.', field='rubrics')
    dims = [r['dimension_id'] for r in rubrics.values()]
    if len(set(dims)) != len(dims):
        raise _invalid('one rubric per dimension in a bank version.', field='rubrics')
    tasks = doc['tasks']
    if not isinstance(tasks, list) or not tasks or len(tasks) > MAX_TASKS:
        raise _invalid(f'the bank has one to {MAX_TASKS} tasks.', field='tasks')
    ids, variants = set(), set()
    for i, t in enumerate(tasks):
        _keys(t, TASK_KEYS, f'tasks/{i}')
        tid = _id(t['task_id'], f'tasks/{i}/task_id')
        if tid in ids:
            raise _invalid('duplicate task id.', field=f'tasks/{i}/task_id')
        ids.add(tid)
        if not _is_int(t['task_version']) or t['task_version'] < 1:
            raise _invalid('task_version must be a positive integer.', field=f'tasks/{i}')
        if t['kind'] not in KINDS:
            raise _invalid(f'kind must be one of {", ".join(KINDS)}.', field=f'tasks/{i}/kind')
        if not isinstance(t['dimension_ids'], list) or not t['dimension_ids'] \
                or any(d not in DIMENSIONS for d in t['dimension_ids']):
            raise _invalid('dimension_ids lists known dimensions.', field=f'tasks/{i}')
        if t['rubric_id'] not in rubrics:
            raise _invalid('unknown rubric.', field=f'tasks/{i}/rubric_id')
        if rubrics[t['rubric_id']]['dimension_id'] not in t['dimension_ids']:
            raise _invalid('the rubric dimension is not among the task dimensions.',
                           field=f'tasks/{i}/rubric_id')
        _text(t['prompt_template'], f'tasks/{i}/prompt_template')
        for k in ('responsibility_tags', 'prerequisite_refs', 'source_refs', 'dependency_keys',
                  'permitted_resources', 'prohibited_actions'):
            _texts(t[k], f'tasks/{i}/{k}')
        for ref in REF.findall(t['prompt_template']):
            if ref not in t['prerequisite_refs']:
                raise _invalid('every reference of the prompt is a prerequisite.',
                               field=f'tasks/{i}/prerequisite_refs', ref=ref)
        _id(t['variant_family'], f'tasks/{i}/variant_family')
        _id(t['variant_id'], f'tasks/{i}/variant_id')
        if (t['variant_family'], t['variant_id']) in variants:
            raise _invalid('duplicate variant.', field=f'tasks/{i}/variant_id')
        variants.add((t['variant_family'], t['variant_id']))
    canonical.dumps(doc)
    return doc


def load(case_dir, *, case_id: str | None = None) -> dict:
    """The bank of the case in ``case_dir``; ``unsupported_case`` when it has none."""
    path = Path(case_dir) / FILE
    if not path.is_file():
        raise refuse('unsupported_case', 'This case has no understanding task bank, so no '
                     'contextualised review can be planned for it.',
                     'Use a case with an understanding.yaml, or add a reviewed bank to it.',
                     case=case_id)
    try:
        doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise _invalid(f'not valid YAML ({exc.__class__.__name__}).') from exc
    return validate(doc, case_id=case_id)


def digest(bank: Mapping) -> str:
    return canonical.digest(bank)


def rubric(bank: Mapping, rubric_id: str) -> dict:
    return next(r for r in bank['rubrics'] if r['rubric_id'] == rubric_id)


def rubric_for(bank: Mapping, dimension: str) -> dict | None:
    return next((r for r in bank['rubrics'] if r['dimension_id'] == dimension), None)


def rubric_digests(bank: Mapping) -> dict:
    return {r['dimension_id']: canonical.digest(r) for r in bank['rubrics']}


def task(bank: Mapping, task_id: str) -> dict | None:
    return next((t for t in bank['tasks'] if t['task_id'] == task_id), None)


def qualified(bank: Mapping) -> bool:
    return bank['qualification']['status'] == 'reviewed'


def simulated_qualification(bank: Mapping) -> bool:
    return any(r['simulated'] for r in bank['qualification']['reviews'])


def resolve(template: str, refs: Mapping[str, str],
            prerequisites=()) -> tuple[str | None, list[str]]:
    """``(text, missing refs)``: the prompt with every reference replaced by its value in
    the snapshot; ``None`` when a reference or a prerequisite (``result:<slot>`` for a
    result that must exist) does not resolve."""
    missing = [r for r in list(REF.findall(template)) + list(prerequisites) if r not in refs]
    if missing:
        return None, sorted(set(missing))
    return REF.sub(lambda m: refs[m.group(1)], template), []


def public_task(t: Mapping) -> dict:
    """The minimal public form of a task (no rubric, no expected answer)."""
    return {k: t[k] for k in ('task_id', 'task_version', 'dimension_ids', 'kind', 'rubric_id',
                              'variant_family', 'variant_id')}
