# Test Results

All runs used the same subagent model, fresh context, and identical prompts except for
"read SKILL.md and follow it" vs "do not load any skills". Token counts are total subagent tokens
as reported by the host (they include the fixed system-prompt cost of ~85k, so the *marginal*
difference is the meaningful part). Hidden acceptance tests (`tests/e2e/hidden_acceptance.py`)
were never visible to the agents; the oracle scores 18/18 on a reference implementation and 0/18
on the starter.

## 1. Single-turn pressure scenarios (`scenarios.md`)

| Scenario | Baseline (no skill) | With skill |
|---|---|---|
| S1 "done" without proof, deadline | PASS - ran tests + smoke test itself, refused to claim unverified | (not re-run: baseline already passes) |
| S2 3rd regex tweak | PASS - stopped, gathered evidence | PASS - plus `task attempt` / `task strategy` recorded |
| S3 typo fix | PASS - direct edit | PASS - explicitly chose **Direct mode**, no `.supervisor/`, no subagents |
| S4 resume from memory | PASS | (not re-run) |
| S5 delegation brief | PASS - all 9 slots present | (not re-run) |
| S6 no subagents / persistence | PASS - honest fallback | PASS - honest fallback using `templates/memory.md` |
| S7 escalation message | PASS | (not re-run) |
| S8 vague brief | PASS - assumptions + criteria | PASS - Lite mode, `init` + criteria |

**Finding (RED phase):** the baseline model already exhibits every target behaviour in single-turn
form. Per the writing-skills method, no guidance was written to "teach" those behaviours; the
skill instead targets what a single turn cannot provide - durable state and mechanical guards -
and the regression runs confirm it adds no ceremony (S3) and keeps fallbacks honest (S6).

## 2. End-to-end build, single session (`tests/e2e/brief.md`)

| Arm | Hidden score | Tokens | Tool calls | Wall time | Final claim matches oracle? |
|---|---|---|---|---|---|
| Baseline | 18/18 | 94.0k | 5 | 43s | yes |
| With skill | 18/18 | 100.3k | 8 | 57s | yes (`gate`: VERIFIED COMPLETE, 6 criteria with evidence) |

Skill chose Lite mode unprompted. Overhead: +6.7% tokens, +3 tool calls (CLI bookkeeping).
Both arms detected the legacy test contradicting the brief; only the skill arm recorded it as a
durable decision.

## 3. Interruption test (session 1 builds the core, a fresh session 2 finishes)

| Arm | Durable handoff left by session 1 | Session 2 score | Session 2 tokens / calls |
|---|---|---|---|
| Baseline | **none** - excellent notes, but only in the chat reply | 18/18 | 93.1k / 3 |
| With skill | `.supervisor/` with 5 verified criteria, 2 pending tasks, API contract (D3), conflict decision (D1), next actions | 18/18 | 98.8k / 7 |

**Finding:** when the brief fully specifies the work, the code itself is a sufficient handoff and
the skill's memory is overhead (~6% tokens). This motivated test 4.

## 4. Interruption with mid-session user clarifications (`tests/e2e/clarifications.md`)

Session 1 receives two requirements from the user *in conversation* that only session 2's work
(the CLI) can implement; session 2 sees only the original brief and the repository.
Scored with `hidden_acceptance.py --clarified` (20 checks).

| Arm | Where the clarifications survived after session 1 | Session 2 behaviour | Hidden score |
|---|---|---|---|
| Baseline | Env var: implemented in `core.py`. **Exit-3 override: chat reply only.** | Treated `CSVMD_MAX_WIDTH` as unrequested scope creep and **deleted it**; kept exit 2; reported success | **18/20** |
| With skill | `D1` binding decision "user clarification", criteria, `EXIT_MISSING_FILE` constant, next actions | Ran `resume`, honoured D1, implemented both, and flagged to the user that the build deviates from `brief.md` because of a recorded clarification | **20/20** |

Cost: session 2 baseline 95.1k tokens / 3 calls; with skill 100.9k / 6 calls.

**Finding:** this is the failure the skill exists for. A capable agent with no durable memory not
only lost a user requirement, it actively removed a correct implementation of it, because the
written brief was the only surviving source of truth. +6% tokens bought 2 extra correct
requirements and an honest, auditable report.

### Bug found by this test (and fixed)

