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
import re
from importlib import resources

import yaml

CONTENT_FILES = ('glossary', 'steps', 'steps_fr', 'activities', 'report', 'report_fr',
                 # Advanced companion (CLI-CONTRACT-COMPANION C11): WP-0 stubs that carry
                 # their schema header only; WP-E1 fills digest, WP-E2 evidence and learn,
                 # WP-E3 drafts.
                 'digest', 'drafts', 'evidence', 'learn',
                 # v0.2b (WP-B2): the concept terms of the training confirmation mode.
                 'concepts',
                 # Owner decision 2026-10-27 (R25 to R30): the lesson-style report, every
                 # text in English and French side by side.
                 'lesson')
BINARY, REGRESSION = 'binary', 'regression'
_TASK = contextvars.ContextVar('hypotrail_texts_task', default=BINARY)
# B6c (M3): the evaluation scheme of the study. Under cross-validation every development
# row is explored and predicted out of fold: the texts say so instead of "training rows"
# and "validation rows" (``cv_steps``, ``cv_activities``, ``cv_terms`` and the
# ``cross_validation`` mapping of the report labels, merged over the task's texts).
VALIDATION, CROSS_VALIDATION = 'validation', 'cross_validation'
_SCHEME = contextvars.ContextVar('hypotrail_texts_scheme', default=VALIDATION)
# Review round 4 (E4-5): the review-v1 explicit plans are cross-validations too (they were
# read as a holdout split: "Stratified split", "Validation rows"). The temporal ones
# (:data:`FORWARD_METHODS`) score each later window with models fitted on earlier rows only,
# and their earliest window (warm-up) is never scored: their texts say so
# (``forward_steps``, ``forward_activities``, merged over the cross-validation texts).
FORWARD_METHODS = ('forward_chaining', 'ordered_retrospective')
CV_METHODS = ('kfold_stratified', 'kfold_quantile', 'temporal_folds', 'group_disjoint') \
    + FORWARD_METHODS
_FORWARD = contextvars.ContextVar('hypotrail_texts_forward', default=False)


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


# v0.3 (WP-J): the language the HTML report writes its glossary definitions in (English
# unless the report is rendered for a French study, ``report_language_context``).
_REPORT_LANGUAGE = contextvars.ContextVar('hypotrail_texts_report_language', default='en')


@contextlib.contextmanager
def report_language_context(language: str | None):
    token = _REPORT_LANGUAGE.set(language if language in ('en', 'fr') else 'en')
    try:
        yield
    finally:
        _REPORT_LANGUAGE.reset(token)


def report_language() -> str:
    return _REPORT_LANGUAGE.get()


# L3 (owner session 2026-10-26, remark R4): whether the glossary's "For example" sentences
# describe the case of the study a surface is written for (``study_context`` sets it from the
# view). They speak of the canonical case of each task; in a study of another case they would
# explain the term with somebody else's data, so a surface shows the definition without them
# there, and the study's own figures (``cited_example``) give the contextual example. The
# case declares it in its translation sidecar (``glossary_examples``, read as
# ``view.case_texts.glossary_examples``): the engine names no dataset (wave W2 integration;
# ``test_synthetic_case.py::test_study_engine_contains_no_dataset_specific_names``). A study
# without a current sidecar reads the definitions without them. ``None``: outside a study.
_EXAMPLES = contextvars.ContextVar('hypotrail_texts_examples', default=None)


_EXAMPLE_SENTENCE = re.compile(r'\s*(?:For example|Par exemple),.*?\.(?=\s|$)', re.S)


@contextlib.contextmanager
def examples_context(apply: bool | None):
    token = _EXAMPLES.set(apply)
    try:
        yield
    finally:
        _EXAMPLES.reset(token)


def glossary_examples_of(view) -> bool:
    """Whether the glossary's own examples describe the case of ``view`` (a view, or a
    state): what its case's translation sidecar declares, false without one."""
    if not isinstance(view, dict):
        return False
    if 'case_texts' in view:
        return bool((view.get('case_texts') or {}).get('glossary_examples'))
    from . import l10n
    return l10n.translations(view).glossary_examples if view.get(l10n.STATE_KEY) else False


def examples_apply(task: str | None = None) -> bool:
    """Whether the glossary's own examples speak of this study's case (always true outside
    a study context)."""
    apply = _EXAMPLES.get()
    return apply is None or apply


def without_examples(text: str) -> str:
    """``text`` without its "For example, ..." (or "Par exemple, ...") sentences."""
    return _EXAMPLE_SENTENCE.sub('', text or '').strip()


