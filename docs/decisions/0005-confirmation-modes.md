# ADR 0005: Confirmation modes (guided now, training and express in v0.2b)

- Status: accepted; the `guided` mode is implemented in v0.2a (WP-A2). `training` and `express` are reserved values, refused by `mode set` until v0.2b.
- Date: 19 October 2026
- Sources: owner remarks R1 and R3 of the first demo ([OWNER-DEMO-1-REMARKS.md](../acceptance/OWNER-DEMO-1-REMARKS.md)), the review synthesis ([V0.2-REVIEW-SYNTHESIS.md](../plans/V0.2-REVIEW-SYNTHESIS.md), "guided first"), and the plan ([V0.2-IMPLEMENTATION-PLAN.md](../plans/V0.2-IMPLEMENTATION-PLAN.md), WP-A2)
- Builds on: the v0.1 confirmation rules (decisions P5.1 delegation, P5.5 and PV.1 reply classification, P5.9 standing delegation scope, in [V0.1-DECISIONS.md](../plans/V0.1-DECISIONS.md))
- Contract: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) §5, §5.1, §5.2

## Context

In v0.1 a confirmation had to share a content word or a number with the proposal (`unrelated_reply`). In the first owner demo, "oui je confirme cela" was refused for the prediction moment: the reply named nothing of the value, and the restatement was in English while the chat was in French, so even a correct French paraphrase could miss the token match (R1). The rule was strict for the wrong reason. It measured vocabulary overlap, not whether the junior had decided.

The same demo showed the opposite failure (R3). The junior confirmed the feature availability with a misattributed reason ("on écarte aussi contact, sa valeur peut être gonflée"; inflation concerns `campaign`, not `contact`). The agent confirmed first and corrected afterwards, so the report records a misconception as the justification, and the junior never had the chance to change their words.

The owner validated three modes: guided (default), training, and express. The engine enforces the mode, lowering it needs the user's words, and policy and conclusion need one reason. The review synthesis kept this but ordered the work. Guided ships first; training and express follow after observations.

## Decision

1. **Modes.** `state.mode` is `guided`, `training`, or `express`. New studies are `guided`; a state without `mode` reads as guided. `hypotrail mode set MODE --user-words TEXT` goes through `apply_command` (revision, request id, idempotent replay) and records each change with the user's words in `mode_history`. In v0.2a only `guided` is accepted. `training` and `express` are refused with `unsupported_capability` and `details.available_in: "v0.2b"`. Words that are empty, negative, a question, conditional, or bare are refused as for a confirmation, so a mode never changes silently.

2. **Guided rule.** A reply confirms when all of the following hold:
   - It is bound to a proposal: the positional `PROPOSAL`, or `--proposal`.
   - That proposal is the single open proposal of its decision at the revision the request expects.
   - The reply is not negative (the v0.1 `is_negative`).
   - It is not a question (`question_reply`: a question mark).
   - It is not conditional (`conditional_reply`). This covers "unless", "sauf si", "only if", "à condition", and hesitations such as "réfléchir" or "let me think". It also covers "but", "mais", "sauf", or "except" right after the endorsement, as in "oui mais", "d'accord sauf", or "yes but".
   - It is not bare (`bare_acknowledgement`). An explicit first-person endorsement is not bare: "je confirme", "I agree", "je suis d'accord", "je valide".

   No word needs to be shared with the proposal. "oui je confirme cela" confirms; "ok" and "oui" do not; "oui mais je veux réfléchir" does not.

3. **Reason for the trade-offs.** In the junior's own words, the choice of the third pause and the conclusion need one reason. The choice is `policy` (binary) or `model_choice` (regression). A reason is a clause beyond the endorsement: a connector ("parce que", "car", "because", "since", "puisque", "vu que", "given") or any content word that is not an endorsement word or an intensifier. Otherwise the refusal is `reason_required`, a new error code. Delegations are unchanged (D1, R1 scope) and need no reason: the restatement states the recommended default.

4. **Basis.** The request's `--basis` stays `explicit` (the junior's own words, default) or `delegated_default`. The recorded basis of own words is one of two values:
   - `restated` when the reply repeats a word or a number of the value, the restatement, or a label, endorsement words left out.
   - `endorsed` otherwise.

   `explicit` stays readable in older studies; nothing is migrated. `explicit`, `endorsed`, and `restated` form one class for the conclusion's credit line, so a change between them never outdates a conclusion.

5. **Language.** A proposal keeps its structured `value` and its `restatement`. It may carry `labels: {en, fr}`, given with `--restatement-en`, `--restatement-fr`, or `--lang` (the language of `--restatement`). `init --lang` sets the study language (default `en`). `status --json` shows each open proposal's `label` in the study language (the `status --summary` shape is unchanged, decision CA.4; surfaces that need the label read the view). A French paraphrase restates through the French label.

6. **Agent concern and corrections (R3).**
   - `decide confirm --agent-concern TEXT` stores the point the agent raised before the junior confirmed, and that the junior kept. It is shown in the view, `decisions`, the report ("Point raised by the agent … kept by the user"), and the handoff pack.
   - `decide note --about D --kind correction --user-words TEXT` attaches a later correction of a confirmed decision's reasoning, in the junior's words. It neither reconfirms nor blocks. Holds keep their semantics.
   - For `feature_availability` the engine checks words against the value mechanically. Suppose a variable is named in a clause with exclusion words while the value keeps it, or with keep words while the value excludes it. The confirm result then carries `warnings: [{code: words_contradict_value, variable, said, value, message}]`. This is a warning, never a refusal.

7. **Behaviour by mode (to implement in v0.2b).**
   - Training: concept matching instead of token overlap (the `unrelated_reply` classifier is kept for it), and a mandatory stop on a contradiction or a misattributed reason.
   - Guided: one stop. The agent raises the concern before confirming, and the junior reformulates, confirms with new words, or keeps their words, recorded with `--agent-concern`.
   - Express: record only.

## Consequences

- Fewer refusals of genuine endorsements, and recorded words that say what kind of agreement they are (`endorsed` or `restated`). The junior's decision is still never inferred from silence or from "ok".
- The policy and the conclusion keep a recorded reason in the junior's words. The heuristic accepts any content word as a reason, so a restatement of the rule ("oui, vingt appels") passes. The agent instructions ask for a real reason first.
- The contradiction check is lexical (English and French word lists, clause cut on punctuation). It misses paraphrases and can warn on unusual phrasing; it never blocks.
- Payloads gain additive keys: `agent_concern`, `warnings`, `labels`, `label`, `mode`, `language`, and the note `kind`. There is one new error code (`reason_required`) and two new `ambiguous_confirmation` reasons (`question_reply`, `conditional_reply`). Schema versions are unchanged.
- The companion's typed confirmation (W1) follows the same engine rule. The panel adds no rule of its own.

## Not decided here

- The training and express modes (v0.2b), including when lowering the mode is allowed during a pause.
- Whether `reason_required` should also apply to `feature_availability` exclusions.
- A finer reason check (a clause that explains rather than restates).
