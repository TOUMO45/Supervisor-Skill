#!/usr/bin/env python3
"""Hidden acceptance tests for the csvmd e2e benchmark (never shown to the agent).

Usage: python3 -I tests/e2e/hidden_acceptance.py <project_dir>
Prints one line per check and a final score. Exit 0 if all pass.
"""
import subprocess
import sys
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve()
# --clarified: score against the brief PLUS the two mid-session user clarifications
# (see tests/e2e/clarifications.md): missing file exits 3; CSVMD_MAX_WIDTH env default.
CLARIFIED = "--clarified" in sys.argv[2:]


def run(args, stdin=""):
    return subprocess.run(
        [sys.executable, "-m", "csvmd", *args],
        cwd=PROJECT, input=stdin.encode("utf-8"), capture_output=True, timeout=20,
    )


def table(*lines):
    return "\n".join(lines) + "\n"


CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def expect_stdout(args, stdin, expected):
    p = run(args, stdin)
    out = p.stdout.decode("utf-8", "replace")
    assert p.returncode == 0, f"exit {p.returncode}: {p.stderr.decode()[:200]}"
    assert out.rstrip("\n") == expected.rstrip("\n"), f"got:\n{out}\nexpected:\n{expected}"


@check("basic numeric table, stdin")
def _():
    expect_stdout([], "a,b\n1,2\n", table("| a | b |", "| ---: | ---: |", "| 1 | 2 |"))


@check("mixed columns auto-align")
def _():
    expect_stdout([], "name,age\nbob,3\nann,4.5\n",
                  table("| name | age |", "| :--- | ---: |", "| bob | 3 |", "| ann | 4.5 |"))


@check("'-' means stdin")
def _():
    expect_stdout(["-"], "x\n1\n", table("| x |", "| ---: |", "| 1 |"))


@check("file argument")
def _():
    f = PROJECT / "_hidden_in.csv"
    f.write_text("k,v\na,b\n", encoding="utf-8")
    try:
        expect_stdout([str(f)], "", table("| k | v |", "| :--- | :--- |", "| a | b |"))
    finally:
        f.unlink()


@check("pipe escaping")
def _():
    expect_stdout([], "c\na|b\n", table("| c |", "| :--- |", "| a\\|b |"))


@check("quoted newline -> <br>")
def _():
    expect_stdout([], 'c\n"l1\nl2"\n', table("| c |", "| :--- |", "| l1<br>l2 |"))


@check("ragged rows padded (header shorter)")
def _():
    expect_stdout(["--align", "none"], "a\n1,2\n", table("| a |  |", "| --- | --- |", "| 1 | 2 |"))


@check("ragged rows padded (data shorter)")
def _():
    expect_stdout(["--align", "none"], "a,b\n1\n", table("| a | b |", "| --- | --- |", "| 1 |  |"))


@check("empty-only column is left in auto")
def _():
    expect_stdout([], "a,b\n1,\n", table("| a | b |", "| ---: | :--- |", "| 1 |  |"))


@check("non-finite is not numeric")
def _():
    expect_stdout([], "a\ninf\n", table("| a |", "| :--- |", "| inf |"))


@check("--align left")
def _():
    expect_stdout(["--align", "left"], "a\n1\n", table("| a |", "| :--- |", "| 1 |"))


@check("--max-width truncates before escaping")
def _():
    expect_stdout(["--max-width", "4"], "c\nabcdef\nab|cd\nabcd\n",
                  table("| c |", "| :--- |", "| abc… |", "| ab\\|… |", "| abcd |"))


@check("--max-width < 2 rejected with exit 2")
def _():
    p = run(["--max-width", "1"], "a\n1\n")
    assert p.returncode == 2, f"exit {p.returncode}"
    assert p.stderr.strip(), "no stderr"


@check("BOM stripped")
def _():
    expect_stdout([], "﻿a\n1\n", table("| a |", "| ---: |", "| 1 |"))


@check("empty input -> no output, exit 0")
def _():
    p = run([], "")
    assert p.returncode == 0 and p.stdout == b"", (p.returncode, p.stdout)


@check("missing file -> exit 2 (3 if clarified), stderr names file, empty stdout")
def _():
    p = run(["nope_404.csv"], "")
    want = 3 if CLARIFIED else 2
    assert p.returncode == want, f"exit {p.returncode}, want {want}"
    assert b"nope_404.csv" in p.stderr and p.stdout == b""


def run_env(args, stdin, env_extra):
    import os
    return subprocess.run([sys.executable, "-m", "csvmd", *args], cwd=PROJECT,
                          input=stdin.encode(), capture_output=True, timeout=20,
                          env={**os.environ, **env_extra})


if CLARIFIED:
    @check("clarified: CSVMD_MAX_WIDTH sets default width")
    def _():
        p = run_env([], "c\nabcdef\n", {"CSVMD_MAX_WIDTH": "4"})
        assert p.returncode == 0, p.stderr.decode()[:200]
        assert "| abc… |" in p.stdout.decode(), p.stdout.decode()

    @check("clarified: --max-width overrides CSVMD_MAX_WIDTH")
    def _():
        p = run_env(["--max-width", "6"], "c\nabcdefgh\n", {"CSVMD_MAX_WIDTH": "3"})
        assert "| abcde… |" in p.stdout.decode(), p.stdout.decode()


@check("README documents every option")
def _():
    text = (PROJECT / "README.md").read_text(encoding="utf-8")
    for opt in ("--align", "--max-width"):
        assert opt in text, f"README lacks {opt}"


@check("project's own tests pass with unittest")
def _():
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=PROJECT, capture_output=True, timeout=120)
    assert p.returncode == 0, p.stderr.decode()[-400:]
    assert b"Ran 0 tests" not in p.stderr, "no tests ran"


def main():
    passed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001 - report every failure
            print(f"FAIL  {name}: {str(exc).splitlines()[0] if str(exc) else type(exc).__name__}")
    print(f"\nSCORE {passed}/{len(CHECKS)}")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
