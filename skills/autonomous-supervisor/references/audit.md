# Audit Mode - Reconstructing What Was Asked

Use this when a project is old, interrupted, inherited, or someone asks "is it really done?". The code and
README only show what was built. What was *asked* also lives in past conversations, and that is where
requirements get lost.

## First: which branch holds the latest work?

`$SUP branches` compares every branch with the default one: commits ahead and behind, last commit date,
merged or not. It names the **most recent unmerged branch** as the latest work. Most commits is not most
recent: on one real audit a month-old side line was 441 commits ahead, and the real latest work was 284.

- A default cloud or CI checkout is usually shallow and single-branch, so `git branch -a` shows one branch.
  `branches` asks the remote when it sees no others and lists what is not fetched. `--fetch` brings them in.
  It updates remote-tracking refs only, so it is safe in a read-only audit.
- Check each requirement on the default branch **and** on the latest branch
  (`git show origin/<branch>:path`, or `git worktree add <scratch dir> origin/<branch>` to run its tests).
- Report three different things separately: *missing* (on no branch), *built but unmerged* (name the branch
  and how far ahead it is), and *merged*. Recommending "implement X" when X sits on a branch wastes the work.

## Sources, in order of authority

1. **Human prompts in past sessions**: `$SUP harvest` extracts every one (H1…Hn, oldest first) from Claude
   Code history (`~/.claude/projects/`, or `$CLAUDE_CONFIG_DIR`), redacts secrets, and writes
   `.supervisor/harvest.md` (git-ignored). It finds sessions by folder name and by the recorded working
   directory, so moved or renamed projects are still found. Pass `--transcripts DIR` for exported or copied
   history. Use `$SUP sessions` for a one-line-per-session overview first.
2. The brief, spec, README, docs and issue tracker in the repo.
3. Existing `.supervisor/` memory (decisions D# are already binding).

**Exit 5** means no transcripts were found *on this machine*. That is not proof there is no history: see
the next section. If there really is none, ask the user for other sources (exported chats, claude.ai
conversations, tickets) and state in the report that the audit covers the repository only.

## Sessions that are not on this machine (cloud, other computers)

`harvest` reads local files. Sessions run in Claude Code on the web, or on another computer, are not there.
If the host has session tools (in Claude Code: `list_sessions`, `get_session`, `list_events`), use them.

1. **Session records are cheap. Collect them all.** List the sessions and keep the ones for this repository.
   Write one line per session to a JSONL file:
   `{"kind":"session","id":"...","title":"...","start":"...","end":"...","status":"blocked|completed|...","note":"what it was waiting on"}`
   Sessions that ended **waiting on the user** are findings in themselves: on one real audit, 14 of 22 had,
   and those unanswered questions were what blocked the project, not missing code.
2. **Prompts are expensive. Read them selectively.** Session events include every tool result, and one long
   session can be hundreds of thousands of tokens. Give this to a subagent (a large read where you need only
   the conclusion): it pages through the events and writes **only what the human typed**:
   `{"kind":"prompt","session":"...","timestamp":"...","text":"..."}` and, for the last assistant message,
   `{"kind":"claim","session":"...","text":"..."}`.
   Read first the sessions most likely to carry requirements: the earliest one (the original brief) and any
   whose record shows a change of scope. Set a budget, and stop at it.
   A page of events is often too large to return inline, and the host saves it to a file. Don't read or
   retype it: `$SUP events FILE... --session ID --out cloud.jsonl` copies the typed prompts and the final
   claim out exactly, and skips tool results and notifications. Only pages returned inline need copying by hand.
3. `$SUP harvest --extra FILE.jsonl` merges everything: the same H numbering and redaction, plus a table of
   **sessions known, prompts NOT read**. That table goes into the report's coverage section unchanged.

The same `--extra` format works for chats the user exports or pastes.

## Turning prompts into criteria

- Read **every** prompt. One prompt often contains several requirements. Split them.
- Record each one with its source: `$SUP criterion add "missing file exits 3" --source H2`.
- A later prompt can override an earlier one, or the brief ("not 2, use 3"). The later instruction wins.
  Record it: `$SUP decide "missing file exit 3 overrides brief's exit 2" --why "user clarification H2"`.
- Session-scoping prompts ("only the core this session") are not requirements. They explain why work
  was deferred.
- Questions, chit-chat and "continue" carry no requirement. Skip them, but note when a prompt changed the
  goal.

## Verifying

- **Final claims are leads, not evidence.** "All tests pass" from an old session proves nothing about today.
  Re-run the tests and exercise each criterion directly, for example by running the CLI with the flag or
  hitting the endpoint.
- Passing tests do not mean the requirements are met: the tests may not cover a chat-only requirement at all.
  Check each criterion with its own command.
- Mark a criterion `fail` with evidence when it is missing. Use `criterion drop --reason` only when the user
  descoped it.
- If a requirement can't be checked here (it needs a service, credentials, hardware or paid runs), record
  `$SUP criterion unverifiable AC# --reason "needs ..."`. It is neither passed nor failed: the gate reports it
  separately and stays at PARTIALLY COMPLETE. Use it also for a claim the project itself has not yet measured
  ("not yet proven" is not "proven false"). A project's own measurements are leads: cite them as *claimed*.

## Reporting

Fill in `templates/audit-report.md`: verdict, coverage, traceability table, what's missing, claims vs
reality, changed requirements, and next actions. The coverage section is mandatory. A "100% complete"
verdict requires both a passing gate **and** no uncovered source.
