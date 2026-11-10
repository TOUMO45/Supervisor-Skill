# Recovery Procedures

## Failure triage (bug, failing test, broken build)

1. **Observe** - exact error, command, environment. Reproduce it once, deliberately.
2. **Isolate** - smallest failing case; what changed since it last passed (`git diff`, recent tasks in the log).
3. **Hypothesize** - one root cause consistent with *all* evidence. Write it down (`task attempt --note` records it if the fix fails).
4. **Fix** - one focused change.
5. **Verify** - the failing check now passes, and adjacent checks still pass.
6. **Record** - `task set ... verified --evidence`, or `task attempt` on failure.

When `RETRY LIMIT` trips: the hypothesis family is wrong. Change the *kind* of investigation:
add instrumentation/logging, bisect, read the framework source, write a minimal reproduction outside the project, or question the test itself. Record it with `task strategy`. After 3 strategies, escalate with the evidence log.

## Subagent problems

| Symptom | Action |
|---|---|
| Reports done, no evidence | Reply asking for the report format's command output; or verify yourself |
| Silent / no report for long | Inspect its owned files and `git status` before re-dispatching; never run two agents on the same files |
| Edited files it didn't own | Revert or integrate deliberately; record a decision; tighten the next brief |
| Went off-scope | Discard the extra work unless it maps to a criterion |

## Interruption / context reset

1. `$SUP resume` - read it fully before acting.
2. Trust **verified** items; do not re-run them unless code they cover changed (`git log`/`git diff` since their timestamp).
3. For **running** items: look for the agent's report or its file changes; mark `done` then verify, or reset to `pending` with a note.
4. Recorded decisions are binding; reversing one needs a new `decide` with a reason.
5. Continue from **Next actions**. Do not ask the user to restate anything memory already holds.

## Corrupted or missing memory

- `state.json` corrupt -> restore from git (`git checkout -- .supervisor/state.json`) or rebuild: re-add criteria/tasks, re-verify with fresh evidence. Never mark items verified from recollection.
- Commit `.supervisor/` at milestones so it survives container loss.
