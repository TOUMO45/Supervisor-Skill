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
