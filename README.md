<div align="center">

# Autonomous Supervisor

**One idea. A coordinated team. Verified results.**

A reusable agent skill that turns an AI coding agent into an accountable senior team lead:
it plans from a brief, delegates to focused specialists, keeps **durable project memory**,
enforces **bounded retries and file ownership**, and only says *complete* when a
**verification gate** agrees.

[![ci](https://github.com/toumo45/supervisor-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/toumo45/supervisor-skill/actions/workflows/ci.yml)
![stdlib only](https://img.shields.io/badge/dependencies-stdlib%20only-2ea44f)
![skill](https://img.shields.io/badge/agent%20skill-SKILL.md-7b61ff)

<img src="assets/supervisor-infographic.webp" alt="Autonomous Supervisor: your idea flows to a supervisor that plans, delegates, monitors and resolves; specialists for research, architecture, design, development, testing and review; shared project memory of goals, decisions, progress and evidence; a feedback loop; and the workflow Understand, Plan, Execute, Verify, Fix, Deliver with repair-and-recheck." width="100%">

</div>

---

## Why this exists

Strong models already *know* the principles of good supervision — verify claims, change strategy
after repeated failures, don't over-engineer a typo fix. We measured it (see [Benchmarks](#benchmarks)):
a baseline agent handled all 8 single-turn pressure scenarios correctly **without** any skill.

What they *don't* have is **state that outlives the conversation** and **rules that hold under drift**:

| Failure in real multi-session work | What the skill adds |
|---|---|
| Handoff notes live only in a chat reply the next session never sees | `.supervisor/state.json` + auto-rendered `MEMORY.md`, updated on every write |
| "Done" is whatever the agent last said | `gate` computes **VERIFIED COMPLETE / PARTIALLY COMPLETE / BLOCKED** from evidence |
| Fix #4 is a variation of fixes #1–3 | `task attempt` trips a **RETRY LIMIT** (exit 3) and forces a recorded strategy change |
| Two agents edit the same file | `task set … running` refuses overlapping file ownership, unmet deps, or exceeding the parallel limit |
| `verified` with no proof | `verify` / `verified` refuse to record without `--evidence` (exit 2) |
| Ceremony on trivial tasks | Explicit **Direct / Lite / Full** mode selection up front |

## Install

**Claude Code plugin (recommended):**

```bash
/plugin marketplace add toumo45/supervisor-skill
```

```bash
/plugin install autonomous-supervisor@supervisor-skill
```

**Or copy the skill** into any skills directory (`~/.claude/skills/`, `.claude/skills/`, or `~/.agents/skills/`):

```bash
cp -r skills/autonomous-supervisor ~/.claude/skills/
```

Requirements: Python 3.8+ for the memory CLI (standard library only). Works without it via a manual memory fallback.

## Use

Give your agent a brief or master prompt:

> Build a CLI expense tracker with CSV import and a monthly report. Stdlib only.

The skill triggers on project-sized work (or say *"use the autonomous-supervisor skill"*). It will:

1. **Pick a mode** — Direct (just do it), Lite (criteria + gate), or Full (memory, delegation, gate).
2. **Define success** — brief with explicit assumptions, scope table, checkable acceptance criteria.
3. **Plan** — tasks with dependencies, owned files, and the criteria each one serves.
4. **Delegate** only where it wins, using a brief template with required slots (ownership, verification command, escalation conditions, report format).
5. **Verify** every report itself, recording the command and observed result as evidence.
6. **Recover** — bounded retries, strategy changes, and `resume` after interruptions.
7. **Deliver** — the gate's exact verdict, evidence per criterion, limitations, excluded scope.

### The memory CLI at a glance

```bash
SUP="python3 skills/autonomous-supervisor/scripts/supervisor.py"
$SUP init --objective "CSV -> Markdown CLI" --max-parallel 3 --max-attempts 3
$SUP criterion add "Pipes escaped as \|"
$SUP task add "Core converter" --criteria AC1 --files "csvmd/core.py,tests/test_core.py"
$SUP task set T1 running --owner backend-agent      # guarded: deps, parallel limit, file overlap
$SUP task set T1 verified --evidence "unittest: Ran 21 tests OK"
$SUP criterion verify AC1 --evidence "echo 'c\na|b' | python3 -m csvmd -> 'a\|b'"
$SUP decide "Brief beats legacy test (newline -> <br>)" --why "spec is the contract"
$SUP resume     # after an interruption: do-not-redo / in-flight / ready / binding decisions
$SUP gate       # 0 VERIFIED COMPLETE | 10 PARTIALLY COMPLETE | 20 BLOCKED
```

## Repository layout

```
skills/autonomous-supervisor/
├── SKILL.md                    # the operating procedure (≈1.3k words, loads on trigger)
├── scripts/supervisor.py       # durable memory + guards + completion gate (stdlib)
├── templates/                  # project-brief, roadmap, task-assignment, verification-report,
│                               # escalation, final-delivery, memory (manual fallback)
└── references/                 # delegation rules, recovery procedures, host adaptation
tests/
├── test_supervisor_cli.py      # 29 behavioural tests of the CLI
├── validate_skill.py           # structural lint (frontmatter, links, word budget)
├── scenarios/                  # 8 pressure scenarios + recorded results
└── e2e/                        # benchmark brief, seeded starter, hidden acceptance oracle
.claude-plugin/                 # plugin + marketplace manifests
```

## Benchmarks

Every number below comes from a real run in this repo's harness: same model, fresh context,
identical prompts except *"read SKILL.md and follow it"*. Hidden acceptance tests were never
shown to the agents. Details and transcripts summary: [`tests/scenarios/results.md`](tests/scenarios/results.md).

| Test | Baseline (no skill) | With skill |
|---|---|---|
| 8 single-turn pressure scenarios | 8/8 correct | No regressions (Direct mode on trivial tasks, honest fallbacks) |
| E2E build, one session | 18/18 · 94k tokens · 5 calls | 18/18 · 100k tokens · 8 calls · chose **Lite** mode |
| Interruption, fully specified brief | 18/18 · no durable handoff | 18/18 · full `.supervisor/` memory |
| **Interruption + user clarifications given mid-session** | **18/20**: session 2 *deleted* a user-requested feature as "scope creep" and dropped the exit-code override | **20/20**: both honoured via a binding decision, deviation from the brief disclosed |

**Honest reading:** on small, fully specified, single-session work a strong model doesn't need
this skill, and the skill costs about 6% more tokens. It pays off where real projects fail.
Requirements that live in conversation, work that crosses sessions or context resets, and
"done" claims that need to be audited. The benchmark also **caught a bug in the skill itself**:
the gate passed on criteria that covered only one session's slice. The bug is fixed and covered
by regression tests.

## Development

```bash
python3 tests/validate_skill.py                    # skill structure lint
python3 -m unittest discover -s tests -v           # CLI behaviour tests
python3 -I tests/e2e/hidden_acceptance.py tests/e2e/reference   # oracle self-check: 18/18
```

The skill was built test-first following the *writing-skills* method: pressure scenarios were run
**without** the skill to record baseline behaviour, guidance was written only for observed gaps,
and the same scenarios were re-run **with** the skill. Full transcripts are summarised in
[`tests/scenarios/results.md`](tests/scenarios/results.md).

## Design references

Evaluated as inspiration, not copied: [obra/superpowers](https://github.com/obra/superpowers)
(evidence-based verification, subagent execution), [ehnruiz/claude-skills](https://github.com/ehnruiz/claude-skills)
(supervisor workflow), [ruvnet/ruflo](https://github.com/ruvnet/ruflo) (shared memory orchestration),
[troykelly/claude-skills](https://github.com/troykelly/claude-skills) (issue-driven autonomy),
[OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) (agent runtime),
[crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) (role-based teams).

## Guiding principle

**One clear objective. One accountable supervisor. Focused specialists. Shared memory.
Measurable progress. Verified completion. Minimal unnecessary human intervention.**
