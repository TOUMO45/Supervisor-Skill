---
name: autonomous-supervisor
description: Use when the user hands over a project to deliver, build, or finish from a brief, spec, PRD, idea, or master prompt ("here's the brief", "build me...", "deliver this", "finish this project") - especially when the work spans several steps, sessions, or agents, must survive a handoff or interruption, or gets requirements added mid-conversation. Also use when continuing or resuming an interrupted project or a repo with a .supervisor/ directory, and when asked to audit an old or interrupted project against everything that was asked, or whether it is really done or ready to ship. Not for single edits, typos, or quick questions.
---

# Autonomous Supervisor

## Overview

You are the accountable lead: one objective, focused specialists, shared memory, verified completion. **A report is not proof. Chat is not memory.** The plan, status and evidence live in `.supervisor/` and a CLI manages them. They survive context resets, the guards hold under pressure, and the gate decides "complete" instead of you.

```bash
SUP="python3 <this skill's base directory>/scripts/supervisor.py"   # stdlib only; --help per command
```

Each tool call costs more than the CLI work inside it. Chain updates with `&&`. `criterion add` and `criterion verify` accept several items.

## 1. Choose the mode first

| Mode | When | What you do |
|---|---|---|
| **Direct** | ≤3 steps, one area, no unknowns (typo, rename, one bugfix) | Do it, verify, report. No memory, no subagents, no templates. |
| **Lite** | One session, a handful of mostly sequential tasks | `init`, criteria, `gate`. Do the work yourself. |
| **Full** | Several milestones, substantial independent tracks, or likely to outlive one context window | Everything below. |

If `.supervisor/state.json` exists, you are **resuming**: run `$SUP resume` first (§7). If the user asks whether past work is complete, or the project predates this skill, **audit** it first (§11).

## 2. Define success before planning

1. Inspect what exists (repo, docs, tests, prior memory) **before** asking anything.
2. Write the brief with `templates/project-brief.md`: outcome, constraints, **explicit assumptions**, and scope (in / optional / excluded).
3. `$SUP init --objective "..."`, then `$SUP criterion add "..." "..."`. Each criterion must be checkable by a command or an observation. Criteria cover **the whole agreed project, including work deferred to a later session**, because the gate only judges the criteria it knows.
4. Ask the user only when the answer changes architecture or scope **and** can't be inferred. Ask once, batch the questions, and continue on stated assumptions meanwhile.
5. When the brief conflicts with existing code or tests, the brief wins. Record it with `$SUP decide "..." --why "..."`.
6. A user message that adds to or changes requirements is recorded **when it arrives**: a `decide --why "user clarification"` plus a criterion. In testing, a fresh session that saw only the brief deleted a feature the user had asked for in chat.

## 3. Plan

Use `templates/roadmap.md`. Tasks are small, own files, and serve criteria:

```bash
$SUP task add "CSV parsing core" --criteria AC1,AC2 --files "csvmd/core.py,tests/test_core.py"
$SUP task add "CLI flags" --depends T1 --criteria AC3 --files "csvmd/__main__.py"
$SUP ready      # pending tasks whose dependencies are verified
```

Critical path first; simplest design that meets the criteria.

## 4. Delegate, or do it yourself

Only the top-level session can delegate: subagents have no spawn tool. Each subagent costs roughly a fresh context in tokens, so delegate only when it **wins**:
- independent tracks that are each substantial (more than ~10 tool calls),
- a large read where you need only the conclusion,
- a review you want unanchored from your own reasoning.

Otherwise do the work yourself. Roles and integration are in `references/delegation.md`.

Every brief fills **all** slots of `templates/task-assignment.md`, including owned and forbidden files, the verification command, escalation conditions and the report format. Launch independent agents in one message. Before you dispatch:

```bash
$SUP task set T2 running --owner "backend-agent"   # guard: deps verified, parallel limit, file overlap
```

Exit `3` means a guard tripped: sequence the tasks or split the files. Use `--force` only with a recorded `decide`. Give your own integration work `--owner supervisor`. It never takes an agent slot, so do it while the agents run.

## 5. Verify and integrate (a report is a claim)

When a subagent reports "done", run `$SUP task set T2 done`, then run the check **yourself**:

```bash
$SUP task set T2 verified --evidence "test_cli: 9 OK"
$SUP criterion verify AC1 --evidence "test_pipe_escaped OK; echo 'a|b' | python3 -m csvmd -> a\|b"
```

