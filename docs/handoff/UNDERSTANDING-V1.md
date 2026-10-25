# Understanding and handover review v1: handoff and acceptance

Status: **implemented and tested locally, off by default; not adopted, not piloted.**
Spec: SPEC-COMPREHENSION v1.0 (sha256 `344e5ebaf6fb9a1f056914ccd91a85312ecef8723037bc339c87709e521e4149`).
Decision: [ADR 0008](../decisions/0008-understanding-review.md). Guide:
[docs/understanding/README.md](../understanding/README.md). Contract:
[CLI-CONTRACT §16](../specs/CLI-CONTRACT.md).

Base: `1f8ff48` (main after the library and Azure integration). The spec was written against
`506180a`; the differences that matter are listed in the ADR (both workstreams merged but not
used; `export handoff` changes only under a required policy; the review has its own canonical
JSON; the learn cards and the panel are untouched).

## What was delivered

| Area | Where |
|---|---|
| Canonical JSON v1 (decimal objects, refusals, vectors) | `framework/mlkit/study/understanding/canonical.py` |
| Policy `hypotrail.understanding-policy/1` (off, coaching, required; refusals) | `understanding/policy.py` |
| Task banks and rubrics per case | `use-cases/{hotel-booking,bank-marketing,auto-mpg}/understanding.yaml` (`to_qualify`); simulated fixtures in `framework/tests/fixtures/understanding/` |
| Snapshot, source manifest, local and public projections, freshness | `understanding/snapshot.py` |
| State extension, actions through `StudyStore.execute` | `understanding/model.py`, `understanding/actions.py` |
| States, conflicts, reservations, arbitration, peer coverage, gate | `understanding/evaluate.py` |
| Approval projection, JSON/Markdown/manifest, immutable publication | `understanding/export.py` |
| Standalone verifier, Git reading, plan, staging helper, commit receipt | `understanding/verify.py` |
| Required `handoff` milestone protocol | `understanding/milestone.py`, `cmd_export.export_handoff` |
| Report section "Understanding and handover" | `understanding/render.py`, `render_html.build(understanding=...)` |
| CLI `hypotrail understanding ...` | `framework/mlkit/study/cmd_understanding.py`, `cli.EXTENSIONS` |
| JSON Schemas (generated, checked) | `understanding/schemas/*.schema.json`, `understanding/schemas.py` |
| Examples (policies, sources, handover, review template) | `docs/understanding/examples/` |
| Tests | `framework/tests/study/understanding/` (112 tests), `test_contract_freeze.py` |

Not delivered: an LLM proposal adapter (lot 6, optional: proposals are accepted from any
author as validated data, none is generated); a managed notebook summary (the report has the
section; the notebook is unchanged); an external attestation adapter (`external_verified`
refused); automatic purge (`purge_after_days` refused); agent instruction files for the review
(the guide documents the workflow; the installed study instructions are unchanged).

## Kinds of evidence

* **Automatic tests** (unit and real CLI processes in-process): every row below marked "test".
* **Simulated humans**: every reviewer, peer and arbiter in the tests is a fixture with
  `simulated: true`; results built on them carry `simulated_human_decisions`.
* **Real Git**: the Git path runs real `git` in temporary repositories (index, commit, clone).
* **Not done**: any session with real people, a review of the rubrics by an ML referent, a
  pilot, a VS Code or Copilot session. No pedagogical benefit is claimed.

## Acceptance criteria A01–A31

