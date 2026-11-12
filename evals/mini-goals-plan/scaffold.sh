#!/usr/bin/env bash
cat > brief.md <<'MD'
# Brief: "Shelfmark" - a small library lending system

Build, in Python standard library only:
1. A catalogue: add, edit, remove and search books (title, author, ISBN); ISBNs are validated and unique.
2. Members: register and deactivate members; a member has an id and an email.
3. Lending: check a book out to a member and return it; a book can be out to one member at a time; a member can
   hold at most 5 books; loans are due after 21 days.
4. Overdue report: list overdue loans with days late, as text and as CSV.
5. A command line interface for all of the above, with exit code 2 on bad input.
6. Data is stored in one SQLite file and survives restarts.
7. A README with every command and one example each.
MD
