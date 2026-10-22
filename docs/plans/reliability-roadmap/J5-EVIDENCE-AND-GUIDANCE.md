# J5 — Context-bound evidence and engine-produced pauses

Depends on the contracts of J0–J4; integration acceptance requires those milestones.
Review coverage: I9, proposals A+B, localization and false numeric refusals.

## Outcome

The agent receives a short, localized explanation it can relay accurately, with
figures bound to their population and decision context. Natural adoption remains
possible, but understanding, silence and a question do not become consent.

## Current implementation anchors

`cite.py` already supports result/slot tokens and numeric paths; extend it rather
than replace it with global string substitution. `numtrace.py`, `wordnum.py`,
`cmd_check.py` check numbers/wording. `junior.enrich`, `view.py`, `content/*.yaml`,
`cmd_explain.py`, `confirm.py`, `agent_files.py` and `agent/` provide guidance.
`status --summary --fields` and mutation `next_action` already exist: preserve them.

## J5.1 — Canonical evidence references

Add a structured reference schema `hypotrail.evidence_ref/1`:

```json
{
  "schema": "hypotrail.evidence_ref/1",
  "result_id": "<immutable registered ID>",
  "path": "<existing cite.py value path>",
  "dataset_sha256": "<dataset digest>",
  "partition": "development",
  "population_digest": "<digest of exact ordered scored keys>",
  "metric": "precision",
  "model": "fit.logistic",
  "rule": "share:0.1",
  "unit": "fraction"
}
```

This schema wraps the existing immutable ID; do not add an independently mutable
“result version.” Result identity already covers input and output hashes. Optional
fields can be null only when irrelevant (e.g. no rule for a distribution). For a
comparison, reference the registered comparison result/path and both source result
IDs; do not compute a difference in free prose with no registered provenance.

Resolve metadata from the registry and input lineage. Caller-supplied context must
match; it is not evidence. A result slot may be used when building a draft, but the
produced reference binds the exact result ID. A later slot replacement must not
silently retarget an already issued reference.

Failures distinguish unknown ID, invalid path, wrong population/partition/rule/unit,
integrity failure and unavailable currency. A historical reference is allowed only
inside an explicitly historical statement and never satisfies a current adoption
claim. No partial rendering substitutes zero or removes a failed reference silently.
Keep the last valid artifact and mark the attempted generation failed.

## J5.2 — Structured statements for sensitive conclusions

Define a small whitelist of statement kinds with deterministic EN/FR templates:

- `metric_observed`: metric, source reference, population and period;
- `comparison_observed`: registered paired difference and reference model;
- `criterion_assessment`: J3's convention, status and uncertainty scope;
- `calibration_description`: observed bins/Brier with their scope, no general guarantee;
- `limitation`: stable limitation code and its evidence/source;
- `next_action`: recommended action and reason.

Each template receives checked references and typed parameters. It cannot call a
development score “final”, a retrospective association “future validation”, or a
targeting result “annulations prevented.” Enforce claim eligibility from J2.

Free discussion remains allowed. The checker flags empirical numbers without a
reference or a declared non-empirical category: confirmed decision value, case fact,
protocol parameter, illustration, or axis scale. Preserve these categories separately;
do not allow a generated empirical result to evade checking by setting `illustrative`
in arbitrary prose. Engine-authored illustrative templates carry their origin and
remain labelled as examples. Number-free causal language also needs a warning.

Extend FR/EN wording fixtures, including “Cette politique évite les annulations”
and “This policy prevents cancellations.” A lexical checker is only a warning aid:
recognize quotations/negations for the tested cases, and disclose incomplete coverage.
Do not claim unrestricted semantic verification. Output “No anomaly detected by the
implemented checks” / “Aucune anomalie détectée par les contrôles implémentés.”

## J5.3 — One formatting implementation

Canonical values stay in stored units. A single formatter handles EN/FR decimals,
thousands, signs, percentages, percentage points, interval bounds and undefined
values. Reuse it across chat payloads, report and notebook; the panel consumes the
formatted value or identical declared formatting metadata.

Examples required in tests:

- fraction .353 → `35.3%` EN / `35,3 %` FR;
- fraction difference .05 → `5 percentage points` / `5 points de pourcentage`;
- integer 37062 → `37,062` / `37 062` (narrow no-break space);
- a declared sentinel -1 is a case fact, not an uncited model result;
- null precision → “undefined: no selected observations,” not `0%`;
- all three references of an interval share metric, model, population and units.

