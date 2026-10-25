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
the embedded policy (`policy_differs`, replaced in round 5 by the gate's own policy digest
rule); the export receipt revalidated under the lock and
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

## Review round 4: fixes (area D)

Regression tests: `framework/tests/study/understanding/test_review_round4_d.py`.

* Every Git call runs without the caller's `GIT_*` variables (`GIT_DIR`, `GIT_INDEX_FILE`,
  `GIT_WORK_TREE`, `GIT_CONFIG_*`...), so a hook or a linked worktree cannot make the
  verifier or `git-stage` read or write another repository than `--repo`.
* A partial clone is accepted with Git 2.44 or later (`GIT_NO_LAZY_FETCH` makes a missing
  object an error, never a fetch); older Git is refused with that advice.
* `export write` writes `docs/understanding/.gitattributes` (`rv-*/** binary -filter
  -ident`; round 5 adds `-working-tree-encoding -eol`) when absent, and `git-plan` stages it with the generation: no autocrlf, eol
  conversion, LFS or other filter transforms a generation's bytes. A different file is left
  untouched and reported.
* Temporary folders of interrupted publications (any review id) are removed after a
  minute; a younger one is named in the `export write` output with what to do, and the
  verifier's problem says it is an interrupted export to delete.
* With a coverage selection, a dimension it does not map shows no review (the verifier
  refuses one that does).

## Review round 4: fixes (area C)

Regression tests: `framework/tests/study/understanding/test_review_round4_c.py` (simulated
humans, temporary directories; the reviewer's reproducing tests of round 4 are ported with
the expected outcome of each fix).

* C4-1: a `review` resolves an attempt reservation only with admissible help: on a dimension
  the policy in force or the session's makes `unaided_required` (the stricter wins), every
  attempt the resolving decision rests on is unaided (`evidence_invalid` otherwise;
  `evaluate.resolution_assistance_admissible`). The gate re-checks it under the policy it
  applies and the resolving decision's session policy, with the help known now:
  `reservation_state` returns `assistance_not_admissible` for a resolution it does not admit
  (recorded under a looser rule, or rectified afterwards), and the gate reports
  `open_reservation` and `assistance_not_admissible` (detail the reservation). Such a
  reservation is open again for `review`, `arbitrate`, `submit` and `task`, so an unaided
  answer to a new variant resolves it again. Expectation changed: the reviewer's probe
  `test_aided_attempt_resolves_an_unaided_required_reservation` asserted that the aided
  resolution was recorded; it is now refused at record time (its port says so).
* C4-2: one function, `evaluate.selected_decision_problems`, gives the problems of a selected
  decision for the gate, the export projection and the report. A dimension whose selected
  decision has one is exported and shown as `needs_review` (never demonstrated and current),
  with `dimension_not_demonstrated` and one `known_gaps` entry per problem (`kind` the gate's
  code); the report's gap names the codes. `verify-export` with the same policy then blocks
  (`dimension_not_demonstrated`). The export schema did not change (`known_gaps.kind` is a
  string) and the `export-valid` fixture did not change (its flow has no such problem;
  regenerated to a scratch folder and compared, only timestamps and digests of the
  temporary run differ).
* C4-3: `verify-export` applies the taskset qualification rule from the export
  (`provenance.taskset_qualification`, and the limitation `taskset_not_qualified`): reason
  `taskset_not_qualified`, so a session on a `to_qualify` bank is `nonconforming` and blocked
  by a `--policy-file` gate, as `check` blocks it. Only `verify._gate_on_export` changed in
  the verifier.
* C4-4: a `review` superseding a decision reads the conflicts as the gate counts them
  (`conflicts(ext, settles)`): a conflict whose arbitration is no longer admissible is
  unsettled, so superseding with `correction_of_review_error` is refused (`review_required`)
  until an admissible arbitration settles it.
