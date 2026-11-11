# Brief: `textkit` — three text utilities behind one CLI

Build a Python 3 package `textkit`, standard library only, in an empty repository.
Run as `python3 -m textkit <command> ...` from the project root.

## 1. `textkit/slug.py` — `slugify(text, sep="-", max_len=None) -> str`

1. Unicode-normalise with NFKD and drop every non-ASCII character (so `"Café Déjà"` → `"Cafe Deja"`).
2. Lower-case.
3. Replace every run of characters that are not `[a-z0-9]` with a single `sep`.
4. Strip `sep` from both ends.
5. If `max_len` is given, cut the result to at most `max_len` characters, then strip any trailing `sep`.

CLI: `python3 -m textkit slug [--sep S] [--max-len N] TEXT [TEXT ...]` prints one slug per TEXT, one per line.

## 2. `textkit/toc.py` — `toc(markdown: str) -> str`

- Use ATX headings of level 2–6 only (`## ` … `###### `). Ignore level 1 and anything inside fenced code blocks (fences start with ```` ``` ```` or `~~~` and end with the same marker).
- The heading text has trailing `#` characters and surrounding whitespace removed.
- Each entry is `"  " * (level - 2) + "- [" + text + "](#" + anchor + ")"`. Entries are joined with `\n`, and there is a trailing `\n` when there is at least one entry. With no entries, return `""`.
- Anchor: lower-case the text, delete every character that is not `a-z`, `0-9`, space, `-` or `_`, then replace each space with `-`. If an anchor was already used earlier in the document, append `-1`, `-2`, … (the first unused one).

CLI: `python3 -m textkit toc [FILE]` (stdin when FILE is omitted or `-`) prints the result unchanged.

## 3. `textkit/stats.py` — `stats(text: str) -> dict`

- `words`: whitespace-separated tokens that contain at least one letter or digit.
- `sentences`: the number of maximal runs of `.`, `!` or `?` that are followed by whitespace or the end of the text. If `words > 0` and this count is 0, use 1.
- `reading_minutes`: `ceil(words / 200)`, which is 0 when `words` is 0.

CLI: `python3 -m textkit stats [FILE]` (stdin when FILE is omitted or `-`) prints exactly `words=W sentences=S reading_minutes=M`.

## CLI-wide rules

- Unknown command, missing command, or bad option: an error on stderr and exit 2.
- Missing input file: an error naming the file on stderr, nothing on stdout, exit 2.

## Deliverables

- The package, plus tests that pass with `python3 -m unittest discover -s tests`.
- A `README.md` documenting every command and option.
