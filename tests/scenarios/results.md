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

RETEST_PLACEHOLDER

## 5. Refactor changes driven by these runs

- **Batch CLI operations** (`criterion add A B C`, `criterion verify AC1 AC2`) and a SKILL.md
  instruction to chain CLI updates with `&&` - transcripts showed CLI bookkeeping as the main
  source of extra tool calls.
- **Criterion-specific evidence recipe** - session 1 of test 3 recorded the same "29 tests OK"
  string as evidence for five different criteria.