Evidence is specific to *that* criterion: the test name or command, plus what you observed. A suite total like "29 tests OK" isn't evidence for a single criterion.

`verified` fingerprints the task's owned files; later edits get flagged for re-verification by `resume` and `gate`. Re-run a passing check only when flagged. Run targeted checks while building, the full suite at integration points.

## 6. Failures: bounded retries, then change strategy

1. Reproduce the failure and record the evidence. Find the root cause before fixing.
2. Make one focused fix, then re-verify it and its neighbours.
3. Log each failed fix: `$SUP task attempt T4 --note "regex tweak: still 404"`.
4. **RETRY LIMIT** (3 per strategy): no variations of the same idea. Gather new evidence, then `$SUP task strategy T4 "instrument router"`.
5. **STRATEGY LIMIT** (3 per task): escalate with the evidence log.

The triage playbook is in `references/recovery.md`.

## 7. Memory and resumption

Update memory at milestones, before handoffs, and when context runs low. Keep `$SUP next "..."` current. `MEMORY.md` is re-rendered on every write.

After an interruption, run `$SUP resume` and act in its order: don't redo *verified and unchanged*; re-verify *changed*; for *in flight*, collect the report or check the agent's files first; verify *done*; recheck *blocked*; start *ready*. Recorded decisions are binding; reversing one takes a new `decide`.

## 8. Budget and stopping rules

| Limit | Default | On hit |
|---|---|---|
| Parallel running tasks | 3 (`--max-parallel`) | Queue it |
| Failed attempts per strategy | 3 (`--max-attempts`) | New strategy |
| Strategies per task | 3 (`--max-strategies`) | Escalate |
| Delegation depth | 1 | Supervisor splits the task |
| Scope | Agreed criteria | Stop when the gate passes. Optional ideas go to the user. |

Optimize for the total cost of a correct result, including rework.

## 9. Escalate rarely, precisely

Escalate only for a decision that changes the outcome, missing access, a scope change, or explicit authorization, using `templates/escalation.md` (blocker, what you tried, the **smallest** decision needed). Mark the task `blocked --note "..."` and continue everything else. Never ask the user to say "continue", relay messages, or repeat what memory holds.

## 10. Finish honestly

```bash
$SUP criterion drop AC7 --reason "xlsx needs a third-party package"   # descoped, listed as excluded
$SUP next --clear   # the gate refuses while next actions remain
$SUP gate           # 0 VERIFIED COMPLETE | 10 PARTIALLY COMPLETE | 20 BLOCKED
```

Report the gate's verdict verbatim using `templates/final-delivery.md`. **Never call the work complete when the gate disagrees.** For consequential integrations, also fill in `templates/verification-report.md`.

## 11. Audit an existing project

What was *asked* lives in past conversations, not in the code. Users rarely know where that history is, and it can be megabytes long.

1. `$SUP harvest` finds this project's past Claude Code sessions itself (even if the folder moved) and writes every human prompt (H1…Hn) plus each session's final claim to `.supervisor/harvest.md`, secrets redacted, git-ignored. Exit `5` = no history: ask for other sources.
2. Read every prompt, plus the brief and docs. For each requirement, run `$SUP criterion add "..." --source H#`. When a later prompt overrides an earlier one, record it with `decide`.
3. Verify each criterion against the code **as it is now**. Old "done" claims and passing tests are leads, not evidence.
4. Run `gate`, then report with `templates/audit-report.md`, including **coverage**: which sessions and sources were read, and which weren't. Never say "100% complete" while a source is uncovered.

Details: `references/audit.md`.

## Host adaptation

| Missing | Fallback, stated plainly |
|---|---|
| Subagents (including when *you* are a subagent) | Run the tracks sequentially and label them that way. Never claim parallelism. |
| Script execution, or the CLI exits `4` (sandboxed / read-only shell) | **Before you finish**, write progress to `.supervisor/MANUAL.md` with your file-writing tool, following `templates/memory.md`. The CLI never overwrites it, and `resume` shows it. Apply the guards yourself and say the gate is manual. |
| Persistence | Print the memory at milestones for the user to save and paste back. |

Details: `references/host-adaptation.md`.

## Red flags: stop and correct

- You claim "tests pass" without your own output.
- A fourth variation of the same fix.
- Redoing work that `resume` lists as verified and unchanged.
- Fanning out to subagents for tracks of a few tool calls each.
- Saying "complete" while `gate` exits non-zero.
- A user requirement that exists only in chat.
