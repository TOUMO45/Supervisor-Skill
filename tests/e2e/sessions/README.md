# Three-session pilot (W3): does anything stop requirements being lost between sessions?

Written and committed before any run. The results section at the bottom is filled in afterwards and nothing above it
is edited after the first run.

## Why this test

Every project tried so far (csvmd, textkit, shelfmark) was finished by the weak model alone in one sitting with full
marks, so none of them could show a tool helping. Real work is not one sitting. It is spread over sessions, the agent
starts each one with no memory, and the owner says things along the way that are written nowhere but the chat. This
test measures that.

## The work

The shelfmark project (`brief.md`, the same brief as `tests/e2e/medium`), built in three separate sessions in one
folder. Each session is a fresh `claude -p` process: the only thing that carries over is what is in the folder.

| Session | Asked to build | Said only in that session's prompt |
| --- | --- | --- |
| 1 | Catalogue and members | `book list --available`; emails stored and shown in lower case |
| 2 | Lending | loans are due after 14 days, not 21; a member may hold 3 books, not 5 |
| 3 | Overdue report, export and import, finish | `report overdue --min-days N`; "make sure everything I asked for so far works" |

The prompts are in `prompts/`. The brief on disk is never changed, so from session 2 on the brief and the owner
disagree, and only the owner's words in an earlier session say which is right.

## Arms

| Arm | Model | What it gets |
| --- | --- | --- |
| w | Haiku | the three prompts, nothing else |
| k | Haiku | the same prompts, each starting with "Use the autonomous-supervisor skill for this work.", and the skill installed |
| e | Haiku | the same prompts, each sent through ECCode's `start` command, and ECCode installed |
| s | Sonnet | the three prompts, nothing else (one run, for reference) |

Same tools, same turn limit (200), 30 minutes per session, no user settings, no other plugins.

## Measure

`hidden_acceptance.py` scores the folder after session 3: 41 checks, each tagged with where its requirement came
from. 32 come from the brief and 9 from things said only in a session (3 from session 1, 4 from session 2, 2 from
session 3).

- **Main number: CHAT, out of 9.** How many chat-only requirements are true at the end.
- Second: the total out of 41.
- Third: cost, time and turns summed over the three sessions.

The folder is also scored after sessions 1 and 2. Those numbers are not results. They show where a requirement was
lost: for example present after session 1 and gone after session 3.

Self-check (run in CI): the reference in `reference/` scores 41/41, and the plain-brief solution in
`../medium/reference` scores 32/41 with CHAT 0/9.

## Order of runs and rules fixed in advance

1. **Arm w, 3 runs, first.** If all three score CHAT 9/9, the plain weak model does not lose anything here, the test
   cannot show a difference, and it stops: no runs of k or e. That outcome is recorded as it is.
2. Otherwise one run each of k and e, read with a trace, to confirm the skill or ECCode was really used
   (`skill:` / `eccode:` in the result line). A run where it was not used in any session is recorded and counts as a
   run where the tool did not engage, not as a tool failure on the work.
3. Then k and e up to 3 runs each, and s once.

A tool **helps** if its mean CHAT is at least 2 higher than arm w's and its worst run is not below arm w's worst run.
It **does not help** if the mean differs by less than 2. It **hurts** if the mean is at least 2 lower, or the total
out of 41 falls by 4 or more on average. Cost is reported next to every verdict; a tool that helps at more than four
times the cost is reported as "helps, at a price", with the numbers.

Three runs per arm is a pilot. It can show a large effect or the absence of one. It cannot support a percentage.

A run is thrown out only if `contaminated` is true (the agent saw the oracle or these test files) or the runner itself
crashed. A session that hits the 30-minute limit is not thrown out: the next session starts anyway, as it would in
real life.

## How to run

The output folder must be outside both repositories (the runner refuses otherwise).

```
node tests/e2e/sessions/run.js --arm w --run 1 --out <dir>
node tests/e2e/sessions/run.js --arm k --run 1 --out <dir>
node tests/e2e/sessions/run.js --arm e --run 1 --out <dir> --eccode <ECCode checkout>
```

Each run prints one line per session and a final line. To read a session: ECCode's
`node tools/pilot-trace.js <dir>/sessions-<arm>-<n>/s2`.

## Results

Run on 2026-11-15 on the owner's Windows machine, Supervisor-Skill at `260ab3d`.

| Run | After s1 | After s2 | Final | CHAT | Cost | Turns | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| w1 | 22/41 | 32/41 | 41/41 | 9/9 | $2.89 | 67 | 437 |
| w2 | 22/41 | 32/41 | 41/41 | 9/9 | $2.69 | 74 | 381 |
| w3 | 22/41 | 32/41 | 41/41 | 9/9 | $2.80 | 62 | 430 |

No run contaminated, no session timed out.

