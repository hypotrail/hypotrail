# Observation protocol: junior developers on the Bank Marketing study

Status: protocol, post-v0.1, written 18 October 2026. **Not yet run.** The owner runs 2 or 3 sessions with human participants later. Templates: [`observation/`](observation/). Instrumentation: `hypotrail session-report` and the opt-in session log ([CLI-CONTRACT.md §8.6](../specs/CLI-CONTRACT.md#86-session-report-and-session-log-post-v01-observation-kit)).

Every agentic result so far is "Claude Code acceptance" with simulated juniors ([checklist](../acceptance/V0.1-CHECKLIST.md), "Outside the checklist and not proven"). These sessions are the first evidence about people. They are formative: they look for problems and their causes. With 2 or 3 participants they cannot estimate a rate, compare conditions, or show that the method teaches.

## 1. What only a person can show

The agentic runs already measure whether the agent follows its rules and whether the engine refuses invalid moves. This protocol looks only at what a simulated junior cannot reveal.

| # | Question | Evidence |
|---|---|---|
| G1 | **Comprehension.** After the session, without help, can the participant explain the unit of observation, the prediction moment, why `duration` is excluded, the metric, what an interval means, what a capacity change does, and one limit? | Comprehension test (§7), scored blind to the session |
| G2 | **Friction of the pauses.** Do the three pauses and the "own words" rule feel useful or bureaucratic? Where do they stall, retype, or give up and delegate? | Think-aloud, observation grid, pause timings and refused confirmations from `session-report` |
| G3 | **Trust.** What does the participant believe because the agent said it? Do they check a number, ask where it comes from, or notice a limit? | Think-aloud, debrief (§8) |
| G4 | **Deliverables.** Do they open the HTML report, the generated notebook, or the workbench, unprompted? What do they look for there? | Observation grid; screen recording if consented |
| G5 | **Delegation.** When and why do they say "use your recommended default"? Do they understand that the decision is then recorded as delegated? | `session-report` (basis, scope), think-aloud, test question 7 |
| G6 | **Resumption.** In a new chat the next day, do they recover the goal, the decisions, and the next step? Is the five-line recap enough? | Task 7, observation grid |

Out of scope: GitHub Copilot (not tested in v0.1), model comparison, timing benchmarks, and the companion.

## 2. Participants

**Profile.** 2 or 3 junior developers: 0 to 3 years of professional programming, comfortable reading Python and using a terminal, **no formal training in statistics or machine learning** beyond an introductory course or tutorials. They have not used Hypotrail and have not seen this repository. Ideally one of them has used a coding agent (Claude Code, Copilot chat, Cursor) and one has not.

**Screening** (5 minutes, before scheduling; record the answers in the session log, not names):

1. How long have you programmed professionally? (exclude more than 3 years)
2. Have you trained or evaluated a predictive model at work? (exclude "yes, several times")
3. Can you explain what a training set and a validation set are? (a confident, correct answer suggests too much ML background; note it, do not exclude for it alone)
4. Have you used an AI coding assistant in chat? How often? (balance the group)
5. Have you seen the UCI Bank Marketing dataset? (note it; it is common in courses)
6. Do you work with the owner, or on Hypotrail? (exclude: they know the intended answers)

**Number.** Two or three sessions find the most frequent, most severe problems, not all of them. The "five users" argument (Nielsen and Landauer, 1993; Nielsen, 2000) concerns iterative tests of one interface; here, treat each session as a probe and fix between sessions if a severity-4 problem appears (§9).

## 3. Setup checklist

Do this before each session, on the participant's machine or a prepared one. Record versions in the session log template.

- [ ] **Clean environment.** A fresh user account or machine. No `~/.claude/CLAUDE.md`, no user-level skills, commands, or memory, no project instructions in parent folders of the study. Claude Code loads instruction files from parent folders and from the user's home; any of them changes the agent.
- [ ] **Tools.** uv installed. Claude Code installed and logged in; record its version (`claude --version`) and the model in use. A browser for the HTML report.
- [ ] **Engine.** Clone this repository at a recorded commit, then `uv sync --project framework --group dev`.
- [ ] **Study, outside the repository.** For example:

  ```sh
  REPO=/path/to/hypotrail
  STUDY=$HOME/hypotrail-sessions/P1/bank-study
  uv run --project $REPO/framework hypotrail init --case $REPO/use-cases/bank-marketing/case.yaml --study $STUDY
  ```

  One fresh study per participant. Never reuse a study, and never reset one (`AGENTS.md`).
- [ ] **Session log on.** Run one command with the variable set; the file then keeps the log on for every later command, in every chat, until deleted:

  ```sh
  HYPOTRAIL_SESSION_LOG=1 uv run --project $REPO/framework hypotrail status --summary --study $STUDY
  test -f $STUDY/.hypotrail/session-log.jsonl && echo "session log on"
  ```

  The log holds commands, codes, counts, and times only; never the participant's words (§4).
- [ ] **Dry check.** `uv run --project $REPO/framework hypotrail session-report --study $STUDY --format text` prints a report with 1 revision and the session log on.
- [ ] **Recording** (only if consented): screen and audio, local files only. Otherwise, the facilitator takes timestamped notes.
- [ ] **Desk.** A terminal opened in `$STUDY` (not started), the observation grid printed or open, a clock visible to the facilitator, the comprehension test on paper or in a separate file the participant cannot open early.
- [ ] **Day 2.** Same machine and study; no `claude --continue` or `--resume`: the participant starts a new chat.

## 4. Consent and data handling

Use [`observation/consent-form.md`](observation/consent-form.md). Read it with the participant and give them a copy.

- **Purpose.** To find problems in a tool, not to evaluate the person. Say it at the start and again before the test.
- **Voluntary.** They may stop at any time, skip any question, and withdraw their data afterwards, with no consequence.
- **What the model sees.** Their messages to Claude Code go to the model provider under the account's terms, as with any use of Claude Code. Ask them not to type personal or confidential information. The data are public (UCI Bank Marketing).
- **What is kept, locally only.** Each item is opt-in on the form:
  - facilitator notes and the observation grid (always, pseudonymised);
  - the comprehension test and debrief answers (always, pseudonymised);
  - the `session-report` output and `.hypotrail/session-log.jsonl` (always: no conversation content);
  - the study folder `.hypotrail/` (it **does** hold their recorded confirmation words: keep only with consent);
  - the Claude Code conversation transcript (stored by Claude Code on the machine): **never exported or copied without explicit consent**;
  - screen and audio recordings.
- **Pseudonyms.** P1, P2, P3. No name, email, or employer in any file. The key linking pseudonyms to people stays with the owner, apart from the data.
- **Storage.** A local folder outside this repository, not synced to a shared drive. Nothing from a session is committed to the repository, except a pseudonymised summary (issue log and scores) and only after the participant agreed to it. Quotations in a summary are short, pseudonymised, and checked for anything identifying.
- **Retention.** Delete recordings and transcripts once the analysis is written, and at the latest after the period stated on the form.

## 5. Session script

Total about 90 minutes on day 1, 25 minutes on day 2. Think-aloud throughout (Ericsson and Simon, 1993, give the method's basis: concurrent verbalisation, with neutral reminders only).

### Introduction (5 min)

Read aloud:

> "Thank you for helping. We are testing a tool, not you: if something is confusing, that is what we want to find. You will do a small data study with an AI assistant in the terminal. Please think aloud: say what you are looking at, what you expect, and what surprises you. I will mostly stay quiet, because I want to see how the tool works without me. If you are stuck, tell me what you would do if I were not here. At the end there is a short questionnaire without the assistant. You can stop at any time."

Think-aloud warm-up (1 minute): ask them to think aloud while finding a file in their home folder.

### Tasks

Give each task on a card, one at a time. The wording below is what the participant reads. Do not add hints.

| # | Task card | Ends when | Time limit | Watch for |
|---|---|---|---|---|
| T1 | **Intent.** "Open a terminal in the study folder, start `claude`, and tell the assistant what you want: your team has a list of bank clients and can only call some of them; you want to know whom to call first." | The agent has proposed the prediction moment | 10 min | First reaction to the plan; whether they read it |
| T2 | **Plan and framing.** "Go through the first decisions with the assistant until it starts working on the data." | Pauses 1 and 2 confirmed or delegated | 20 min | Each pause: time, retyping after a refused "ok", delegation, questions about `duration` and the last-contact columns |
| T3 | **Exploration.** "Let the assistant explore the training data. Ask anything you want explained." | Training EDA results shown | 10 min | Whether they ask why only training rows; whether they ask about `pdays = -1` |
| T4 | **Models.** "Continue until the assistant has compared models." | Both fits done and explained | 10 min | Reaction to the baseline; accuracy vs base rate; "where does this number come from?" |
| T5 | **Policy.** "Your team must decide whom to call. Work with the assistant to choose a rule." | Policy proposed; confirmed or explicitly left open | 15 min | Understanding of threshold vs capacity; whether they delegate; menu repetition |
| T6 | **A neighbouring change.** "Your manager just told you: the team can make only 100 calls. Tell the assistant." | A `capacity:100` evaluation and a new proposal | 10 min | Whether they expect a refit; whether the agent says the model is unchanged; whether they understand which rows the 100 apply to |
| — | **Deliverables (no card).** At the end of T6, if they have not opened it, say once: "The assistant mentioned a report; feel free to look at anything in the folder." | | | Which file they open first; what they look for |
| T7 | **Day 2, new chat.** "Start a new chat in the same folder. Find out where the study stands and what is left." | They state the goal, the decisions, and the next step | 10 min | Do they use `/hypotrail-resume` or ask "where are we?"; is the recap enough; what they still remember |
| T8 | **Conclusion.** "Finish the study with a conclusion you could send to your manager." | A conclusion proposed and confirmed, or the participant stops | 15 min | Proportionate wording; "lost sales"; whether they read the "not yet defensible" list |

If time runs out on day 1, stop after T6 and do T8 on day 2 after T7. Note where they were.

Then, on day 2 after T8: the **comprehension test without assistance** (15 min, §7) and the **debrief** (10 min, §8). Close the terminal and the browser before the test.

### Day-2 timing

Schedule day 2 between 18 and 48 hours after day 1, so that the chat context is gone and memory has decayed as it would at work.

## 6. Facilitator rules

**Do not help.** Do not explain a term, point at a file, confirm an answer, or correct the agent. Neutral prompts only:

- "What are you thinking?" / "What do you expect to happen?" (after 15 to 20 seconds of silence);
- "What would you do if I were not here?" (when they ask you a question);
- "Please keep going in your own way."

Never say "good", "right", or "hmm". Keep the same face for every outcome.

**Intervene only when:**

| Situation | Action | Log it as |
|---|---|---|
| The participant is distressed or wants to stop | Stop at once; thank them; no pressure to continue | stop, reason |
| A setup fault, not the product (network down, login expired, wrong folder) | Fix it, note the time lost, resume | setup |
| Stuck on the same point for the task's time limit, after one "what would you do?" | Give the **standard unblock** for that task (below), then continue | intervention, severity 3 at least |
| The agent asks for something outside the study (credentials, installing packages, editing files outside the folder) | Tell the participant to refuse it; note it | agent off-script, severity 4 |
| They are about to type personal or confidential data | Remind them of the consent form | consent |

Standard unblocks, one sentence each, read verbatim: T2 "You can tell the assistant what you want in your own words, or ask it to choose for you." T5 "You can ask the assistant what each option would mean for your team." T7 "You can ask the assistant where the study stands." T8 "You can ask the assistant to draft the conclusion with you."

## 7. Comprehension test (without assistance)

Paper, or a document on another screen; no terminal, no report, no notebook. 15 minutes. Questions and rubric: [`observation/comprehension-test.md`](observation/comprehension-test.md). Seven open questions, one per concept:

1. the unit of observation;
2. the prediction moment, and why it matters;
3. why `duration` was excluded;
4. the metric used to compare and choose, and why not accuracy;
5. what the interval around a precision means;
6. what changed, and what did not, when the capacity became 100, and why there was no refit;
7. one limit of the study's conclusion (and, if a decision was delegated, what that means).

Each answer scores 0, 1, or 2 against the rubric. Scorers grade without seeing the session notes; with two scorers, compare and discuss differences before the analysis. The answer key refers to the study's own recorded results (result slots and paths, such as `eda.target_rate` `rate`), not to fixed numbers: decisions differ between participants, so the expected figures do too. Read them from that participant's study with `hypotrail status --summary` after the session.

## 8. Debrief interview (10 min)

Semi-structured. Ask in this order; follow up with "Can you say more?" only.

1. "In one sentence, what did you and the assistant produce?"
2. "Was there a moment when the assistant asked you something and you did not know what to answer? What did you do?"
3. "The assistant sometimes did not accept 'ok' and asked for your own words. How did that feel? Did it help, or get in the way?"
4. "Did you rely on any number without checking it? Which one, and why did you trust it?"
5. "Did you open the report or a notebook? What were you looking for? Would you send the report to your manager as it is?"
6. "When you came back the next day, what did you remember, and what did you need to look up?"
7. "If you used 'use your recommended default': what do you think it means for that decision?"
8. "What one thing would you change?"

Then a single rating, 1 to 7: "How confident would you be presenting this study's conclusion to your manager?" Ask what would raise it by one point.

## 9. Analysis

Within two days of each session:

1. Run `hypotrail session-report --study $STUDY --format text > report-P1.md` (outside the repository) and attach it to the session log.
2. Fill the [observation grid](observation/observation-grid.md) from the notes and recording, with a timestamp for each observation.
3. Score the comprehension test.
4. Log each problem in the issue log of the [session log template](observation/session-log-template.md): one row per problem, with evidence and the transcript or recording timestamp, and a severity.

**Severity** (Nielsen's 0 to 4 scale, adapted):

| Severity | Meaning here |
|---|---|
| 0 | Not a problem on reflection |
| 1 | Cosmetic: noticed, no effect on the study or on understanding |
| 2 | Minor: slowed the participant or caused a recoverable mistake |
| 3 | Major: needed the facilitator's standard unblock, or the participant left with a wrong belief on one test concept |
| 4 | Critical: an invalid study move was recorded, a wrong belief on a core concept (leakage, prediction moment, refit) survived the debrief, the agent went off-script, or the participant gave up |

Rate severity from the evidence, not from how often it happened. Merge rows across sessions only when the cause is the same; keep the count of sessions in which it appeared.

**Cross-session summary**, after the last session: the issue log sorted by severity then frequency; comprehension scores per question (a table of P1–P3, no mean with n = 3); the pause timings and refused confirmations from `session-report`; which deliverables were opened; when delegation was used. State what the sessions cannot show (§10). Link each recommendation to issue ids.

**What counts as a finding.** A behaviour seen once with clear evidence is a finding to investigate, not a rate. A behaviour seen in 2 of 3 sessions is a priority. An absence (nobody opened the notebook) is a finding about this group, not a proof that juniors never do.

## 10. Limits

- 2 or 3 participants, recruited by the owner: no estimate of how often a problem occurs, and the group may share a background.
- The facilitator knows the product; neutral prompts reduce, but do not remove, their influence. Think-aloud itself slows people and can change what they attend to.
- One case (Bank Marketing, often used in courses), one agent (Claude Code), one model, at one commit. The model's answers vary between runs: a problem not seen may still occur.
- The test measures what the participant can say the next day, not long-term learning or performance on a new case.
- Day 2 depends on scheduling; record the actual delay.

## References

- Ericsson, K. A., and Simon, H. A. (1993). *Protocol Analysis: Verbal Reports as Data* (revised edition). MIT Press.
- Nielsen, J., and Landauer, T. K. (1993). A mathematical model of the finding of usability problems. *Proceedings of INTERCHI '93*, 206–213.
- Nielsen, J. (2000). Why you only need to test with 5 users. Nielsen Norman Group.
- Nielsen, J. (1994). Severity ratings for usability problems. Nielsen Norman Group.

Other choices in this protocol (task cards, neutral prompts, a standard unblock, blind scoring, an issue log with evidence) are standard usability practice.
