#!/usr/bin/env python3
"""Structural lint for every skill under skills/.

Checks: frontmatter present; `name` uses only [a-z0-9-] and matches the folder;
`description` starts with "Use when", is third person, under 1024 chars total;
every relative path referenced in backticks (templates/, references/, scripts/)
exists; SKILL.md stays within the word budget.

Run: python3 tests/validate_skill.py   (exit 1 on any problem)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORD_BUDGET = 1500
REF = re.compile(r"`((?:templates|references|scripts)/[\w./-]+)`")


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def check_skill(skill_dir):
    problems = []
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    fm = frontmatter(text)
    if fm is None:
        return [f"{skill_md}: missing YAML frontmatter"]
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not re.fullmatch(r"[a-z0-9-]+", name):
        problems.append(f"name {name!r} must be lowercase letters, digits, hyphens")
    if name != skill_dir.name:
        problems.append(f"name {name!r} must match folder {skill_dir.name!r}")
    if not desc.startswith("Use when"):
        problems.append("description must start with 'Use when'")
    if re.search(r"\b(I|my|we)\b", desc):
        problems.append("description must be third person")
    if len(name) + len(desc) > 1024:
        problems.append(f"frontmatter too long ({len(name) + len(desc)} > 1024)")
    for rel in sorted(set(REF.findall(text))):
        if not (skill_dir / rel).exists():
            problems.append(f"referenced file missing: {rel}")
    words = len(text.split())
    if words > WORD_BUDGET:
        problems.append(f"SKILL.md has {words} words (budget {WORD_BUDGET})")
    for md in list(skill_dir.glob("references/*.md")) + list(skill_dir.glob("templates/*.md")):
        for rel in set(REF.findall(md.read_text(encoding="utf-8"))):
            if not (skill_dir / rel).exists():
                problems.append(f"{md.relative_to(skill_dir)} references missing {rel}")
    return [f"{skill_dir.name}: {p}" for p in problems]


def main():
    skills = [p.parent for p in sorted((ROOT / "skills").glob("*/SKILL.md"))]
    if not skills:
        print("no skills found")
        return 1
    problems = [p for s in skills for p in check_skill(s)]
    for p in problems:
        print(f"FAIL {p}")
    for s in skills:
        print(f"{'ok  ' if not any(p.startswith(s.name) for p in problems) else 'bad '} {s.name} "
              f"({len((s / 'SKILL.md').read_text().split())} words)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
