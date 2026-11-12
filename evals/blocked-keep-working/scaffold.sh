#!/usr/bin/env bash
# An interrupted project where one task truly waits on the owner (a registry token) and the rest does not.
set -euo pipefail
bash "$(dirname "$0")/../fixtures/make_resume_state.sh"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SUP="python3 $ROOT/skills/autonomous-supervisor/scripts/supervisor.py"
$SUP criterion add "Package published to the company registry" >/dev/null
$SUP task add "Publish to the company registry" --depends T3 --criteria AC4 >/dev/null
$SUP ask "Registry upload token for the publish step?" --default "leave it unpublished until you provide the token" --blocks T4 --because access >/dev/null
