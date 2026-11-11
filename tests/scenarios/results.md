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

## 10. v1.2 audit mode: reconstruct what was asked from past sessions

**Feature:** `sessions` / `harvest` read Claude Code session history (`~/.claude/projects/`, matched by folder
name *or* recorded working directory). They extract only human prompts (origin `human`, never tool results,
notifications, hook feedback, injected skill text or subagent transcripts) plus each session's final claim,
redact secrets and git-ignore the digest. `criterion add --source H#` traces each requirement to its prompt.
SKILL.md §11, `references/audit.md` and `templates/audit-report.md` hold the procedure.

**Real-data check:** on this repo's own 5.8 MB transcript, harvest found **11/11** human prompts and nothing
else, in **0.08 s**, giving a **6.8 KB** digest (~850x smaller). Bug found and fixed (TDD): Markdown headings
inside a pasted prompt leaked into the digest structure. Prompts are now quoted.

**Benchmark 1, transcripts location given** (fixture: brief met, two chat requirements buried mid-session in
388 KB of tool noise, final claim "finished, all tests pass"):

| Arm | Found both gaps | Tokens | Calls |
|---|---|---|---|
| No skill | yes | 97k | 5 |
| Skill v1.1 (no audit guidance) | yes (+ flagged an unspecified edge case) | 101k | 6 |

When pointed at a small history, a strong model audits it fine alone.

**Benchmark 2, live audit of this repo, history location NOT given** (ground truth written before results:
H11 audit feature unfinished; H5-H7 questions; H4/H8-H10 chat-only deliverables):

| Arm | Verdict | Tokens | Calls | Notes |
|---|---|---|---|---|
| No skill | correct (H11 incomplete) | 139k | 20 | found `~/.claude/projects` itself; part of its gap evidence quoted the old session's own progress notes |
| **Skill v1.2** | correct, gate PARTIALLY COMPLETE | **116k** | **13** | verified each gap directly (zip contents, installed plugin version, README grep); coverage section listed unseen sources |

Detection ties on this history size. The skill was ~17% cheaper in tokens and ~35% in tool calls, and its
evidence didn't depend on a previous agent having narrated its gaps. n=1 per arm: treat as signal, not proof.

**Note on test design:** planting fixture sessions in `~/.claude/projects/` was blocked by the environment's
safety classifier as transcript tampering. That block is correct, which is why benchmark 2 used the real history.

**Trigger regression after the description change:** 16/16 runs. The new `trigger-audit-old-project` case fired
2/2; all earlier positives still fire and the typo/question negatives don't.

**CI:** `tests/e2e/audit/make_fixture.py` + a CI step checks harvest finds the buried requirement, excludes
noise, and that the oracle confirms both gaps (18/20 on `--clarified`).

## 11. v1.3: three gaps found by auditing a real project (ECCode)

The audit mode was run on a real, unseen project: 20 branches, 22 cloud sessions, v0.16.0. It produced a
correct, cited audit (3 criteria verified by running the code, 4 failed, 2 unverifiable), and exposed three
gaps in the skill. All three are fixed test-first.

| Gap | What happened on the real project | Fix |
|---|---|---|
| The skill never said to look at other branches | The default checkout was shallow and showed 1 branch; the real latest work was on an unmerged line 284 commits ahead. Found by judgment, not by the skill. | `branches` (ahead/behind, merged?, most recent unmerged branch; warns on shallow clones and lists unfetched remote branches; `--fetch`). SKILL.md §11 step 1. |
| History reader only saw this machine | All 22 sessions were cloud sessions: `harvest` saw none. | `harvest --extra` merges session records and prompts collected elsewhere; `events` copies typed prompts exactly out of saved session dumps; coverage lists sessions whose prompts were not read and tallies final statuses. |
| No "not yet proven" status | The project's central claim (beats a plain agent) is unmeasured; it had to be recorded as `failed`. | `criterion unverifiable --reason`: neither passed nor failed, reported separately, gate stays PARTIALLY COMPLETE. |

**RED/GREEN on the branch trap** (`tests/e2e/audit/make_branch_fixture.py`: a shallow single-branch clone;
`search`/`export` built with tests on an unfetched branch; `sync` needs a real server):

| Skill | Runs | Result |
|---|---|---|
| v1.2 | 2 | **0/2.** Both reported search, export and sync as "MISSING, no code" and recommended implementing them. Neither looked beyond the local checkout. |
| v1.3 | 2 | **2/2.** Both ran `branches`, fetched, reported "built but unmerged" with the branch name and commit count, and recorded sync as `unverifiable`. Verified from their recorded state, not only their reports. |

Cost: v1.2 about 98k tokens and 7 tool calls per run; v1.3 about 104k and 9.

**Real-data checks:**
- `branches` on the full ECCode clone named `s4-add3/base` (284 ahead, 2026-11-09) as the latest work in one
  command. A research subagent had needed about 200k tokens and 4 minutes for the same answer.
  Bug found on the way and fixed: the first version picked the branch with the *most commits* (an October side
  line, 441 ahead) instead of the *most recent* one.
