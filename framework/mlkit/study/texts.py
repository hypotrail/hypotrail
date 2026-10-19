"""Teaching texts and labels of the deliverables, stored as data (plan §9 bis, WP3.1).

The glossary, the step explanations, the activity display specifications, and the
report labels live in ``mlkit/study/content/*.yaml`` (package data). Renderers read
them through :func:`load`; nothing pedagogical is hard-coded in the HTML or notebook
renderers. Every explanation introduces the statistical term first, then explains it
in the context of the case.

The texts contain no literal numbers: a number shown to the junior is always a cited
registry value (``{{slot:...}}`` templates, see :mod:`mlkit.study.cite`).

Task-aware (M3). A regression study reads the same files with their regression overlays:
``regression_terms`` and ``binary_only`` in the glossary, ``regression_steps`` in the
steps, ``regression_activities`` and ``regression_metrics`` in the activities, and the
``regression`` mapping of the report labels (merged over the binary labels). The task is
given explicitly or by :func:`task_context` (the renderers set it from ``view.task``), so
a regression report never shows the vocabulary of a decision rule on scores.

Read-only and free of pandas, numpy, and scikit-learn.
"""
from __future__ import annotations

import contextlib
import contextvars
import copy
import functools
from importlib import resources

import yaml

CONTENT_FILES = ('glossary', 'steps', 'activities', 'report',
                 # Advanced companion (CLI-CONTRACT-COMPANION C11): WP-0 stubs that carry
                 # their schema header only; WP-E1 fills digest, WP-E2 evidence and learn,
                 # WP-E3 drafts.
                 'digest', 'drafts', 'evidence', 'learn',
                 # v0.2b (WP-B2): the concept terms of the training confirmation mode.
                 'concepts')
BINARY, REGRESSION = 'binary', 'regression'
_TASK = contextvars.ContextVar('hypotrail_texts_task', default=BINARY)
# B6c (M3): the evaluation scheme of the study. Under cross-validation every development
# row is explored and predicted out of fold: the texts say so instead of "training rows"
# and "validation rows" (``cv_steps``, ``cv_activities``, ``cv_terms`` and the
# ``cross_validation`` mapping of the report labels, merged over the task's texts).
VALIDATION, CROSS_VALIDATION = 'validation', 'cross_validation'
_SCHEME = contextvars.ContextVar('hypotrail_texts_scheme', default=VALIDATION)
CV_METHODS = ('kfold_stratified', 'kfold_quantile', 'temporal_folds')


@contextlib.contextmanager
def task_context(task: str | None):
    """Read texts for ``task`` (``binary`` or ``regression``) inside the block."""
    token = _TASK.set(task or BINARY)
    try:
        yield
    finally:
        _TASK.reset(token)


def current_task(task: str | None = None) -> str:
    return task or _TASK.get()


@contextlib.contextmanager
def scheme_context(scheme: str | None):
    """Read texts for an evaluation ``scheme`` (``validation`` or ``cross_validation``)."""
    token = _SCHEME.set(scheme or VALIDATION)
    try:
        yield
    finally:
        _SCHEME.reset(token)


@contextlib.contextmanager
def study_context(view):
    """The task and the evaluation scheme of a view (or a state): both contexts at once."""
    with task_context(view.get('task')), scheme_context(scheme_of(view)):
        yield


def current_scheme(scheme: str | None = None) -> str:
    return scheme or _SCHEME.get()


def is_cv(scheme: str | None = None) -> bool:
    return current_scheme(scheme) == CROSS_VALIDATION


def scheme_of(view) -> str:
    """``cross_validation`` when the study's split decision (confirmed or proposed) is a
    cross-validation, or when a study with a final test has not decided it yet (its draft
    is a cross-validation); ``validation`` otherwise."""
    decisions = (view or {}).get('decisions') or {}
    split = decisions.get('split') or {}
    value = split.get('value')
    if isinstance(value, dict) and value.get('method'):
        return CROSS_VALIDATION if value.get('method') in CV_METHODS else VALIDATION
    proposals = (view or {}).get('open_proposals')
    if proposals is None and isinstance((view or {}).get('proposals'), dict):
        proposals = [p for p in view['proposals'].values() if p.get('status') == 'open']
    for p in proposals or []:
        if p.get('decision_id') == 'split' and isinstance(p.get('value'), dict):
            return CROSS_VALIDATION if p['value'].get('method') in CV_METHODS else VALIDATION
    return CROSS_VALIDATION if 'final_test' in decisions else VALIDATION


