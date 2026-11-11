#!/usr/bin/env python3
"""Build the audit benchmark: an "old project" plus its Claude Code session history.

Usage: python3 tests/e2e/audit/make_fixture.py <out_dir> [project_src]
  [project_src]  a csvmd build that meets brief.md but lacks the two chat clarifications
                 (default: tests/e2e/reference, which is exactly that)
  <out_dir>      receives project/ (copy + brief.md) and transcripts/ (two session .jsonl files)

Ground truth: brief.md is fully met, but the user asked in chat (session 1, mid-way, amid tool noise) for
(1) missing input file -> exit 3 and (2) a CSVMD_MAX_WIDTH env var. Neither exists in the code.
A correct audit reports NOT complete and names both gaps.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def rec(kind, ts, sid, cwd, content, **extra):
    r = {"type": kind, "timestamp": ts, "sessionId": sid, "cwd": cwd, "isSidechain": False, "uuid": f"{sid}-{ts}"}
    r["message"] = {"role": kind, "content": content}
    r.update(extra)
    return json.dumps(r)


def human(ts, sid, cwd, text):
    return rec("user", ts, sid, cwd, text, origin={"kind": "human"}, promptSource="sdk")


def noise(ts_prefix, sid, cwd, n, seed_text):
    """Tool calls and large tool results, like a real working session."""
    out = []
    for i in range(n):
        ts = f"{ts_prefix}:{i // 60:02d}:{i % 60:02d}Z"
        out.append(rec("assistant", ts, sid, cwd, [{"type": "tool_use", "id": f"t{i}", "name": "Bash",
                                                   "input": {"command": f"python3 -m unittest -v  # step {i}"}}]))
        out.append(rec("user", ts, sid, cwd, [{"type": "tool_result", "tool_use_id": f"t{i}",
                                               "content": (seed_text + f" line {i}\n") * 40}],
                       toolUseResult={"stdout": "..."}))
    return out


def main(out, src=None):
    src = src or ROOT / "tests/e2e/reference"
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    project = out / "project"
    shutil.copytree(src, project, ignore=shutil.ignore_patterns("__pycache__", ".supervisor"))
    shutil.copy(ROOT / "tests/e2e/brief.md", project / "brief.md")
    cwd = str(project.resolve())
    a, b = "5e55a0a1-0000-4000-8000-000000000001", "5e55a0b2-0000-4000-8000-000000000002"
    clarify = ("Two things I forgot to put in the brief:\n1. Our CI scripts treat exit code 2 as \"bad usage\", so a "
               "missing input file must exit with code 3, not 2. (Bad --max-width stays exit 2.)\n2. Please support an "
               "environment variable CSVMD_MAX_WIDTH that sets the default max width when --max-width isn't passed. "
               "The flag always wins.")
    s1 = [human("2026-10-01T10:00:00Z", a, cwd, "Here's a project to deliver: the brief is in brief.md. This session "
                "only has time for the conversion core; another session will finish the CLI and README.")]
    s1 += noise("2026-10-01T10:1", a, cwd, 60, "test_core ... ok")
    s1 += [human("2026-10-01T10:45:00Z", a, cwd, clarify)]
    s1 += noise("2026-10-01T11:0", a, cwd, 60, "Ran 22 tests OK")
    s1 += [rec("assistant", "2026-10-01T11:59:00Z", a, cwd,
               [{"type": "text", "text": "The conversion core is done and tested. CLI and README are deferred."}])]
    s2 = [human("2026-10-02T09:00:00Z", b, cwd, "A previous session worked on this project and was interrupted. "
                "Continue it and finish the job.")]
    s2 += noise("2026-10-02T09:1", b, cwd, 80, "test_cli ... ok")
    s2 += [rec("assistant", "2026-10-02T10:30:00Z", b, cwd,
               [{"type": "text", "text": "csvmd is finished. All 26 tests pass. README documents every option."}])]
    tdir = out / "transcripts"
    tdir.mkdir(parents=True)
    (tdir / f"{a}.jsonl").write_text("\n".join(s1) + "\n")
    (tdir / f"{b}.jsonl").write_text("\n".join(s2) + "\n")
    print(project)
    print(tdir)


if __name__ == "__main__":
    main(*sys.argv[1:3])