def definition(entry: dict | None, task: str | None = None) -> tuple[str, str] | None:
    """``(definition, language)`` of a glossary entry as a surface shows it: in the report's
    language when the entry has it (``definition_fr``), without the glossary's examples in a
    study of another case (:func:`examples_apply`)."""
    if not entry:
        return None
    if _REPORT_LANGUAGE.get() == 'fr' and entry.get('definition_fr'):
        text, lang = entry['definition_fr'], 'fr'
    else:
        text, lang = entry['definition'], 'en'
    return (text if examples_apply(task) else without_examples(text)), lang


def concept(term_id: str | None, task: str | None = None) -> tuple[str, str, str] | None:
    """``(term, definition, language)`` of a glossary entry as the report shows it: in a
    French report (v0.3, WP-J) the French term and definition when the entry has
    ``definition_fr`` (the English otherwise); None for an unknown term. L3: without the
    glossary's examples in a study of another case (:func:`definition`)."""
    entry = glossary(term_id, task) if term_id else None
    if not entry:
        return None
    text, lang = definition(entry, task)
    term = (entry.get('term_fr') or entry['term']) if lang == 'fr' else entry['term']
    return term, text, lang


@contextlib.contextmanager
def forward_context(forward: bool):
    """Read texts for a forward-chaining plan (E4-5) inside the block."""
    token = _FORWARD.set(bool(forward))
    try:
        yield
    finally:
        _FORWARD.reset(token)


def is_forward() -> bool:
    return is_cv() and _FORWARD.get()


@contextlib.contextmanager
def study_context(view):
    """The task and the evaluation scheme of a view (or a state): both contexts at once
    (and whether its plan chains forward in time, E4-5)."""
    with task_context(view.get('task')), scheme_context(scheme_of(view)), \
            forward_context(split_method_of(view) in FORWARD_METHODS), \
            examples_context(glossary_examples_of(view)):
        yield


def current_scheme(scheme: str | None = None) -> str:
    return scheme or _SCHEME.get()


def is_cv(scheme: str | None = None) -> bool:
    return current_scheme(scheme) == CROSS_VALIDATION


def split_method_of(view) -> str | None:
    """The method of the study's split decision (confirmed or proposed), else of its open
    split proposal; None when neither names one."""
    decisions = (view or {}).get('decisions') or {}
    split = decisions.get('split') or {}
    value = split.get('value')
    if isinstance(value, dict) and value.get('method'):
        return value.get('method')
    proposals = (view or {}).get('open_proposals')
    if proposals is None and isinstance((view or {}).get('proposals'), dict):
        proposals = [p for p in view['proposals'].values() if p.get('status') == 'open']
    for p in proposals or []:
        if p.get('decision_id') == 'split' and isinstance(p.get('value'), dict):
            return p['value'].get('method')
    return None


def scheme_of(view) -> str:
    """``cross_validation`` when the study's split decision (confirmed or proposed) is a
    cross-validation, or when a study with a final test has not decided it yet (its draft
    is a cross-validation); ``validation`` otherwise."""
    method = split_method_of(view)
    if method:
        return CROSS_VALIDATION if method in CV_METHODS else VALIDATION
    decisions = (view or {}).get('decisions') or {}
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
                merged = _merge(out[key], value)
                if 'definition' in value and 'definition_fr' not in value:
                    # v0.3 (WP-J): a French definition describes the text it translates.
                    merged.pop('definition_fr', None)
                if 'cited_example' in value and 'cited_example_fr' not in value:
                    merged.pop('cited_example_fr', None)        # L3: the same rule
                out[key] = merged
    return out


def glossary(term_id: str, task: str | None = None) -> dict | None:
    return glossary_terms(task).get(term_id)


@functools.cache
def _report(task: str, scheme: str = VALIDATION, language: str = 'en') -> dict:
    data = load('report')
    base = {k: v for k, v in data.items() if k not in (REGRESSION, CROSS_VALIDATION)}
    regression = {k: v for k, v in (data.get(REGRESSION) or {}).items()
                  if k != CROSS_VALIDATION}
    out = base if task != REGRESSION else _merge(base, regression)
    if scheme == CROSS_VALIDATION:
        out = _merge(out, data.get(CROSS_VALIDATION, {}))
        if task == REGRESSION:
            out = _merge(out, (data.get(REGRESSION) or {}).get(CROSS_VALIDATION, {}))
    if language == 'fr':
        french = load('report_fr')
        out = _merge(out, {k: v for k, v in french.items()
                           if k not in ('schema', REGRESSION, CROSS_VALIDATION)})
        # the same order as the English: the task, then the scheme, then the task's scheme
        # (a French regression under cross-validation reads "out-of-fold predictions" too)
        if task == REGRESSION:
            out = _merge(out, {k: v for k, v in (french.get(REGRESSION) or {}).items()
                               if k != CROSS_VALIDATION})
        if scheme == CROSS_VALIDATION:
            out = _merge(out, french.get(CROSS_VALIDATION, {}))
            if task == REGRESSION:
                out = _merge(out, (french.get(REGRESSION) or {}).get(CROSS_VALIDATION, {}))
    return out


