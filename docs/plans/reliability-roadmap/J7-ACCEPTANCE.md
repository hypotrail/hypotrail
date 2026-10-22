# J7 — Acceptance evidence and bounded release

Depends on J0–J6. Review coverage: M3 and lack of demonstrated real-tool/human usage.

## Outcome

The project has reproducible evidence for what was implemented and an honest list
of what remains unverified. A happy scripted conversation must not conceal missing
methodological checks, and a passing technical gate must not become a claim that
juniors learned or Copilot was tested.

This milestone has separate technical, real-tool and human-observation tracks.
Human sessions are **not a mandatory development/release gate**, preserving the
owner's existing decision. Their absence limits claims of usability/learning, not
the ability to complete the implementation. Do not repeatedly ask the owner for
participants. Prepare the kit and mark observations not run until arranged.

## Existing anchors

`CONTRIBUTING.md`, `framework/tests/study/flowkit.py`, synthetic fixture generator,
`framework/tests/acceptance/test_graders.py`, agent scenario/runner files,
`docs/research/OBSERVATION-PROTOCOL.md`, `docs/research/E1-STEELMAN.md`,
`clients/vscode-companion/MANUAL-TEST.md`, `docs/acceptance/runs/`.
Reuse the harness; do not replace it with an unrelated benchmark system.

## J7.1 — Fixed synthetic regression suite

Create one small, deterministic suite that exercises the independent oracles from
J1–J6. Each test records expected behavior before calling the engine. Include:

1. temporal future-training and delayed-label traps;
2. inner-fold group overlap and exact-duplicate/entity transitive linkage;
3. known unavailable predictor versus genuinely uncertain predictor;
4. AUC versus top-share selection reversal;
5. median versus mean baseline and zero-baseline criterion;
6. complete point/lower-bound verdict truth table;
7. stale, wrong-population and wrong-rule evidence references;
8. missing diagnostics at direct final opening;
9. exploration retry/conflict/interruption and A→B versus A→C compatibility;
10. label-preview exposure, unrecorded surfaces and preserved prior exposure;
11. FR/EN confirmation, explanation, change and resumption;
12. partial render failure and user-annotation preservation.

This enumerated suite is a bounded regression corpus. “All pass” means these cases
pass, not that all forms of leakage or misleading claims are impossible. Synthetic
holdouts may be opened for tests; historical project holdouts may not.

## J7.2 — Complete deterministic journeys

At minimum run four complete new-profile synthetic journeys:

| Journey | Task/language | Special path |
|---|---|---|
| T1 | Binary EN | Independent rows; valid adoption and one final opening |
| T2 | Binary FR | Temporal windows, unknown uncertainty; honest inconclusive outcome |
| T3 | Regression EN | Median baseline; keep-baseline outcome |
| T4 | Regression FR | Change preparation, explain, regenerate and resume |

Each starts at init and finishes at a conclusion plus HTML/notebook. Do not preconfirm
the “difficult” decisions in setup and then claim those pauses were exercised. Setup
may construct synthetic data/contracts; the scenario must traverse the relevant
decision transitions itself. Include one fresh-chat/state resumption and one changed
decision in the combined matrix. Test profile-specific compatibility separately.

Also run the existing repository gate, including committed-case regression tests as
documented. Add adapter-level checks for Hotel's restricted claim, Bank full's timing
limitations and Auto MPG units/baseline. Do not rerun case preparation/training scripts
merely to inspect their existing documentation. A new actual-case model run outside
the already authorized test gate needs an implementation/acceptance task that covers it.

## J7.3 — Agent acceptance, when authorized

Use the existing opt-in harness and budget control. Paid runs require an explicitly
covered budget; preparing tests does not authorize spend. Keep raw sessions outside
the repository and redact secrets. Record model, harness version, prompt revision,
case, language, starting state, token/tool cost when available, and exact tested commit.

Use complete journeys plus targeted counterexamples. Do not change the grader after
seeing a failure simply to improve the score; version any justified rubric correction
and rerun the affected cases. Keep canned grader unit tests independent of paid calls.

Report raw counts and denominators, not just a percentage. Define metrics:

- **Escaped invalid action/claim:** a planted invalid case was accepted or presented
  as supported. Count by finding and transition.
- **False block:** a valid supported action was refused or required an irrelevant
  extra confirmation. Use a predeclared valid-case corpus.
- **Completion:** conclusion plus accessible consistent deliverables; report
  successful, unsuccessful and inconclusive conclusions separately.
- **Interaction turns:** distinguish decision turns, voluntary explanations,
  corrections after engine errors and routine status messages.
- **Tool calls/cost/time:** total and by stage; include retries and failed attempts,
  do not remove slow runs from the denominator.
- **Unsupported claim:** success stronger than the evidence scope, missing uncertainty
  disclosure, causal claim from risk scoring or claimed user authentication.

