#!/usr/bin/env python3
"""Hidden acceptance tests for the textkit (parallel) benchmark - never shown to agents.

Usage: python3 -I tests/e2e/parallel/hidden_acceptance.py <project_dir>
"""
import subprocess
import sys
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve()
CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def run(args, stdin=""):
    return subprocess.run([sys.executable, "-m", "textkit", *args], cwd=PROJECT,
                          input=stdin.encode("utf-8"), capture_output=True, timeout=20)


def out_ok(args, stdin, expected):
    p = run(args, stdin)
    assert p.returncode == 0, f"exit {p.returncode}: {p.stderr.decode()[:200]}"
    got = p.stdout.decode("utf-8")
    assert got == expected, f"got {got!r} expected {expected!r}"


# ---- slug -----------------------------------------------------------------
@check("slug: basic + accents")
def _():
    out_ok(["slug", "Café Déjà Vu!"], "", "cafe-deja-vu\n")


@check("slug: runs collapse, ends stripped")
def _():
    out_ok(["slug", "  --Hello,   World--  "], "", "hello-world\n")


@check("slug: custom sep")
def _():
    out_ok(["slug", "--sep", "_", "A b C"], "", "a_b_c\n")


@check("slug: max-len strips trailing sep")
def _():
    out_ok(["slug", "--max-len", "6", "hello world"], "", "hello\n")


@check("slug: multiple texts one per line")
def _():
    out_ok(["slug", "One", "Two Three"], "", "one\ntwo-three\n")


@check("slug: non-ascii only -> empty line")
def _():
    out_ok(["slug", "日本"], "", "\n")


# ---- toc ------------------------------------------------------------------
@check("toc: levels and indentation, h1 ignored")
def _():
    md = "# Title\n## Intro\n### Deep Dive\n## Usage\n"
    out_ok(["toc"], md, "- [Intro](#intro)\n  - [Deep Dive](#deep-dive)\n- [Usage](#usage)\n")


@check("toc: duplicate anchors get -1, -2")
def _():
    md = "## FAQ\n## FAQ\n## FAQ\n"
    out_ok(["toc"], md, "- [FAQ](#faq)\n- [FAQ](#faq-1)\n- [FAQ](#faq-2)\n")


@check("toc: fenced code ignored (``` and ~~~)")
def _():
    md = "## A\n```\n## not\n```\n~~~\n## nope\n~~~\n## B\n"
    out_ok(["toc"], md, "- [A](#a)\n- [B](#b)\n")


@check("toc: trailing hashes and punctuation in anchor")
def _():
    md = "## Hello, World! ##\n"
    out_ok(["toc"], md, "- [Hello, World!](#hello-world)\n")


@check("toc: no headings -> empty output")
def _():
    out_ok(["toc"], "just text\n", "")


@check("toc: file argument")
def _():
    f = PROJECT / "_hidden.md"
    f.write_text("## X\n", encoding="utf-8")
    try:
        out_ok(["toc", str(f)], "", "- [X](#x)\n")
    finally:
        f.unlink()


# ---- stats ----------------------------------------------------------------
@check("stats: words, sentences, minutes")
def _():
    out_ok(["stats"], "Hello there. How are you? Fine!", "words=6 sentences=3 reading_minutes=1\n")


@check("stats: punctuation-only tokens are not words; '...' counts once")
def _():
    out_ok(["stats"], "Wait... what - now", "words=3 sentences=1 reading_minutes=1\n")


@check("stats: no terminal punctuation -> 1 sentence")
def _():
    out_ok(["stats"], "no punctuation here", "words=3 sentences=1 reading_minutes=1\n")


@check("stats: empty -> zeros")
def _():
    out_ok(["stats"], "", "words=0 sentences=0 reading_minutes=0\n")


@check("stats: 401 words -> 3 minutes; '3.14' is not a sentence end")
def _():
    out_ok(["stats"], "Pi is 3.14 ok. " + "w " * 397, "words=401 sentences=1 reading_minutes=3\n")


# ---- CLI-wide -------------------------------------------------------------
@check("unknown command -> exit 2 + stderr")
def _():
    p = run(["frobnicate"])
    assert p.returncode == 2 and p.stderr.strip(), (p.returncode, p.stderr)


@check("missing file -> exit 2, names file, empty stdout")
def _():
    p = run(["stats", "nope_404.txt"])
    assert p.returncode == 2 and b"nope_404.txt" in p.stderr and p.stdout == b"", (p.returncode, p.stdout)


@check("README documents commands and options")
def _():
    text = (PROJECT / "README.md").read_text(encoding="utf-8")
    for needle in ("slug", "toc", "stats", "--sep", "--max-len"):
        assert needle in text, f"README lacks {needle}"


@check("project tests pass with unittest")
def _():
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=PROJECT, capture_output=True, timeout=120)
    assert p.returncode == 0, p.stderr.decode()[-300:]
    assert b"Ran 0 tests" not in p.stderr


def main():
    passed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            print(f"FAIL  {name}: {msg}")
    print(f"\nSCORE {passed}/{len(CHECKS)}")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
