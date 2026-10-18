# Synthetic planted-trap case

`make_case.py` generates a contamination-free binary case whose truth is known. It serves two purposes:

- acceptance runs (plan WP0.7) and the E1 steelman (plan WP0.8) run every scenario on Bank Marketing and on this case. Models have probably memorised Bank, so spotting its `duration` leakage proves little. An arm that succeeds on Bank and fails here is reciting, not guiding;
- unit tests can compare engine outputs with a known generating truth.

The domain is fictitious: renewal reminders sent by the Quillmere Library Network to members whose membership expired. Column names are invented, so no memorised recipe applies.

## Planted traps

| Trap | Column(s) | What the case documents |
|---|---|---|
| Real pre-decision signal with a known effect | `holds_open` | An ordinary member attribute |
| Post-decision leakage under a neutral name | `desk_followups` | Recorded after the outcome |
| "Last contact" with ambiguous availability | `reminders_sent`, `last_reminder_weekday` | Availability `unknown`; prediction time unspecified |
| Sentinel shared by two columns on the same rows | `days_since_last_lapse = -1`, `last_lapse_reason = unknown` | Each sentinel separately; the second meaning is undocumented |
| Adjustable class imbalance | `outcome` (positive label `renewed`) | Nothing |
| Tied scores | `visit_band` and the other discrete inputs | Nothing |
| Optional exact duplicates | all columns | Duplicates `unknown` |
| Optional repeated groups | `member_ref` | Group column declared |
| Optional time column | `cycle_start_date` | Time column declared |

The optional traps exist so that later tests can check `unsupported_capability` refusals.

## Generating a case

Tests call the function with a temporary directory:

```python
paths = make_case(tmp_path, seed=20261018, n_rows=4000, positive_rate=0.12,
                  duplicates=0, groups=False, time=False)
# {'data': .../data.csv, 'case': .../case.yaml, 'truth': .../truth.json}
```

For manual inspection, write a case outside the repository:

```sh
framework/.venv/bin/python framework/tests/fixtures/synthetic/make_case.py /tmp/synthetic-case --seed 7 --duplicates 20 --groups --time
```

The output is byte-for-byte deterministic for a given seed and options. Randomness comes only from `Generator.random()` on PCG64 streams, so it does not depend on numpy's algorithms for specific distributions. Optional columns use separate streams and do not change the target draws. Never commit generated files.

## Files

- `data.csv`: separator `;`, UTF-8, header on line 1, one physical line per row, no quoting. Row keys follow the `source_line` rule: `L<line>`, so the first data row is `L2`.
- `case.yaml`: the [`hypotrail.case/1`](../../../../docs/specs/CASE-CONTRACT.md) contract an agent under test may read; `mlkit.study.case.load_case` accepts it. Every column has an epistemic status (`documented_fact`, `scenario_assumption`, `observed`, or `unknown`) and an availability entry. No status is ever `confirmed`: confirmation is a human decision recorded in study state, not a case property.
- `truth.json`: the generating model, the exact signal effect, the leaking column and its exact AUC, the sentinel row keys, the number of distinct true scores, a reference split recipe with its train target rate, and the duplicates, groups, and time column when enabled.

## Rule: truth.json is never exposed to an agent under test

`truth.json` is for graders and unit tests only. Acceptance runners must copy only `data.csv` and `case.yaml` into the workspace of an agent under test, and must keep `truth.json` outside every directory that agent can read. A run in which the agent could read `truth.json` is invalid.