| Id | Status | Evidence |
|---|---|---|
| A01 | test | `test_policy_plan.py::test_off_by_default_adds_nothing`; render without the section (`test_render_cases.py`); the panel's learn cards are not touched |
| A02 | test | `test_policy_set_logs_both_digests_and_reason`; refusals without fallback (parametrised) |
| A03 | test | `test_plan_shows_coverage_and_critical_dimensions_stay` |
| A04 | test | `test_workflow.py::test_first_attempt_is_immutable_and_coaching_marks_help` |
| A05 | test | `test_proposal_never_creates_a_human_decision` |
| A06 | test (mechanics) | `test_keyword_rubric_is_not_a_matcher`; the pedagogical validity of rubrics needs people |
| A07 | test | `test_missing_mandatory_or_unevaluated_dimension_blocks` |
| A08 | test | `test_peer_with_author_id_and_note_approval_are_not_a_handover` |
| A09 | test | `test_freshness.py` (code, transformation, security rule, decision) |
| A10 | test | `test_missing_source_is_unknown_not_current`, `test_review_activity_never_changes_the_source_digests` |
| A11 | test | `test_the_review_changes_no_scientific_record` |
| A12 | test | `test_concurrent_and_idempotent_submissions`, `test_late_review_against_a_changed_context_has_no_current_effect` |
| A13 | test (publication) | `test_generations_are_immutable_and_publication_survives_faults`; store interruptions reuse the existing StudyStore protocol and its tests |
| A14 | test | `test_export_is_canonical_private_and_concordant`, `test_every_contributor_approves_the_same_content` |
| A15 | test | `test_review_activity_never_changes_the_source_digests`, `test_real_git_path_index_commit_and_receipt` (code and proof in one commit), `test_modified_artefact_alone_is_detected` |
| A16 | test, real Git | `test_index_and_worktree_divergence_and_concurrent_staging`, `test_study_outside_moved_repository` |
| A17 | test, real Git | `test_verifier_reads_the_tree_and_runs_nothing` (commit read from objects, hook not run, symlink refused) |
| A18 | test, real Git | no commit or push by the engine; receipt after the commit is identified |
| A19 | test | refusals of `external_verified`, waivers (`test_waivers_are_refused_by_default`, `test_waiver_gives_allowed_by_waiver_never_allowed`), relaxed candidate policy not an authority |
| A20 | test, offline Chromium | section escaped, offline, 390 px light and dark, distinct from the verdict |
| A21 | test | case banks validated, no figure in prompts, results tasks wait for real results, no positive class for Auto MPG |
| A22 | test | answers absent from logs, state, outputs and errors; commands and file links refused; limits and depth |
| A23 | test | the human workflow with sockets forbidden and no API key; the panel's sources do not mention the review |
| A24 | test, simulated humans, real Git | `test_end_to_end_simulated_humans` |
| A25 | test | `test_direct_handoff_call_is_gated_and_check_is_not_a_token`, concurrent source, policy and decision changes leave a candidate |
| A26 | test, real Git clone | `test_clean_clone_public_integrity_and_honest_limits` |
| A27 | test | contradictions in both orders, arbitration, new rubric, active session not selectable, unrelated positive review |
| A28 | test | removed answer: judgement kept, unavailable, new review refused, milestone by `evidence_requirement`; `purge_after_days` refused |
| A29 | test | contributors' approvals; handover change stales the transfer; adding results does not |
| A30 | test | `test_canonical.py` (bytes and SHA-256 vectors, refusals) |
| A31 | test | fault injection at each write, before and after the rename, reconciling retry, same id other content refused, concurrent publications |

## Independent review of the code and fixes

A separate agent reviewed the diff read-only against the spec. Its ten major findings were
fixed, each with a regression test in `test_review_findings.py`: self-review and
overruling another reviewer on a critical dimension (refused; arbitration needed); the
arbitration choice limited to the conflicting decisions and binding for the gate
(`lost_arbitration`); peer coverage only from selected, completed, current and fresh
transfers (no search for an old pass); coaching carried over to linked sessions; an explicit
`--policy-file` checking assistance, reviewer distinctness, expiry and the review terms of
the embedded policy (`policy_differs`); the export receipt revalidated under the lock and
checked against the announced bytes; the required handoff recorded inside the lock that
publishes it, compared with the reserved digests, and released on failure; export possible
without a selection; Git plan and receipt checked against the announced bytes; the verifier
answering `invalid` on malformed artefacts. Minor findings fixed: raw floats and wrong shapes
in input files are refusals, duplicate criterion results refused, plan sources revalidated,
private verification limited to private entries, `core.fsmonitor=false`, untracked sources
reported, the publication path checked before creating folders, a rectified help re-opens the
dimension in status.

Left as documented limits: the policy's `role_policy.arbiters` aliases are published as part
of the policy; simulated reviews keep `allowed` with the `simulated_human_decisions`
limitation (tests need it; a real team must not use simulated declarations); switching to
`required` while an `export handoff` without `--expected-revision` is running can let that one
export through ungated (the switch is read before the lock); a crash between the rename and the
commit of the handoff record, inside the same lock, leaves a published folder with a
`reserved` record.

