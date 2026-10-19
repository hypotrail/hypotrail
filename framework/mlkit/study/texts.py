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
    reads its own definitions where they differ."""
    data = load('glossary')
    if current_task(task) != REGRESSION:
        return dict(data['terms'])
    hidden = set(data.get('binary_only', []))
    out = {k: v for k, v in data['terms'].items() if k not in hidden}
    out.update(data.get('regression_terms', {}))
    return out


def glossary(term_id: str, task: str | None = None) -> dict | None:
    return glossary_terms(task).get(term_id)


@functools.cache
def _report(task: str) -> dict:
    data = load('report')
    if task != REGRESSION:
        return data
    base = {k: v for k, v in data.items() if k != REGRESSION}
    return _merge(base, data.get(REGRESSION, {}))


def report(task: str | None = None) -> dict:
    return _report(current_task(task))


def step(step_id: str, task: str | None = None) -> dict:
    data = load('steps')
    if current_task(task) == REGRESSION and step_id in data.get('regression_steps', {}):
        return data['regression_steps'][step_id]
    return data['steps'].get(step_id, {})


def activity(slot: str, task: str | None = None) -> dict:
    """Display specification of an activity slot (an empty spec for an unknown slot).

    A per-column slot ``eda.rate_by:<column>`` uses the spec of ``eda.rate_by`` with the
    column in its label."""
    data = load('activities')
    specs = dict(data['activities'])
    if current_task(task) == REGRESSION:
        specs.update(data.get('regression_activities', {}))
    if slot in specs:
        return specs[slot]
    base, sep, column = slot.partition(':')
    if sep and base in specs:
        spec = dict(specs[base])
        spec['label'] = f'{spec.get("label", base)}: {column}'
        return spec
    return {}


def policy_metrics() -> list[dict]:
    return list(load('activities').get('policy_metrics', []))


def regression_metrics() -> list[dict]:
    return list(load('activities').get('regression_metrics', []))
