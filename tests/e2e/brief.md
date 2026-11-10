# Brief: `csvmd` — CSV → GitHub Markdown table CLI

A teammate started this repo and left. Finish it.

Build a Python 3 command-line tool, run as `python3 -m csvmd [FILE] [options]`
from the project root, that converts CSV to a GitHub-flavoured Markdown table.
Standard library only (no third-party packages).

## Behaviour

- Input: `FILE`, or stdin when `FILE` is omitted or is `-`. UTF-8; a leading BOM is ignored.
- The first CSV row is the header. Standard CSV quoting applies (quoted fields may contain commas and newlines).
- Column count = the longest row. Shorter rows (including the header) are padded with empty cells.
- Output format, exactly:
  - each row is `| ` + cells joined by ` | ` + ` |`
  - the second line is the alignment row, using `---:` (right), `:---` (left), or `---` (none)
- Cell escaping: `|` becomes `\|`; newlines inside a cell become `<br>`.
- `--align auto|left|none` (default `auto`):
  - `auto`: a column is right-aligned if it has at least one non-empty data cell and every non-empty data cell parses as a finite number; otherwise left-aligned.
  - `left`: every column `:---`. `none`: every column `---`.
- `--max-width N`: a cell whose text is longer than N characters is cut to its first N-1 characters followed by `…`. Truncation applies to the raw cell text, before escaping. N must be ≥ 2, otherwise exit code 2 with an error on stderr.
- Empty input: print nothing, exit 0.
- Missing input file: print an error naming the file to stderr, print nothing to stdout, exit 2.

## Deliverables

- The package `csvmd/` runnable with `python3 -m csvmd`.
- Automated tests that pass with `python3 -m unittest discover -s tests` (pytest is not installed).
- `README.md` with usage that documents every option.

## Nice to have, only if cheap

- Excel (`.xlsx`) input.
