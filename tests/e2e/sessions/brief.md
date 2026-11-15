# Brief: `shelfmark` — a small library lending system

Build a Python 3 package `shelfmark`, standard library only, in this repository.
Every command is a separate run of `python3 -m shelfmark ...` from the project root, so all data must be stored
in a SQLite file and survive between runs.

## Global rules

- **Database file.** `--db PATH` (given before the command) names the SQLite file. Without it, the environment
  variable `SHELFMARK_DB` names it. Without both, use `shelfmark.db` in the current directory. `--db` wins over the
  variable. The file and its tables are created on first use.
- **Today.** `--today YYYY-MM-DD` (given before the command) sets the current date for that run. Without it, use
  the real date. All due dates and lateness are computed from this date.
- **Success:** exit code 0, the output described below on stdout, one item per line.
- **Any error** (bad input, a rule refused, unknown command, missing arguments): a message on stderr that starts
  with `error:`, **nothing on stdout**, exit code 2. Nothing is changed in the database.
- Fields in list output are separated by a single TAB character.

## 1. Catalogue

- `book add ISBN TITLE AUTHOR` prints `added ISBN`.
  - An ISBN is 13 digits; hyphens may be typed anywhere and are ignored (`978-0-306-40615-7` is `9780306406157`).
    It is stored and always printed without hyphens.
  - It must pass the ISBN-13 check: multiply the digits alternately by 1 and 3 (first digit by 1), and the sum
    must be divisible by 10. Anything else is an error.
  - Adding an ISBN that already exists is an error.
- `book list [--search TEXT]` prints one line per book: `ISBN<TAB>TITLE<TAB>AUTHOR<TAB>STATUS`, where STATUS is
  `available` or `on loan`. Lines are sorted by title, ignoring case. With `--search`, only books whose title or
  author contains TEXT, ignoring case. No books: print nothing.
- `book remove ISBN` prints `removed ISBN`. Removing an unknown book, or a book that is on loan, is an error.

## 2. Members

- `member add EMAIL NAME` prints `member ID`. IDs are integers starting at 1, increasing by 1.
  - EMAIL must contain exactly one `@`, with at least one character on each side. Otherwise an error.
  - Two members may not have the same email, ignoring case.
- `member list` prints one line per member, sorted by ID: `ID<TAB>EMAIL<TAB>NAME<TAB>STATE`, where STATE is
  `active` or `inactive`.
- `member deactivate ID` prints `deactivated ID`. Unknown member, or a member who still has a book on loan, is an
  error. A deactivated member stays in the list as `inactive`.

## 3. Lending

- `loan out ISBN MEMBER_ID` prints `due YYYY-MM-DD`, the date 21 days after today. Errors: unknown book, unknown
  member, the book is already on loan, the member is inactive, the member already has 5 books on loan.
- `loan return ISBN` prints `returned ISBN`. A book that is not on loan is an error.

## 4. Overdue report

- A loan is overdue when its due date is before today. Days late = today minus the due date, in days.
- `report overdue` prints one line per overdue loan: `ISBN<TAB>TITLE<TAB>MEMBER_ID<TAB>DUE<TAB>DAYS_LATE`,
  sorted by days late (largest first), then by ISBN. Nothing overdue: print nothing.
- `report overdue --csv` prints CSV with the header `isbn,title,member_id,due,days_late` and the same rows in the
  same order, quoted as Python's `csv` module does by default. Nothing overdue: the header line only.

## 5. Quality

- Unit tests under `tests/`, runnable with `python3 -m unittest discover -s tests`.
- A `README.md` that shows every command (`book add`, `book list`, `book remove`, `member add`, `member list`,
  `member deactivate`, `loan out`, `loan return`, `report overdue`) with one example each, and explains `--db`,
  `SHELFMARK_DB` and `--today`.
