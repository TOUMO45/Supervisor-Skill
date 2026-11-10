---
name: autonomous-supervisor
description: Use when the user hands over a project to deliver, build, or finish from a brief, spec, PRD, idea, or master prompt ("here's the brief", "build me...", "deliver this", "finish this project") - especially when the work spans several steps, sessions, or agents, must survive a handoff or interruption, or gets requirements added mid-conversation. Also use when continuing or resuming an interrupted project or a repo with a .supervisor/ directory, and when asked whether a project is really done or ready to ship. Not for single edits, typos, or quick questions.
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

If `.supervisor/state.json` exists, you are **resuming**: run `$SUP resume` first (§7).

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

Do the critical path first, with the simplest design that meets the criteria. Replan on evidence, but keep the objective.

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

`verified` fingerprints the task's owned files. If they change later, `resume` and `gate` flag the task for re-verification. So re-run a passing check only when it's flagged or something it covers changed. Run targeted checks while building and the full suite at each integration point.

## 6. Failures: bounded retries, then change strategy

1. Reproduce the failure and record the evidence. Find the root cause before fixing.
2. Make one focused fix, then re-verify it and its neighbours.
3. Log each failed fix: `$SUP task attempt T4 --note "regex tweak: still 404"`.
4. **RETRY LIMIT** (3 per strategy): no variations of the same idea. Gather new evidence, then `$SUP task strategy T4 "instrument router"`.
5. **STRATEGY LIMIT** (3 per task): escalate with the evidence log.

The triage playbook is in `references/recovery.md`.

## 7. Memory and resumption

Update memory at milestones, before handoffs, and when context runs low. Keep `$SUP next "..."` current. `MEMORY.md` is re-rendered on every write.

After an interruption, run `$SUP resume` and act in this order:
1. **Verified and unchanged**: don't redo.
2. **Changed since verification**: re-verify.
3. **In flight**: collect the report, or check the agent's files and age before re-dispatching.
4. **Done**: verify.
5. **Blocked**: recheck.
6. **Ready**: start.

Recorded decisions are binding. Reversing one takes a new `decide` with the reason.

## 8. Budget and stopping rules

| Limit | Default | On hit |
|---|---|---|
| Parallel running tasks | 3 (`--max-parallel`) | Queue it |
| Failed attempts per strategy | 3 (`--max-attempts`) | New strategy |
| Strategies per task | 3 (`--max-strategies`) | Escalate |
| Delegation depth | 1 | Supervisor splits the task |
| Scope | Agreed criteria | Stop when the gate passes. Optional ideas go to the user. |

`status` and `gate` report effort (dispatches, failed attempts, strategy changes). Optimize for the total cost of a correct result, including rework.

## 9. Escalate rarely, precisely

Escalate only when you need a decision that changes the outcome, missing access, a scope change, or explicit authorization. Follow `templates/escalation.md`: what blocks you, what you tried, the **smallest** decision needed, and what continues meanwhile. Mark the task `blocked --note "..."` and keep working on everything else. Never ask the user to say "continue", to relay messages between agents, or to repeat anything memory holds.

## 10. Finish honestly

```bash
$SUP criterion drop AC7 --reason "xlsx needs a third-party package"   # descoped, listed as excluded
$SUP next --clear   # the gate refuses while next actions remain
$SUP gate           # 0 VERIFIED COMPLETE | 10 PARTIALLY COMPLETE | 20 BLOCKED
```

Report the gate's verdict verbatim using `templates/final-delivery.md`. **Never call the work complete when the gate disagrees.** For consequential integrations, also fill in `templates/verification-report.md`.

## Host adaptation

| Missing | Fallback, stated plainly |
|---|---|
| Subagents (including when *you* are a subagent) | Run the tracks sequentially and label them that way. Never claim parallelism. |
| Script execution, or the CLI exits `4` (sandboxed / read-only shell) | Keep `.supervisor/MEMORY.md` by hand with your file-writing tool, using `templates/memory.md`. Apply the guards yourself and say the gate is manual. |
| Persistence | Print the memory at milestones for the user to save and paste back. |

Details: `references/host-adaptation.md`.

## Red flags: stop and correct

- You claim "tests pass" without your own output.
- A fourth variation of the same fix.
- Redoing work that `resume` lists as verified and unchanged.
- A roadmap or subagents for a Direct-mode task.
- Fanning out to subagents for tracks of a few tool calls each.
- Saying "complete" while `gate` exits non-zero.
- Two running agents with overlapping files.
- A feature that maps to no criterion.
- A user requirement that exists only in chat.