* C4-5: the export projection judges the peer coverage and its gap under the same applied
  policy as the gate (it judged the gap with the session's).
* C4-6: when the policy's stored payload cannot be read, `milestone.required` follows the
  mode the state recorded: `off` and `coaching` never block `export handoff` (ungated
  contract); `required` takes the gated protocol, which refuses and writes no pack. `status`
  reports `policy_available: false`, the recorded mode and digest, and freshness `unknown`
  (repository origin `unavailable` when a plan payload is gone) instead of failing. Note on
  the port: the reviewer's probe removed every blob of the study, the scientific study's own
  payloads (exposure row keys) included, and the core export then refuses with
  `integrity_error`, a rule of the study engine outside the review; the port removes the
  payloads the review's state names.

## Review round 5: fixes (areas C and D)

Regression tests: `framework/tests/study/understanding/test_review_round5_cd.py` (simulated
humans, temporary directories). The reviewer's probes p1 to p12 are ported with the expected
outcome of each fix; p11 (no scientific record changes) failed only because its assertion
was too strict: `receipts` (the store's idempotency receipts) and `updated` (the time of the
last write) change with any recorded request, so the port excludes them and checks instead
that every new receipt is one of the review's requests and that no earlier one changed.
`test_one_judgement_one_gap_list` checks the invariant on twenty study states (reviews,
aided and rectified help, conflicts, arbitrations no longer admissible, reservations in
another session, missing peers, policy re-issued or switched around a selection, expiry,
rubric change, private decisions changed or unknown under `public_only`, waivers, a removed
answer, coaching, no selection, an explicit policy file): `check`, the export preview, the
report and `verify-export [--policy-file F] --study` give the same verdict, and the gate's
reason codes are the export's and the report's gap codes (both ways when a selection of the
person exists and the policy requires the milestone).

The invariant of ADR 0008 did not hold because the judgement had two implementations (the
gate, and the verifier's and the export's own rules). Decided design, implemented:

* **One judgement** (R5-1 to R5-5, R5-9). `verify-export --study`, once the generation is
  bound to a recorded export intent, returns as `gate_result` the study's own gate
  (`service.gate`, new `actor_scope`) for the exported session's milestone, author and
  profile, with `--policy-file` as the override or the study's policy, and as
  `declared_conformity` the same gate under the study's policy. It adds
  `exported_content_current` (projection digest now against the generation's) and
  `judgement: study`. So: unrelated study progress after a review no longer blocks it
  (R5-1, `private_context_unknown` was the verifier's own rule); an unknown private
  dependency under `public_only` is the gate's limitation (R5-2); a private decision
  changed after the export blocks (R5-3); the same re-issued policy file blocks in both
  (R5-4); a selection made under another policy blocks in both (R5-5); waivers are the
  gate's (R5-9).
* **One gap list** (R5-6, R5-7). `service.session_judgement` gives the export projection and
  the report the gate of the session's scope (every reason computed even in coaching;
  without a selection, the decisions shown judged as a virtual selection, plus
  `no_selection`); `evaluate.gaps_of` turns each reason into a `known_gaps` entry with the
  gate's code and `evaluate.judged_status` shows a demonstrated dimension with a blocking
  reason as `needs_review`. An aided demonstration on an `unaided_required` dimension
  (R5-6) and an expired policy (R5-7, every dimension `stale`) now appear in the export and
  the report. The ad hoc `dimension_stale`/`dimension_unknown` gaps are gone; the embedded
  policy is the one the gate applies. The gate itself now gives `dimension_not_demonstrated`
  for a selected decision that is not demonstrated (a selected `to_consolidate` decision
  whose reservation was resolved by another passed silently) or has a problem.
* **Standalone verifier**. `_gate_on_export` mirrors the gate's rules on the content, with
  the gate's codes (policy digest strictness, replacing `policy_differs`; expiry;
  assistance; distinctness; qualification per dimension; required, selected and
  demonstrated dimensions; freshness and the `private_context_unknown` limitation; peers;
  and, under the same policy, every gap of the export). The differences that remain
  (waivers, judgements under another policy, a single policy per export, freshness after
  the export, the current task set, unrelated public sources) are listed in CLI-CONTRACT §16.
* **R5-8**. With the policy payload unreadable, the report shows the recorded mode and the
  gap `policy_unavailable`, as `status` does.
* **R5-10**. The written `docs/understanding/.gitattributes` is `rv-*/** binary -filter
  -ident -working-tree-encoding -eol`: a root `*.md working-tree-encoding=UTF-16LE` or
  `eol=crlf` no longer transforms a generation (staging, commit and a fresh clone keep the
  exported bytes). The exact-bytes rule stays: the round-4 line reads `differs` and is left
  untouched.

Expectations changed by the unification (each test's docstring says so):
`test_review_findings.py::test_explicit_policy_rejects_reviews_made_under_another_policy`
(`policy_differs` is now the gate's `selection_policy_changed`/`decision_policy_changed`),
`test_export_git.py::test_clean_clone_public_integrity_and_honest_limits` (a relaxed policy
file that is not the reviews' policy now blocks, as `check --policy-file` does; the allowing
half of A26 moved to `test_clean_clone_allows_a_public_only_export_with_its_limits`, whose
study policy is the relaxed one), `test_review_round4_c.py` (two tests:
`taskset_not_qualified` is now given per dimension, as the gate gives it) and
`test_review_round2_c.py::test_export_peer_coverage_follows_the_selection` (the local
`gate_result` is the gate's, whose reason carries a `detail`). The `export-valid` fixture
did not change (regenerated to a scratch folder and compared: only the run's salts, times
and digests differ) and the schemas did not change (`schemas.main(['--check'])`).

## Review round 6: fixes

Regression tests: `framework/tests/study/understanding/test_review_round6_cd.py` (simulated
humans, temporary directories). The reviewer's probes p1 to p8 are ported with the expected
outcome of each fix; p5 was exploratory and crashed on its own last print (it read the
dimensions from an empty slice of the Markdown), so its question (does a second active
session of the same person export what `check` and the verifier judge?) is asserted instead.
`test_review_round5_cd.test_one_judgement_one_gap_list` now also compares, on its twenty
study states, the standalone verifier's reasons under the embedded policy with the export's
recorded gate reasons (and with `check`'s when the export is about the selection `check`
judges).

* **R6-1 (major), fixed.** The export intent recorded the session's policy digest and the
  receipt compared the study's policy with it, so an export of a session started before a
  policy change was always `not_current` (no `git-plan`, no `git-receipt`, absent from the
  report), even in coaching, although round 5 embeds the applied policy. The intent now
  records the projection's `policy_digest` (the policy the gate applies) and the receipt
  compares the policy the gate applies at receipt time with it; the projection digest check
  stays, and a policy applied between the intent and the receipt still gives `not_current`.
* **R6-2 (major), fixed.** Local `verify-export --study` judged only the study's live gate
  on the session's recorded working tree: a commit or index whose sources differ from the
  snapshot, or a generation exported into another repository, verified `allowed` and
  conforming. `gate_result` is now the study's gate (its reasons unchanged, still `check`'s)
  plus the reasons established on the verified tree that `check` did not judge
  (`privacy_review_pending`; `public_sources_stale|unknown` unless the verified tree holds
  the session working tree's very bytes for every mapped public source, which `check`
  judged per dimension), listed in `target_tree_reasons`; an allowed or waived verdict then
  blocks (`waiver_not_accepted` for a waiver). `declared_conformity` follows. The export
  intent records the local repository it was written to (state only, never in an
  artefact); local verification reports `verified_repository` and gives
  `verified_repository_not_the_session_one`, blocking when the verified tree's public
  sources are not the snapshot's and a limitation otherwise (a clean clone of the reviewed
  repository is still allowed). Decision taken: the verified tree's freshness is not added
  when its bytes are the ones `check` read, so the round-5 invariant (`check` and local
  verification of the session's tree agree, waivers included, R5-9) still holds and
  `gate_result` differs from `check` only for bytes `check` never read. CLI-CONTRACT §16
  says precisely what local mode judges.
* **R6-3 (minor), fixed.** The private-context comparison read the session's plan and
  snapshot outside the error handling: a missing payload gave `malformed artefact
  (StudyError)` and an invalid generation. It now leaves the private context unknown and,
  as §16 promised, `gate_result` null, `declared_conformity: unknown` and
  `study_gate_unavailable`.
* **R6-4 (minor), fixed.** (a) The standalone verifier added `dimension_not_demonstrated`
  for a dimension shown `needs_review` or `to_consolidate` because of a reason that is not
  about the decision (help rule, distinct reviewer, evidence, open reservation, conflict);
  it now applies the gate's rule from the recorded status of the selected decision
  (`decisions_summary`, or the status shown when no other reason of the export's gate
  explains it). (b) Without `coverage_selection`, the export's gaps were not imported (the
  import sat in the selection branch); they now are, under the embedded policy.

No existing expectation changed: `test_one_judgement_one_gap_list` keeps its exact
equality between the local `gate_result` and `check` (the session's own working tree is
verified there) and now also asserts that no target-tree reason is added and that the
standalone reasons are the export's. No assertion was weakened; the schemas and the
`export-valid` fixture did not change (the intent is study state, not an artefact).

## Review round 7: fixes

Root cause of the three findings: an export of session S2 may show decisions of another
session S1 (the selection of its person and profile maps them), but local verification
decided "judged bytes" from S2's scope and repository only, and the export's
`public_source_scope` was S2's, which does not cover the sources S1's decisions depend on.
The reviewer's probes q1, q1b and q4 are ported in
`framework/tests/study/understanding/test_review_round7_cd.py` (q1 and q1b failed on round
6; q4 passed and now also asserts `written_to`), with a scope-conflict case, a clone without
a change and a single-session export whose scope must not change.
`test_review_round5_cd.test_one_judgement_one_gap_list_cross_session` extends the round-5
invariant to eight cross-session states (S1 selected, S2 exported; the same repository or a
clone; S1's sources or a narrower scope; a later commit, a scope conflict, or nothing):
local verification never relaxes `check`, its verdict is the verdict of `check` run on the
verified bytes (put in every working tree the gate reads), on those bytes its reasons are
`check`'s, and the standalone verifier never says `allowed`, `conforming` or `current`
where `check` on those bytes blocks or finds a source stale or unknown.

* **R7-1 (blocking), fixed.** `verify-export --study` compared the verified tree with the
  exported session's scope and repository only: with S1's decisions selected, a commit
  changing a source only S1 maps (q1, S2 with a narrower scope) or a clone where S2 was
  started and exported (q1b) verified `allowed` although `check` blocks on those bytes. The
  local checker now lists every session whose decisions or context the gate judged (the
  exported one, then `gate_result.repositories`) with its repository and snapshot scope,
  and the verifier compares the verified tree with each session's own working tree.
  `public_sources_judged_by_study` is true only when every mapped public source of every
  such session matches; otherwise each session's `public_sources_stale|unknown` on the
  verified tree is added, and `verified_repository_not_the_session_one` per session read
  from another repository (blocking when its scope or the export's is not current there).
  `verified_repository.judged_sessions` reports the comparison. Reasons are only added.
* **R7-2 (major), fixed.** The export's `public_source_scope` is now the union of the
  public scopes of the exported session and of every session whose decisions are shown (or
  whose context the export's gate read), entries and omitted private references
  deduplicated by logical key. When a shown decision cannot be covered (an unreadable
  snapshot, or one logical key with two digests), the export records
  `scope_does_not_cover_shown_decision` for each dimension shown from that session, and
  the verifier (standalone and local) reads the public sources `unknown`, never `current`.
  Decision taken: a conflicting key keeps the exported session's entry and records the gap
  rather than both entries (one set cannot hold one key twice, and a scope holding two
  digests for one path would read stale whatever the tree). The gap is an export-only gap
  (`verify.EXPORT_ONLY_GAPS`), not a gate code. The schemas did not change (`kind` is a
  string; `schemas.main(['--check'])` passes) and neither did the `export-valid` fixture (a
  single-session export keeps its own scope, asserted by a test).
* **R7-3 (minor), fixed.** The intent recorded only the first repository the generation
  was written to: the same generation written again elsewhere reused the intent, so local
  verification of the second place said `is_written_repository: false`. The intent now
  keeps `repository` (the first place) and lists `repositories`; a new study action
  `export_written`, applied after a successful publication with a request id derived from
  the intent and the place, adds a place not listed yet (idempotent; local state only, never
  in an artefact). `written_to` is the list and `is_written_repository` considers all of
  them.

No existing expectation changed and no assertion was weakened: the round-5 and round-6
tests verify single-session exports or sessions sharing one repository and one scope, where
the union and the per-session comparison give what they gave.

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
