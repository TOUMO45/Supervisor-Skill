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

CLARIFIED_PLACEHOLDER

## 5. Refactor changes driven by these runs

- **Batch CLI operations** (`criterion add A B C`, `criterion verify AC1 AC2`) and a SKILL.md
  instruction to chain CLI updates with `&&` - transcripts showed CLI bookkeeping as the main
  source of extra tool calls.
- **Criterion-specific evidence recipe** - session 1 of test 3 recorded the same "29 tests OK"
  string as evidence for five different criteria.
