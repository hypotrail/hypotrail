# Online Shoppers Purchasing Intention

Discovery case from v0.2b: the first study a junior runs. It is a **binary** scoring study on real sessions of an online shop, with a leakage question to settle (`PageValues`) and a follow-up budget stated as a share.

## Data and licence

`data/online_shoppers_intention.csv`: 12,330 sessions, 18 columns, from the UCI Machine Learning Repository, [dataset 468](https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset), licence **CC BY 4.0**. The file is committed unmodified (CRLF line ends included).

Attribution: Sakar, C. O., Polat, S. O., Katircioglu, M., and Kastro, Y. (2019). Real-time prediction of online shoppers' purchasing intention using multilayer perceptron and LSTM recurrent neural networks. *Neural Computing and Applications* 31, 6893–6908. doi:10.1007/s00521-018-3523-0. Dataset DOI 10.24432/C5F88Q. See also [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

## Provenance and verification

The UCI site (and OpenML) were blocked by the network proxy of the preparation environment, so the file was taken on 2026-10-19 from a public GitHub mirror, `https://raw.githubusercontent.com/fenago/datasets/main/online_shoppers_intention.csv`, and checked against the figures UCI publishes:

| Check | UCI | File |
|---|---|---|
| Rows | 12,330 | 12,330 |
| Columns | 18 | 18 (every row) |
| `Revenue` TRUE / FALSE | 1,908 / 10,422 | 1,908 / 10,422 |

sha256 `b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9`. `build_case.py --verify` repeats the checks. Only one mirror was found, and the file was not compared byte for byte with the UCI archive. **To do on a machine that reaches UCI:** download the archive from the dataset page and compare the sha256 of its CSV with the one above; if they differ, replace the file and regenerate `case.yaml`.

## What is not verified

The UCI page and the article could not be read from the preparation environment. The variable descriptions, the observation unit, and the definitions of the Google Analytics metrics come from the UCI documentation and the article **as recalled by the preparer**, so every description has status `scenario_assumption` with a source that says so; none is a `documented_fact`. What the case states as `observed` (row and column counts, class counts, duplicate rows, months present, the mirror and its sha256) was established from the file itself. The licence and the DOIs are those UCI lists, not re-checked from that environment.

## Scenario

An online shop can follow up only some finished sessions (an email or a retargeting ad). When a session ends, a score ranks the sessions; the team follows up the top share of them. The prediction moment is **the end of the session**. `Revenue` says whether that session ended with a purchase: the score learns which sessions look like buying sessions, a proxy of purchase intention. The data record no follow-up and no later purchase, so they say nothing about the effect of a follow-up (fact `target_as_proxy`).

`scenario_defaults.capacity_share` is **10 %** (`scenario_assumption`): the exercise assumes the budget covers one finished session in ten. The agent asks the capacity as a share, shows what 5, 10 and 20 % would select (`policy.evaluation` → `gain_points`), and, when the junior keeps the default, the study lists "capacity assumed for the exercise" in what is not yet defensible. A real business case has no default.

## Questions the case leaves to the junior

- **`PageValues`.** A Google Analytics "page value" is built from transactions: the average value of a page for sessions that went on to a transaction. Whether the value of a session includes its own purchase, and over which period it was computed, is not documented. Its availability is `uncertain`; the single-feature signal flags it (out-of-fold AUC about 0.86 on training rows, far above the other features). It is the first availability question to settle.
- `BounceRates` and `ExitRates` are Google Analytics page metrics computed over many visitors and an undocumented period: also `uncertain`.
- The codes of `OperatingSystems`, `Browser`, `Region`, and `TrafficType` have no documented meaning; `VisitorType = Other` is undocumented.

## Structure

- No date: only the month (ten months; January and April are absent; June is written in full), no year, no documented row order. The sealed final test is therefore a **stratified** random 20 % (2,466 rows), not the latest sessions.
- No user or session identifier. 125 rows repeat an earlier row on every column (76 groups, 201 rows), mostly short sessions. The case declares `duplicates: {policy: group}`: each group of identical rows stays on one side of the final test, the split and the folds (a cautious choice, not a claim that they are one session).
- `Revenue` and `Weekend` are written `TRUE`/`FALSE`; they are read as booleans, so the labels are `True`/`False`.

## Files

- `data/online_shoppers_intention.csv`: the data.
- `build_case.py`: generates `case.yaml` (`--check` compares it, `--verify` re-runs the integrity checks, `--out DIR` writes a copy for tests). `mlkit.study.migrate` does not apply: there is no companion `project.json`.
- `case.yaml`: the [`hypotrail.case/1`](../../docs/specs/CASE-CONTRACT.md) adapter. Edit `build_case.py`, never the YAML.

## Running the study

```sh
uv sync --project framework --group dev
uv run --project framework hypotrail init --case use-cases/online-shoppers/case.yaml --study ~/studies/shoppers
cd ~/studies/shoppers && claude
```

Create the study outside the repository. First figures of a test run (default preprocessing, every feature kept as the case states it, `PageValues` included, stratified 70/30 split of the development rows, seed 20261017): 9,864 development rows (6,905 training, 1,068 purchases, rate 15.5 %); logistic validation AUC 0.905; at 10 % of the 2,959 validation rows (296 sessions), precision 74.3 % against a base rate of 15.5 % (+58.8 points), 48 % of the purchases found. These include `PageValues`; they are a test run, not a study conclusion.