def _merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


@functools.cache
def load(name: str) -> dict:
    """The parsed content file ``name`` (one of :data:`CONTENT_FILES`)."""
    if name not in CONTENT_FILES:
        raise KeyError(f'unknown content file {name!r}')
    text = (resources.files('mlkit.study') / 'content' / f'{name}.yaml').read_text(encoding='utf-8')
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not str(data.get('schema', '')).startswith(
            f'hypotrail.content.{name}/'):
        raise ValueError(f'content/{name}.yaml does not declare its schema')
    return data


def glossary_terms(task: str | None = None) -> dict:
    """Every glossary entry of a task: a regression study drops the binary-only terms and
    reads its own definitions where they differ; under cross-validation (B6c) the
    ``cv_terms`` (and ``regression_cv_terms``) are merged over them."""
    data = load('glossary')
    if current_task(task) != REGRESSION:
        out = dict(data['terms'])
        overlay = data.get('cv_terms', {})
    else:
        hidden = set(data.get('binary_only', []))
        out = {k: v for k, v in data['terms'].items() if k not in hidden}
        out.update(data.get('regression_terms', {}))
        overlay = _merge(data.get('cv_terms', {}), data.get('regression_cv_terms', {}))
    if is_cv():
        for key, value in overlay.items():
            if key in out:
                out[key] = _merge(out[key], value)
    return out


def glossary(term_id: str, task: str | None = None) -> dict | None:
    return glossary_terms(task).get(term_id)


@functools.cache
def _report(task: str, scheme: str = VALIDATION) -> dict:
    data = load('report')
    base = {k: v for k, v in data.items() if k not in (REGRESSION, CROSS_VALIDATION)}
    regression = {k: v for k, v in (data.get(REGRESSION) or {}).items()
                  if k != CROSS_VALIDATION}
    out = base if task != REGRESSION else _merge(base, regression)
    if scheme == CROSS_VALIDATION:
        out = _merge(out, data.get(CROSS_VALIDATION, {}))
        if task == REGRESSION:
            out = _merge(out, (data.get(REGRESSION) or {}).get(CROSS_VALIDATION, {}))
    return out


def report(task: str | None = None) -> dict:
    return _report(current_task(task), current_scheme())


def step(step_id: str, task: str | None = None) -> dict:
    data = load('steps')
    regression = current_task(task) == REGRESSION
    if regression and step_id in data.get('regression_steps', {}):
        out = data['regression_steps'][step_id]
    else:
        out = data['steps'].get(step_id, {})
    if is_cv():
        overlay = (data.get('regression_cv_steps', {}) if regression else {}).get(step_id) \
            or data.get('cv_steps', {}).get(step_id)
        if overlay:
            out = _merge(out, overlay)
    return out


def activity(slot: str, task: str | None = None) -> dict:
    """Display specification of an activity slot (an empty spec for an unknown slot).

    A per-column slot ``eda.rate_by:<column>`` uses the spec of ``eda.rate_by`` with the
    column in its label."""
    data = load('activities')
    specs = dict(data['activities'])
    if current_task(task) == REGRESSION:
        specs.update(data.get('regression_activities', {}))
    if is_cv():
        # B6c (M3): a cross-validated study replaces a few whole specs (the split) and
        # renames the labels that speak of training or validation rows (``cv_labels``).
        specs.update(data.get('cv_activities', {}))
        if current_task(task) == REGRESSION:
            specs.update(data.get('regression_cv_activities', {}))
        labels = data.get('cv_labels', {})
        specs = {k: _relabel(v, labels) for k, v in specs.items()}
    if slot in specs:
        return specs[slot]
    base, sep, column = slot.partition(':')
    if sep and base in specs:
        spec = dict(specs[base])
        spec['label'] = f'{spec.get("label", base)}: {column}'
        return spec
    return {}


def _relabel(node, labels: dict):
    """``node`` with every ``label`` value found in ``labels`` replaced (B6c, M3)."""
    if isinstance(node, dict):
        return {k: (labels.get(v, v) if k == 'label' and isinstance(v, str)
                    else _relabel(v, labels)) for k, v in node.items()}
    if isinstance(node, list):
        return [_relabel(v, labels) for v in node]
    return node


def policy_metrics() -> list[dict]:
    return list(load('activities').get('policy_metrics', []))


def regression_metrics() -> list[dict]:
    return list(load('activities').get('regression_metrics', []))
