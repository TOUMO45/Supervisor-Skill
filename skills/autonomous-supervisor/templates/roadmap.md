# Roadmap

## Architecture sketch
(components, data flow, interfaces agreed between tasks - record each as `$SUP decide`)

## Milestones (mini-goals) -> `$SUP milestone add`, `$SUP criterion add ... --milestone M1`
Each is a **vertical slice** a user could see working: one path through every layer it needs ("a user can
register"), never one layer for every feature ("the whole database"). Order them so the riskiest assumption is
tested first. Every task also meets `templates/definition-of-done.md`.
| # | Outcome (observable) | Criteria served | Exit check |
|---|---|---|---|
| M1 | | AC1 | `$SUP gate --milestone M1` |

## Tasks -> `$SUP task add`
| ID | Task | Depends | Owns files | Serves | Owner (self / role) | Parallel? |
|---|---|---|---|---|---|---|
| T1 | | - | | AC1 | self | |

Task size: one focused session, 1-5 files. Split a task when it needs more than three acceptance bullets, touches
two independent subsystems, or has "and" in its title.

Critical path: T1 -> ...
Parallel groups (no shared files, deps satisfied): {T2, T3}
Integration points (run full suite here): after M1, after M2, final
