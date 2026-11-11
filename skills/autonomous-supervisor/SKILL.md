---
name: autonomous-supervisor
description: Use when the user hands over a project to deliver, build, or finish from a brief, spec, PRD, idea, or master prompt ("here's the brief", "build me...", "deliver this", "finish this project") - especially when the work spans several steps, sessions, or agents, must survive a handoff or interruption, or gets requirements added mid-conversation. Also use when continuing or resuming an interrupted project or a repo with a .supervisor/ directory, and when asked to audit an old or interrupted project against everything that was asked, or whether it is really done or ready to ship. Not for single edits, typos, or quick questions.
---

# Autonomous Supervisor

## Overview

You are the accountable lead: one objective, focused specialists, shared memory, verified completion. **A report is not proof. Chat is not memory.** Plan, status and evidence live in `.supervisor/`, managed by a CLI: they survive context resets, and the gate decides "complete", not you.

```bash
SUP="python3 <this skill's base directory>/scripts/supervisor.py"   # stdlib only; --help per command
```

Chain updates with `&&`; `criterion add`/`verify` take several items.

## 1. Choose the mode first

| Mode | When | What you do |
|---|---|---|
| **Direct** | ≤3 steps, one area, no unknowns (typo, rename, one bugfix) | Do it, verify, report. No ceremony. |
| **Lite** | One session, a handful of mostly sequential tasks | `init`, criteria, `gate`. Do the work yourself. |
| **Full** | Several milestones, substantial independent tracks, or likely to outlive one context window | Everything below. |

If `.supervisor/state.json` exists, you are **resuming**: run `$SUP resume` first (§7). If the user asks whether past work is complete, or the project predates this skill, **audit** it first (§11).

## 2. Define success before planning

1. Inspect what exists (repo, docs, tests, prior memory) **before** asking anything.
2. Write the brief with `templates/project-brief.md`: outcome, constraints, **explicit assumptions**, and scope (in / optional / excluded).
3. `$SUP init --objective "..."`, then `$SUP criterion add "..." "..."`. Each criterion must be checkable by a command or an observation. Criteria cover **the whole agreed project, including work deferred to a later session**: the gate judges only those.
4. Don't ask what you can infer or decide (§9).
5. When the brief conflicts with existing code or tests, the brief wins: `$SUP decide "..." --why "..."`.
6. A user message that adds or changes requirements is recorded **when it arrives**: a `decide --why "user clarification"` plus a criterion. In testing, a fresh session deleted a feature requested only in chat.

## 3. Plan

Use `templates/roadmap.md`. Split a big project into ordered **mini-goals**, each an observable outcome with its own criteria; finish one before starting the next:

```bash
$SUP milestone add "Core parses CSV" && $SUP criterion add "pipes escaped" --milestone M1
$SUP gate --milestone M1      # this mini-goal only; the project gate still decides "complete"
```

Tasks are small, own files, and serve criteria:

```bash
$SUP task add "CSV parsing core" --criteria AC1,AC2 --files "csvmd/core.py,tests/test_core.py"
$SUP task add "CLI flags" --depends T1 --criteria AC3 --files "csvmd/__main__.py"
$SUP ready      # pending tasks whose dependencies are verified
```

Critical path first; simplest design that works.

## 4. Delegate, or do it yourself

Only the top-level session can delegate. Each subagent costs a fresh context, so delegate only when it **wins**:
- independent tracks that are each substantial (more than ~10 tool calls),
- a large read where you need only the conclusion,
- a review you want unanchored from your own reasoning.

Otherwise do it yourself. Roles: `references/delegation.md`.

Every brief fills **all** slots of `templates/task-assignment.md`. Launch independent agents in one message. Before dispatching:

```bash
$SUP task set T2 running --owner "backend-agent"   # guard: deps verified, parallel limit, file overlap
```

Exit `3` = a guard tripped: sequence the tasks or split the files (`--force` only with a `decide`). Your own work is `--owner supervisor`: it takes no agent slot.

## 5. Verify and integrate (a report is a claim)

On a subagent's "done": `$SUP task set T2 done`, then run the check **yourself**:

```bash
$SUP task set T2 verified --evidence "test_cli: 9 OK"
$SUP criterion verify AC1 --evidence "test_pipe_escaped OK; echo 'a|b' | python3 -m csvmd -> a\|b"
```

Evidence is specific to *that* criterion: the command plus what you observed, not a suite total.

`verified` fingerprints the task's owned files; `resume` and `gate` flag later edits for re-verification. Targeted checks while building; the full suite at integration points.

## 6. Failures: bounded retries, then change strategy

