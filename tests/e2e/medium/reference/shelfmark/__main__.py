import csv
import datetime
import os
import sqlite3
import sys


class Refused(Exception):
    pass


def isbn_of(text):
    digits = text.replace("-", "")
    if len(digits) != 13 or not digits.isdigit():
        raise Refused(f"not a 13-digit ISBN: {text}")
    if sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10:
        raise Refused(f"ISBN check digit is wrong: {text}")
    return digits


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE IF NOT EXISTS books(isbn TEXT PRIMARY KEY, title TEXT, author TEXT);"
        "CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, name TEXT, active INTEGER DEFAULT 1);"
        "CREATE TABLE IF NOT EXISTS loans(isbn TEXT PRIMARY KEY, member_id INTEGER, due TEXT);")
    return db


def run(db, today, args, out):
    def need(n):
        if len(args) != n:
            raise Refused("wrong number of arguments")

    cmd = tuple(args[:2])
    rest = args[2:]
    if cmd == ("book", "add"):
        args = rest; need(3)
        isbn = isbn_of(rest[0])
        if db.execute("SELECT 1 FROM books WHERE isbn=?", (isbn,)).fetchone():
            raise Refused(f"book {isbn} already exists")
        db.execute("INSERT INTO books VALUES(?,?,?)", (isbn, rest[1], rest[2]))
        out.append(f"added {isbn}")
    elif cmd == ("book", "list"):
        search = None
        if rest:
            if len(rest) != 2 or rest[0] != "--search":
                raise Refused("usage: book list [--search TEXT]")
            search = rest[1].lower()
        rows = db.execute("SELECT b.isbn, b.title, b.author, l.isbn FROM books b LEFT JOIN loans l ON l.isbn=b.isbn").fetchall()
        for isbn, title, author, loan in sorted(rows, key=lambda r: (r[1].lower(), r[0])):
            if search is None or search in title.lower() or search in author.lower():
                out.append("\t".join([isbn, title, author, "on loan" if loan else "available"]))
    elif cmd == ("book", "remove"):
        args = rest; need(1)
        isbn = isbn_of(rest[0])
        if not db.execute("SELECT 1 FROM books WHERE isbn=?", (isbn,)).fetchone():
            raise Refused(f"unknown book {isbn}")
        if db.execute("SELECT 1 FROM loans WHERE isbn=?", (isbn,)).fetchone():
            raise Refused(f"book {isbn} is on loan")
        db.execute("DELETE FROM books WHERE isbn=?", (isbn,))
        out.append(f"removed {isbn}")
    elif cmd == ("member", "add"):
        args = rest; need(2)
        email = rest[0]
        local, at, domain = email.partition("@")
        if email.count("@") != 1 or not local or not domain:
            raise Refused(f"not an email address: {email}")
        if db.execute("SELECT 1 FROM members WHERE lower(email)=?", (email.lower(),)).fetchone():
            raise Refused(f"a member with {email} already exists")
        cur = db.execute("INSERT INTO members(email, name) VALUES(?,?)", (email, rest[1]))
        out.append(f"member {cur.lastrowid}")
    elif cmd == ("member", "list"):
        args = rest; need(0)
        for mid, email, name, active in db.execute("SELECT id, email, name, active FROM members ORDER BY id"):
            out.append("\t".join([str(mid), email, name, "active" if active else "inactive"]))
    elif cmd == ("member", "deactivate"):
        args = rest; need(1)
        mid = member_id(rest[0])
        if not db.execute("SELECT 1 FROM members WHERE id=?", (mid,)).fetchone():
            raise Refused(f"unknown member {mid}")
        if db.execute("SELECT 1 FROM loans WHERE member_id=?", (mid,)).fetchone():
            raise Refused(f"member {mid} still has books on loan")
        db.execute("UPDATE members SET active=0 WHERE id=?", (mid,))
        out.append(f"deactivated {mid}")
    elif cmd == ("loan", "out"):
        args = rest; need(2)
        isbn, mid = isbn_of(rest[0]), member_id(rest[1])
        if not db.execute("SELECT 1 FROM books WHERE isbn=?", (isbn,)).fetchone():
            raise Refused(f"unknown book {isbn}")
        row = db.execute("SELECT active FROM members WHERE id=?", (mid,)).fetchone()
        if not row:
            raise Refused(f"unknown member {mid}")
        if not row[0]:
            raise Refused(f"member {mid} is inactive")
        if db.execute("SELECT 1 FROM loans WHERE isbn=?", (isbn,)).fetchone():
            raise Refused(f"book {isbn} is already on loan")
        if db.execute("SELECT count(*) FROM loans WHERE member_id=?", (mid,)).fetchone()[0] >= 5:
            raise Refused(f"member {mid} already has 5 books")
        due = (today + datetime.timedelta(days=21)).isoformat()
        db.execute("INSERT INTO loans VALUES(?,?,?)", (isbn, mid, due))
        out.append(f"due {due}")
    elif cmd == ("loan", "return"):
        args = rest; need(1)
        isbn = isbn_of(rest[0])
        if not db.execute("SELECT 1 FROM loans WHERE isbn=?", (isbn,)).fetchone():
            raise Refused(f"book {isbn} is not on loan")
        db.execute("DELETE FROM loans WHERE isbn=?", (isbn,))
        out.append(f"returned {isbn}")
    elif cmd == ("report", "overdue"):
        if rest not in ([], ["--csv"]):
            raise Refused("usage: report overdue [--csv]")
        rows = []
        for isbn, title, mid, due in db.execute("SELECT l.isbn, b.title, l.member_id, l.due FROM loans l JOIN books b ON b.isbn=l.isbn"):
            late = (today - datetime.date.fromisoformat(due)).days
            if late > 0:
                rows.append((isbn, title, mid, due, late))
        rows.sort(key=lambda r: (-r[4], r[0]))
        if rest:
            return ("csv", rows)
        out.extend("\t".join(str(x) for x in r) for r in rows)
    else:
        raise Refused("unknown command")
    return None


def member_id(text):
    if not text.isdigit():
        raise Refused(f"not a member id: {text}")
    return int(text)


def main(argv):
    path = os.environ.get("SHELFMARK_DB") or "shelfmark.db"
    today = datetime.date.today()
    try:
        while argv and argv[0] in ("--db", "--today"):
            if len(argv) < 2:
                raise Refused(f"{argv[0]} needs a value")
            if argv[0] == "--db":
                path = argv[1]
            else:
                try:
                    today = datetime.date.fromisoformat(argv[1])
                except ValueError:
                    raise Refused(f"not a date: {argv[1]}")
            argv = argv[2:]
        if len(argv) < 2:
            raise Refused("usage: python3 -m shelfmark [--db PATH] [--today DATE] <command> ...")
        db = connect(path)
        out = []
        special = run(db, today, argv, out)
        db.commit()
    except Refused as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", newline="\n", closefd=False)
    if special:
        writer = csv.writer(stdout, lineterminator="\n")
        writer.writerow(["isbn", "title", "member_id", "due", "days_late"])
        writer.writerows(special[1])
    else:
        stdout.write("".join(line + "\n" for line in out))
    stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
