# ADR 0005: Confirmation modes (guided, training, express)

- Status: accepted; the `guided` mode is implemented in v0.2a (WP-A2), the `training` and `express` modes in v0.2b (WP-B2, decision 8 below); amended by WP-A9 (decision 9: partial refusals, off-topic words and non-reasons, the guided stop on a contradiction). In v0.2a `mode set` refused them with `unsupported_capability` and `details.available_in: "v0.2b"`; it now accepts all three.
- Date: 19 October 2026
- Sources: owner remarks R1 and R3 of the first demo ([OWNER-DEMO-1-REMARKS.md](../acceptance/OWNER-DEMO-1-REMARKS.md)), the review synthesis ([V0.2-REVIEW-SYNTHESIS.md](../plans/V0.2-REVIEW-SYNTHESIS.md), "guided first"), and the plan ([V0.2-IMPLEMENTATION-PLAN.md](../plans/V0.2-IMPLEMENTATION-PLAN.md), WP-A2)
- Builds on: the v0.1 confirmation rules (decisions P5.1 delegation, P5.5 and PV.1 reply classification, P5.9 standing delegation scope, in [V0.1-DECISIONS.md](../plans/V0.1-DECISIONS.md))
- Contract: [CLI-CONTRACT.md](../specs/CLI-CONTRACT.md) §5, §5.1, §5.2, §5.3 (v0.2b)

## Context

In v0.1 a confirmation had to share a content word or a number with the proposal (`unrelated_reply`). In the first owner demo, "oui je confirme cela" was refused for the prediction moment: the reply named nothing of the value, and the restatement was in English while the chat was in French, so even a correct French paraphrase could miss the token match (R1). The rule was strict for the wrong reason. It measured vocabulary overlap, not whether the junior had decided.

The same demo showed the opposite failure (R3). The junior confirmed the feature availability with a misattributed reason ("on écarte aussi contact, sa valeur peut être gonflée"; inflation concerns `campaign`, not `contact`). The agent confirmed first and corrected afterwards, so the report records a misconception as the justification, and the junior never had the chance to change their words.

The owner validated three modes: guided (default), training, and express. The engine enforces the mode, lowering it needs the user's words, and policy and conclusion need one reason. The review synthesis kept this but ordered the work. Guided ships first; training and express follow after observations.

## Decision

1. **Modes.** `state.mode` is `guided`, `training`, or `express`. New studies are `guided`; a state without `mode` reads as guided. `hypotrail mode set MODE --user-words TEXT` goes through `apply_command` (revision, request id, idempotent replay) and records each change with the user's words in `mode_history`. In v0.2a only `guided` was accepted (`training` and `express` were refused with `unsupported_capability` and `details.available_in: "v0.2b"`); v0.2b accepts the three, with the strictness rule of decision 8. Words that are empty, negative, a question, conditional, or bare are refused as for a confirmation, so a mode never becomes less strict silently.

2. **Guided rule.** A reply confirms when all of the following hold:
   - It is bound to a proposal: the positional `PROPOSAL`, or `--proposal`.
   - That proposal is the single open proposal of its decision at the revision the request expects.
   - The reply is not negative (the v0.1 `is_negative`).
   - It is not a question (`question_reply`: a question mark).
   - It is not conditional (`conditional_reply`). This covers "unless", "sauf si", "only if", "à condition", and hesitations such as "réfléchir" or "let me think". It also covers "but", "mais", "sauf", or "except" right after the endorsement, as in "oui mais", "d'accord sauf", or "yes but".
   - It is not bare (`bare_acknowledgement`). An explicit first-person endorsement is not bare: "je confirme", "I agree", "je suis d'accord", "je valide".

   - It holds an explicit endorsement expression ("je confirme", "je valide", "je suis d'accord", "d'accord pour moi", "ça me va", "c'est bon pour moi", "I confirm", "I agree", "agreed", "that works for me"), or it repeats a word or a number of the value, the restatement, or a label. Otherwise it is `unrelated_reply`: a bare agreement word followed by unrelated content ("yes, I like pizza") never becomes a decision (integrator decision on WP-A2).

   "oui je confirme cela" confirms; "ok" and "oui" do not; "oui mais je veux réfléchir" does not.

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

7. **Behaviour by mode (implemented in v0.2b, decision 8).**
   - Training: concept matching instead of token overlap (the `unrelated_reply` classifier is kept for it), and a mandatory stop on a contradiction or a misattributed reason.
   - Guided: one stop. The agent raises the concern before confirming, and the junior reformulates, confirms with new words, or keeps their words, recorded with `--agent-concern`.
   - Express: record only.