Reproduce, find the root cause, make one focused fix, re-verify. Log each failed fix: `$SUP task attempt T4 --note "regex tweak: still 404"`.

- **RETRY LIMIT** (3 per strategy): gather new evidence, then `$SUP task strategy T4 "instrument router"`.
- **STRATEGY LIMIT** (3 per task): escalate with the evidence log.

Triage playbook: `references/recovery.md`.

## 7. Memory and resumption

Update memory at milestones, before handoffs, and when context runs low. Keep `$SUP next "..."` current. In an ephemeral container, commit `.supervisor/`.

After an interruption, run `$SUP resume` and act in its order: don't redo *verified and unchanged*; re-verify *changed*; for *in flight*, check the agent's report or files first; verify *done*; recheck *blocked*; start *ready*. Decisions are binding; reversing one takes a new `decide`.

## 8. Budget and stopping rules

| Limit | Default | On hit |
|---|---|---|
| Parallel running tasks | 3 (`--max-parallel`) | Queue it |
| Failed attempts per strategy | 3 (`--max-attempts`) | New strategy |
| Strategies per task | 3 (`--max-strategies`) | Escalate |
| Scope | Agreed criteria | Stop when the gate passes; offer extras, don't build them |

## 9. Decide yourself; ask only for four things

Work may wait for the owner **only** for `spend` (beyond an approved ceiling), `irreversible` (delete, publish, merge), `access` (you tried and failed to get it), or `goal` (scope changes). Everything else you decide, record, and report afterwards:

```bash
$SUP decide "export omits the cache folder" --why "init fails with it; reversible"
$SUP ask "Postgres or SQLite?" --default "SQLite"                                 # assumption: work continues
$SUP ask "Run the paid benchmark?" --default "no" --blocks T7 --because spend     # only T7 waits
$SUP answer Q2 "yes, up to $5"                                                    # becomes a decision; unblocks T7
```

Ask blocked questions once, together (`templates/escalation.md`). While `gate` or `resume` says **NOT A STOPPING POINT**, keep working. Never ask the user to say "continue". Research, debugging, dry runs and efficiency: `references/engineering.md`. Read it when starting Full mode.

## 10. Finish honestly

```bash
$SUP criterion drop AC7 --reason "xlsx needs a third-party package"   # descoped, listed as excluded
$SUP next --clear   # the gate refuses while next actions remain
$SUP gate           # 0 VERIFIED COMPLETE | 10 PARTIALLY COMPLETE | 20 BLOCKED
```

Report the gate's verdict verbatim, including any unconfirmed assumptions, with `templates/final-delivery.md` (and `templates/verification-report.md` for consequential integrations). **Never call the work complete when the gate disagrees.**

## 11. Audit an existing project

What was *asked* lives in past conversations; the newest work may be on another branch.

1. `$SUP branches --fetch` **first**: every branch against the default one. A default checkout hides branches and inflates counts. Work on an unmerged branch is **unmerged, not missing**: audit the latest branch too.
2. `$SUP harvest` finds this project's past Claude Code sessions itself and writes every human prompt (H1…Hn) plus each session's final claim to `.supervisor/harvest.md`, secrets redacted, git-ignored. Sessions held elsewhere (cloud, other machines) are merged with `--extra`: read each one's **last page first**, since it may hold a summary listing every earlier user message. Exit `5` or a short list is **not** proof there is no history. See `references/audit.md`.
3. For each requirement: `$SUP criterion add "..." --source H#`. A later prompt that overrides an earlier one is a `decide`.
4. Verify each criterion against the code **as it is now**; old "done" claims and passing tests are leads. If it can't be checked here (credentials, a service, paid runs): `$SUP criterion unverifiable AC# --reason "needs ..."`, never `fail` or `verify`.
5. Run `gate`; report with `templates/audit-report.md`, including **coverage** (what was and wasn't read). Never say "100% complete" while a source is uncovered.

## Host adaptation

| Missing | Fallback, stated plainly |
|---|---|
| Subagents (or *you* are one) | Run the tracks sequentially and say so. |
| Script execution, or the CLI exits `4` (read-only shell) | **Before you finish**, write progress to `.supervisor/MANUAL.md` following `templates/memory.md`; `resume` shows it. Apply the guards yourself and say the gate is manual. |
| Persistence | Print the memory at milestones for the user to save. |

More: `references/host-adaptation.md`.

## Red flags: stop and correct

- You claim "tests pass" without your own output.
- Saying "complete" while `gate` exits non-zero.
- A user requirement, or a question for the owner, that exists only in chat.
- Asking the owner something reversible, or stopping while unblocked work remains.
- An expensive or irreversible step with no dry run first.
- Calling work "missing" without checking other branches.