Correct the canonical AP definition: a weighted sum of precisions over increases in
recall; do not equate it with arbitrary trapezoidal PR area. Fold spread is not a
confidence interval. These corrections apply to both language dictionaries.

## J5.4 — A pause payload the agent can relay

Add `next_action.pause` while preserving existing action/decision identifiers and
legacy keys for compatibility:

```json
{
  "schema": "hypotrail.pause/1",
  "kind": "decision",
  "language": "fr",
  "revision": 42,
  "position": {"step_id": "policy", "completed": 3, "total": 6},
  "learned": [{"statement": "<typed statement>", "refs": []}],
  "limitations": [{"code": "development_only", "text": "<localized>"}],
  "proposal_id": "<pending proposal ID>",
  "proposal_text": "<exact decision being adopted>",
  "recommended_option": "adopt",
  "options": ["adopt", "change", "explain"],
  "question": "Adoptez-vous cette décision ?",
  "evidence_refs": [],
  "detail_topics": ["metric", "uncertainty"]
}
```

Numbers and IDs above illustrate shape only. `kind` is `decision|action|explanation|
blocked|complete`. A decision pause must name a real current proposal before adoption
is possible. A proposed default without a proposal ID is an action to prepare a
proposal, not a confirmation request. Action/complete pauses have no adoption
question. Completed/total counts are computed from the current plan, not fixed text.

The primary rendered pause SHOULD fit 150 words, excluding collapsed evidence and
full proposal details. This is an ergonomic target, not a validity guarantee. Never
truncate the proposal or a critical limitation to satisfy a word counter. Put
additional explanation behind existing `explain` topics and stable evidence links.
Introduce the statistical term before its contextual example.

The compact path is the existing mutation's `next_action` and targeted status fields;
do not add a new mandatory status call after every successful mutation. If a caller
needs more, it requests the detail explicitly. Limit routine payload growth by not
embedding all predictions, coefficients or historical registry entries in a pause.

## J5.5 — Interaction state machine

| User action | Required effect |
|---|---|
| Explicit adopt/yes to the immediately shown proposal | Confirm exact ID and expected revision with verbatim words |
| “I understand” / “j'ai compris” | No adoption inferred; short closed adoption question if needed |
| Explain | No decision mutation; explain current proposal, then return to the same pending choice |
| Change | Ask one useful change question or create replacement proposal; old ID cannot be adopted as current |
| Conditional/partial/negative answer | No whole-proposal adoption; clarify only the unresolved part |
| Old picker response after another mutation | Stale revision/proposal refusal; show refreshed context |
| Resume in fresh chat | Read state and pending action; no replay of already valid decisions |
| No decision required | Continue routine authorized work; no empty confirmation pause |

R39: show the quoted decision before the adoption question. R40: Copilot uses the
single-select choice picker when available and records channel `choice`; otherwise
use text. Localize the picker in English studies too; do not preserve a hard-coded
French question across all languages. Choice-picker interaction remains agent-reported
consent, not independently authenticated consent. Preserve existing nondelegable
final-test adoption and mode-specific rules.

## Acceptance

| ID | Test | Expected |
|---|---|---|
| J5-A01 | Unknown/stale reference, bad path, mismatched rule/population | Distinct actionable failures; no fabricated replacement value |
| J5-A02 | Final .353 reference used in development statement | Context mismatch rejected even though number exists |
| J5-A03 | Correct reference in a causal statement | Unsupported claim flagged/refused in typed conclusion |
| J5-A04 | EN/FR numeric examples above, intervals and Unicode signs | Correct display and no false numeric refusals |
| J5-A05 | Same figure with two eligible sources | Explicit source remains bound; no arbitrary global numeric match |
| J5-A06 | Explain/change/resume/stale picker/understood-only | State-machine behavior above, no accidental confirmation |
| J5-A07 | Repeated render or status | Read-only; identical decision state |
| J5-A08 | Every pause kind in EN/FR | Terms, recommendation, useful question and limits; no raw agent boilerplate |
| J5-A09 | Large registry with many old results | Routine pause does not grow with registry size |
| J5-A10 | Existing result/slot tokens and old reports | Compatibility retained; stronger claims require new typed path |

Use new reference/guidance tests and existing `test_wp_c_junior_payloads.py`,
`test_guided_confirmation.py`, `test_partial_and_offtopic_replies.py`, numeric
tracing and agent-file suites. Do not declare semantic soundness from a finite list
of phrases. Update the CLI contract and freeze tests with the new payload.
