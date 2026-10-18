"""Teaching texts and labels of the deliverables, stored as data (plan §9 bis, WP3.1).

The glossary, the step explanations, the activity display specifications, and the
report labels live in ``mlkit/study/content/*.yaml`` (package data). Renderers read
them through :func:`load`; nothing pedagogical is hard-coded in the HTML or notebook
renderers. Every explanation introduces the statistical term first, then explains it
in the context of the case.

The texts contain no literal numbers: a number shown to the junior is always a cited
registry value (``{{slot:...}}`` templates, see :mod:`mlkit.study.cite`).

Read-only and free of pandas, numpy, and scikit-learn.
"""
from __future__ import annotations

import functools
from importlib import resources

import yaml

CONTENT_FILES = ('glossary', 'steps', 'activities', 'report')


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


def glossary(term_id: str) -> dict | None:
    return load('glossary')['terms'].get(term_id)


def report() -> dict:
    return load('report')


def step(step_id: str) -> dict:
    return load('steps')['steps'].get(step_id, {})


def activity(slot: str) -> dict:
    """Display specification of an activity slot (an empty spec for an unknown slot).

    A per-column slot ``eda.rate_by:<column>`` uses the spec of ``eda.rate_by`` with the
    column in its label."""
    specs = load('activities')['activities']
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
