# Audit Mode - Reconstructing What Was Asked

Use this when a project is old, interrupted, inherited, or someone asks "is it really done?". The code and
README only show what was built. What was *asked* also lives in past conversations, and that is where
requirements get lost.

## Sources, in order of authority

1. **Human prompts in past sessions**: `$SUP harvest` extracts every one (H1…Hn, oldest first) from Claude
   Code history (`~/.claude/projects/`, or `$CLAUDE_CONFIG_DIR`), redacts secrets, and writes
   `.supervisor/harvest.md` (git-ignored). It finds sessions by folder name and by the recorded working
   directory, so moved or renamed projects are still found. Pass `--transcripts DIR` for exported or copied
   history. Use `$SUP sessions` for a one-line-per-session overview first.
2. The brief, spec, README, docs and issue tracker in the repo.
3. Existing `.supervisor/` memory (decisions D# are already binding).

**Exit 5** means no transcripts were found. Say so, ask the user for other sources (exported chats,
claude.ai conversations, tickets), and state in the report that the audit covers the repository only.

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
- If a requirement can't be checked here (it needs a service, credentials, or hardware), mark it unverifiable
  in the report. Don't count it as passed.

## Reporting

Fill in `templates/audit-report.md`: verdict, coverage, traceability table, what's missing, claims vs
reality, changed requirements, and next actions. The coverage section is mandatory. A "100% complete"
verdict requires both a passing gate **and** no uncovered source.
