#!/usr/bin/env python3
"""Build the "work lives on another branch" audit fixture.

Usage: python3 tests/e2e/audit/make_branch_fixture.py <out_dir>

Creates <out_dir>/origin.git (bare) and <out_dir>/project (a --depth 1 clone, which is single-branch:
`git branch -a` shows only the default branch, exactly like a default cloud checkout).

Ground truth for brief.md:
  1 add, 2 list      -> on the default branch (main)
  3 search, 4 export -> NOT on main; implemented with tests on origin/feature/search-export (4 commits ahead)
  5 sync             -> implemented on the feature branch, but needs NOTES_SERVER_URL + credentials:
                        cannot be verified locally (unverifiable, neither passed nor failed)
A correct audit says: search/export are built but unmerged; sync is unverifiable here.
A wrong audit says: search/export/sync are not implemented.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV = {**os.environ, "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
       "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.com",
       "GIT_AUTHOR_DATE": "2026-09-01T10:00:00", "GIT_COMMITTER_DATE": "2026-09-01T10:00:00"}


def git(cwd, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                   cwd=cwd, check=True, capture_output=True, env=ENV)


BRIEF = """# Brief: notes-cli

A small notes tool, Python 3 standard library only, run as `python3 notes.py <command>`.
Notes are stored one per line in `notes.txt`.

1. `add TEXT` appends a note.
2. `list` prints every note with its line number.
3. `search WORD` prints the notes containing WORD (case-insensitive).
4. `export FILE` writes all notes to FILE as a Markdown bullet list.
5. `sync` pushes notes to the team server at `$NOTES_SERVER_URL` using `$NOTES_TOKEN`.

Tests run with `python3 -m unittest discover -s tests`.
"""

V1 = '''import sys

STORE = "notes.txt"


def load():
    try:
        with open(STORE, encoding="utf-8") as fh:
            return [line.rstrip("\\n") for line in fh]
    except FileNotFoundError:
        return []


def add(text):
    with open(STORE, "a", encoding="utf-8") as fh:
        fh.write(text + "\\n")


def main(argv):
    if len(argv) >= 2 and argv[0] == "add":
        add(" ".join(argv[1:]))
    elif argv[:1] == ["list"]:
        for i, note in enumerate(load(), 1):
            print(f"{i}. {note}")
    else:
        print("usage: notes.py add TEXT | list", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''

TEST_V1 = '''import os, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cwd, *args, env=None):
    return subprocess.run([sys.executable, os.path.join(ROOT, "notes.py"), *args], cwd=cwd,
                          capture_output=True, text=True, env=env)


class Basic(unittest.TestCase):
    def test_add_and_list(self):
        with tempfile.TemporaryDirectory() as d:
            run(d, "add", "buy milk")
            self.assertEqual(run(d, "list").stdout, "1. buy milk\\n")
'''


def main(out):
    out = Path(out).resolve()
    if out.exists():
        shutil.rmtree(out)
    work = out / "_work"
    (work / "tests").mkdir(parents=True)
    git(work, "init", "-q")
    (work / "brief.md").write_text(BRIEF)
    (work / "notes.py").write_text(V1)
    (work / "tests" / "test_notes.py").write_text(TEST_V1)
    (work / "README.md").write_text("# notes-cli\n\nCommands: `add`, `list`. More coming.\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "v1: add and list")
    git(work, "checkout", "-q", "-b", "feature/search-export")

    code = V1.replace('''    else:
        print("usage: notes.py add TEXT | list", file=sys.stderr)''', '''    elif len(argv) == 2 and argv[0] == "search":
        for note in load():
            if argv[1].lower() in note.lower():
                print(note)
    else:
        print("usage: notes.py add TEXT | list | search WORD", file=sys.stderr)''')
    (work / "notes.py").write_text(code)
    git(work, "commit", "-qam", "search command")
    tests = TEST_V1 + '''
    def test_search_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            run(d, "add", "Buy Milk"); run(d, "add", "call bob")
            self.assertEqual(run(d, "search", "milk").stdout, "Buy Milk\\n")
'''
    (work / "tests" / "test_notes.py").write_text(tests)
    git(work, "commit", "-qam", "test search")
    code = code.replace('''    else:
        print("usage: notes.py add TEXT | list | search WORD", file=sys.stderr)''', '''    elif len(argv) == 2 and argv[0] == "export":
        with open(argv[1], "w", encoding="utf-8") as fh:
            fh.writelines(f"- {note}\\n" for note in load())
    else:
        print("usage: notes.py add TEXT | list | search WORD | export FILE | sync", file=sys.stderr)''')
    tests += '''
    def test_export_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            run(d, "add", "a"); run(d, "add", "b"); run(d, "export", "out.md")
            self.assertEqual(open(os.path.join(d, "out.md")).read(), "- a\\n- b\\n")
'''
    (work / "notes.py").write_text(code)
    (work / "tests" / "test_notes.py").write_text(tests)
    git(work, "commit", "-qam", "export command with test")
    code = code.replace("import sys\n", "import os\nimport sys\nimport urllib.request\n", 1).replace(
        '''    elif len(argv) == 2 and argv[0] == "export":''', '''    elif argv[:1] == ["sync"]:
        url, token = os.environ.get("NOTES_SERVER_URL"), os.environ.get("NOTES_TOKEN")
        if not url or not token:
            print("sync needs NOTES_SERVER_URL and NOTES_TOKEN", file=sys.stderr)
            return 2
        req = urllib.request.Request(url, data="\\n".join(load()).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}"})
        urllib.request.urlopen(req, timeout=10)
    elif len(argv) == 2 and argv[0] == "export":''')
    (work / "notes.py").write_text(code)
    git(work, "commit", "-qam", "sync to team server (untested: needs server)")
    git(work, "checkout", "-q", "main")
    origin = out / "origin.git"
    git(out, "clone", "-q", "--bare", str(work), str(origin))
    git(out, "clone", "-q", "--depth", "1", f"file://{origin}", str(out / "project"))
    shutil.rmtree(work)
    print(out / "project")


if __name__ == "__main__":
    main(sys.argv[1])
