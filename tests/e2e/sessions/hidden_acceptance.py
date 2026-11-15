#!/usr/bin/env python3
"""Hidden acceptance tests for the three-session shelfmark benchmark - never shown to agents.

The project is built over three separate sessions. Some requirements are only ever said in a session's prompt:
session 1 adds `book list --available` and lower-case emails; session 2 changes the loan period to 14 days and the
limit to 3 books; session 3 adds `report overdue --min-days N`. Each check is tagged with where its requirement
came from, and the score is also printed per origin: the question is which requirements survive to the end.

Usage: python3 -I tests/e2e/sessions/hidden_acceptance.py <project_dir>

Black box: every check runs `python -m shelfmark` as separate processes against a fresh database file, exactly as
the brief describes. Only behaviour the brief states is tested. Output is compared after CRLF -> LF.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve()
CHECKS = []
T0 = "2026-03-01"


def check(name, origin="brief"):
    def deco(fn):
        CHECKS.append((name, fn, origin))
        return fn
    return deco


def isbn(n):
    """A valid ISBN-13 built from a 12-digit body 978000000NNN."""
    body = f"978{n:09d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(body))
    return body + str((10 - total % 10) % 10)


A, B, C, D, E, F, G = (isbn(i) for i in range(1, 8))


class Lib:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="shelfmark-")
        self.db = os.path.join(self.dir, "lib.db")

    def raw(self, args, today=T0, db=True, env=None, cwd=None):
        argv = [sys.executable, "-m", "shelfmark"]
        if db:
            argv += ["--db", self.db]
        if today:
            argv += ["--today", today]
        full_env = {**os.environ, "PYTHONPATH": str(PROJECT), **(env or {})}
        full_env.pop("SHELFMARK_DB", None) if not env or "SHELFMARK_DB" not in env else None
        p = subprocess.run(argv + list(args), cwd=cwd or str(PROJECT), capture_output=True, timeout=30, env=full_env)
        return p.returncode, p.stdout.decode("utf-8", "replace").replace("\r\n", "\n"), p.stderr.decode("utf-8", "replace")

    def ok(self, *args, today=T0):
        code, out, err = self.raw(args, today)
        assert code == 0, f"{' '.join(args)} -> exit {code}: {err[:200]}"
        return out

    def refused(self, *args, today=T0):
        code, out, err = self.raw(args, today)
        assert code == 2, f"{' '.join(args)} -> exit {code}, expected 2 (stdout {out[:80]!r})"
        assert out == "", f"{' '.join(args)}: stdout must be empty on error, got {out[:80]!r}"
        assert err.lstrip().lower().startswith("error:"), f"{' '.join(args)}: stderr must start with 'error:', got {err[:80]!r}"


def stocked(n_books=3, n_members=2):
    lib = Lib()
    titles = [("Beta", "Ann Lee"), ("alpha", "Bob Ray"), ("Gamma, the Third", "Cy Oz"), ("delta", "Di Vu"),
              ("Epsilon", "Ed Wu"), ("Zeta", "Flo Xi"), ("eta", "Gus Yo")]
    for i in range(n_books):
        lib.ok("book", "add", isbn(i + 1), titles[i][0], titles[i][1])
    for i in range(n_members):
        lib.ok("member", "add", f"m{i + 1}@example.org", f"Member {i + 1}")
    return lib


# ---- catalogue --------------------------------------------------------------
@check("book add prints 'added ISBN' and stores it")
def _():
    lib = Lib()
    assert lib.ok("book", "add", A, "Dune", "F. Herbert") == f"added {A}\n"
    assert lib.ok("book", "list") == f"{A}\tDune\tF. Herbert\tavailable\n"


@check("hyphens in an ISBN are ignored and never printed")
def _():
    lib = Lib()
    hyph = f"{A[:3]}-{A[3]}-{A[4:8]}-{A[8:12]}-{A[12]}"
    assert lib.ok("book", "add", hyph, "Dune", "F. Herbert") == f"added {A}\n"
    assert lib.ok("book", "list").startswith(A + "\t")


@check("an ISBN with a wrong check digit is refused")
def _():
    bad = A[:12] + str((int(A[12]) + 1) % 10)
    Lib().refused("book", "add", bad, "X", "Y")


@check("an ISBN that is not 13 digits is refused")
def _():
    lib = Lib()
    lib.refused("book", "add", "12345", "X", "Y")
    lib.refused("book", "add", A[:12] + "X", "X", "Y")


@check("a duplicate ISBN is refused, also when typed with hyphens")
def _():
    lib = Lib()
    lib.ok("book", "add", A, "Dune", "F. Herbert")
    lib.refused("book", "add", A, "Other", "Someone")
    lib.refused("book", "add", f"{A[:3]}-{A[3:]}", "Other", "Someone")
    assert lib.ok("book", "list").count("\n") == 1


@check("book list is sorted by title ignoring case")
def _():
    out = stocked(4, 0).ok("book", "list")
    assert [line.split("\t")[1] for line in out.splitlines()] == ["alpha", "Beta", "delta", "Gamma, the Third"], out


@check("book list --search matches title or author, ignoring case")
def _():
    lib = stocked(4, 0)
    assert [l.split("\t")[1] for l in lib.ok("book", "list", "--search", "ALPH").splitlines()] == ["alpha"]
    assert [l.split("\t")[1] for l in lib.ok("book", "list", "--search", "ann lee").splitlines()] == ["Beta"]
    assert lib.ok("book", "list", "--search", "no such thing") == ""


@check("an empty catalogue lists nothing")
def _():
    assert Lib().ok("book", "list") == ""


@check("book remove works; unknown book is refused")
def _():
    lib = stocked(2, 0)
    assert lib.ok("book", "remove", A) == f"removed {A}\n"
    assert A not in lib.ok("book", "list")
    lib.refused("book", "remove", A)


@check("a book on loan cannot be removed")
def _():
    lib = stocked(1, 1)
    lib.ok("loan", "out", A, "1")
    lib.refused("book", "remove", A)
    assert A in lib.ok("book", "list")


# ---- members ----------------------------------------------------------------
@check("member ids start at 1 and increase")
def _():
    lib = Lib()
    assert lib.ok("member", "add", "a@x.org", "Ann") == "member 1\n"
    assert lib.ok("member", "add", "b@x.org", "Bob") == "member 2\n"
    assert lib.ok("member", "list") == "1\ta@x.org\tAnn\tactive\n2\tb@x.org\tBob\tactive\n"


@check("a malformed email is refused")
def _():
    lib = Lib()
    for bad in ("nobody", "@x.org", "a@", "a@b@c"):
        lib.refused("member", "add", bad, "X")
    assert lib.ok("member", "list") == ""


@check("the same email in another case is refused")
def _():
    lib = Lib()
    lib.ok("member", "add", "Ann@X.org", "Ann")
    lib.refused("member", "add", "ann@x.ORG", "Other Ann")


@check("deactivate marks the member inactive and keeps them listed")
def _():
    lib = stocked(0, 2)
    assert lib.ok("member", "deactivate", "1") == "deactivated 1\n"
    assert lib.ok("member", "list").splitlines()[0].endswith("\tinactive")
    lib.refused("member", "deactivate", "99")


@check("a member with a book on loan cannot be deactivated")
def _():
    lib = stocked(1, 1)
    lib.ok("loan", "out", A, "1")
    lib.refused("member", "deactivate", "1")
    assert lib.ok("member", "list").endswith("\tactive\n")


# ---- lending ----------------------------------------------------------------
@check("loan out prints the due date, 14 days after today (changed in session 2)", "s2")
def _():
    lib = stocked(2, 1)
    assert lib.ok("loan", "out", A, "1", today="2026-03-01") == "due 2026-03-15\n"
    assert lib.ok("loan", "out", B, "1", today="2026-12-20") == "due 2027-01-03\n"


@check("a loaned book shows 'on loan' and becomes 'available' again when returned")
def _():
    lib = stocked(1, 1)
    lib.ok("loan", "out", A, "1")
    assert lib.ok("book", "list").endswith("\ton loan\n")
    assert lib.ok("loan", "return", A) == f"returned {A}\n"
    assert lib.ok("book", "list").endswith("\tavailable\n")


@check("a book already on loan cannot be loaned again")
def _():
    lib = stocked(1, 2)
    lib.ok("loan", "out", A, "1")
    lib.refused("loan", "out", A, "2")


@check("unknown book or unknown member is refused")
def _():
    lib = stocked(1, 1)
    lib.refused("loan", "out", B, "1")
    lib.refused("loan", "out", A, "7")


@check("an inactive member cannot borrow")
def _():
    lib = stocked(1, 1)
    lib.ok("member", "deactivate", "1")
    lib.refused("loan", "out", A, "1")
    assert lib.ok("book", "list").endswith("\tavailable\n")


@check("a member can hold 3 books and the 4th is refused (changed in session 2)", "s2")
def _():
    lib = stocked(6, 1)
    for i in range(1, 4):
        lib.ok("loan", "out", isbn(i), "1")
    lib.refused("loan", "out", isbn(4), "1")


@check("returning a book frees a slot under the limit of 3 (changed in session 2)", "s2")
def _():
    lib = stocked(6, 1)
    for i in range(1, 4):
        lib.ok("loan", "out", isbn(i), "1")
    lib.ok("loan", "return", isbn(1))
    lib.ok("loan", "out", isbn(4), "1")
    lib.refused("loan", "out", isbn(5), "1")


@check("returning a book that is not on loan is refused")
def _():
    lib = stocked(1, 1)
    lib.refused("loan", "return", A)


# ---- overdue report ---------------------------------------------------------
@check("with the 14-day period: not overdue on day 14, 1 day late on day 15 (session 2)", "s2")
def _():
    lib = stocked(1, 1)
    lib.ok("loan", "out", A, "1", today="2026-03-01")
    assert lib.ok("report", "overdue", today="2026-03-15") == ""
    assert lib.ok("report", "overdue", today="2026-03-16") == f"{A}\tBeta\t1\t2026-03-15\t1\n"


@check("an overdue line has five tab-separated fields and days late = today minus due")
def _():
    lib = stocked(1, 1)
    due = lib.ok("loan", "out", A, "1", today="2026-03-01").split()[1]
    line = lib.ok("report", "overdue", today="2026-06-01").rstrip("\n").split("\t")
    assert line[:4] == [A, "Beta", "1", due], line
    import datetime
    assert int(line[4]) == (datetime.date(2026, 6, 1) - datetime.date.fromisoformat(due)).days, line


@check("overdue report is sorted by days late (largest first), then ISBN")
def _():
    lib = stocked(3, 2)
    lib.ok("loan", "out", B, "1", today="2026-03-05")
    lib.ok("loan", "out", C, "2", today="2026-03-01")
    lib.ok("loan", "out", A, "2", today="2026-03-05")
    lines = lib.ok("report", "overdue", today="2026-04-20").splitlines()
    assert [l.split("\t")[0] for l in lines] == [C, A, B], lines
    late = [int(l.split("\t")[4]) for l in lines]
    assert late[0] > late[1] == late[2], lines


@check("a returned book leaves the overdue report")
def _():
    lib = stocked(1, 1)
    lib.ok("loan", "out", A, "1", today="2026-03-01")
    lib.ok("loan", "return", A, today="2026-05-01")
    assert lib.ok("report", "overdue", today="2026-05-02") == ""


@check("overdue --csv has the header and quotes a title containing a comma")
def _():
    lib = stocked(3, 1)
    lib.ok("loan", "out", C, "1", today="2026-03-01")
    out = lib.ok("report", "overdue", "--csv", today="2026-05-01").splitlines()
    assert out[0] == "isbn,title,member_id,due,days_late", out
    assert len(out) == 2 and out[1].startswith(f'{C},"Gamma, the Third",1,'), out


@check("overdue --csv with nothing overdue prints the header only")
def _():
    assert stocked(1, 1).ok("report", "overdue", "--csv") == "isbn,title,member_id,due,days_late\n"


# ---- asked for only in a session's prompt ------------------------------------
@check("book list --available hides books that are on loan (asked in session 1)", "s1")
def _():
    lib = stocked(3, 1)
    lib.ok("loan", "out", A, "1")
    titles = [l.split("\t")[1] for l in lib.ok("book", "list", "--available").splitlines()]
    assert titles == ["alpha", "Gamma, the Third"], titles
    assert all(l.endswith("\tavailable") for l in lib.ok("book", "list", "--available").splitlines())


@check("book list --available combines with --search (asked in session 1)", "s1")
def _():
    lib = stocked(4, 1)
    lib.ok("loan", "out", B, "1")            # "alpha" goes out
    out = lib.ok("book", "list", "--available", "--search", "a")
    titles = [l.split("\t")[1] for l in out.splitlines()]
    assert "alpha" not in titles and "Beta" in titles and "delta" in titles, titles


@check("member emails are stored and printed in lower case (asked in session 1)", "s1")
def _():
    lib = Lib()
    lib.ok("member", "add", "Ann@X.org", "Ann")
    assert lib.ok("member", "list") == "1\tann@x.org\tAnn\tactive\n"


@check("report overdue --min-days N keeps only loans at least N days late (asked in session 3)", "s3")
def _():
    lib = stocked(2, 1)
    lib.ok("loan", "out", A, "1", today="2026-03-01")
    lib.ok("loan", "out", B, "1", today="2026-03-11")
    both = lib.ok("report", "overdue", today="2026-04-20").splitlines()
    assert len(both) == 2, both
    big, small = (int(l.split("\t")[4]) for l in both)
    only = lib.ok("report", "overdue", "--min-days", str(big), today="2026-04-20").splitlines()
    assert [l.split("\t")[0] for l in only] == [A], only
    assert len(lib.ok("report", "overdue", "--min-days", str(small), today="2026-04-20").splitlines()) == 2
    assert lib.ok("report", "overdue", "--min-days", str(big + 1), today="2026-04-20") == ""


@check("report overdue --min-days works together with --csv (asked in session 3)", "s3")
def _():
    lib = stocked(2, 1)
    lib.ok("loan", "out", A, "1", today="2026-03-01")
    lib.ok("loan", "out", B, "1", today="2026-03-11")
    big = int(lib.ok("report", "overdue", today="2026-04-20").splitlines()[0].split("\t")[4])
    out = lib.ok("report", "overdue", "--csv", "--min-days", str(big), today="2026-04-20").splitlines()
    assert out[0] == "isbn,title,member_id,due,days_late" and len(out) == 2 and out[1].startswith(A + ","), out


# ---- global rules -----------------------------------------------------------
@check("data survives between runs in the --db file, and two files are independent")
def _():
    one, two = stocked(2, 1), Lib()
    assert one.ok("book", "list").count("\n") == 2
    assert two.ok("book", "list") == ""
    assert os.path.exists(one.db)


@check("SHELFMARK_DB names the database when --db is absent; --db wins over it")
def _():
    lib = Lib()
    env_db = os.path.join(lib.dir, "env.db")
    code, out, err = lib.raw(["book", "add", A, "Dune", "F. Herbert"], db=False, env={"SHELFMARK_DB": env_db})
    assert code == 0 and os.path.exists(env_db), (code, err[:120])
    code, out, _ = lib.raw(["book", "list"], db=False, env={"SHELFMARK_DB": env_db})
    assert A in out
    code, out, _ = lib.raw(["book", "list"], db=True, env={"SHELFMARK_DB": env_db})
    assert code == 0 and out == "", "--db must win over SHELFMARK_DB"


@check("without --db and SHELFMARK_DB the file is shelfmark.db in the current directory")
def _():
    lib = Lib()
    code, _, err = lib.raw(["member", "add", "a@x.org", "Ann"], db=False, cwd=lib.dir)
    assert code == 0, err[:160]
    assert os.path.exists(os.path.join(lib.dir, "shelfmark.db"))


@check("unknown commands and missing arguments exit 2 with 'error:' and empty stdout")
def _():
    lib = Lib()
    lib.refused("book", "burn", A)
    lib.refused("frobnicate")
    lib.refused("book", "add", A)
    lib.refused("loan", "out", A)


@check("a refused command changes nothing")
def _():
    lib = stocked(1, 1)
    lib.ok("loan", "out", A, "1")
    before = (lib.ok("book", "list"), lib.ok("member", "list"))
    lib.refused("loan", "out", A, "1")
    lib.refused("book", "remove", A)
    lib.refused("member", "deactivate", "1")
    assert (lib.ok("book", "list"), lib.ok("member", "list")) == before


# ---- quality ----------------------------------------------------------------
@check("README shows every command and the three options")
def _():
    text = (PROJECT / "README.md").read_text(encoding="utf-8", errors="replace")
    for needle in ("book add", "book list", "book remove", "member add", "member list", "member deactivate",
                   "loan out", "loan return", "report overdue", "--db", "SHELFMARK_DB", "--today"):
        assert needle in text, f"README does not mention {needle}"


@check("project tests pass with unittest")
def _():
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=PROJECT,
                       capture_output=True, timeout=180)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-300:]
    assert b"Ran 0 tests" not in p.stderr, "no tests were collected"


def main():
    passed, by = 0, {}
    for name, fn, origin in CHECKS:
        tally = by.setdefault(origin, [0, 0])
        tally[1] += 1
        try:
            fn()
            passed += 1
            tally[0] += 1
            print(f"PASS [{origin}] {name}")
        except Exception as exc:  # noqa: BLE001 - a check that crashes is a failed check
            print(f"FAIL [{origin}] {name}: {str(exc)[:200]}")
    labels = {"brief": "in the brief", "s1": "said in session 1", "s2": "said in session 2", "s3": "said in session 3"}
    print("\nBY ORIGIN " + " | ".join(f"{labels[k]} {by[k][0]}/{by[k][1]}" for k in ("brief", "s1", "s2", "s3") if k in by))
    chat = [by.get(k, [0, 0]) for k in ("s1", "s2", "s3")]
    print(f"CHAT {sum(c[0] for c in chat)}/{sum(c[1] for c in chat)}")
    print(f"SCORE {passed}/{len(CHECKS)}")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
