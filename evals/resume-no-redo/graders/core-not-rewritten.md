---
type: regex
# The verified core must not be replaced wholesale (targeted Edit calls are fine). The pattern is tied to the
# Write call's own file_path: a notes file that merely names the core once tripped the looser version.
pattern: "\"name\":\\s*\"Write\",\\s*\"input\":\\s*\\{\\s*\"file_path\":\\s*\"[^\"]*csvmd/__init__\\.py\""
match: not_contains
target: trace
---
