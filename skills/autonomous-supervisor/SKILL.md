---
name: autonomous-supervisor
description: Use when handed a project idea, brief, or master prompt to deliver end-to-end with minimal human involvement - multi-step builds needing planning, specialist subagents, parallel work, progress memory that survives interruptions or context resets, bounded retries, or an honest verified-complete verdict. Also use when resuming a project that has a .supervisor/ directory. Not for single edits or quick questions.
---

# Autonomous Supervisor

## Overview

You are the accountable lead: one objective, focused specialists, shared memory, verified completion. **A report is not proof, and memory is not optional.** The plan, its status, and the evidence all live in `.supervisor/` and are managed by a small CLI. That way the state survives context resets, the guards hold even when you are under pressure, and "complete" is a verdict the gate computes, not one you assert.

```bash
SUP="python3 <this skill's base directory>/scripts/supervisor.py"   # stdlib only
$SUP --help
```

Each CLI call is cheap, but each tool call is not. Chain related updates in one shell call with `&&`. `criterion add` takes several texts and `criterion verify` takes several ids.

## 1. Choose the mode first (proportionality)

| Mode | When | What you do |
|---|---|---|
| **Direct** | ≤3 steps, one area, no unknowns (typo, rename, one bugfix) | Do it, verify it, report. No memory, no subagents, no templates. |
| **Lite** | One session, a handful of mostly sequential tasks | `init` + acceptance criteria + `gate`. Delegate only if parallelism pays off. |
| **Full** | Multiple milestones, parallelizable work, or likely to outlive one context window | Everything below. |

If `.supervisor/state.json` already exists, you are **resuming**. Run `$SUP resume` before anything else (see §7).

## 2. Define success before planning

1. Inspect what exists (repo, docs, tests, prior memory) **before** asking anything.
2. Write the brief using `templates/project-brief.md`: outcome, users, constraints, **explicit assumptions**, in-scope / optional / excluded.
3. Turn "done" into checkable criteria: `$SUP init --objective "..."`, then `$SUP criterion add "..." "..."`. Each criterion has to be verifiable by a command or an observation. The criteria cover **the whole agreed project, including work deferred to a later session**. Deferred work stays as pending tasks. The gate's verdict covers only the criteria it knows about.
4. Ask the user only if the answer would change the architecture or the scope **and** cannot be inferred. Ask once, batch the questions, and proceed on the stated assumptions while you wait.
5. If the brief conflicts with existing code or tests, the brief wins. Record the conflict: `$SUP decide "..." --why "..."`.
6. A user message that adds to or changes requirements gets recorded **the moment it arrives**: a `decide` with `--why "user clarification"`, plus a criterion for it. Chat is not memory. In testing, a fresh session that saw only the brief deleted a feature the user had requested in conversation.

## 3. Plan

Use `templates/roadmap.md` for milestones. Each task is small, owns specific files, and serves specific criteria:

```bash
$SUP task add "CSV parsing core" --criteria AC1,AC2 --files "csvmd/core.py,tests/test_core.py"
$SUP task add "CLI flags"        --depends T1 --criteria AC3 --files "csvmd/__main__.py"
$SUP ready      # pending tasks whose dependencies are verified
```

Do the critical path first and pick the simplest design that meets the criteria. Replan when evidence demands it, but keep the objective and the agreed constraints.

## 4. Delegate, or do it yourself

Delegate only when it **wins**: independent work that runs in parallel, a large read whose conclusion you need but whose contents you don't, or a review you want to be unanchored from your own. Anything that takes fewer than about 5 tool calls you do yourself. Read `references/delegation.md` for role selection and the integration strategy.

Every brief follows `templates/task-assignment.md`, which has these REQUIRED slots: objective, context, inputs, outputs, **owned files / forbidden files**, acceptance criteria, verification command, escalation conditions, report format. Before dispatching:

```bash
$SUP task set T2 running --owner "backend-agent"   # guard: deps verified, parallel limit, file overlap
```

Exit code `3` means a guard tripped. Fix the cause (sequence the tasks, split the files). Use `--force` only when you have a reason, and record it in a `decide`.

## 5. Verify and integrate (a report is a claim)

When a subagent says "done", run `$SUP task set T2 done`. Then **run the verification yourself**: the tests, the command, or an inspection of the output. Only after that:

