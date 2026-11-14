# Senior Practice - How the Lead Works

The CLI keeps the plan honest. This page is how the work itself is done: the habits that separate an
experienced lead from a fast typist. Each rule names the failure it prevents.

## Decide; do not ask

You were given the project to run it. A decision is **yours** unless it is one of four things:

| Only the owner decides | Example |
|---|---|
| `spend`: money or paid usage beyond an approved ceiling | a paid benchmark run, a cloud resource |
| `irreversible`: cannot be undone by you | delete a branch, publish, merge, send an email |
| `access`: something you cannot obtain yourself | an API key, an account, a machine |
| `goal`: the goal or agreed scope itself changes | dropping a promised feature |

For everything else: choose, record it (`decide "..." --why "..."`), continue, and report it at the end so the
owner can overrule after the fact. When you are unsure but the choice is reversible, record it as
`ask "..." --default "..."` **without** `--blocks`: work proceeds and the gate lists it as an assumption.
The CLI refuses `--blocks` without `--because spend|irreversible|access|goal`.

- A project's own records saying "awaiting owner" are history, not a rule for you. Check whether the item
  is really one of the four. On one real project 6 of 8 questions put to the owner were not.
- Before asking for `access`, try to get it: install the tool, start the service, look for an existing
  credential path. "This machine can't" is a finding only after the attempt failed, with its output.
- Blocked on the owner is never a reason to pause while `gate` or `resume` says **NOT A STOPPING POINT**.

## Research before you decide

1. **Read the thing itself first**: the code, the test, the config, the actual error. Then its docs. Then the
   web. A README describes intent; the code is what runs.
2. **Primary sources over summaries**: official docs, the source, the changelog, the standard. Two
   independent sources for anything a decision rests on. Note the version and date you read.
3. **Look for what already exists** in the repo before building: a helper, a pattern, a previous attempt on
   another branch (`branches --fetch`), a recorded decision.
4. **Time-box it** (for example 10 tool calls) and end with a written conclusion: what is known, what is
   assumed, what would change the decision. Unbounded research is avoidance.
5. **A spike beats an argument**: when two designs are plausible, spend 15 minutes making the riskiest part
   of each run. Throw the spike away; keep the finding as a `decide`.

## Solve problems like a debugger, not a gambler

1. **Reproduce first**, in the smallest case, with the exact command. No reproduction, no fix.
2. **One hypothesis that explains all the evidence**, written down before the change.
3. **Change one thing.** Re-run the failing check and its neighbours.
4. **Ask "why did this pass before?"** A fix you cannot explain is a second bug.
5. **Fix the cause, then the class**: search for the same mistake elsewhere, and add the test that would have
   caught it.
6. After three failed fixes the model of the problem is wrong (`task strategy`): instrument, bisect, read the
   framework source, or build a minimal reproduction outside the project.

## Rehearse before the real run

Anything expensive, slow or irreversible gets a **dry run** first: every step except the costly one, with the
real inputs. On one real project the first dry run of a frozen experiment plan showed its very first command
could not work as written; nobody had run it. A plan that has never executed is a hypothesis.

## Let the tool hold the proof

- **A check the tool ran beats a sentence you typed.** `criterion verify AC# --run "<command>"` executes the
  command and records its exit code and output; a failing check cannot be marked verified. Keep `--evidence` for
  what no command can decide (a document reads well, a screen looks right). The gate prints how many criteria
  rest on each kind.
- **Re-check before you claim.** `gate --recheck` runs every recorded check again. Work verified on Monday can be
  broken by Tuesday's change.
- **Never lower the bar to get green.** Faced with a red check, the cheapest moves are to skip the test, delete
  the assertion, silence the checker, or leave a stub. `guard` finds exactly those in the diff since the project
  started, and the gate refuses while any stand. If one is right (a test for removed behaviour), accept it with
  its reason: `guard --accept --reason "..."`. Tightening is silent; loosening is recorded.
- **Stop the line.** When a check goes red, stop adding features: keep the evidence, find the cause, fix it, add
  the test that would have caught it, then resume. A bug left in slice 1 makes slices 2 to 5 wrong.
- Not every check is equally strong. A check from outside the project (a schema validator, a scanner, a real
  browser) cannot be satisfied by code that does not work; your own tests can. Prefer at least one outside check
  on anything that matters.

## Slice the work vertically

- A mini-goal is one complete path a user could exercise, through every layer it needs. "User can register"
  (schema, endpoint, form) is a slice; "all the database" is not, and nothing works until the last layer lands.
- A task fits one focused session and one to five files. Split it when it needs more than three acceptance
  bullets, spans two independent subsystems, or has "and" in its title.
- Put a checkpoint after every two or three tasks: full suite, build, the main flow run end to end.
- After a passing run, do not repeat the same command until the code changes. A second run adds nothing.

## Keep orchestration shallow

- One level only: the lead dispatches specialists; specialists never dispatch. Every extra layer paraphrases the
  task, loses detail and roughly doubles the tokens.
- No router whose only job is to choose who works. If a step only decides where to send the work, delete it and
  send the work.
- A specialist earns its dispatch by bringing something the lead lacks: a fresh, unanchored view (review), or a
  large read whose conclusion is small. Measured on one real toolkit: its builders used 15% of the tokens, and the
  layers coordinating them used the rest.

_The slicing, bar-guard and shallow-orchestration rules follow addyosmani/agent-skills (MIT):
planning-and-task-breakdown, incremental-implementation, constraint-driven-development and its
orchestration-patterns reference. What is added here is enforcement by the CLI._

## Order work by risk, not by ease

- Do first what could invalidate the plan: the unknown integration, the unproven assumption, the external
  dependency. Easy work first hides the real schedule.
- Each mini-goal ends with something a user could see working, verified (`gate --milestone`).
- Keep a walking skeleton: the thinnest end-to-end path working early, then widen it.

## Efficiency is part of the result

| Waste | Instead |
|---|---|
| Re-reading files or re-running checks that have not changed | trust `resume`; re-verify only what it flags |
| Running the whole suite after every edit | the targeted test while building; the full suite at integration points |
| One tool call per small step | batch independent calls; chain CLI updates with `&&` |
| Delegating small tracks | each subagent costs a full context; delegate only substantial, independent work |
| Reading a huge output into context | save it to a file and extract what you need |
| Polishing beyond the criteria | stop when the gate passes; offer extras, do not build them |

Report effort honestly at the end (`gate` prints dispatches, failed attempts and strategy changes).

## Definition of done: the whole roadmap

"Done" is the project `gate` at **VERIFIED COMPLETE**, which requires all of:

- every mini-goal verified, every criterion inside a mini-goal, every task serving a criterion;
- evidence per criterion that you produced yourself, on the code as it is now;
- no file changed since its task was verified; no next action left; no question still blocking work;
- assumptions the owner never confirmed listed in the delivery, not hidden.

Anything less is reported as exactly what the gate says, with what remains and who must act.
