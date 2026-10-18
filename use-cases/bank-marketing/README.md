# Bank Marketing

First acceptance case for the junior Copilot + HTML + Marimo workflow.

## Data and question

The public UCI Bank Marketing `bank.csv` extract contains 4,521 rows. Source, DOI, authors, and CC BY 4.0 attribution are recorded in `project.json` and `data/bank-names.txt`.

Proposed teaching scenario: prioritize contacts **before a call** when call capacity is limited. Target `y` is an observed subscription. Present the scenario as an exercise, not as a bank manager's decision.

`duration` is known after the call and is unsuitable for a pre-call prediction. `pdays = -1` denotes no previous contact in this extract. Use documentation rather than column names alone to interpret variables.

## Included files

- `data/bank.csv`: public reference data.
- `data/split.json`: existing tutorial partition, 3,164 training and 1,357 validation rows.
- `data/predictions.csv`: historical experiment predictions.
- `prepare_bank.py`: explicit deterministic experiment; trains two logistic regressions, including a leakage counterexample. Do not run it merely to open the tutorial.
- `case.yaml`: the junior study case contract ([`hypotrail.case/1`](../../docs/specs/CASE-CONTRACT.md)), generated from `project.json` and `case-supplement.yaml` by `mlkit.study.migrate`. It contains no confirmation: tutorial choices are scenario assumptions.
- `project.json`, `results.json`: companion contracts, including training-only EDA.
- `tutorial-results.json`, `bank-tutorial.html`: historical result/export formats; `design.css` is the export's frozen stylesheet.

## Limits and next work

Random stratified validation is exploratory. Without a complete timestamp or customer identifier, this extract does not establish customer independence or future-campaign performance. Threshold selection on validation is part of model selection. Observed subscriptions do not measure the causal effect of calling.

The new workflow needs distinct study state, progressively generated reports and notebook, and tested resumption. See [the specification](../../docs/specs/JUNIOR-WORKFLOW.md). Do not import synthetic-demo or companion answers as new study confirmations.
