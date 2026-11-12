---
type: regex
# A plan was written to disk by a tool call.
pattern: "\"name\":\\s*\"(Write|Edit|MultiEdit|Bash)\"[^\\n]*?(Overdue|overdue)"
match: contains
target: trace
---