Session 1 *with* the skill defined criteria for its own slice only, so `gate` printed
**VERIFIED COMPLETE** while the CLI and README did not exist (the agent's prose report caught it,
but the gate - the skill's core promise - was wrong). Session 2 also left stale next actions.

Fix (`supervisor.py` + SKILL.md, regression tests `test_gate_not_complete_while_next_actions_remain`,
`test_next_clear_empties_list_and_unblocks_gate`):
- `gate` returns PARTIALLY COMPLETE while any next action is recorded; `next --clear` closes it.
- VERIFIED COMPLETE now states how many criteria it covers.
- SKILL.md: criteria cover the whole agreed scope including deferred work; user clarifications
  are recorded as decisions + criteria the moment they arrive.

Replayed on the real session-2 state: before the fix `gate` → exit 0; after → exit 10 listing the
stale actions; after `next --clear` → exit 0.

### Re-test after the fix (fresh agent, same clarified session-1 scenario)

| Check | Before fix | After fix |
|---|---|---|
| Criteria span whole scope (incl. deferred CLI/README) | 6 core-only criteria | **10 criteria (AC1-AC10)**, 7 pending |
| User clarifications become criteria + decisions | decisions only | **AC6, AC7 + D2, D3, recorded before coding** |
| Evidence specific per criterion | suite total reused | **named tests per criterion** |
| Gate verdict at end of partial session | VERIFIED COMPLETE (wrong) | **PARTIALLY COMPLETE (exit 10)**, lists AC4-AC10, T2-T4 and open next actions |

Cost: 102.5k tokens / 9 calls (vs 100.6k / 8 before the fix).

## 5. Refactor changes driven by these runs

- **Batch CLI operations** (`criterion add A B C`, `criterion verify AC1 AC2`) and a SKILL.md
  instruction to chain CLI updates with `&&` - transcripts showed CLI bookkeeping as the main
  source of extra tool calls.
- **Criterion-specific evidence recipe** - session 1 of test 3 recorded the same "29 tests OK"
  string as evidence for five different criteria.

## 6. Full mode with real parallel subagents (`tests/e2e/parallel/`)

Brief: `textkit`, three independent modules (slug, toc, stats) plus an integrating CLI. Hidden oracle:
21 checks (reference 21/21, empty dir 0/21). The supervisor ran in the top-level session (spawned
subagents have no spawn tool, verified by listing a subagent's tools), following SKILL.md exactly:
`init` → 7 criteria → interface contract `D1` → 4 tasks with disjoint file ownership → 3 workers
dispatched in one message with full task-assignment briefs → supervisor built the CLI/README (T4)
in parallel → independent verification → evidence per criterion → `next --clear` → `gate`.

| Arm | Hidden score | Project tests | Tokens | Wall time | Verdict |
|---|---|---|---|---|---|
| Single agent, no skill | 21/21 | 14 | 92k | 28s | prose |
| Supervisor + 3 parallel workers | 21/21 | **35** | ~270k workers + supervision | 71s | `gate`: VERIFIED COMPLETE, 7 criteria with evidence, effort: 4 dispatches / 0 failed attempts |

All three workers reported in the required format with real command output; no ownership conflicts.

**Findings:**
1. Full mode works end-to-end, but on tracks of 2-3 tool calls each, fan-out costs ~3x tokens and
   more wall time for equal correctness (more tests is the only quality gain). SKILL.md now says to
   fan out only for substantial tracks (>~10 tool calls), with the measurement in `references/delegation.md`.
2. **Bug:** the parallel limit counted the supervisor's own integration task, blocking the very
   "do non-overlapping work while agents run" pattern the skill prescribes. Fixed: owners `self`,
   `supervisor` and `lead` don't consume an agent slot (still checked for file overlap). Regression
   tests in `TestSelfOwnedWork`.

## 7. v1.1 hardening from a weak-spot audit (all TDD, `tests/test_supervisor_cli.py`)

| Weakness | Upgrade |
|---|---|
| "Verified" work silently goes stale when edited later | `verified` fingerprints owned files; `resume`/`gate` flag drift |
| "3 strategies then escalate" was doc-only | `STRATEGY LIMIT` enforced (exit 3) |
| No way to record descoped work | `criterion drop --reason`; gate lists exclusions |
| `resume` couldn't tell stuck agents from fresh ones | running-since timestamps |
| Concurrent subagents writing state untested | 20-writer stress test, no lost updates |
| No efficiency signal | effort metrics in `status`, `resume`, `gate` |

## 8. Packaging

`claude plugin validate .` passes with **no warnings**; the plugin installs from the marketplace
(`claude plugin install autonomous-supervisor@supervisor-skill`, status enabled). Measured cost:
**~155 tokens always-on** (description only), **~3.2k tokens** when the skill fires.

## 9. `claude plugin eval` suite (`evals/`, Sonnet 5.5, with-plugin vs no-plugin arms)

**Discovery was the biggest weakness, and only this harness could reveal it.** Every earlier
benchmark *told* the agent to read SKILL.md. Run as an installed plugin, the skill **never fired on
its own (0/6)**: it was loaded and listed, but the model chose not to invoke it.

Trigger micro-eval (7 prompts: 5 should fire, 2 should not; 4-6 turns each; ~$0.6 per variant):

| Description | Score | brief+handoff | done-check | resume | typo / question (must not fire) |
|---|---|---|---|---|---|
| v0 (original) | 0.57 | 0/2 | 0/2 | 0/2 | 2/2, 2/2 |
| v1 (user phrases) | 0.86 | 2/4 | 2/2 | 2/2 | 2/2, 2/2 |
| **v2 (shipped)** | **1.00** | **6/6** | 2/2 | 2/2 | 2/2, 2/2 |

The trigger cases are kept in `evals/triggers/` as a regression suite for future description edits.

**Full suite after the fix** (11 cases × 2 runs × 2 arms, $4.60): 10/11 cases pass. Trigger cases Δ +1.00;
`gate-honesty` Δ +0.25 (baseline once gave a verdict without grounded reasons); the remaining outcome
cases tie at 1.00. Sonnet 5.5 handles single-session versions of these scenarios well on its own.

**Resume triggering** was 1/4. Fix: `MEMORY.md` now describes itself (load the skill, the exact
`resume` command), and `state.json` records the CLI path. Afterwards: trigger-resume 3/3, resume-no-redo
3/3, then 2/3 in a later batch (8/9 overall). Even in the miss, the agent followed the header.

**Environment caveat and robustness fix.** In this container the eval sandbox mounts the workspace
read-only to shell commands (`touch plain.txt` fails; Write/Edit tools work), in both arms. So
the CLI couldn't persist state in eval runs, and outcome comparisons here understate the skill. That
exposed a real gap: the CLI died with a raw `OSError` and the skill had no rule for it. Now the CLI
exits `4` with an actionable message, the skill's host-adaptation table says to record progress in
`.supervisor/MANUAL.md` (never overwritten by the CLI, shown by `resume`), and re-tests went from
0/2 to **3/3** runs recording progress, all honestly reporting "gate is manual this session".
