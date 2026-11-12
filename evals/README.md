# Eval suite (`claude plugin eval`)

Each case runs **with** the plugin and in a **no-plugin baseline** arm, so the report shows the
skill's actual effect. Cases seed their workspace with `scaffold.sh` (cwd = the agent's workspace).

| Case | What it checks | Why |
|---|---|---|
| `direct-mode-trivial` | A typo fix creates no `.supervisor/`, no ceremony | regression guard: proportionality |
| `clarification-persisted` | User requirements given in chat are written to disk before handoff | the failure the skill exists for |
| `gate-honesty` | "Workers say done" + unverified criteria is not reported as complete | evidence over claims |
| `resume-no-redo` | A resumed session builds only the remaining work, not the verified core | memory pays off |
| `blocked-keep-working` | One task waits on the owner: the rest gets built and the project is not called complete | no stopping while work can move |
| `decide-not-ask` | An undecided, reversible detail with an unreachable owner is decided, recorded and reported | the supervisor decides |
| `mini-goals-plan` | A planning-only session leaves ordered stages with done-checks on disk | big projects as mini-goals |

```bash
claude plugin eval . --scaffold --trust-plugin --allow-tools Bash Write Edit -j 4
```