## Review of 24 October 2026: fixes (areas C and D)

Findings of [REVIEW-2026-10-24](../acceptance/REVIEW-2026-10-24.md), each reproduced by the
review's own adversarial tests, now kept in the repository as regression tests
(`framework/tests/study/understanding/test_adv_*.py`, helpers `advkit.py`; tests whose
expectation changed with a fix say so in their docstring).

* C-M1: assistance of a decision is `unaided` only when every cited attempt is unaided
  (`evaluate.assistance_summary`); one coached attempt makes it coached, so help is not
  laundered by citing a weak unaided attempt beside it.
* C-M2: `transfer_decision_map` values take one id or a list of distinct ids, so
  `team_coverage.minimum_people` of 3 or more can be met.
* C-M3: an arbitration is checked against the union of the session's and the current
  critical dimensions, and the gate re-checks every arbitration it relies on
  (`arbitration_not_admissible`): toggling the policy no longer lets the author arbitrate.
* C-M4: a mapped source unreadable at capture is kept with its role; `role:` dependency keys
  match it, so the dimension is `unknown`, not `current`.
* D-F1: the verifier recomputes the required contributors from the approval projection
  (author included) and checks the declared status against them.
* D-F2: local verification binds the artefact to a recorded export intent of the study (same
  review id, projection digest and session); an unrecorded generation is a problem and makes
  integrity invalid.
* D-F3: duplicate paths in a commit tree are refused.
* Minor: `start` and a full `export write` retry are replays; after a repository move,
  `check --repo` says it is a preview and `understanding relocate` records the new place,
  after which `check` and `export handoff` agree; completed (or abandoned) sessions refuse
  handover, transfers and proposals; a negative transfer review opens a reservation that only
  a later transfer review resolves; parties to a conflict cannot arbitrate it; an arbitration
  that settles reservations alone needs evidence, and its references are allowlisted; a
  session links only to the same person's; concurrent handoffs each publish (other handoffs'
  bookkeeping is not a relevant change) and a lost race is retried; the gated pack revision
  is documented (CLI-CONTRACT §16); a required policy requires at least one dimension; a
  waiver approved by the author is ignored; `rectify` is refused when off; a reserved export
  intent with the same hashes is reconciled; Markdown escapes `\r`, control and separator
  characters and every Markdown punctuation; `git diff` without rename detection;
  `git-stage` compares the staged blobs; foreign `rv-*` entries and leftovers are treated
  alike for every target; a symlinked path component is refused in the worktree; duplicate
  dimension ids are refused; zero mapped public sources read as `unknown`; the report
  section shows freshness per session; `verify-export` on a missing repository refuses.

## Review round 2: fixes (area D)

