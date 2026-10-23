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
