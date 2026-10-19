# Case contract `hypotrail.case/1`

Status: implemented in `framework/mlkit/study/case.py` (plan WP0.4). Tests: `framework/tests/study/test_case.py` and `test_case_migration.py`.

A case file, `use-cases/<id>/case.yaml`, is the static adapter between a dataset and the junior study engine. It says:

- where the dataset is and how to read it;
- how rows are keyed;
- what each variable means, and what is known about it;
- what the task is.

A case **never records a human decision**. The prediction time, feature availability, the split, the policy, and the conclusion are decisions recorded in study state (`.hypotrail/state.json`, plan §3.1). A case may *inform* those decisions, for example with a `prediction_time` fact marked `scenario_assumption`, but it never answers them.

The synthetic generator (`framework/tests/fixtures/synthetic/make_case.py`) and the migration tool (`mlkit.study.migrate`) both produce this one schema.

## Epistemic statuses

Every `status` field in a case takes one of four values:

| Status | Meaning | Typical source |
|---|---|---|
| `documented_fact` | Stated by the dataset documentation | `data/bank-names.txt:63` |
| `scenario_assumption` | Plausible, or chosen by the teaching scenario, but not established | `Tutorial scenario` |
| `observed` | Established by structural inspection of the file | `Structural inspection of data/x.csv` |
| `unknown` | Not known | — |

`confirmed` does not exist in a case. The loader refuses the words `confirmed` and `confirmation` as a key or as a whole string value anywhere in the document (`confirmed_status_forbidden`). `scripts/check_layout.py` is stricter for committed files: it refuses either word anywhere in `case.yaml` or `case-supplement.yaml`.

Every `source` field is a non-empty string. For a `documented_fact`, cite the documentation file by line (`path:line`) whenever possible. The migration supplement *requires* such a citation (see below).

`observed` facts come from **structural inspection** only: counts of rows, columns, distinct values, duplicates, and encodings of missing values. Target rates and relationships between variables belong to training-partition EDA, with recorded exposure. They are not case facts.

## Document

Top-level keys, in this order. Unknown keys are refused.