Regression tests: `framework/tests/study/understanding/test_adv2_d*.py` (the round-2
review's own probes; the GFM rendering checks skip without `cmarkgfm`).

* Local verification (`verify-export --study`) binds a generation to a recorded export
  intent by its three file hashes as well as its review id, projection and session: a
  generation edited outside the projection (approvals, times, base commit, renderer
  version) is `not_recorded` and invalid. A reserved intent whose bytes are present counts
  (an interrupted publication), and the next `export write` of the session gives such
  intents their receipt.
* The verifier refuses approvals by a non-contributor or several approvals by one person,
  a renderer version other than the engine's, a dimension id outside D1–D8, malformed peer
  coverage, digests that are not SHA-256 hex and an embedded policy the engine refuses.
  Every field rendered into the Markdown is escaped; `&` and `$` are escaped too and `@` is
  rendered as its own code span, so no GFM e-mail link, entity or math forms.
* A partial clone is refused (reading a missing object would fetch it and run the
  configured transport); `GIT_NO_LAZY_FETCH=1` is set for Git that honours it.
* `git-plan` sees staged submodule changes (`--ignore-submodules=none`) and reports a
  staged path that is not UTF-8 instead of crashing; a case variant of
  `docs/understanding` or of an `rv-*` folder is a problem for every target.
* Without an atomic rename without replacement, `export write` refuses with
  `unsupported_capability` (a retry where it exists reconciles the same export).
* Not changed, owner decision pending (D2-9): an approval binds a content digest, so content
  changed and changed back to an approved digest counts those approvals again. The test
  `test_withdrawn_content_revives_old_approvals` is a strict xfail until decided.

## Review round 2: fixes (area C)

Regression tests: `framework/tests/study/understanding/test_review_round2_c.py` (simulated
humans, temporary directories; several are the reviewer's reproducing tests, ported).

* C2-1: `understanding relocate` records a **move**: it needs `--author` and `--reason`
  (kept in the session's `relocations` history), the recorded repository must be gone, and
  `--repo` must be the top level of a Git work tree (checked by the CLI with `git rev-parse
  --show-toplevel`; the handler, which runs no Git, checks the old path is gone and the new
  one holds `.git`). The gate result (`repositories`) and `status` (`repository`,
  `relocations`) say which repository each session's freshness was read from. Residual,
  cooperative limit: nothing authenticates the content of the new place, so whoever
  controls the repository (or removes the original and relocates to a re-initialised copy)
  can still fake freshness.
* C2-2: the gate re-checks only the arbitrations it relies on: those whose conflict
  includes the selected decision, or that settle a conflict or resolve a reservation of the
  person and dimension in the selected decision's session. They must still be admissible
  under the current policy **and** the session's policy (C-M3 kept; `arbitrate` itself now
  also applies the session policy's arbiter list). An arbitration of a session the
  selection does not use no longer blocks for ever. (Corrected by round 3, R3C-1: the gate
  relies on any session's arbitration that closes a reservation or settles a conflict it
  counts; such an arbitration is now re-checked too, and can be settled again.)
* C2-3: the export projection computes `peer_coverage` with the gate's own function and
  loaders (`evaluate.selected_peer_coverage`, `service.gate_loaders`) from the latest
  selection of the session's author and profile; without one it is `missing`, never a search
  for any demonstrated transfer. The `export-valid` fixture did not change. (Round 3,
  R3C-3: the HTML report section uses the same selection-based coverage and gap rule.)
* C2-4: an arbitration refuses a reservation opened by a handover review.
* C2-5: such a reservation is resolved only by another transfer started after the failed
  review and on the current handover content.
* C2-6: `export handoff` tolerates, before the build, revisions that are only other
  handoffs' milestone bookkeeping (as the revalidation already did).
* C2-7 (**integrator default awaiting the owner's decision**): a transfer whose peer
  declared AI assistance (or no declaration) does not count toward the peer coverage of a
  dimension whose assistance rule is `unaided_required` (`peer_assistance_not_admissible`);
  under `aided_allowed` it counts.

## Review round 3: fixes (area D)

Regression tests: `framework/tests/study/understanding/test_review_round3_d.py`. `cmarkgfm`
is now a dev dependency, so the GFM rendering checks of `test_adv2_d.py` run in the gate.

* `verify-export --study` with a study that never enabled the review reports the
  generation as not exported by that study (`not_recorded`, invalid), never a silent skip.
* Git replace objects are ignored (`GIT_NO_REPLACE_OBJECTS=1`) by the verifier, `git-plan`,
  `git-stage`, `git-receipt` and the relocate check: the bytes read are those the tree names.
* The verifier requires the manifest to be exactly the one of the published JSON and
  Markdown, every alias (author included) to be a declared id, and one peer coverage entry
  per dimension.
* An unreadable source's gap names its logical key (a string, as the schema says).
* A retry removes the temporary folder of a publication killed before its rename once it is
  older than a minute (a younger one may belong to a live concurrent publication).
* A run of `@` is one code span, so the rendered text keeps its characters.

## Review round 3: fixes (area C)

Regression tests: `framework/tests/study/understanding/test_review_round3_c.py` (simulated
humans, temporary directories; the reviewer's reproducing tests of round 3 are ported with
the expected outcome of each fix).

* R3C-1: the gate counts reservations and conflicts in every session of the person, so it
  re-checks every arbitration it relies on in any session (`evaluate.arbitration_checker`:
  admissible under the policy it applies and under the arbitration's own session policy).
  A non-admissible one settles nothing: the reservation or conflict counts again, with
  `arbitration_not_admissible`. An arbitration nothing relies on is never asked (C2-2's
  property, in its corrected form). So that this never blocks for ever, such a reservation
  can be settled again: `arbitrate` (now also on an `abandoned` session), `review`
  (`resolves_reservation_ids` with a new variant) and `task`/`submit` treat it as open; the
  replaced resolution stays in `previous_resolutions`. Expectation changed:
  `test_review_round2_c.py::test_an_old_arbitration_of_an_unused_session_does_not_block_for_ever`
  (round 2 allowed a session 1 arbitration by an arbiter v2 no longer names; the gate
  relies on it, so it now blocks until the arbiter v2 names settles it again; its docstring
  says so).
* R3C-2: with a selection of the session's author and profile, the export projection's
  dimensions and the report's rows are the decisions it maps (`evaluate.shown_decision`),
  the ones the gate judges; without one, the history's latest decision of the session, and
  `coverage_selection` is null (a selection of another profile was published before). The
  verifier refuses a document whose dimension `human_review_ref` differs from
  `coverage_selection.dimension_decision_map` for a mapped dimension: `public_integrity`
  invalid, since the document contradicts itself and the engine never writes it (chosen
  over `nonconforming`, which judges a coherent document against a policy). The check lives
  in `export.validate_review`, the closed-schema check of the verifier. The `export-valid`
  fixture did not change (its selection maps the latest decisions).
* R3C-3: one peer gap rule (`evaluate.peer_gap`) for the gate, the export and the report:
  fewer declared people than `team_coverage.minimum_people`, or not `current`.
* R3C-4: a handover resolves a handover reservation on a dimension whose assistance rule
  is `unaided_required` (in the policy in force or the session's) only when its peer
  declared no AI assistance (`evidence_invalid` otherwise), the C2-7 rule. The gate applies
  it again under the policy it uses (`peer_assistance_not_admissible`), so a resolution
  recorded under a looser rule does not settle the reservation under a stricter one; a later
  unaided handover resolves it again.
* R3C-5: two `export handoff` without `--out`, rendered at the same revision, both publish:
  the second one into `handoff/revision-N-<reservation>` (eight hex characters of its
  reservation id). With `--out`, the folder given stays the only target, never replaced.
* R3C-6: under `payloads_available`, a selected transfer whose peer answer blob is gone does
  not count (`evidence_unavailable`); under `recorded_decisions` it counts with the
  limitation `evidence_not_reauditable` (A28); local verification reports the evidence as
  unavailable.

## Gate run

Run in this container (Python 3.13, uv 0.11, the `dev`, `browser` and `azureml` groups and the
`diagnostics` and `uncertainty` extras), commands of [CONTRIBUTING.md](../../CONTRIBUTING.md):

| Command | Result |
|---|---|
| Engine pytest line (pilot, quality, discovery, reliability, classical, env, synthetic case, `framework/tests/study`, `acceptance`, `exporters`) on `149d906` | 2220 passed, 100 skipped, **2 failed**: the two guards that forbid dataset names in `mlkit/study` (`test_study_engine_contains_no_dataset_specific_names`, `test_the_engine_names_no_dataset`) matched "bank" and the substring `site_ref` of `prerequisite_refs` |
| After the rename (`taskset`, `required_refs`): the two guards, `test_contract_freeze.py`, `test_isolation.py`, `test_export_handoff.py`, `framework/tests/study/understanding` | 303 passed, 1 skipped (`jsonschema` absent; run once with `uv run --with jsonschema`: passed) |
| `node --test clients/vscode-companion/test/*.test.js` | 239 passed, 0 failed (the client is unchanged) |
| Panel pytest (pixel baselines deselected, they depend on fonts here) | 390 passed, 0 failed |
| `python3 scripts/check_layout.py` | no error |

The whole engine line was not rerun after the rename: the rename touches only the review
package, its CLI module, its test files and the case task sets.

## Limits and human validation still needed

* Assurance is `human_declared`; nothing proves a real person answered or reviewed.
* The banks are drafted by the implementing agent: an ML referent and the person in charge of
  handovers must review and qualify them before any required result.
* Freshness depends on the explicit source mapping: an unmapped relevant file is not seen.
* The verifier trusts Git plumbing; it does not authenticate commits.
* The pilot of spec §20 has not been run; durations and usefulness are unmeasured.
