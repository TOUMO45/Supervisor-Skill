#!/usr/bin/env bash
# Seeds a csvmd project whose core (T1) is verified and whose CLI + README remain.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SUP="python3 $ROOT/skills/autonomous-supervisor/scripts/supervisor.py"
cp "$ROOT/tests/e2e/brief.md" brief.md
mkdir -p csvmd tests
cp "$ROOT/tests/e2e/reference/csvmd/__init__.py" csvmd/__init__.py
cat > tests/test_core.py <<'PY'
import unittest
from csvmd import convert
class Core(unittest.TestCase):
    def test_table(self):
        self.assertEqual(convert("a,b\n1,2\n"), "| a | b |\n| ---: | ---: |\n| 1 | 2 |\n")
    def test_pipe(self):
        self.assertIn("a\\|b", convert("c\na|b\n"))
PY
printf '# csvmd\n\nWork in progress.\n' > README.md
$SUP init --objective "csvmd per brief.md" >/dev/null
$SUP criterion add "convert() core per brief (format, escaping, align, max_width, BOM, padding)" \
  "CLI python3 -m csvmd [FILE|-] --align --max-width; missing file exit 2; bad max-width exit 2" \
  "README documents every option" >/dev/null
$SUP task add "Conversion core convert(text, align='auto', max_width=None)" --criteria AC1 --files "csvmd/__init__.py,tests/test_core.py" >/dev/null
$SUP task add "CLI entry point csvmd/__main__.py + CLI tests" --depends T1 --criteria AC2 --files "csvmd/__main__.py,tests/test_cli.py" >/dev/null
$SUP task add "README" --depends T2 --criteria AC3 --files "README.md" >/dev/null
$SUP decide "Core API: csvmd.convert(text, align='auto', max_width=None) -> str with trailing newline; '' for empty" --why "contract for the CLI" >/dev/null
$SUP task set T1 verified --evidence "tests.test_core 2 OK" >/dev/null
$SUP criterion verify AC1 --evidence "tests.test_core 2 OK" >/dev/null
$SUP next "Build csvmd/__main__.py on top of convert()" "CLI tests" "README" >/dev/null