- Cloud path: a subagent recovered 3 typed prompts and 2 final claims from two real sessions in 6 calls.
  `events` reproduced its lines exactly from the saved pages. Merged with 22 session records, `harvest`
  reported "2 read, 20 known but not read; final status: blocked 14, completed 7, review_ready 1".
- That tally corrected a hand count ("13 of 22 blocked") made earlier in the same audit. Counts are now printed
  by the tool.

**Other bugs found and fixed in this round (each with a regression test):** `token=...` was not redacted;
piping any command into `grep -q` printed a false "cannot write project memory" error.

**Limits:** reading cloud prompts is still expensive (events include every tool result), so the procedure reads
session records for all sessions and prompts for selected ones, and says which were not read. n=2 per arm.

## 12. Reading a project's entire cloud history (ECCode: 22 sessions, 5 weeks)

Asked to study everything from the first prompt to today, the supervisor read 21 of 22 cloud sessions back
to their first event, and the last 20 hours of the 22nd (stopped on budget: 224 pages for 20 hours of a
hackathon side project; the rest is covered by that session's own continuation summary and stated as such).

| Measure | Value |
|---|---|
| Pages of events paged | 989 (about 1 MB each on busy stretches) |
| Typed prompts recovered | 139, including the original 12,697-character brief |
| Harness lines filtered out | 63 (safety notices, continuation summaries, subagent briefs, images) |
| Raw data entering the supervisor's context | none: pages are saved to files and parsed by `events` |
| Paging agents | haiku, one per session queue, 110-call budget each, resumable cursor |
| Analysis | 7 analysts by phase, each writing a cited requirements ledger |

**Bugs found in the tool by real data, all fixed test-first:** strict JSON rejected pages with raw line
breaks; a second save format nests the events as a JSON string inside a text block; harness messages were
taken for typed prompts.

**Process failures, kept for the record:**
- A paging agent read "110 calls in total" as including earlier agents' calls and stopped after one page.
  The brief now says whose calls count.
- The supervisor first reported a "docs contradict themselves" finding from a subagent after confirming
  only that the quoted sentences existed. Opening the files before "fixing" them showed two of the three
  gaps were false alarms (a dated addendum that was true on its date; a troubleshooting table the checker
  had missed). The audit was corrected, and `references/audit.md` now requires checking date and context.
- End-of-turn summaries were captured at 2,500 characters at first, cutting some "decision needed"
  sections; raised to 9,000 for the later sessions.

## 13. Second run on ECCode (v1.4): what the tool itself got wrong or lacked

A fresh session was asked to pick the project up again. Everything the earlier study had produced was in an
ephemeral scratchpad and was gone; only the skill, the repository and the cloud sessions remained. Running
the skill's own audit flow on itself and on ECCode found these, each reproduced before it was fixed:

| Found | How | Fix |
|---|---|---|
| `branches` reported the latest branch **640** commits ahead; the true figure is **284** | shallow clone: counts stop at the cut. The warning also still said "re-run with --fetch" after `--fetch` | `--fetch` now fetches full history; warning rewritten; regression test on a shallow clone |
| Final claim of a 5-week session was "Nothing changed on the pull request" | the session ended in automatic PR check-ins | `events` keeps the last three assistant messages |
| The cheapest source was being thrown away | continuation summaries were filtered as harness noise, yet the last page of one long session held all 16 of its user messages | `events`/`harvest` extract them as a separate, labelled lead; coverage says which sessions rest on a summary only |
| Two agents could own the same file | `./src//a.py` and `src/a.py` did not overlap | paths normalised when a task is added |
| Traceback instead of an error | an absolute path in `--files` crashed `verified` | refused at `task add`; tolerated in old state files |
| `--evidence " "` verified a criterion | blank string passed the check | blank evidence and reasons are refused (exit 2) |
| A task waiting on a dropped task could never start | dependency had to be `verified` | a dropped dependency no longer holds dependents; the drop names them |
| Sort by date compared local-time text | branches committed in different time zones | sorted by commit instant |

**Missing capabilities, added:**
- **Owner questions (`ask` / `answer`).** In ECCode's history 14 of 22 sessions ended waiting on the owner,
  and the open questions were re-derived each session. They are now state: recorded with a recommended
  default, shown first by `resume`, blocking only the tasks named, listed by the gate, and turned into a
  binding decision when answered. The earlier study itself is the proof of need: its ten recommendations
  were lost with its container.
- **Mini-goals (`milestone add`, `gate --milestone`).** A large project now has ordered, separately gated
  slices; `resume` marks the current one. A verified mini-goal never makes the project gate pass.

**Not measured:** whether mini-goals and recorded questions reduce the number of prompts a human must send
on a large build. That needs a with/without run on a multi-session project and has not been done.