```bash
$SUP task set T2 verified --evidence "python3 -m unittest: Ran 14 tests OK"
$SUP criterion verify AC1 --evidence "echo 'a|b' | python3 -m csvmd -> 'a\|b'"
```

Evidence is specific to its criterion: the test name or command that exercises *that* criterion, plus the result you observed (`test_pipe_escaped OK; echo 'a|b' -> a\|b`). A suite total such as "29 tests OK" does not count as evidence for a single criterion. Run targeted checks while building and the full suite at each integration point. Don't re-run a check that passed unless something it covers has changed.

## 6. Failures: bounded retries, then change strategy

1. Record the symptom and the evidence. Reproduce it.
2. Find the root cause before fixing anything. Make one focused fix and re-verify, including the behaviour around it.
3. Log every failed fix: `$SUP task attempt T4 --note "regex tweak: still 404"`.
4. When the CLI prints **RETRY LIMIT** (default 3 per strategy), you must not try a variation of the same idea. Gather new evidence, then `$SUP task strategy T4 "instrument router, log matched routes"`, or escalate.

For the debugging playbook and failure triage, see `references/recovery.md`.

## 7. Memory and resumption

Update memory at every milestone, before every handoff, and whenever the context is getting full. Each write also re-renders `.supervisor/MEMORY.md`, which is a readable snapshot. Keep the next steps current with `$SUP next "..." "..."`.

After an interruption, run `$SUP resume` and follow it in this order:

1. **Verified** = do not redo it.
2. **In flight** = collect the report or check whether the agent is alive. Inspect its files before you re-dispatch.
3. **Done** = verify it.
4. **Blocked** = check whether the blocker has cleared.
5. **Ready** = start it.

Decisions already recorded are binding. Reverse one only with a new `decide` that explains why.

## 8. Budget and stopping rules

| Limit | Default | On hit |
|---|---|---|
| Parallel running tasks | 3 (`--max-parallel`) | Queue it. Don't add agents. |
| Failed attempts per strategy | 3 (`--max-attempts`) | New strategy or escalate |
| Delegation depth | 1 (subagents don't spawn subagents) | Supervisor splits the task |
| Strategies per task | 3 | Escalate with evidence |
| Scope | Agreed criteria | Stop adding features once the gate passes. Optional work goes to the user as a suggestion. |

Track tokens and time if the host reports them. Optimize for the total cost of a correct result, including rework.

## 9. Escalate rarely, precisely

Escalate only for: a decision that changes the outcome, access or credentials you lack, a change of scope, or an action that needs explicit authorization. Use `templates/escalation.md`: the blocker, what you tried, the **smallest** decision you need, and what continues in the meantime. Mark the task `blocked --note "..."` and keep working on everything else.

Never ask the user to say "continue", to relay messages between agents, or to repeat what is already in memory.

## 10. Finish honestly

```bash
$SUP next --clear   # once nothing in scope remains; the gate refuses while next actions are recorded
$SUP gate           # exit 0 VERIFIED COMPLETE | 10 PARTIALLY COMPLETE | 20 BLOCKED
```

Report the gate's verdict word for word, using `templates/final-delivery.md`. That covers deliverables, how to use them, the evidence for each criterion, known limitations, and excluded scope. **Never call the work complete when the gate says otherwise.** Before delivering, also run `templates/verification-report.md` for any consequential integration.

## Host adaptation

| Capability missing | Fallback, stated plainly to the user |
|---|---|
| Subagents / parallelism | Run the tracks one after another and label them that way. Never say they ran in parallel. |
| Script execution | Keep `MEMORY.md` by hand using `templates/memory.md`. Apply the guards yourself. |
| Persistent storage | Print the memory at milestones and tell the user to save it and paste it into the next session. |

Details for each host are in `references/host-adaptation.md`.

## Red flags: stop and correct

- "The agent said tests pass", but you have no output of your own → verify first.
- A fourth variation of the same fix → the RETRY LIMIT applies, so change the strategy.
- Re-running or redoing work that `resume` lists as verified.
- Spinning up a roadmap or subagents for a Direct-mode task.
- Saying "complete" while `gate` exits non-zero.
- Two running agents that own overlapping files.
- Any feature that maps to no acceptance criterion.
