---
name: trigger-brief-handoff
runs: 2
max_turns: 6
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep, Skill]
---
Here's a project to deliver: the brief is in brief.md. This session only has time for the core; another agent will continue later. Also, two things I forgot: missing files must exit 3, and support a CSVMD_MAX_WIDTH env var.
