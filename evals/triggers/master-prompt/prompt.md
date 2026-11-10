---
name: trigger-master-prompt
runs: 2
max_turns: 6
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep, Skill]
---
Master prompt: create a CLI expense tracker with CSV import, categories, monthly reports, tests and docs. Plan it, split the work, use subagents where it helps, and deliver a verified result.
