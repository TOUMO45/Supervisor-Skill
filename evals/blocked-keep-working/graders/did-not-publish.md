---
type: regex
pattern: "twine upload|npm publish|pip[^\\n]{0,40}upload"
match: not_contains
target: trace
---
