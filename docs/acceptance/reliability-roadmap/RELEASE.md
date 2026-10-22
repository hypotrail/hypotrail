# Reliability roadmap release dossier

Tested tree: final J4–J7 change set based on `0263ccc`; the immutable commit SHA is recorded
in the delivery note because a commit cannot contain its own hash. Date: 2026-10-22.

## Independent status axes

| Axis | Status | Evidence |
|---|---|---|
| Technical implementation | implemented; automated gates passed | J0–J7 records and repository tests |
| Real tool integration | not run | `REAL-TOOL-MANUAL.md` is prepared; no real Copilot/VS Code/Marimo claim |
| Human use and learning | not observed | `HUMAN-SESSION-SHEET.md` is prepared; no efficacy claim |

## J0–J7 requirement matrix

| Milestone | Implemented boundary | Automated evidence | External evidence / limit |
|---|---|---|---|
| J0 | `review-v1` contract and explicit assurance | existing J0/profile suites | local source accessibility remains |
| J1 | exact reserved membership and leakage-resistant evaluation plan | J1 and split/evaluation suites | bounded supported protocols |
| J2 | requirements, validity and claim eligibility | J2/validity suites | eligibility is not proof of truth |
| J3 | criterion conventions and verdict logic | J3 truth-table suites | bounded metric conventions |
| J4 | exact compatibility edges, inspection ledger, exposure coverage/history | J4 tests in the bounded corpus | preview/workbench/external files unrecorded; cross-study history not enforced |
| J5 | context-bound references, typed wording, formatter, pause payload | J5 tests plus numeric/guidance suites | lexical causal coverage is incomplete |
| J6 | common snapshot, guarded notebook, historical/final drift, preservation | J6 and existing render/preservation suites | real Marimo UI not observed |
| J7 | bounded corpus, four journey families, scripts and dossier | existing binary/regression EN/FR journey suites plus J7 corpus | paid agent, real tools and humans not run |

## Profile, defaults, cases and rollout

`review-v1` remains explicit; this work does not silently change default activation. Legacy
studies remain readable and are not reset or migrated destructively. Compatibility attestations
are directed from one digest to one destination and one activity; missing, wildcard and
transitive compatibility are rejected. A stale declaration merely stops matching.

The automated gate covers synthetic binary/regression journeys and the committed case adapters
already in the repository. It does not authorize rerunning historical holdouts or case-training
scripts. Hotel’s restricted claim, Bank timing limits and Auto MPG units/baseline remain adapter
requirements rather than general claims about all datasets.

## Automated gate results

Run on 2026-10-22 from the repository root:

| Gate | Result |
|---|---|
| `uv run --project framework python -m pytest -q -p no:cacheprovider framework/tests` | 1,881 passed, 94 skipped |
| `python3 scripts/check_layout.py` | clean: 7 cases, 0 errors |
| `node --test clients/vscode-companion/test/*.test.js` | 239 passed |
| `uv run --project framework python -m pytest -q -p no:cacheprovider clients/vscode-companion/test` | 401 passed, 12 expected environment/tool skips |
| `test_webview_gate.py --update-baselines` after visual review | 36 passed; 12 parameterized pixel cases rewrote their affected images |
| `test_webview_gate.py` against the rewritten baselines | 36 passed |
| J4–J7 bounded corpus | 5 passed |

The browser image initially resolved generic system fonts to an unusable WOFF2 face. The
functional and visual reruns used a temporary Fontconfig mapping to the already required DejaVu
Sans and DejaVu Sans Mono fonts; the mapping is not part of the product. Representative wide,
mobile and high-contrast baseline/actual/diff images were reviewed before regeneration.

## Known limits and next developer instructions

- Do not describe an unrun real-tool script as observed, or a simulated junior as learning.
- Keep raw paid-agent sessions outside the repository; record budget, model and denominators.
- Before changing the default profile, rerun the legacy/new-profile matrix and explain existing
  study behavior. Default activation, publication and extension installation are separate acts.
- Never use a state reset as rollout. Preserve the single opening and history of final evidence.
- Record the immutable integration commit in the delivery note; do not infer one from an
  uncommitted worktree.