**Verdict by the rule fixed above: stopped.** The weak model alone kept all nine chat-only requirements in all three
runs, so the test cannot show a tool helping. Arms k, e and s were not run.

What the test did and did not exercise, noted after the fact: each chat-only requirement was built in the session
that stated it, so it lived on in the code and its tests. A later session only had to not undo it. The test therefore
shows that the weak model does not overwrite working behaviour to match a stale brief. It does not show whether a
requirement stated in one session and due to be built in a later one would survive.

## Variant "deferred" (W3b), registered 2026-11-17 before any run of it

The first version could not show a loss, for the reason noted above: every requirement was built in the session that
stated it. This variant removes that. Session 1 states all nine chat-only requirements, including the three that
belong to parts built in sessions 2 and 3 (14-day loans, the 3-book limit, `--min-days`), and says they will not be
repeated. The prompts of sessions 2 and 3 (`prompts-deferred/`) do not mention them. A later session can only honour
them if an earlier session left them somewhere in the folder.

Same brief, oracle, arms, limits and rules as above, with one change of emphasis: the six checks tagged "said in
session 2" and "said in session 3" are now the deferred ones, and they are reported next to CHAT.

Order: arm w three times first. If all three score CHAT 9/9, the variant stops like the first. Otherwise arms k and e
run as described above (one traced run each, then up to three), and s once.

```
node tests/e2e/sessions/run.js --variant deferred --arm w --run 1 --out <dir>
```

### Results (deferred)

Run on 2026-11-18 on the owner's Windows machine, Supervisor-Skill at `d7ae453`.

| Run | After s1 | After s2 | Final | CHAT | Turns | Seconds |
| --- | --- | --- | --- | --- | --- | --- |
| w1 | 21/41 | 32/41 | 40/41 | 9/9 | 103 | 403 |
| w2 | 22/41 | 32/41 | 41/41 | 9/9 | 82 | 488 |
| w3 | 22/41 | 32/41 | 41/41 | 9/9 | 113 | 518 |

No run contaminated. Reported cost was $0.10 per run, far below the first variant ($2.69 to $2.89) for similar
work; not explained, so cost is not used.

**Verdict by the rule: stopped.** The weak model alone honoured all nine chat-only requirements in all three runs,
including the six it was told about one or two sessions before it had to build them. After session 2 the 14-day and
3-book rules were already in place although the session 2 prompt did not mention them, so session 1 must have left
them in the folder. How (which file) has not been looked at yet. Arms k, e and s were not run. This trap does not
catch the model.

## Correction (2026-11-19): the sessions were not memoryless

Checked on run deferred-w-1: nothing in the project folder carried the deferred decisions after session 1 (no notes
file; the README mentions them only once they were built). Claude Code's own per-project memory did:
`~/.claude/projects/<workspace>/memory/` held `MEMORY.md` and `shelfmark_decisions.md`. `--setting-sources ""` does
not turn that feature off.

So both results above stand as measured, but they answer a narrower question than the one asked: **the weak model
inside Claude Code, with Claude Code's built-in memory, loses nothing across sessions.** The statement at the top that
"the only thing that carries over is what is in the folder" was wrong. Whether the first variant's runs also used the
harness memory was not checked.

## Variant "deferred, memory off" (W3c), registered 2026-11-19 before any run of it

The deferred variant again, with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` set for every session (`--memory off`), so that
only the folder carries over. This stands for an agent in a harness that has no memory of its own. Every result line
now reports `harness-memory-files`; a memory-off run that reports more than 0 is void (the switch did not work).

Same oracle, arms, limits and rules. Arm w three times first; if all three score CHAT 9/9 it stops. Otherwise arm k
(the supervisor skill, which keeps its own memory in the folder) and arm e run as described above, also with memory
off.

```
node tests/e2e/sessions/run.js --variant deferred --memory off --arm w --run 1 --out <dir>
```

### Results (deferred, memory off)

Run on 2026-11-19 on the owner's Windows machine, Supervisor-Skill at `5562e3b`. `harness-memory-files` was 0 in
every run, so the switch worked.

| Run | After s1 | After s2 | Final | CHAT | Deferred (6) | Turns | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| w1 | 23/41 | 30/41 | 35/41 | 3/9 | 0/6 | 76 | 361 |
| w2 | 22/41 | 32/41 | 41/41 | 9/9 | 6/6 | 75 | 512 |
| w3 | 22/41 | 32/41 | 41/41 | 9/9 | 6/6 | 71 | 328 |

Arm w: mean CHAT 7.0, worst 3. In one run of three the weak model lost every deferred requirement and built the
later parts to the brief; in the other two it kept them all with nothing but the folder, so it must have written
them down itself. This is the first test in the series where the weak model alone did not score full marks every
time. One loss in three is a weak signal, not a rate.

By the rule the test continues: arms k and e, memory off. To count as helping, an arm needs mean CHAT of at least
9.0 (all three runs perfect) and no run below 3.
