# Roadmap

## Architecture sketch
(components, data flow, interfaces agreed between tasks - record each as `$SUP decide`)

## Milestones (mini-goals) -> `$SUP milestone add`, `$SUP criterion add ... --milestone M1`
Each is a slice a user could see working. Order them so the riskiest assumption is tested first.
| # | Outcome (observable) | Criteria served | Exit check |
|---|---|---|---|
| M1 | | AC1 | `$SUP gate --milestone M1` |

## Tasks -> `$SUP task add`
| ID | Task | Depends | Owns files | Serves | Owner (self / role) | Parallel? |
|---|---|---|---|---|---|---|
| T1 | | - | | AC1 | self | |

Critical path: T1 -> ...
Parallel groups (no shared files, deps satisfied): {T2, T3}
Integration points (run full suite here): after M1, after M2, final
