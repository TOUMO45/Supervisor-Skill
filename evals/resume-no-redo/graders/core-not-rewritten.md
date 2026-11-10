---
type: regex
# The verified core must not be replaced wholesale (targeted Edit calls are fine).
pattern: "\"name\":\\s*\"Write\"[^\\n]*?csvmd/__init__\\.py"
match: not_contains
target: trace
---
