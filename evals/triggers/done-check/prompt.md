---
name: trigger-done-check
runs: 2
max_turns: 6
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep, Skill]
---
My two workers on this project both reported 'done, all tests pass'. I'm about to tell the client it's finished. Check the project's tracked status and tell me whether it's really complete.
