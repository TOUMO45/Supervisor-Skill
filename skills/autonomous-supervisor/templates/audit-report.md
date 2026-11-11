# Audit Report - <project>

**Verdict:** <exact `$SUP gate` verdict> - <one line: complete, or N of M requirements incomplete>

## Coverage (what this audit could and could not see)
- Branches: <N> known · default `<name>` · latest work on `<branch>` (<N> ahead, <date>) · from `branches`
- Sessions read: <N> (<first date> → <last date>) · human prompts: <M> · from `harvest`
- Sessions known but prompts **not** read: <N> (table from `harvest.md`)
- Other sources read: <brief.md, README, issues, docs...>
- **Not covered:** <claude.ai chats, other machines, cloud sessions, verbal requests...> - ask the user, or state the audit excludes them
- A verdict is only as complete as its sources. Never write "100% complete" while a source is missing.

## Requirements traceability
| ID | Requirement | Source | Status | Evidence (command → observed result) |
|---|---|---|---|---|
| AC1 | | H1 / brief.md | verified / failed / built but unmerged (`<branch>`) / unverifiable (needs …) | |

## Incomplete - what is missing
- **AC#** <requirement> [H#]: <what exists vs what was asked>; evidence: <command → result>

## Sessions that ended waiting on the user
- <session title, date>: <the question or approval it is waiting for>

## Claims vs reality
- Session <n> claimed "<claim>" → <true / false, with evidence>

## Changed requirements
- H# overrides H#: <what changed> (recorded as D#)

## Recommended next actions
1. <smallest step to close each gap>
