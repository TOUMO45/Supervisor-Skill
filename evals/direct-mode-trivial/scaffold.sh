#!/usr/bin/env bash
printf '# Inbox\n\nYou will recieve a summary every morning.\n' > README.md
printf 'def fetch():\n    """Recieve the latest messages."""\n    return []\n' > utils.py