8. **Training and express (v0.2b, WP-B2).** The checks of the guided mode that do not depend on the proposal (empty, negative, question, conditional, bare; the binding, hold, staleness, and delegation checks) apply in every mode. Then, for the junior's own words:
   - **Training.** The reply restates the proposal **on its concepts**, not on shared tokens. `concepts.concept_map` builds a small concept map per decision from the value: the timing and the event of the prediction moment ("before the call" / "avant l'appel"), the excluded variables by name with an exclusion word ("exclude duration" / "retirer duration"), the share held apart for validation, the measure and minimum gain of the success criterion, each non-default preprocessing parameter, the rule and its number ("capacity 100" / "appeler les 100 meilleurs"), the chosen model, the verdict. A concept is said when the reply holds one of its English or French terms, listed as data in `content/concepts.yaml` (with translation groups for the words of a free-text moment, and the proposal's labels). A concept left unsaid is the refusal `paraphrase_required`, whose `details.missing` names each concept with a hint for the junior and whose `details.junior_message` can be shown as it is. "oui je confirme cela" is therefore refused in training. The trade-offs (`policy` or `model_choice`, and `conclusion`) also need a reason connector ("because", "parce que", "car", "since", ...): a restatement is already content, so a content word is no reason there (`reason_required`). Words that contradict a `feature_availability` value are the refusal `words_contradict_value`, not a warning. The recorded basis is `restated`.
   - **Guided** is unchanged: the contradiction stays a warning.
   - **Express.** The guided rules, plus a standing delegation that also covers the framing decisions that follow the split: `success_criterion` and `preprocessing` (`state.EXPRESS_STANDING_DELEGATION_DECISIONS`). A delegated decision is recorded as `delegated_default` with its scope and stays in `not_yet_defensible`. The policy, the model choice, the conclusion, and any later decision such as a final test are never covered by a standing delegation (R1 of v0.1 unchanged). A contradiction is a warning, recorded only.
   - **Changing the mode.** The modes are ordered by strictness, express < guided < training. Lowering it needs the user's words, and they must name the mode asked for (`unrelated_reply` otherwise); raising it needs no words, so the agent may make a study stricter on its own. Keeping the same mode needs words. A mode change never touches a decision: past confirmations stay valid. Each confirmation records the mode in force (`confirmation.mode`, `result.mode`).

9. **Amendment (WP-A9, fresh review of v0.2a).** Three holes a reviewer reproduced are closed, in every mode where they apply:
   - **Partial refusal (B1).** "ok pour le plafonnement, pas pour le log" and "Yes for the caps, not for the log transform." were recorded as confirmations. "pas pour", "not for", "but not" and "mais pas" are now conditional anywhere, and `confirm.partial_refusal` refuses a negator ("pas", "not", "sans", "except", "sauf", "no", "non", "without", or "non"/"no" after the part) applied to a part the value holds, for the multi-part decisions (`feature_availability`, `preprocessing`, `split`): `conditional_reply` with `details.partial`. It is checked against the value, so "all features except X" stays accepted when the value excludes X, and "pas de log" when the value has no log transform.
   - **Off-topic words and non-reasons (H1).** One shared common noun no longer relates a reply ("oui, la pizza du client est bonne"): an overlap counts only in a reply that agrees (an agreement word, or a clause that states the decision) and only when a clause is about the proposal (a number or a key of the value, or two of its content words, all of them in a one-word clause, from the value, the restatement, the labels, the concept terms of the value, or the decision's `reason_domain` words). A reason is a connector or a clause that is neither a restatement of the value nor unrelated: "ok, 10 %" and "je confirme, j'aime la pizza" are `reason_required` on the policy. The owner's sentences still confirm. This replaces "any content word counts as a reason" of decision 3.
   - **Contradiction in guided (H3).** Words that contradict a `feature_availability` value are refused in `guided` (`words_contradict_value`) until the agent raises the point: with `--agent-concern`, the confirmation is recorded with its warnings, which the record keeps (`confirmation.warnings`) and the report shows. `express` records the warning; `training` refuses as before. This replaces "a warning, never a refusal" of decision 6 for the guided mode.

## Consequences

- Fewer refusals of genuine endorsements, and recorded words that say what kind of agreement they are (`endorsed` or `restated`). The junior's decision is still never inferred from silence or from "ok".
- The policy and the conclusion keep a recorded reason in the junior's words. The heuristic accepts any content word as a reason, so a restatement of the rule ("oui, vingt appels") passes. The agent instructions ask for a real reason first.
- The contradiction check is lexical (English and French word lists, clause cut on punctuation). It misses paraphrases and can warn on unusual phrasing; it never blocks.
- Payloads gain additive keys: `agent_concern`, `warnings`, `labels`, `label`, `mode`, `language`, and the note `kind`. There is one new error code (`reason_required`) and two new `ambiguous_confirmation` reasons (`question_reply`, `conditional_reply`). Schema versions are unchanged.
- v0.2b adds two error codes (`paraphrase_required`, `words_contradict_value`), the confirmation key `mode` (record, view, and confirm result), and `user_words: null` in `mode_history` for a raise. The concept matching is lexical: it misses paraphrases outside the lists, and it can accept a reply that names every concept without understanding it. It never replaces the agent's R3 stop on a misattributed reason, which it cannot see.
- The companion's typed confirmation (W1) follows the same engine rule. The panel adds no rule of its own.

## Not decided here

- When lowering the mode is allowed during a pause (v0.2b allows it at any time, in the user's words naming the mode).
- Whether delegation should be refused in the training mode (v0.2b keeps the guided delegation rules there).
- Whether `--agent-concern` should be refused in the training mode, making the R3 stop mechanical (v0.2b records it, as in guided; the agent instructions ask for new words).
- Whether `reason_required` should also apply to `feature_availability` exclusions.
- A finer reason check (a clause that explains rather than restates).

## Amendment (v0.2b, WP-B6c): the default preprocessing under a guided standing delegation

Integrator decision, open to review (V0.2-DECISIONS.md, WP-B6c). In the guided mode a standing delegation also covers the `preprocessing` decision when its value is the engine's default (`governance.is_default`: no missing-value indicator, every category kept, no cap, no transform), so a junior who delegated the framing questions is not paused for a preparation that changes nothing (`commands.standing_covers_default_preprocessing`). A preparation that changes anything still needs the junior's words or a delegation given at that pause; the success criterion is still asked; express is unchanged; training never covers it. The delegated decision is recorded as `delegated_default` with scope `standing` and listed in `delegated_decisions`.
