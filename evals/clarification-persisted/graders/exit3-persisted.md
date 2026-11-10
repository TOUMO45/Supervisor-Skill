---
type: regex
# Matches only inside a Write/Edit/Bash tool call (never the user prompt): the agent wrote the
# "missing file exits 3" requirement into the repository (code, test, notes or memory/state).
pattern: "\"name\":\\s*\"(Write|Edit|MultiEdit|Bash)\"[^\\n]*?(exit\\w*\\s*(code|status)?\\s*(=|:|of|with|is|->|to|\\()?\\s*3\\b|missing\\w*\\s*=\\s*3\\b)"
flags: i
match: contains
target: trace
---
