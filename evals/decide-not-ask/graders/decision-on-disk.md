---
type: regex
# The choice is written down by a tool call (memory, README or a test), not only said in chat.
pattern: "\"name\":\\s*\"(Write|Edit|MultiEdit|Bash)\"[^\\n]*?header[- ]only|\"name\":\\s*\"(Write|Edit|MultiEdit|Bash)\"[^\\n]*?no data rows"
match: contains
flags: i
target: trace
---
