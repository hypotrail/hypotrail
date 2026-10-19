# Bank Marketing

First case of the junior workflow (v0.1: Claude Code chat, an evolving HTML report, and a generated Marimo notebook; GitHub Copilot is not tested yet).

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

## Running the study (v0.1)

From the repository root, create a study in a folder outside the repository and open it with Claude Code:

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/bank-marketing/case.yaml --study ~/studies/bank
cd ~/studies/bank && claude
```

The study starts with every decision open, after `init` has sealed a **final test**: 904 rows (20 %, stratified on the outcome) that no command reads until the junior opens it once; the other 3,617 rows are the development rows. A study created today has nine decisions. The agent first shows the data card (step 0), then guides the pauses: the prediction moment and the availability of each feature (`duration` is documented as known only after the call; `day`, `month`, `contact`, and `campaign` describe the last contact and must be discussed); the split (by default a 5-fold stratified cross-validation of the development rows, a 30 % train/validation split stays possible), the success criterion fixed before any model, and, after the exploration, the preprocessing; the variant to compare with the logistic model; the decision rule (by default a share, the case's teaching assumption `scenario_defaults.capacity_share` 10 %), the opening of the final test, and the conclusion. `keep_baseline` is a valid conclusion. Every number in `reports/study.html` cites a recorded result. See [the handoff](../../docs/handoff/IMPLEMENTATION.md) for what is supported and what is refused.

The study records that this public extract and its figures were explored and published before, so development evidence is not independent evidence; the final test, opened once, is held out from the study's own choices, though its rows are public too. Studies created under v0.1 (five decisions, 3,164 training and 1,357 validation rows, no final test) and v0.2a (seven decisions) still load unchanged. Bank Marketing is kept as the v0.1/v0.2a reference and a regression check; [Online Shoppers](../online-shoppers/README.md) is the discovery case, and [the full file](../bank-marketing-full/README.md) adds a temporal final test.

## Limits

Cross-validation and a random validation split are development evidence. Without a complete timestamp or customer identifier, this extract does not establish customer independence or future-campaign performance. Choosing a rule on out-of-fold or validation rows is part of model selection. Observed subscriptions do not measure the causal effect of calling. The study lists these limits in its "What is not yet defensible" section.

Do not import synthetic-demo or companion answers as new study confirmations: `case.yaml` contains none, and `hypotrail init` ignores the companion files.
