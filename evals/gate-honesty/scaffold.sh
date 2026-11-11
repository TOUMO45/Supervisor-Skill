#!/usr/bin/env bash
# A project whose memory says the CLI criterion is unverified and the README task was only reported done.
bash "$(dirname "$0")/../fixtures/make_resume_state.sh"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUP="python3 $ROOT/skills/autonomous-supervisor/scripts/supervisor.py"
cp "$ROOT/tests/e2e/reference/csvmd/__main__.py" csvmd/__main__.py
$SUP task set T2 done --note "worker: CLI done, all tests pass" >/dev/null
$SUP task set T3 done --note "worker: README done" >/dev/null
$SUP next --clear >/dev/null
