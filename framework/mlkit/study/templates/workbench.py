"""Template of ``notebooks/workbench.py`` (plan §6, ADR 0001 decision 1).

The workbench is created once and never overwritten. It reads the study through the
same read API as the generated notebook and does not import that notebook. A slider
labelled "Experiment, not adopted" evaluates a rule with the pure
``mlkit.study.policy.evaluate`` on the stored validation predictions and shows the
adopted policy next to it. Nothing it computes is recorded.

Template version 2 (v0.2a, WP-A6) adds a starter cell that loads the development
training rows with :func:`mlkit.study.notebook_view.training_frame` (never the sealed final
test), so a cell copied from the generated notebook has rows to run on.

Template version 3 (v0.3, WP-F2, R29) writes the starter as the pandas a junior types: a
cell each for ``head()``, ``info()``, ``describe()`` and ``isna().sum()`` on those rows,
and a cell of commented idioms for a rate or mean by group (``groupby``, ``pd.crosstab``,
``value_counts``, ``plot.hist``) to adapt. Nothing in it asserts against the registry: the
generated notebook does that, and the workbench is free space.

Bump :data:`TEMPLATE_VERSION` when the cells change: an existing workbench is then
left intact and ``workbench.candidate.py`` is written next to it.
"""
from __future__ import annotations

TEMPLATE_VERSION = 3
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

Try a threshold, a capacity or a share on the stored predictions (out-of-fold under
cross-validation). **Experiments here
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

STARTER = '''# The training rows of the current split: development rows only, the final test stays
# sealed. Copy a cell of the generated notebook below and adapt it. Nothing is recorded,
# and a look at the outcome here is not counted in the study's ledger of looks.
train_rows = nv.training_frame(study)
train_rows.head()'''

# v3 (WP-F2, R29): the first looks, as a junior types them.
STARTER_INFO = '''# Columns, types, and how many cells hold a value.
train_rows.info()'''

STARTER_DESCRIBE = '''# Summary statistics of the numeric columns: count, mean, spread, and quartiles.
train_rows.describe()'''

STARTER_MISSING = '''# Missing values: cells with no value, counted by column.
train_rows.isna().sum()'''

STARTER_IDIOMS = '''import pandas as pd

# Idioms to adapt: replace "a_column" and "the_target" with names of your study.
# train_rows["a_column"].value_counts(normalize=True)          # shares of each value
# train_rows.groupby("a_column")["the_target"].agg(["mean", "count"])
# pd.crosstab(train_rows["a_column"], train_rows["the_target"], normalize="index")
# train_rows["a_column"].plot.hist(bins=10)                    # a numeric column
# train_rows.select_dtypes("number").corr(method="spearman")
train_rows.dtypes.to_frame("type")'''

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
        out = [('setup', SETUP), ('intro', REGRESSION_INTRO), ('load_study', REGRESSION_LOAD),
               ('controls', REGRESSION_CONTROLS), ('experiment', REGRESSION_EXPERIMENT)]
    else:
        out = [('setup', SETUP), ('intro', INTRO), ('load_study', LOAD),
               ('controls', CONTROLS), ('experiment', EXPERIMENT)]
    if template_version >= 2:
        out.append(('training_rows', STARTER))
    if template_version >= 3:
        out += [('first_look_info', STARTER_INFO), ('first_look_describe', STARTER_DESCRIBE),
                ('first_look_missing', STARTER_MISSING), ('idioms', STARTER_IDIOMS)]
    return out + [('your_notes', NOTES)]



def header(template_version: int = TEMPLATE_VERSION) -> str:
    return (f'# Hypotrail workbench, template_version = {template_version}.\n'
            '# Created once. Hypotrail never overwrites this file; experiments here are not '
            'tracked.')