| Key | Required | Content |
|---|---|---|
| `schema` | yes | `hypotrail.case/1` |
| `id` | yes | Stable identifier |
| `title`, `description` | yes | Non-empty strings |
| `provenance` | yes | Mapping with `kind` (`public_dataset`, `synthetic`, or `unspecified`), plus free attribution fields (authors, DOI, licence, URLs) |
| `dataset` | yes | See [Dataset](#dataset) |
| `target` | yes | See [Target and task](#target-and-task) |
| `row_key` | yes | See [Row key](#row-key) |
| `facts` | yes | List of `{id, value, status, source}`; ids are unique |
| `variables` | yes | One entry per data column, in column order. See [Variables](#variables) |
| `special_values` | yes | Index of every variable special value, in variable order, as `{column, value, meaning, status, source}`. It must equal the per-variable lists |
| `structure` | yes | See [Structure](#structure) |
| `task` | yes | `binary` or `regression` |
| `prior_exposure` | no | List of `{value, status, source}`: what is already published or exposed for this dataset |
| `order` | no | v0.2a: the declared row order, see [Order](#order) |
| `duplicates` | no | v0.2b: how identical records are treated, see [Duplicates](#duplicates) |
| `scenario_defaults` | no | v0.2b: defaults of a teaching scenario, see [Scenario defaults](#scenario-defaults) |
| `prior_exposed_rows` | no | v0.2b: rows already seen outside the study, kept out of the final test, see [Prior-exposed rows](#prior-exposed-rows) |
| `migration` | no | See [Migration block](#migration-block) |

### Dataset

| Key | Content |
|---|---|
| `path` | Relative path inside the case directory; `..` and absolute paths are refused |
| `format` | `csv` (delimited text) |
| `sep` | A single character, or `whitespace` for runs of spaces and tabs |
| `encoding` | For example `utf-8` |
| `decimal` | A single character |
| `header` | `true` if line 1 holds the column names |
| `sha256` | Lowercase hex digest of the file bytes |
| `rows` | Number of data rows |
| `columns` | Number of columns; equals the number of variables |
| `quotechar` | Optional single character (default `"`) |
| `na_values` | Optional list of strings read as missing; each should also be a documented special value |

On load, the dataset must exist inside the case directory (`dataset_missing`), its bytes must match `sha256` (`dataset_changed`), the number of physical data lines must equal `rows`, and with a header, the header fields must equal the variable names in order (`invalid_case`). A changed dataset is never accepted silently: row keys and every recorded result are anchored to the sha256.

**Values (structural inspection, `data.check_values`).** When the data are read (by `init`, then by every activity), values that would silently change meaning are refused:

- a `numeric` or `integer` variable with a cell that is not a number once `na_values` are read as missing (a blank, `n/a`, `?`) is `invalid_case`, with the variable path, the offending tokens, and their first row keys: pandas would read the column as text and the models would one-hot encode it as a category. Declare the token in `na_values` (and as a special value) or change the type;
- a `binary` target holding a label other than `positive_label` and `negative_label` (or, without `negative_label`, more than one other label), or never holding `positive_label`, is `invalid_case`: every unexpected label would silently count as negative;
- a missing target value (a cell matching `na_values`) is `unsupported_capability`, capability `missing target values (v0.2)`, with the count and the first row keys, for both tasks: rows are neither dropped nor imputed.

Only which cells parse and which labels occur are read, never a rate; the reading is the structural inspection that `init` records as exposure.

**Development rows and the sealed final test (v0.2a, ADR 0006).** `init` first sets aside a final test (20 % of the rows, `CLI-CONTRACT.md` §4.1). The checks above, with values and row keys, run on the development rows only. The final-test rows get the same checks as counts of failing rows only (`numeric_cells`, `target_missing`, `target_labels`), never a value, a label, or a row key: a failure refuses `init` with `invalid_case` (or `unsupported_capability` for missing targets) and those counts. Row keys and duplicates are still read on every record. Every later reading of the data (by every activity) receives the development rows only.

### Row key

```yaml
row_key:
  rule: source_line
  format: L<line>
  description: ...
```

The key of a record is `L` followed by its physical 1-based line number in the dataset file. **Line 1 is the header when there is one**, so the first data row is `L2`; without a header it is `L1`. The rule requires one physical line per record. The key is meaningful only together with the dataset sha256.

### Target and task

```yaml
target:
  column: y
  positive_label: 'yes'
  negative_label: 'no'     # optional
task: binary
```

`column` names the single variable whose role is `target`. `positive_label` is required for `binary` and must be `null` for `regression`. Quote labels such as `'yes'` and `'no'`, which YAML 1.1 would otherwise read as booleans. A `regression` target has type `numeric` or `integer` and declares its `unit` (the variable's `unit`): errors are reported in it (`invalid_case` otherwise; a binary target is never reframed as a number).

### Variables

| Key | Content |
|---|---|
| `name` | Column name, unique |
| `type` | `numeric`, `integer`, `binary`, `category`, `ordinal`, `string`, or `date` |
| `role` | `feature`, `target`, `identifier`, `group_id`, or `time` |
| `unit`, `format` | Optional |
| `group` | Optional (v0.2a, WP-A4): the group the data card (`hypotrail data`) shows the variable in, for example `Client` or `Last contact of this campaign` |
| `labels` | Optional (v0.2a, WP-A4): the description in another language, `{fr: "..."}` (languages `en`, `fr`); the data card shows `labels.fr` next to the description |
| `range` | Optional (v0.2a, WP-A4), numeric or integer variables only: `{min, max, status, source}`, the possible values (either bound may be `null`, not both); `eda.quality` counts the ordinary values outside it |
| `description` | What the value means. For a variable that describes an event close to the outcome, say so: for example "last contact of the current campaign" |
| `status`, `source` | Epistemic status of the description |
| `availability` | `{value, status, source}`, see below |
| `special_values` | List of `{value, meaning, status, source}` (sentinels, undocumented categories, missing-value markers) |

`role` is structural. Whether a feature is used is a study decision: there is no `excluded` role.

**Availability** states what is known about whether the value is known at prediction time:

- `value` ∈ `available_at_prediction`, `not_available`, `uncertain`, `unknown`;
- `status` is an epistemic status. `value: unknown` goes with `status: unknown`, and only with it;
- `source` says why.

Availability is almost never a `documented_fact`. Documentation usually describes what a variable measures, not when it becomes known; that depends on the prediction time, which is a study decision. Study state records the availability *decision* (`available_at_prediction`, `not_available`, `uncertain_excluded`, `uncertain_included`; plan §3.2) and may differ from the case.

### Order

```yaml
order:
  by: line            # or the name of a numeric or integer variable
  direction: ascending
  status: documented_fact
  source: data/README.md:12
```

Optional (v0.2a, ADR 0006). It states that the rows are ordered in time: `by: line` (the physical order of the file) or a variable of type `numeric` or `integer` (not the target); `direction` is `ascending` (later rows come later, or have larger values) or `descending`. `status` and `source` say why the order is known. With `order`, the sealed final test is the last rows in that order (`temporal`, ties broken by file line, the count of ties at the cut recorded); without it, a stratified random sample. A variable named `line` makes `by: line` ambiguous and is refused (`invalid_case`), as are an unknown variable, a variable of another type, and another direction. A row whose order column holds no number refuses `init`.

Bank Marketing's `bank.csv` documents no order, and Auto MPG's time column (`model_year`) is used by the `ordinal_cutoff` split of the development rows, not by the final test; neither declares one. Since v0.2b, Bank Marketing's full file (`use-cases/bank-marketing-full`) declares `order: {by: line, direction: ascending}` (`bank-names.txt:31`, "ordered by date"): its final test is the last 20 % of the lines, less the `bank.csv` records among them ([Prior-exposed rows](#prior-exposed-rows)).

### Duplicates

```yaml
duplicates:
  policy: group
  status: scenario_assumption
  source: 125 rows repeat an earlier row; nothing says whether they are one session recorded twice
```

Optional (v0.2b, WP-B3). Without it, two records with the same content (every column, the target included) refuse `init` (`duplicate records (v0.2)`, see [Capabilities](#capabilities)). With `policy: group` (the only policy), the records with identical content form one **entity group** (`data.entity_groups`: the group is named by its first row key), and a group is never divided:

- the sealed final test draws whole groups: a stratified assignment draws groups (identical records share their target, hence their stratum) until the stratum's share is reached (`partition.grouped_stratified`; with no repeated record it draws exactly the rows of the ungrouped assignment); a temporal assignment moves every copy of a group divided by the cut to the side of its earliest record. The partition record gains `groups: {policy, n_groups, n_rows, moved_rows}`;
- the `split` decision draws whole groups for validation (a stratified or random split; an ordinal cutoff keeps identical rows together by construction), and its values report `duplicates: {policy, n_groups, n_rows, divided_groups}` (`divided_groups` is 0);
- the folds of `eda.single_feature_signal` are grouped (`StratifiedGroupKFold`, `GroupKFold`; `grouped_folds` in its values).

Every record keeps its own row key, and exposure counts rows. The data card reports the groups (`development.duplicates`) and so does `eda.quality` (`duplicates.records`). `status` and `source` say why the policy is chosen; it is almost always a `scenario_assumption`: a file rarely documents whether identical rows are one entity.

### Scenario defaults

```yaml
scenario_defaults:
  capacity_share:
    value: 0.1
    status: scenario_assumption
    source: 'Teaching scenario: the follow-up budget covers one finished session in ten.'
```

Optional (v0.2b, WP-B3, remark R6), for **teaching cases only**. `capacity_share` is the share of the scored rows the exercise assumes the team can act on (`0 < value <= 1`); its status must be `scenario_assumption` (`invalid_case` otherwise): a default capacity is never a fact about a business, and a real business case declares no default (a team figure, or an explicit per-decision delegation, is required). It is not a decision either: the view shows it (`view.scenario_defaults`), the agent asks the capacity as a share and shows the gain at 5, 10 and 20 % (`policy.evaluation` values `gain_points`), and when the adopted policy is `share:p` with `p` equal to this value, `not_yet_defensible` lists `capacity_assumed_for_exercise`.

### Prior-exposed rows

```yaml
prior_exposed_rows:
  path: data/prior-exposed-rows.txt   # row keys, one per line
  sha256: db0cdae76b7c…
  rows: 4521
  match: row_key
  status: observed
  source: Fact data_contains_sample; the bank-full.csv records that are bank.csv records
```

Optional (v0.2b, WP-B6a, review M2). It names the rows of the dataset that were already seen outside the study (a tutorial or a paper published results on them): `path` is a file inside the case directory (`..` and absolute paths are refused) listing their row keys, one per line; `sha256` its bytes; `rows` its number of keys; `match` is `row_key`, the only rule (the keys name records of this dataset). `status` and `source` say how the rows were identified; `prior_exposure` keeps the statement in words.

On load the file must exist (`dataset_missing`), match its sha256 (`dataset_changed`), and list `rows` distinct keys (`invalid_case`); at `init` a key that names no row refuses the study (`invalid_case`). These rows (and, under `duplicates: group`, every copy of them) are never sealed: a temporal final test is the last `fraction` of every row in the declared order less them, so the cut in time is unchanged and the final test is smaller; a stratified final test is drawn among the other rows. The partition record keeps `prior_exposed: {path, sha256, declared_rows, excluded_rows}`, and the status surfaces `final_test.excluded_prior_exposed` (CLI-CONTRACT §2, §12). Changing a split never makes an explored row unseen; this key makes sure the final test starts unseen.

Bank Marketing's full file declares the 4,521 `bank.csv` records (generated by `build_case.py`): 893 of them fall in its latest 9,042 lines, so its final test holds 8,149 rows (lines `L36171` to `L45212` less those 893) and its development rows are 37,062.

### Structure

```yaml
structure:
  row_unit:     {value: ..., status: ..., source: ...}
  group_column: {value: <column or null>, status: ..., source: ...}
  time_column:  {value: <column or null>, status: ..., source: ...}
  duplicates:   {value: <count of exact duplicate rows or null>, status: ..., source: ...}
```

`group_column` and `time_column` name a variable or are `null`. The variables with role `group_id` (respectively `time`) must be exactly that column.

## Capabilities

`load_case` validates the contract. `unsupported_capabilities(case)` then lists what this version cannot do, and `require_supported(case)` refuses with every reason. Each reason is structured:

```json
{"code": "unsupported_capability", "capability": "temporal split on a date or non-integer time column (v0.2)",
 "path": "structure.time_column", "column": "cycle_start_date", "reason": "..."}
```

| Condition | Capability |
|---|---|
| `structure.time_column.value` names a variable whose type is not `integer` (a date, a decimal number) | `temporal split on a date or non-integer time column (v0.2)` |
| Two records have the same content (`data.row_index`, at `init`), and the case declares no `duplicates: {policy: group}` | `duplicate records (v0.2)` |
| A target cell is missing (`data.check_values`, at `init`) | `missing target values (v0.2)` |

Since M3, `binary` and `regression` tasks are supported, and a declared time column of type `integer` is supported: the study splits it by an ordinal cutoff (`{"method": "ordinal_cutoff", "column", "cutoff"}`, `CLI-CONTRACT.md` §5), reading its values as integers, never as dates.

There is no silent fallback: a declared time column is never handled by a random split (an `ordinal_cutoff` split is then the only method), a date time column is refused rather than converted, and a regression target is never reframed as a classification. A time or group column is "declared" whatever its status, because a `scenario_assumption` of dependence is enough to invalidate a random split.

**Limitations (not refusals).** `limitations(case)` names capabilities a supported case lacks: a declared group column (`structure.group_column.value` not null) gets `grouped split (v0.2)`. The case is accepted, but nothing keeps a group's rows on one side of the split: every split reports the group values its partitions share (`split.values.groups`), and the study lists `grouped_split_unsupported` under what is not yet defensible. Independence across partitions is never claimed silently.

## Errors

`CaseError.to_dict()` returns `{code, message, problems?, details?}`. `problems` is a list of `{path, problem}` with dotted paths such as `variables[3].availability.status`.

| Code | When |
|---|---|
| `invalid_case` | Schema violation, row count or header mismatch |
| `confirmed_status_forbidden` | A confirmation is claimed anywhere |
| `dataset_missing` | Dataset file absent or outside the case directory |
| `dataset_changed` | sha256 mismatch; `details` gives both digests |
| `invalid_case` (values) | A numeric cell that is not a number, or an undeclared binary target label (see [Dataset](#dataset)) |
| `unsupported_capability` | Valid case, missing capability; `details.reasons` |

## Migration block

A case produced from a companion `project.json` carries:

```yaml
migration:
  from: project.json
  from_schema: hypotrail.project/1
  from_sha256: <sha256 of project.json>
  supplement: case-supplement.yaml        # when present
  supplement_sha256: <sha256>
  tool: mlkit.study.migrate
  tool_version: 1
  rules: [ "<path>: <mapping applied>", ... ]
  notes: [ ... ]
```

`rules` records every non-trivial mapping, so a reviewer can see each status that changed and why.

## Migration from a companion project

`project.json` and `results.json` are companion tutorial contracts. They stay untouched. `python -m mlkit.study.migrate use-cases/<id> --write` regenerates `case.yaml`, and `--check` reports drift. Committed cases are regenerated in tests and must match byte for byte, so a case is changed by editing its inputs, never by hand.

| Companion status | Companion source | Case status |
|---|---|---|
| `confirmed` | tutorial or scenario | `scenario_assumption` |
| `confirmed` | dataset documentation (the word "documentation", or a file shipped next to the dataset) | `documented_fact` |
| `confirmed` | anything else | `scenario_assumption` |
| `proposed` | any | `scenario_assumption` |
| `unknown` | any | `unknown` |

- `available_at_prediction: yes` becomes `available_at_prediction` / `scenario_assumption`; `no` becomes `not_available` / `scenario_assumption`; `unknown` stays `unknown`.
- Every data column receives an entry. A column that `project.json` does not describe has status `unknown` and availability `unknown`, unless the supplement documents it.
- Companion role `excluded` becomes `feature`: exclusion is a study decision. Companion role `group` (a reporting breakdown) becomes `feature`.
- Companion labels, `{{…}}` template placeholders, journeys, and activities are not carried over. A placeholder that survives the supplement makes the migration fail.
- `results.json` protocols become `prior_exposure` entries with status `observed`: their rows are not unseen.
- An unknown status, availability, role, type, or problem type makes the migration fail instead of guessing.

### Supplement

What `project.json` does not carry comes from `use-cases/<id>/case-supplement.yaml` (`hypotrail.case-supplement/1`): reading parameters (`sep`, `header`, `quotechar`, `na_values`, `column_names` for a headerless file), the positive label, line-cited documentation of columns, fact and structure overrides, extra `prior_exposure` entries, and notes. Rules:

- a supplement never records a confirmation;
- every `documented_fact` in a supplement cites an existing use-case file as `path:line`, with a line number inside that file;
- availability may be a `documented_fact` only with value `not_available`. In Bank Marketing this applies to `duration` alone: `data/bank-names.txt:56,60` documents it as the duration of the last contact of the current campaign.

The supplement may set `group` and `labels` per variable (v0.2a, WP-A4); Bank Marketing and Auto MPG do, and their `case.yaml` is regenerated from it (the dataset sha256 is unchanged; the case file sha256 changes, so a study created on the previous case file reports `sources_changed`).

## Committed cases

| Case | Task | Capability check |
|---|---|---|
| `use-cases/bank-marketing/case.yaml` | `binary` | supported |
| `use-cases/auto-mpg/case.yaml` | `regression`, time column `model_year` (integer), group column `car_name` | supported (M3); limitation `grouped split (v0.2)` |
| `use-cases/breast-cancer-wdbc/case.yaml` | `binary`, 30 numeric features, no time or group column; generated by `prepare.py`, data copied from the installed scikit-learn (not committed) | supported |
| `use-cases/online-shoppers/case.yaml` | `binary`, 125 repeated rows under `duplicates: {policy: group}`, `scenario_defaults.capacity_share` 0.1; generated by `build_case.py`, data committed | supported |
| `use-cases/bank-marketing-full/case.yaml` | `binary`, `order: {by: line}` (temporal final test), `prior_exposed_rows` (the `bank.csv` records, 893 of them kept out of the final test), `scenario_defaults.capacity_share` 0.1; generated by `build_case.py` from the Bank Marketing case, data committed | supported |
| `use-cases/diabetes/case.yaml` | `regression`, no time or group column; generated by `prepare.py`, data copied from the installed scikit-learn (not committed) | supported |

A case without a companion `project.json` may be written by a generator script next to it, which builds the document in code and is the only way the YAML changes (`--check` compares the committed file with a fresh generation; the case tests run it). v0.2b's two cases use `build_case.py` (committed data, which must be present, plus `--verify`, the integrity checks of the data against the figures their source publishes); the scikit-learn cases use `prepare.py` (below). A generated case follows this contract exactly as a migrated one; it has no `migration` block.

A case generated by a use case's `prepare.py` (data whose redistribution terms are not stated) commits `case.yaml` and the script, never the data: `prepare.py` copies the data into an ignored `data/` folder, `prepare.py --check` compares the committed `case.yaml` with a fresh generation, and `scripts/check_layout.py` lists such a dataset as not materialized when it is absent.
