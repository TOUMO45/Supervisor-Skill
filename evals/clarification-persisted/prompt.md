---
name: clarification-persisted
tags: [memory, core]
runs: 2
max_turns: 40
timeout_seconds: 600
allowed_tools: [Read, Edit, Write, Glob, Grep, Bash, Skill]
---
Here's a project to deliver: the brief is in brief.md (a teammate's unfinished starter is already in this repo).

This session only has time for the conversion core (the CSV -> Markdown logic and its unit tests). Do NOT build the command-line entry point or the README now: a different agent with no access to this conversation will continue later, using the same repository.

Two things I forgot to put in the brief:
1. Our CI scripts treat exit code 2 as "bad usage", so a missing input file must exit with code 3, not 2. (Bad --max-width stays exit 2.)
2. Please support an environment variable CSVMD_MAX_WIDTH that sets the default max width when --max-width isn't passed. The flag always wins.
