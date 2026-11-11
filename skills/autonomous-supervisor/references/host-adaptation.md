# Host Adaptation

Detect capabilities from the tools you actually have; never assume them.

| Host | Subagents | Parallel | Persistence | Notes |
|---|---|---|---|---|
| Claude Code (CLI / desktop / web) | `Agent` tool (types: general-purpose, Explore, Plan, ...) | Multiple `Agent` calls in one message; background agents | Files in repo; commit `.supervisor/` | Subagents have **no** spawn tool (verified: a spawned agent's tool list has no `Agent`). Only the top-level session can delegate. A supervisor running as a subagent uses Lite mode. Cloud sessions are ephemeral: commit and push memory. |
| Codex / other CLI agents | Varies (spawn/exec tools) | Varies | Files in repo | Use whatever spawn tool exists; else sequential. |
| Chat-only (no tools) | None | None | None | Sequential tracks; print memory at milestones for the user to save. |

## Fallback rules (say them, don't hide them)

- **No subagents:** "This host can't run subagents, so I'll run the three tracks sequentially in this session." Label sections "Track 1 (sequential)". Offer self-contained briefs the user can run in separate sessions if they want true parallelism.
- **No script execution:** keep `.supervisor/MEMORY.md` by hand with `templates/memory.md` and enforce the guards manually.
- **No persistence:** at each milestone print the memory block and say: "Save this; paste it at the start of the next session to resume."
- **Token/time metrics unavailable:** use proxies - tool calls, agents spawned, retries - and report them in the delivery.
