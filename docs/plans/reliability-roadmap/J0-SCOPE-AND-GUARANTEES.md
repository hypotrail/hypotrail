# J0 — Scope, evidence and guarantees

Depends on: no implemented milestone. Read [COMMON.md](COMMON.md) first.
Review coverage: B1, B2; groundwork for all other findings.

## Outcome

The engine and documentation state what a study can establish. The implementation
model has a current, testable backlog rather than treating every review statement
as a current defect or every existing test as a proof of validity.

## Current implementation anchors

- `framework/mlkit/study/state.py`, `commands.py`, `cli.py`: study creation,
  settings, decisions, strict keys and command arguments.
- `framework/mlkit/study/case.py`, `data.py`: case schema and source verification.
- `framework/mlkit/study/partition.py`, `view.py`, `junior.py`: reserved-test state,
  derived summaries and junior language.
- `framework/mlkit/study/agent_files.py` and `agent/`: generated instructions;
  `fe42ffd` and `57d75fc` already added R40 and R39 after the reviewed commit.
- `use-cases/hotel-booking/build_case.py`, `README.md`, `case.yaml`: derive contract
  changes from the case builder, never patch the generated YAML alone.
- `docs/handoff/IMPLEMENTATION.md`, `docs/specs/CASE-CONTRACT.md`,
  `docs/specs/CLI-CONTRACT.md`, ADRs 0006/0007: claimed behavior and historical choices.

The attached review reproduced future training, the known late Hotel predictor,
final opening without diagnostics and unrestricted old-code equivalence at a41c851.
The inspected diff to 8672917 changes agent instructions and generation tests; it
does not establish that those engine findings were fixed. This is code inspection,
not a rerun of those experiments.

## Ordered work packages

### J0.1 — Reconcile the evidence ledger

Create `docs/acceptance/reliability-roadmap/FINDINGS.md` with one row per review ID.
Columns: review finding, current code location, current behavior, evidence type,
reproduction/test, status, owner milestone, residual limitation. Allowed statuses:
`confirmed_open`, `fixed_and_verified`, `partially_fixed`, `accepted_limit`,
`not_retested`. Start uncertain rows as `not_retested`.

Do not rerun the review's raw Hotel holdout-reading probe. Convert bypass probes to
temporary synthetic examples. Do not copy tests that fabricate a human confirmation
into a product workflow; they demonstrate the cooperative trust boundary only.
Preserve already implemented prompt compaction, next-action payloads, guided-mode
handling and diagnostic speed improvements unless a failing requirement justifies
a change.

### J0.2 — Add the opt-in contract scaffolding

Implement COMMON C2/C3's settings flag, init option, schema validation and optional
case analysis contract. Require numeric/integer non-target timing columns when
declared; enforce enums and required provenance. Reject unknown keys and target-as-
clock/group configurations. Do not yet claim J1's protocol algorithm exists.

An early `review-v1` study may initialize and display a plan, but attempting an
unimplemented capability MUST return `unsupported_capability`, with the missing
capability named. No fallback to the legacy temporal algorithm.

Expose additive `assurance` in `status --json` and the selected summary fields:

```json
{
  "profile": "review-v1",
  "evaluation_protection": "protocol_reserved",
  "consent_provenance": "agent_reported",
  "cross_study_history": "not_enforced",
  "analysis_contract_status": "present",
  "claim_scope": ["retrospective_association"]
}
```

`analysis_contract_status` is `present|absent`; `claim_scope` reflects the ceiling,
not eligibility. Derive labels from this structure in all later surfaces. Keep the
machine identifier `sealed` for compatibility, but junior wording must explain that
the local source file remains accessible. `authenticated: false` must not become
true merely because Copilot used a choice picker.

### J0.3 — Bound the teaching cases

- Hotel: record `intended_use: leakage_exercise`; claim ceiling
  `retrospective_association`; retain the snapshot limitation, uncertain timing,
  public/prior exposure and arrival-based historical split. Display “Performance
  at booking is not established” / “La performance à la réservation n'est pas
  établie.” No inference that dropping a few obvious leak columns cures the snapshot.
- Bank full: use `retrospective_comparison` unless a documented prediction/label
  timing contract actually exists. Its campaign order supports an ordered exercise;
  it does not prove that every earlier outcome was available when acting later.
- Auto MPG: bounded retrospective regression, target unit mpg, dependence assumptions
  explicit. Do not turn model year into a prospective guarantee.
- Synthetic: provide one independent fixture and one future-prediction fixture
  with known prediction and label-availability clocks for J1. Fixtures are versioned
  test inputs, not confirmed human decisions.

Case changes can invalidate old source fingerprints. Do not add an equivalence
exception for a substantive scenario change. Verify old-state loading with an
unchanged copy of the old case in a temporary fixture; report source changes honestly
when the original study points at a changed file.

### J0.4 — Align documentation and proposed decisions

Update the handoff's stale statements only when supported by code or the new scope.
Record the design amendment for Hotel's instructional claim and ADR 0006's cooperative
protection. Add pending amendments for ADR 0007 changes in J1–J3; do not mark future
implementation accepted/verified merely because the spec exists.

No rebranding of all completed work as broken: distinguish integrity guarantees,
methodological gaps, ergonomic defects and intentionally unimplemented security.

## Acceptance

| ID | Setup/action | Expected result |
|---|---|---|
| J0-A01 | Load old fixture without profile | Bytes and revision unchanged; derived profile is legacy |
| J0-A02 | Init with explicit review-v1 on valid synthetic case | New settings and contract visible; no decision preconfirmed |
| J0-A03 | Unknown profile, clock column, target clock, invalid enum | Structured refusal, no half-created successful study |
| J0-A04 | Missing analysis contract | Inspection possible; claims incomplete; fitting requiring it refused |
| J0-A05 | Show Hotel data card, plan and summary | Booking-performance limitation present before any model score |
| J0-A06 | Synthetic local file accessible while reserved | Assurance remains cooperative; no claim of filesystem isolation |
| J0-A07 | Choice-picker confirmation | Stored channel choice, verbatim words; authentication still false |
| J0-A08 | Read source-change status on an older changed case | Explicit source change; no automatic case rewrite/allowlist |
| J0-A09 | Generate Claude and Copilot files | R39 proposal quote and R40 picker/text fallback retained |

Suggested tests: `test_review_j0_contracts.py`, existing `test_case.py`,
`test_sources_changed.py`, `test_agent_files.py`, `test_contract_freeze.py`.

## Completion and exclusions

Complete when the ledger, scaffolding, case scope and automated acceptance pass.
Do not implement protected storage, authenticate user messages or retrofit all
historical studies. J0 supplies honest boundaries; J1–J6 supply the new guarantees.