def report(task: str | None = None) -> dict:
    return _report(current_task(task), current_scheme(), report_language())


def step(step_id: str, task: str | None = None) -> dict:
    english = load('steps')
    # L3 (owner session 2026-10-26, R4): a French report, notebook or "Learn" tab reads each
    # section with its French form (``steps_fr.yaml``) merged over the English.
    french = load('steps_fr') if _REPORT_LANGUAGE.get() == 'fr' else {}

    def section(name: str) -> dict:
        out = {}
        for key, value in english.get(name, {}).items():
            fr = (french.get(name) or {}).get(key)
            out[key] = _merge(value, fr) if isinstance(value, dict) and fr else value
        return out
    data = {name: section(name) for name in ('steps', 'regression_steps', 'cv_steps',
                                             'regression_cv_steps', 'forward_steps',
                                             'regression_forward_steps')}
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
    if is_forward():
        overlay = (data.get('regression_forward_steps', {}) if regression else {}).get(step_id) \
            or data.get('forward_steps', {}).get(step_id)
        if overlay:
            out = _merge(out, overlay)
    return out


def step_status_words() -> dict:
    """``{pending, stale}`` of ``steps.yaml`` in the report's language (L3)."""
    english = load('steps')
    french = load('steps_fr') if _REPORT_LANGUAGE.get() == 'fr' else {}
    return {k: french.get(k) or english[k] for k in ('pending', 'stale')}


VARIANT_ORDINALS = {'2': 'second', '3': 'third'}
VARIANT_ORDINALS_FR = {'2': 'deuxième', '3': 'troisième'}


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
    if is_forward():
        specs.update(data.get('forward_activities', {}))
        if current_task(task) == REGRESSION:
            specs.update(data.get('regression_forward_activities', {}))
    if _REPORT_LANGUAGE.get() == 'fr':
        # E4-5: the labels the French report translates (``fr_labels``).
        specs = {k: _relabel(v, data.get('fr_labels', {})) for k, v in specs.items()}
    if slot in specs:
        return specs[slot]
    base, sep, column = slot.partition(':')
    if sep and base in specs:
        spec = dict(specs[base])
        ordinal = VARIANT_ORDINALS.get(column) if base == 'fit.variant' else None
        # v0.3 (WP-F1): the second and third variants, in words (a digit in a label would
        # read as an uncited number).
        if ordinal and _REPORT_LANGUAGE.get() == 'fr':
            # L3: the ordinal of a French report (no digit, as above).
            spec['label'] = f'{spec.get("label", base)}, la {VARIANT_ORDINALS_FR[column]}'
        else:
            spec['label'] = (f'{spec.get("label", base)}, the {ordinal} one' if ordinal
                             else f'{spec.get("label", base)}: {column}')
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


# --- the lesson-style report (owner decision 2026-10-27, R25 to R30) -------------------------

@functools.cache
def _lesson(task: str) -> dict:
    data = load('lesson')
    base = {k: v for k, v in data.items() if k not in ('schema', REGRESSION, BINARY)}
    return _merge(base, data.get(task) or {})


def lesson(path: str, task: str | None = None):
    """The node of ``content/lesson.yaml`` at the dotted ``path`` for the study's task (its
    ``regression`` or ``binary`` overlay merged over the shared texts). A leaf stays a
    ``{en, fr}`` mapping: :func:`say` picks the language. KeyError when absent."""
    node = _lesson(current_task(task))
    for part in path.split('.'):
        node = node[part]
    return node


def has_lesson(path: str, task: str | None = None) -> bool:
    try:
        lesson(path, task)
    except (KeyError, TypeError):
        return False
    return True


def say(node, language: str | None = None) -> str:
    """The text of a ``{en, fr}`` leaf in ``language`` (the report language by default)."""
    lang = language or report_language()
    if isinstance(node, dict) and ('en' in node or 'fr' in node):
        return node.get(lang) or node.get('en') or ''
    return '' if node is None else str(node)