“13 turns” and “50 calls” are observations/possible targets, not universal acceptance
thresholds. An explanation requested by the user is not a failure. For the fixed
planted critical corpus, require zero accepted invalid transitions and zero silent
state corruption. Report false-block counts separately; they must be zero on the
deterministic canonical valid examples before claiming those examples supported.

## J7.4 — Real Copilot/VS Code/Marimo acceptance

Prepare a manual script with these steps and evidence fields; execute only when the
tools and authorization are available. A CLI test or mocked VS Code API is not proof.

1. Start a new temporary study outside the repository and open its folder in VS Code.
2. Select the generated Hypotrail custom Copilot agent; verify instruction uptake.
3. Observe the quoted proposal and real choice picker, with localized options.
4. Choose Explain, return to the same proposal, then adopt it. Inspect the recorded
   proposal ID, channel and verbatim label through the CLI.
5. Complete the remaining study with one changed choice and one resumed chat.
6. Open the HTML and generated notebook; verify no unrequested refit at notebook open.
7. Run an explicit supported synthetic notebook recomputation; add a workbench note.
8. Regenerate outputs and verify the note, current figures and revision display.
9. Verify the final-test transition on synthetic data and the resulting scope/limits.
10. If the panel is separately enabled for this test, run the applicable manual
    checklist. Record its stage and restore any temporary user setting you changed.

Record app/extension/Marimo versions, date, task language, commit, observations,
unexpected behavior and evidence locations. Do not install an extension or modify
the user's VS Code profile just to make an unapproved test possible. A failed picker
must still allow the documented text fallback; classify picker support as failed,
not silently passed because the text route worked.

## J7.5 — Human observation kit, not an efficacy claim

Reuse the observation protocol and add a short session sheet for a junior and a
relecteur. An initial convenience sample of 4–6 juniors is a **proposed qualitative
pilot**, not a powered learning study or a release requirement. Do not infer an
effect size or broad success rate from it.

Observe one complete bounded study. Ask for unaided explanations after completion:

- what was predicted and what was known at that moment;
- why the split reflects (or fails to reflect) the intended use;
- what the selected metric and baseline mean;
- what the reported gain and its uncertainty do and do not establish;
- whether a risk score proves that an intervention helps;
- what changing the selected rule would require recomputing.

Use a predefined 0/1/2 rubric: incorrect/missing, partly correct with prompt, correct
without prompt. Record examples and observer prompts; a recitation of agent text
is not automatically understanding. The reviewer independently identifies objective,
protocol, chosen configuration, evidence scope and main limitation from deliverables.
Record time-to-find and discrepancies, not just satisfaction.

Initially evaluate usability/understanding of this workflow alone. Comparing chat
alone versus panel, or demonstrating a learning benefit, requires a separate designed
comparison with order/case allocation and an appropriate sample-size rationale; do
not conflate that study with this small pilot. Do not recruit or message participants
without explicit authorization.

## J7.6 — Release status and acceptance dossier

Produce `docs/acceptance/reliability-roadmap/RELEASE.md` with three independent axes:

| Axis | Allowed summary |
|---|---|
| Technical implementation | pending / implemented / automated acceptance passed |
| Real tool integration | not run / failed / observed passing, with versions |
| Human use and learning | not observed / qualitative observations / separate efficacy evidence |

Include a complete J0–J7 requirement matrix, known limits, profile/default behavior,
case scope, exact gate results, invalidation/compatibility notes and instructions for
the next developer. No invented manual successes, no “Copilot validated” based on
Claude Code sessions, no “learning proven” based on simulated juniors.

Before proposing a default-profile change, inspect the legacy/new-profile regression
matrix and clearly explain what happens to existing studies. Default activation,
publication and extension installation are separate release actions; this milestone
does not silently perform them. No state reset is a rollout strategy.

## Acceptance IDs

| ID | Artifact/check | Completion criterion |
|---|---|---|
| J7-A01 | Independent regression corpus | All specified critical cases pass, exact expected outcomes retained |
| J7-A02 | Four deterministic journeys | Complete coherent outputs and expected verdict classes |
| J7-A03 | Repository gate | Actual green run recorded; skips and environment limitations explicit |
| J7-A04 | Agent scenarios and graders | Canned graders pass; paid run status/budget recorded separately |
| J7-A05 | Real-tool script | Executable instructions and truthful observed/not-run record |
| J7-A06 | Human session kit | Rubric and limits prepared; no efficacy assertion without evidence |
| J7-A07 | Release dossier | Every claim mapped to evidence and every unrun check visible |
| J7-A08 | Preservation and architecture audit | No reset, reopened historical final test, new panel write or server |

J7's implementation work is complete when the automated evidence and observation
materials are delivered, with external/manual runs explicitly classified. A pending
human session does not block that completion. A failed automated prerequisite does.
