---
type: regex
# The CSVMD_MAX_WIDTH requirement was written to disk by a tool call (not only said in chat).
pattern: "\"name\":\\s*\"(Write|Edit|MultiEdit|Bash)\"[^\\n]*?CSVMD_MAX_WIDTH"
match: contains
target: trace
---
