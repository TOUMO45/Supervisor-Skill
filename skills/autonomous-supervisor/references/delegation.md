# Delegation and Integration Rules

## Delegate or do it yourself?

| Situation | Choice |
|---|---|
| < ~5 tool calls, or you already know the exact files | Do it yourself |
| 2+ independent tracks (no shared files, deps verified) | Parallel subagents, one per track |
| Large read/search where you need only the conclusion | One research subagent |
| Consequential change you want reviewed without your bias | Independent reviewer - give it the code and criteria, not your conclusion |
| Tasks that share files or an unfinished interface | Sequence them, or agree the interface first (`decide`) and split files |

Every subagent costs a context handoff in each direction. Spawn only when parallel time saved or context kept clean outweighs that.

## Role catalogue (use only what the project needs)

| Role | Typical output | Verify by |
|---|---|---|
| Researcher / requirements analyst | Findings with sources, recommendation | Spot-check 1-2 primary sources |
| Architect | Components, interfaces, data model -> `decide` | Interfaces compile / contract tests |
| Designer (product/UI) | Flows, component spec, copy | Render / screenshot review |
| Frontend / backend developer | Code + tests in owned files | Run their tests + integration check yourself |
| Tester / QA | New tests for criteria, bug reports | Tests fail on broken code, pass on fixed |
| Debugging specialist | Root cause with evidence, focused fix | Reproduce before/after |
| Security / performance reviewer | Findings with reproduction and impact | Reproduce the top finding |
| Docs / delivery | README, usage, handoff | Follow the docs from a clean state |

## Brief rules

- Fill every slot of `templates/task-assignment.md`. Missing ownership is the #1 cause of integration conflicts.
- Context = the decisions and interfaces this task touches, plus file paths. Not the whole memory.
- Reuse verified findings: pass them as inputs so nobody re-researches.
- Ask for a structured report with real command output. "Done" without output is returned for evidence.

## Parallelism rules

1. Only tasks listed by `$SUP ready` may start; the `running` guard enforces deps, the parallel limit, and file overlap.
2. Launch independent agents in a single message so they truly run concurrently (where the host supports it).
3. Two agents never own the same file. If both need a shared file (e.g. a router index), the supervisor owns it and integrates.
4. While agents run, do non-overlapping work: prepare the next briefs, write integration tests, review returned work.

## Integration

1. On each report: `task set <id> done` -> verify yourself -> `verified --evidence` or send back with the exact failing output.
2. Merge one track at a time; run the targeted tests after each merge.
3. At milestone boundaries run the full suite and record it (`log`, or `criterion verify`).
4. Conflicting outputs: the brief + recorded decisions decide; record the resolution as a new decision.
