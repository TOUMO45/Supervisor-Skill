#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cp -r "$ROOT/tests/e2e/starter/." .
cp "$ROOT/tests/e2e/brief.md" brief.md
