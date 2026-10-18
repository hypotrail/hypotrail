"""Template of ``notebooks/workbench.py`` (plan §6, ADR 0001 decision 1).

The workbench is created once and never overwritten. It reads the study through the
same read API as the generated notebook and does not import that notebook. A slider
labelled "Experiment, not adopted" evaluates a rule with the pure
``mlkit.study.policy.evaluate`` on the stored validation predictions and shows the
adopted policy next to it. Nothing it computes is recorded.

Bump :data:`TEMPLATE_VERSION` when the cells change: an existing workbench is then
left intact and ``workbench.candidate.py`` is written next to it.
"""
from __future__ import annotations

TEMPLATE_VERSION = 1
EXPERIMENT_LABEL = 'Experiment, not adopted'

SETUP = '''import os

os.environ["HYPOTRAIL_READ_ONLY"] = "1"
from pathlib import Path

import marimo as mo
from mlkit.study import notebook_view as nv

STUDY_DIR = Path(__file__).resolve().parents[1]'''

INTRO = '''mo.md(
    """
# Workbench

Try a threshold or a capacity on the stored validation predictions. **Experiments here
are not recorded and are not decisions**: to adopt a policy, ask the agent, who records
your own words with `hypotrail decide`.
"""
)'''

LOAD = '''study = nv.open_study(STUDY_DIR)
policy = nv.policy_module()
scores = nv.workbench_scores(study)'''

CONTROLS = f'''rule_kind = mo.ui.radio(
    options=["threshold", "capacity"], value="threshold", label="Rule type"
)
threshold = mo.ui.slider(
    start=0.0, stop=1.0, step=0.01, value=0.5, label="{EXPERIMENT_LABEL}"
)
capacity = mo.ui.slider(
    start=1, stop=max(1, scores["n"]), step=1, value=max(1, scores["n"] // 10),
    label="{EXPERIMENT_LABEL}",
)
mo.vstack([rule_kind, threshold, capacity])'''

EXPERIMENT = '''mo.Html(
    nv.experiment_html(
        policy, scores, study, rule_kind.value, threshold.value, capacity.value
    )
)'''

NOTES = '''mo.md(
    """
## Your notes

Write your observations here. Hypotrail does not read or track this notebook.
"""
)'''


# A regression study (M3) has no decision rule on scores: its workbench lists the
# validation rows with the largest residuals of a chosen model, from the stored
# predictions. Same rules: nothing is recorded, nothing is a decision.
REGRESSION_INTRO = '''mo.md(
    """
# Workbench

Look at the stored validation predictions of a model: the rows with the largest errors.
**Experiments here are not recorded and are not decisions**: to choose a model, ask the
agent, who records your own words with `hypotrail decide`.
"""
)'''

REGRESSION_LOAD = '''study = nv.open_study(STUDY_DIR)
preds = nv.regression_predictions(study)'''

REGRESSION_CONTROLS = f'''model = mo.ui.radio(
    options=["fit.linear", "fit.baseline"], value="fit.linear", label="Model"
)
rows = mo.ui.slider(start=1, stop=50, step=1, value=10, label="{EXPERIMENT_LABEL}")
mo.vstack([model, rows])'''

REGRESSION_EXPERIMENT = '''mo.Html(nv.residuals_html(preds, model.value, rows.value))'''


def cells(template_version: int = TEMPLATE_VERSION,
          task: str = 'binary') -> list[tuple[str, str]]:
    if task == 'regression':
        return [('setup', SETUP), ('intro', REGRESSION_INTRO), ('load_study', REGRESSION_LOAD),
                ('controls', REGRESSION_CONTROLS), ('experiment', REGRESSION_EXPERIMENT),
                ('your_notes', NOTES)]
    return [('setup', SETUP), ('intro', INTRO), ('load_study', LOAD),
            ('controls', CONTROLS), ('experiment', EXPERIMENT), ('your_notes', NOTES)]



def header(template_version: int = TEMPLATE_VERSION) -> str:
    return (f'# Hypotrail workbench, template_version = {template_version}.\n'
            '# Created once. Hypotrail never overwrites this file; experiments here are not '
            'tracked.')
