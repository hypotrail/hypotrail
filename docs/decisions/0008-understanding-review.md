# ADR 0008: An opt-in understanding and handover review

- Status: accepted for implementation, implemented as v1 (23 October 2026); not adopted as an
  organisational rule. Pedagogical value not established.
- Date: 23 October 2026
- Source: SPEC-COMPREHENSION v1.0 (sha256 `344e5ebaf6fb9a1f056914ccd91a85312ecef8723037bc339c87709e521e4149`)
  and its independent review. The spec was written against `506180a`; this ADR records the
  differences with the checkout it was implemented on (`1f8ff48`).
- Contracts: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) §16,
  [understanding guide](../understanding/README.md),
  [handoff](../handoff/UNDERSTANDING-V1.md).

## Context

Work produced with generative AI can be correct and still not be understood by the team that
keeps it. The aim is narrow: the author can explain the decisions and behaviours that
matter, a colleague can take the critical parts over, and a reviewed synthesis is versioned
with the work. The mechanism must not become a quiz, a grade, an AI filling a form for a
person, or a claim about competence, security or scientific validity.

## Decision

1. **Four things kept apart.** Guided learning (the existing `learn` cards and training
   mode stay as they are: answers local to the panel, never sent to the engine),
   demonstration of understanding (attempts reviewed by a person against a rubric), handover
   (a colleague's own task on the repository and the handover note), and authorisation of a
   milestone (a gate under a required policy). No global score; a dimension has a status, a
   freshness, an assistance summary, an evidence availability and an assurance, as separate
   axes.
2. **Off by default.** A study without the `understanding` extension of its state is `off`
   and behaves exactly as before (`export handoff` included). `coaching` gives the tools
   without blocking; `required` blocks only the milestones the policy names. The only
   protected action the engine has is `export handoff`, so `handoff` is the only milestone;
   other names are refused rather than checked by a control that does not exist (no Azure
   deployment gate is invented).
3. **One authority: the study store.** The review is an optional extension of
   `hypotrail.study/1` (`understanding`, schema `hypotrail.understanding-state/1`), written only
   through `StudyStore.execute` with request ids and expected revisions. Answers, documents
   and decisions are immutable local blobs; the revision log carries their digests only. No
   second database, journal or service.
4. **Assurance is `human_declared`.** A review attributed to a person by a local declaration;
   `external_verified` is refused (`unsupported_assurance`) until a tested attestation adapter
   exists, never lowered. The policy is cooperative: whoever can change the repository or the
   state can bypass it. The engine never creates a human decision; a proposal (agent, model or
   person) is stored as a proposal. Test fixtures mark their humans `simulated`, and every
   result built on them says so.
5. **The gate is computed where it is used.** `understanding check` is informative. In a
   required policy, `export handoff` reserves the milestone under the writer lock after
   computing the gate again on the reread state and a fresh capture of the sources, renders
   from that revision, revalidates under the lock, and publishes only when nothing relevant
   changed; otherwise the written folder stays a `.candidate`. This is the one change to the
   C7 contract: in a required policy the export records a reservation and its outcome (two
   revisions) and re-renders the deliverables.
6. **Freshness by dependency, without circularity.** A capture freezes the mapped repository
   sources (their bytes are stored) and digests two projections: the local snapshot (private
   entries included) and the public source scope (Git entries only, private ones as opaque
   references). Review artefacts, logs, times and revision numbers are outside both, so
   adding a review never stales its own sources nor any ML result. Rubrics declare dependency
   keys; a change stales the linked dimensions; a missing source is `unknown`.
7. **Export as immutable generations with explicit consent.** The approval projection has a
   fixed list of fields; every contributor whose alias, rationale or contribution appears
   approves the same digest; any change invalidates every approval. Publication uses an intent
   in the store, a temporary sibling folder, `renameat2(RENAME_NOREPLACE)` (never a
   replacement) and a receipt. Git is a path the user drives: `git-plan`, explicit staging of
   the listed artefacts, `verify-export --target index`, an ordinary commit, `verify-export
   --target COMMIT`, an optional receipt. The engine never commits or pushes.
8. **Case content, not engine branches.** Each case ships `understanding.yaml` (rubrics per
   dimension, two variants per family, a handover task) whose prompts cite the study by
   references resolved at capture; a missing reference is a missing prerequisite. The banks of
   Hotel booking, Bank Marketing and Auto MPG are drafted by the implementing agent and marked
   `to_qualify`: they produce no required result until a person reviews them.

## Differences between the audited base and the implementation checkout

| Spec assumption (`506180a`) | Checkout (`1f8ff48`) | Effect |
|---|---|---|
| Library and Azure workstreams not merged | Both merged (`hypotrail_runtime`, `export azureml`) | Not used: the review reads no runtime contract and depends on no extra; `export azureml` is not a milestone. |
| `export handoff` never changes the study | Unchanged when off or coaching | Required policy: reservation and outcome revisions (decision 5). |
| Canonical JSON | `hypotrail_runtime.canonical` exists (floats allowed) | The review has its own canonical v1 (decimal objects, no raw float), as the spec requires. |
| `learn.yaml` and the panel's local learn cards | Unchanged | Not read, not migrated; the panel is untouched (A23). |
| J0 `assurance` object (`status --summary`) | Present | Unrelated name: it concerns analytical reliability, not the review. |
| TaskSpec field `prerequisite_refs`, "bank" | The engine's guard tests forbid dataset names as substrings in `mlkit/study` (`site_ref`, `bank`) | The field is `required_refs` and the task bank is a *task set* (`taskset.py`, `hypotrail.understanding-tasks/1`); same meaning. |

## Consequences

- The review costs time; a workshop session covers a few dimensions, not the policy.
- A demonstrated and current dimension says what a declared reviewer judged on evidence at a
  context; it does not certify the person or the code.
- Long-term retention, pedagogical value and organisational robustness need a pilot with
  real people (spec §20); no test establishes them.
- Evidence is kept durably; `purge_after_days` is refused; deleting payloads by hand keeps
  the historical judgement and marks the evidence unavailable.
