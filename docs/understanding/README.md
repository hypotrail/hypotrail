# Understanding and handover review (opt-in)

[ADR 0008](../decisions/0008-understanding-review.md) · [CLI contract §16](../specs/CLI-CONTRACT.md) ·
[handoff and acceptance](../handoff/UNDERSTANDING-V1.md)

The review helps a team keep what it understands about a study produced with an assistant:
the author explains the decisions and behaviours that matter, a colleague takes the critical
parts over from the repository and a handover note, and a reviewed synthesis can be
committed with the work.

What it is **not**: a grade, a ranking, a test of general competence, a security review, a
proof that the study is scientifically valid, or a detector of AI help. A dimension marked
`demonstrated` says that a declared person judged identified answers against a rubric, in a
given context; it is `human_declared` (a local declaration, not an authenticated identity).
The policy is a cooperative control: anyone who can edit the repository or the study state
can bypass it. An organisation that needs a guarantee enforces the policy of the target
branch with a trusted external system.

## Activation

The review is **off** for every study, new or existing. Nothing is collected until a team
applies a policy:

```sh
hypotrail understanding policy set --file docs/understanding/examples/policy-coaching.json \
  --author lead --reason "team pilot" --request-id p1 --expected-revision REV --study STUDY
```

* `coaching`: the same tools, nothing blocks.
* `required`: blocks only `export handoff` (the `handoff` milestone), never exploration,
  commits, saves, reading or learning.
* `off` again: stops; nothing is deleted.

`external_verified` assurance and `purge_after_days` retention are refused in version 1
(not implemented), never silently replaced.

## Roles and dimensions

| Id | Dimension |
|---|---|
| D1 | Purpose: unit, population, target, decision supported, moment of prediction |
| D2 | Data: provenance, availability at the useful moment, exclusions, leakage |
| D3 | Evaluation: partitions, time or groups, validation, selection, final test status |
| D4 | Results: main metric, baseline, trade-offs, uncertainty, scope of the comparison |
| D5 | Transformations: what is learned, on which rows, train and prediction consistency |
| D6 | Implementation: input-to-output path, where a control lives, diagnosing an anomaly |
| D7 | Limits: assumptions, uses not covered, conditions forbidding a conclusion |
| D8 | Handover and safety: dependencies, environment, data and secret rules, safe reproduction, change to verify, point of return |

A policy maps responsibility profiles to dimensions (an analyst need not explain the
optimiser); critical dimensions are always included, whatever the profile.

## The workflow, for the person and for the chat agent

1. **Plan** (read-only). The agent shows the purpose, the mode, what stays local (answers,
   help declarations, proposals, reviews) and what may be committed (an approved synthesis).
   The person confirms their responsibilities.
   `hypotrail understanding plan --profile pipeline --milestone handoff --actor alice
   --repo PROJECT --sources-file sources.json --write-plan plan.json --study STUDY`
2. **Start**: `understanding start --plan-file plan.json` freezes the context (study
   decisions, case, mapped sources, policy, rubrics).
3. **One task at a time**: `understanding task --session SID`. The person answers **in their
   own words first**, with the references they used; "I do not know" is a valid answer. The
   agent shows no expected answer, does not reformulate before submission and never completes
   the answer silently. `understanding submit ... --response-file answer.txt
   --assistance-file assistance.json`.
4. **Help after the first answer**: `understanding coach --attempt AID` records the help,
   then returns hints. A later answer to the same task is aided. A new demonstration uses a
   new variant of the task (`understanding task` offers it), never the same question again.
5. **Review by a person**. An agent or a model may store a proposal
   (`propose-review`); it never becomes a decision. The decision is an explicit act of a
   declared reviewer: a file such as `examples/human-review.TEMPLATE.json`, filled and
   confirmed by the reviewer (the `declaration.statement` is theirs). **An agent never fills
   this act in a person's name.** When the reviewer gives their judgement in the chat, the
   agent writes the file with `declaration.source: chat_relay`, quotes the reviewer's
   statement verbatim, and shows it back before running `understanding review`. On a critical
   dimension the reviewer is another person than the author.
6. **Handover**: the author records `HandoverContent` (`handover set`). A colleague runs a
   handover task (`transfer start --peer carol`), works from the repository and the note, and
   submits their own references (`transfer submit`); a person other than the peer reviews it
   (`transfer review`). Reading or approving the note is not a handover. "Impossible to take
   over with the current note" is a useful outcome: improve the note, then try again.
7. **Close and select**: `close --to completed`, then `select` the decisions that count for
   the milestone. `understanding check --milestone handoff` explains what is missing; it
   authorises nothing.
8. **Export and commit** (optional): `export preview` gives the exact content and its
   digest; **each** contributor named in it approves that digest (`export approve`); `export
   write --repo PROJECT` writes `docs/understanding/<review_id>/`. Then:

   ```sh
   hypotrail understanding git-plan --session SID --repo PROJECT --study STUDY
   git -C PROJECT add -- docs/understanding/<review_id>/   # or understanding git-stage
   hypotrail understanding verify-export --repo PROJECT --target index
   git -C PROJECT commit -m "..."                          # your usual commit; nothing is pushed
   hypotrail understanding verify-export --repo PROJECT --target HEAD --study STUDY
   ```

   `PROJECT` is the top level of its Git work tree (a project inside a monorepo is
   refused from `plan` on). `git-plan` says when the generation is no longer what the study
   exports now (`exported_content_current: false`: export it again, `git-stage` refuses
   it), and when Git converts a mapped source on its way to the index
   (`source_transformed_by_git`, for example `core.autocrlf=true`: add a `.gitattributes`
   line `<path> -text` for those sources, or review the bytes Git stores).

A workshop session of 10 to 15 minutes covers a few dimensions and a short exchange with a
peer; it is a pilot budget, not full coverage. The plan shows the estimate and what remains.
Pause, resume and abandon lose no scientific work and produce no false result. No timer is
used as a measure of competence.

## What changes a result

* A relevant source change (a mapped file, a scientific decision, the case contract, the
  engine, the dependency lock) makes the dimensions that depend on it `stale`; a missing
  source makes them `unknown`. Time alone does not, unless the policy sets an expiry.
* A new policy or rubric needs a new human review for what changed.
* Editing the handover content, even to remove something, makes earlier handovers stale.
* Deleting an answer keeps the historical judgement but makes the evidence `unavailable`.

Answers are local files of the study (`.hypotrail/blobs/`): not encrypted, not sent
anywhere, never written into the revision log, an event, a command output or an export.

## Pilot (not done)

Before any wider use, have an ML referent and the person in charge of handovers review the
rubrics of each case (they are marked `to_qualify`), try correct, partial, eloquent but wrong,
and informal but right answers, compare judgements, and observe a short pilot across the four
workshop roles (duration, ambiguities, errors caught or missed, disagreements, whether the
peer could find and explain an element, the note's usefulness at a later handover, the cost
of keeping it current). Pass rates are not the goal; long-term retention cannot be inferred
from one session.
