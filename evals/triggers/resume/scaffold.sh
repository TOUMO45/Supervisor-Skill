#!/usr/bin/env bash
# An interrupted project is never an empty folder: seed one with its memory, as a real resume would find it.
bash "$(dirname "$0")/../../fixtures/make_resume_state.sh"
