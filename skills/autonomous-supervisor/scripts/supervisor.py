#!/usr/bin/env python3
"""supervisor.py - durable project memory and guard rails for a supervising agent.

Zero dependencies (Python 3.8+ stdlib). State lives in `.supervisor/state.json`
(override with SUPERVISOR_DIR) and is re-rendered to `.supervisor/MEMORY.md`
after every write, so any agent - or a human - can read the current truth.

Exit codes
  0   ok / VERIFIED COMPLETE
  1   usage or input error
  2   evidence, reason or recommended default missing (claims and questions must carry one)
  3   guard tripped (dependency, parallel limit, file overlap, retry limit)
  4   read-only shell: the step is valid but was not saved - append the printed line to journal.jsonl
  5   harvest/sessions: no session transcripts found for this project
  10  gate: PARTIALLY COMPLETE
  20  gate: BLOCKED

Run `supervisor.py --help` or `supervisor.py <command> --help` for details.
"""
import argparse
import contextlib
import datetime as _dt
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # POSIX advisory lock so concurrent agents don't clobber the state file
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

SCHEMA_VERSION = 1
TASK_STATES = ("pending", "running", "blocked", "done", "verified", "dropped")
DEFAULT_MAX_STRATEGIES = 3
SELF_OWNERS = {"self", "supervisor", "lead"}  # owners that are not delegated agents
OPEN_TASK_STATES = ("pending", "running", "blocked", "done")
# The only reasons a supervisor may stop work to wait for the owner. Everything else it decides and reports.
BLOCK_REASONS = {
    "spend": "money or paid usage beyond an approved ceiling",
    "irreversible": "a destructive or irreversible action (delete, publish, merge, send)",
    "access": "a key, account or machine the supervisor cannot obtain itself",
    "goal": "a change to the goal or agreed scope itself",
}
DEP_MET = ("verified", "dropped")  # a dropped dependency was descoped on purpose: it must not deadlock its dependents
SUMMARY_MARK = "This session is being continued from a previous conversation"
EXIT_USAGE, EXIT_EVIDENCE, EXIT_GUARD, EXIT_UNWRITABLE, EXIT_NO_SOURCES, EXIT_PARTIAL, EXIT_BLOCKED = 1, 2, 3, 4, 5, 10, 20


class CliError(Exception):
    def __init__(self, message, code=EXIT_USAGE):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def state_dir():
    return Path(os.environ.get("SUPERVISOR_DIR", ".supervisor"))


# Journal mode. Some hosts run shell commands in a sandbox that cannot write the project (the agent's file tool
# still can). There the CLI cannot save, so each change is handed back as one line for the agent to append to
# .supervisor/journal.jsonl. Every later command replays the journal over state.json, so guards, `resume` and
# `gate` keep working on the true state. The first command in a writable shell folds the journal back in.
_REPLAY = None   # {"state": ...} while a journal line is being re-applied in memory
_CLOCK = None    # the recorded time of the line being replayed
_PRINTS = None   # fingerprints recorded with the line being replayed (files may have changed since)
_REC = None      # other results recorded with the line: a check's exit and output, accepted guard findings


class ReadOnlyState(Exception):
    """The change is valid but could not be saved: the caller hands it to the agent as a journal line."""


def now():
    return _CLOCK or _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def one_line(text):
    """Collapse whitespace so user text can't break MEMORY.md structure."""
    return " ".join(str(text).split())


@contextlib.contextmanager
def locked(directory):
    handle = None
    if _REPLAY is None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            handle = open(directory / ".lock", "a+")
            if fcntl:
                fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError:  # read-only shell: no lock is possible, and no other writer can get in either
            handle = None
    try:
        yield
    finally:
        if handle is not None:
            if fcntl:
                fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()


def journal_lines(directory):
    path = directory / "journal.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
            if isinstance(rec, dict) and isinstance(rec.get("argv"), list):
                out.append(rec)
        except json.JSONDecodeError:
            continue
    return out


def replay(directory, state):
    """Re-apply journal lines not yet folded into state.json, in memory. An invalid line changes nothing."""
    global _REPLAY, _CLOCK, _PRINTS, _REC
    lines = journal_lines(directory)
    for rec in lines[(state or {}).get("journal_folded", 0):]:
        _REPLAY, _CLOCK, _PRINTS, _REC = {"state": state}, rec.get("at"), rec.get("fingerprint"), rec.get("recorded") or {}
        try:
            with contextlib.redirect_stdout(None), contextlib.redirect_stderr(None):
                args = build_parser().parse_args([str(a) for a in rec["argv"]])
                args.fn(args, directory)
        except (CliError, SystemExit, KeyError, AssertionError):
            pass
        finally:
            state, _REPLAY, _CLOCK, _PRINTS, _REC = _REPLAY["state"], None, None, None, None
    return state, len(lines)


def load(directory):
    if _REPLAY is not None:
        if _REPLAY["state"] is None:
            raise CliError("no project yet")
        return _REPLAY["state"]
    path = directory / "state.json"
    state = None
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CliError(f"{path} is corrupt ({exc}); restore it from git") from exc
    state, total = replay(directory, state)
    if state is None:
        raise CliError(f"no project at {directory}/ - run `supervisor.py init --objective ...` first")
    state["_journal_total"] = total
    return state


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def save(directory, state):
    global _REPLAY
    state["updated"] = now()
    state["cli"] = str(Path(__file__).resolve())  # lets a fresh agent find the CLI from the memory alone
    if _REPLAY is not None:
        _REPLAY["state"] = state
        return
    total = state.pop("_journal_total", 0)
    journal = directory / "journal.jsonl"
    try:
        if os.environ.get("SUPERVISOR_READONLY"):  # treat the shell as read-only (tests; hosts that discard writes)
            raise OSError(30, "Read-only file system")
        directory.mkdir(parents=True, exist_ok=True)
        if total:
            state["journal_folded"] = total       # these journal lines are now part of state.json
        atomic_write(directory / "state.json", json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        atomic_write(directory / "MEMORY.md", render(state))
        if not (directory / ".gitignore").exists():  # memory is committed; the lock and the raw harvest are not
            atomic_write(directory / ".gitignore", ".lock\nharvest.md\n")
        if total:
            journal.unlink()
            state.pop("journal_folded", None)
            atomic_write(directory / "state.json", json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise ReadOnlyState(str(exc.strerror or exc)) from exc


def next_id(state, prefix, bucket):
    state["counters"][prefix] = state["counters"].get(prefix, 0) + 1
    new = f"{prefix}{state['counters'][prefix]}"
    assert new not in state.setdefault(bucket, {})  # setdefault: buckets added after a project was created
    return new


def get(state, bucket, item_id):
    item_id = item_id.upper()
    if item_id not in state.setdefault(bucket, {}):
        raise CliError(f"unknown id {item_id}")
    return item_id, state[bucket][item_id]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _task_line(tid, task):
    bits = [f"**{tid}** {task['title']} - `{task['status']}`"]
    if task.get("owner"):
        bits.append(f"owner: {task['owner']}")
    if task.get("depends"):
        bits.append("after: " + ",".join(task["depends"]))
    if task.get("criteria"):
        bits.append("serves: " + ",".join(task["criteria"]))
    if task.get("files"):
        bits.append("files: " + ", ".join(f"`{f}`" for f in task["files"]))
    if task.get("attempts"):
        bits.append(f"attempts: {len(task['attempts'])}")
    if task["status"] == "running" and task.get("started"):
        bits.append(f"running since {task['started']}")
    line = "- " + " | ".join(bits)
    if task.get("strategy"):
        line += f"\n  - strategy: {task['strategy']}"
    if task.get("evidence"):
        line += f"\n  - evidence: {task['evidence']}"
    if task.get("note"):
        line += f"\n  - note: {task['note']}"
    return line


def open_questions(state):
    return {q: x for q, x in state.get("questions", {}).items() if x["status"] == "open"}


def _question_line(qid, q):
    blocks = (f" | blocks: {','.join(q['blocks'])}" + (f" ({q['because']})" if q.get("because") else "")
              if q.get("blocks") else " | nothing blocked: proceeding on the default")
    return f"- **{qid}** {q['text']} - recommended default: {q['default']}{blocks}"


def milestone_progress(state):
    """[(id, title, verified, total, complete)] over each milestone's non-dropped criteria."""
    rows = []
    for mid, m in state.get("milestones", {}).items():
        live = [c for c in m["criteria"] if state["criteria"][c]["status"] != "dropped"]
        ok = [c for c in live if state["criteria"][c]["status"] == "verified"]
        rows.append((mid, m["title"], len(ok), len(live), bool(live) and len(ok) == len(live)))
    return rows


def _milestone_lines(state):
    lines, current_marked = [], False
    for mid, title, ok, total, complete in milestone_progress(state):
        mark = ""
        if not complete and not current_marked:
            mark, current_marked = "  <- current mini-goal", True
        lines.append(f"- **{mid}** {title} - {ok}/{total} criteria verified ({', '.join(state['milestones'][mid]['criteria']) or 'no criteria yet'}){mark}")
    return lines


def render(state):
    out = [
        "# Project Memory",
        "",
        f"_Updated {state['updated']} - generated by supervisor.py; edit via the CLI, not by hand._",
        "",
        "> **Resuming this project?** FIRST load the `autonomous-supervisor` skill (Skill tool): its rules are not "
        "in this file, and the CLI alone does not give them to you. Then run "
        "`python3 <skill directory>/scripts/supervisor.py resume` before doing anything else "
        f"(on the machine that last wrote this file the CLI was at `{state.get('cli') or 'supervisor.py'}`; "
        "on another machine use the skill's own copy). "
        "Verified work and recorded decisions below are binding. If the CLI cannot write (exit 4), append the "
        "line it prints to `.supervisor/journal.jsonl` with your file tool; a journal next to this file holds "
        "steps newer than this page (`resume` reads both).",
        "",
        f"**Objective:** {state['objective']}",
        "",
        f"**Budget:** max parallel {state['budget']['max_parallel']} | "
        f"max attempts per strategy {state['budget']['max_attempts']}",
        "",
        f"**Effort:** {metrics(state)}",
        "",
        "## Acceptance criteria",
    ]
    for cid, c in state["criteria"].items():
        ev = f" - evidence: {c['evidence']}" if c.get("evidence") else ""
        ev += f" - reason: {c['reason']}" if c.get("reason") else ""
        src = f" [{c['source']}]" if c.get("source") else ""
        out.append(f"- **{cid}**{src} {c['text']} - `{c['status']}`{ev}")
    if not state["criteria"]:
        out.append("- _none yet_")
    if state.get("milestones"):
        out += ["", "## Milestones (mini-goals, in order)", *_milestone_lines(state)]
    if open_questions(state):
        out += ["", "## Waiting on the owner", *[_question_line(q, x) for q, x in open_questions(state).items()]]
    out += ["", "## Tasks"]
    out += [_task_line(t, task) for t, task in state["tasks"].items()] or ["- _none yet_"]
    out += ["", "## Decisions"]
    out += [f"- **{d}** {x['text']} - why: {x['why']}" for d, x in state["decisions"].items()] or ["- _none_"]
    out += ["", "## Risks"]
    out += [f"- **{r}** {x['text']}" for r, x in state["risks"].items()] or ["- _none_"]
    out += ["", "## Next actions"]
    out += [f"{i}. {a}" for i, a in enumerate(state["next"], 1)] or ["- _none_"]
    out += ["", "## Log"]
    out += [f"- {e['at']} {e['text']}" for e in state["log"][-20:]] or ["- _empty_"]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def clean_pattern(pattern, strict=True):
    """One spelling per path: `./src//a.py` and `src/a.py` are the same file to the overlap guard."""
    raw = pattern.strip().replace("\\", "/")
    is_dir = raw.endswith("/")
    cleaned = posixpath.normpath(raw) if raw else ""
    outside = raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or cleaned == ".." or cleaned.startswith("../")
    if strict and (outside or cleaned in ("", ".")):
        raise CliError(f"--files {pattern!r}: own specific files, globs or directories given relative to the project "
                       "root (not absolute paths, not paths outside it, not the whole project)")
    return cleaned + ("/" if is_dir and cleaned not in ("", ".") else "")


def _norm(pattern):
    pattern = clean_pattern(pattern, strict=False)
    return pattern.rstrip("/") + ("/**" if pattern.endswith("/") else "")


def patterns_overlap(a, b):
    """Heuristic: two ownership patterns overlap if either matches the other
    or one is a directory prefix of the other."""
    a, b = _norm(a), _norm(b)
    if a == b or fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    a_root, b_root = a.split("*")[0], b.split("*")[0]
    return bool(a_root and b_root) and (a_root.startswith(b_root) or b_root.startswith(a_root)) and (
        a_root.endswith("/") or b_root.endswith("/")
    )


def project_root(directory):
    return directory.resolve().parent


def owned_files(root, patterns):
    """Expand ownership patterns (globs or directories) to existing files, relative to root."""
    found = set()
    for pattern in patterns:
        target = root / pattern
        if pattern.endswith("/") or target.is_dir():
            matches = target.rglob("*")
        else:
            try:
                matches = list(root.glob(pattern))
            except (NotImplementedError, ValueError):  # absolute or empty pattern in an older state file
                continue
        for path in matches:
            if path.is_file() and "__pycache__" not in path.parts and ".supervisor" not in path.parts:
                found.add(path.relative_to(root).as_posix())
    return sorted(found)


def fingerprint(root, patterns):
    if _PRINTS is not None:  # replaying: the fingerprint taken when the step was really done
        return dict(_PRINTS)
    return {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()[:16] for rel in owned_files(root, patterns)}


def drift(root, task):
    """Files added, removed or changed since the task was verified (empty if not tracked)."""
    before = task.get("fingerprint")
    if task["status"] != "verified" or before is None:
        return []
    after = fingerprint(root, task.get("files", []))
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def run_check(command, root, timeout=600):
    """Run a verification command in the project and report what happened. This is the difference between
    "the agent says it passes" and "it passed when the tool ran it"."""
    if _REC is not None and "ran" in _REC:  # replaying a journal line: the result recorded when it really ran
        return dict(_REC["ran"])
    started = _dt.datetime.now()
    try:
        proc = subprocess.run(command, shell=True, cwd=str(root), capture_output=True, text=True, timeout=timeout,
                              errors="replace")
        code, text = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code, text = 124, f"timed out after {timeout}s\n" + str(exc.stdout or "")[-400:]
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return {"exit": code, "seconds": round((_dt.datetime.now() - started).total_seconds(), 1),
            "tail": redact(one_line(" | ".join(lines[-2:])))[:300]}


# The quality-bar guard. An agent that meets a red check tends to take the cheapest road to green: silence the
# checker, skip or delete the test, strip the assertion, leave a stub. These are visible in the diff. The five
# moves and the diff-scoped approach follow "constraint-driven-development" in addyosmani/agent-skills (MIT).
GUARD_SUPPRESS = re.compile(r"@ts-ignore|@ts-nocheck|eslint-disable|biome-ignore|#\s*noqa|#\s*type:\s*ignore|"
                            r"#\s*pragma:\s*no cover|istanbul ignore|nosemgrep|gitleaks:allow|Stryker disable|"
                            r"@SuppressWarnings|#\[allow\(|//\s*nolint")
GUARD_STUB = re.compile(r"[Nn]ot ?[Ii]mplemented|catch\s*(\(\w*\))?\s*\{\s*\}|except[^:]*:\s*pass\b|\bTODO\b|\bFIXME\b")
GUARD_SKIP = re.compile(r"\.(skip|todo|only)\b|\bxit\(|\bxdescribe\(|@pytest\.mark\.(skip|xfail)|@unittest\.skip|"
                        r"\bt\.Skip\(|@Disabled|@Ignore\b|\bskipTest\(")
GUARD_ASSERT = re.compile(r"\b(expect|assert\w*|should)\b")
GUARD_TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.|_test\.|(^|/)test_[^/]*$")
GUARD_PROSE = re.compile(r"\.(md|txt|rst|adoc)$")


def git_out(root, *argv):
    proc = subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True, errors="replace")
    return proc.stdout if proc.returncode in (0, 1) and (proc.returncode == 0 or argv[0] == "diff") else None


def guard_findings(root, base):
    """[(rule, file, text)] for every bar-lowering move between `base` and the working tree, or None when the
    guard cannot run (not a repository, unknown base). None must never read as clean."""
    diff = git_out(root, "diff", "--unified=0", base, "--")
    untracked = git_out(root, "ls-files", "--others", "--exclude-standard")
    if diff is None or untracked is None:
        return None
    added, removed, deleted = [], [], []
    current, old, header = "", "", False
    for line in diff.splitlines():
        if line.startswith("diff "):
            header = True
        elif line.startswith("@@"):
            header = False
        elif header:
            if line.startswith("--- "):
                old = re.sub(r"^[ab]/", "", line[4:])
            elif line.startswith("+++ "):
                new = re.sub(r"^[ab]/", "", line[4:])
                current = old if new == "/dev/null" else new
                if new == "/dev/null":
                    deleted.append(current)
        elif line.startswith("+"):
            added.append((current, line[1:]))
        elif line.startswith("-"):
            removed.append((current, line[1:]))
    for name in filter(None, untracked.splitlines()):
        path = Path(root) / name
        with contextlib.suppress(OSError, UnicodeDecodeError):
            if path.is_file() and path.stat().st_size < 1_000_000:
                added += [(name, text) for text in path.read_text(encoding="utf-8").splitlines()]
    skip = lambda f: f.startswith(".supervisor/") or GUARD_PROSE.search(f)  # noqa: E731
    found = []
    for f, text in added:
        if skip(f):
            continue
        if GUARD_SUPPRESS.search(text):
            found.append(("checker silenced", f, text))
        if GUARD_STUB.search(text):
            found.append(("unfinished work", f, text))
        if GUARD_TEST_FILE.search(f) and GUARD_SKIP.search(text):
            found.append(("test skipped", f, text))
    found += [("test file deleted", f, "file deleted") for f in deleted if GUARD_TEST_FILE.search(f)]
    for f, text in removed:
        if GUARD_TEST_FILE.search(f) and f not in deleted and GUARD_ASSERT.search(text) and not skip(f):
            # an assertion that was only edited (the same file adds one back) is not a removed assertion
            if not any(g == f and GUARD_ASSERT.search(t) for g, t in added):
                found.append(("assertion removed", f, text))
    seen, out = set(), []
    for rule, f, text in found:
        key = (rule, f, redact(one_line(text))[:120])
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def guard_key(finding):
    return " | ".join(finding)


def open_guard_findings(state, root):
    """(findings not yet accepted, or None if the guard cannot run; the base it used)."""
    base = state.get("base_commit")
    if not base:
        return [], None
    found = guard_findings(root, base)
    if found is None:
        return None, base
    accepted = set(state.get("guard_accepted", []))
    return [f for f in found if guard_key(f) not in accepted], base


def cmd_guard(args, directory):
    with locked(directory):
        state = load(directory)
        root = project_root(directory)
        if args.base:
            state["base_commit"] = args.base
        if not state.get("base_commit"):
            raise CliError("the guard needs a base commit to compare with: this project was not started inside a git "
                           "repository. Pass --base <commit or branch> once.")
        if _REC is not None and "accepted" in _REC:
            found = [tuple(k.split(" | ", 2)) for k in _REC["accepted"]]
        else:
            found, _ = open_guard_findings(state, root)
        if found is None:
            raise CliError(f"the guard could not run (git cannot diff against {state['base_commit']}). "
                           "This is not a clean result.")
        if args.accept:
            if not (args.reason or "").strip():
                raise CliError("`guard --accept` requires --reason: why lowering the bar here is right", EXIT_EVIDENCE)
            keys = [guard_key(f) for f in found]
            args.recorded = {"accepted": keys}
            state.setdefault("guard_accepted", []).extend(k for k in keys if k not in state["guard_accepted"])
            did = next_id(state, "D", "decisions")
            state["decisions"][did] = {"text": f"Accepted {len(keys)} quality-bar finding(s): " + "; ".join(keys)[:400],
                                       "why": one_line(args.reason), "at": now()}
            save(directory, state)
            print(f"{len(keys)} finding(s) accepted, recorded as {did}")
            return
        if args.base:
            save(directory, state)
    if not found:
        print(f"guard: clean against {state['base_commit'][:12]} (no silenced checker, skipped or deleted test, "
              "removed assertion or unfinished stub in the changes)")
        return
    print(f"guard: {len(found)} move(s) that lower the quality bar since {state['base_commit'][:12]}:")
    for rule, f, text in found:
        print(f"- {rule}: {f}: {text}")
    print("Fix each one. If one is right, record why: `guard --accept --reason \"...\"`. The gate refuses while any stand.")
    args.post_exit = EXIT_GUARD


def metrics(state):
    tasks = state["tasks"].values()
    return (f"dispatches: {state.get('dispatches', 0)} | failed attempts: {sum(len(t['attempts']) for t in tasks)}"
            f" | strategy changes: {sum(t.get('strategies', 0) for t in tasks)}")


def guard_start(state, tid, task):
    problems = []
    unmet = [d for d in task.get("depends", []) if state["tasks"][d]["status"] not in DEP_MET]
    if unmet:
        problems.append(f"dependencies not verified: {', '.join(unmet)}")
    running = {k: t for k, t in state["tasks"].items() if t["status"] == "running" and k != tid}
    # The limit caps delegated agents; the supervisor's own work never takes a slot.
    delegated = [k for k, t in running.items() if (t.get("owner") or "").lower() not in SELF_OWNERS]
    limit = state["budget"]["max_parallel"]
    if (task.get("owner") or "").lower() not in SELF_OWNERS and len(delegated) >= limit:
        problems.append(f"parallel limit {limit} reached (delegated running: {', '.join(delegated)})")
    for other_id, other in running.items():
        clashes = [
            f"{mine} ~ {theirs}"
            for mine in task.get("files", [])
            for theirs in other.get("files", [])
            if patterns_overlap(mine, theirs)
        ]
        if clashes:
            problems.append(f"file ownership overlaps running {other_id}: {'; '.join(clashes)}")
    return problems


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_init(args, directory):
    if _REPLAY is not None and _REPLAY["state"] is not None:
        raise CliError("already initialised")
    if _REPLAY is None:
        existing = None
        with contextlib.suppress(CliError):
            existing = load(directory)
        if existing is not None:
            raise CliError(f"{directory}/state.json already exists - use `resume` instead of re-initialising")
    state = {
        "schema": SCHEMA_VERSION,
        "objective": one_line(args.objective),
        "created": now(),
        "updated": now(),
        "budget": {"max_parallel": args.max_parallel, "max_attempts": args.max_attempts,
                   "max_strategies": args.max_strategies},
        "counters": {},
        "criteria": {},
        "tasks": {},
        "decisions": {},
        "risks": {},
        "next": [],
        "log": [{"at": now(), "text": "project initialised"}],
    }
    base = (_REC or {}).get("base") if _REC is not None else (git_out(project_root(directory), "rev-parse", "HEAD") or "").strip()
    if base:
        state["base_commit"] = base  # what the quality-bar guard compares the work with
        args.recorded = {"base": base}
    with locked(directory):
        save(directory, state)
    print(f"initialised {directory}/ (state.json + MEMORY.md)")


def cmd_criterion(args, directory):
    with locked(directory):
        state = load(directory)
        msgs = []
        if args.action == "add":
            milestone = get(state, "milestones", args.milestone)[1] if args.milestone else None
            for text in args.items:
                cid = next_id(state, "AC", "criteria")
                state["criteria"][cid] = {"text": one_line(text), "status": "pending"}
                if args.source:
                    state["criteria"][cid]["source"] = one_line(args.source)
                if milestone is not None:
                    milestone["criteria"].append(cid)
                msgs.append(f"{cid} added")
        else:
            targets = [get(state, "criteria", item) for item in args.items]  # validate all first
            if args.action in ("drop", "unverifiable"):
                status = "dropped" if args.action == "drop" else "unverifiable"
                if not (args.reason or "").strip():
                    why = "why this is out of scope" if status == "dropped" else "what is needed to check it"
                    raise CliError(f"`{args.action}` requires --reason ({why})", EXIT_EVIDENCE)
                for cid, crit in targets:
                    crit.update(status=status, reason=one_line(args.reason), at=now())
                    state["log"].append({"at": now(), "text": f"{cid} {status}: {crit['reason']}"})
                    msgs.append(f"{cid} {status}")
                save(directory, state)
                print("\n".join(msgs))
                return
            ran = None
            if args.run:
                if args.action != "verify":
                    raise CliError("--run belongs to `criterion verify`: the tool runs the check and records what it saw")
                ran = run_check(args.run, project_root(directory), args.timeout)
                args.recorded = {"ran": ran}
            elif not (args.evidence or "").strip():
                raise CliError(f"`{args.action}` requires --run \"<command>\" (the tool runs it) or --evidence "
                               "(command + observed result)", EXIT_EVIDENCE)
            for cid, crit in targets:
                if ran:
                    crit["status"] = "verified" if ran["exit"] == 0 else "failed"
                    crit["evidence"] = (f"tool ran `{one_line(args.run)}` -> exit {ran['exit']} in {ran['seconds']}s: "
                                        f"{ran['tail']}" + (f" ({one_line(args.evidence)})" if args.evidence else ""))
                    crit["check"] = one_line(args.run)
                else:
                    crit["status"] = "verified" if args.action == "verify" else "failed"
                    crit["evidence"] = one_line(args.evidence)
                    crit.pop("check", None)
                crit["at"] = now()
                state["log"].append({"at": now(), "text": f"{cid} {crit['status']}: {crit['evidence']}"})
                msgs.append(f"{cid} {crit['status']}" + (f": {crit['evidence']}" if ran else ""))
            if ran and ran["exit"] != 0:
                args.post_exit = EXIT_GUARD
        save(directory, state)
    print("\n".join(msgs))


def cmd_task_add(args, directory):
    with locked(directory):
        state = load(directory)
        depends = [d.strip().upper() for d in (args.depends or "").split(",") if d.strip()]
        criteria = [c.strip().upper() for c in (args.criteria or "").split(",") if c.strip()]
        for d in depends:
            if d not in state["tasks"]:
                raise CliError(f"dependency {d} does not exist")
        for c in criteria:
            if c not in state["criteria"]:
                raise CliError(f"criterion {c} does not exist")
        tid = next_id(state, "T", "tasks")
        state["tasks"][tid] = {
            "title": one_line(args.title),
            "status": "pending",
            "owner": one_line(args.owner) if args.owner else None,
            "depends": depends,
            "criteria": criteria,
            "files": [clean_pattern(f) for f in (args.files or "").split(",") if f.strip()],
            "attempts": [],
            "strategy": None,
        }
        save(directory, state)
    print(f"{tid} added")


def cmd_task_set(args, directory):
    with locked(directory):
        state = load(directory)
        tid, task = get(state, "tasks", args.id)
        if args.status == "verified" and not (args.evidence or "").strip():
            raise CliError(f"{tid}: `verified` requires --evidence (command + observed result)", EXIT_EVIDENCE)
        if args.owner:
            task["owner"] = one_line(args.owner)
        if args.status == "running" and not args.force:
            problems = guard_start(state, tid, task)
            if problems:
                raise CliError(f"GUARD {tid}: " + " | ".join(problems) + " (use --force to override deliberately)", EXIT_GUARD)
        if args.status == "running" and task["status"] != "running":
            task["started"] = now()
            state["dispatches"] = state.get("dispatches", 0) + 1
        if args.status == "verified":
            task["fingerprint"] = fingerprint(project_root(directory), task.get("files", []))
            args.recorded_fingerprint = task["fingerprint"]
        task["status"] = args.status
        if args.owner:
            task["owner"] = one_line(args.owner)
        if args.evidence:
            task["evidence"] = one_line(args.evidence)
        if args.note:
            task["note"] = one_line(args.note)
        state["log"].append({"at": now(), "text": f"{tid} -> {args.status}" + (f" ({one_line(args.note)})" if args.note else "")})
        save(directory, state)
    print(f"{tid} {args.status}")
    if args.status == "dropped":
        dependents = [k for k, t in state["tasks"].items() if tid in t.get("depends", []) and t["status"] in OPEN_TASK_STATES]
        if dependents:
            print(f"note: {', '.join(dependents)} depended on {tid}; they are no longer held back by it. "
                  "Check they still make sense without it.")


def cmd_task_attempt(args, directory):
    with locked(directory):
        state = load(directory)
        tid, task = get(state, "tasks", args.id)
        task["attempts"].append({"at": now(), "note": one_line(args.note), "strategy": task.get("strategy")})
        same = [a for a in task["attempts"] if a.get("strategy") == task.get("strategy")]
        limit = state["budget"]["max_attempts"]
        state["log"].append({"at": now(), "text": f"{tid} attempt {len(same)}/{limit}: {one_line(args.note)}"})
        save(directory, state)
    if len(same) >= limit:
        raise CliError(
            f"RETRY LIMIT {tid}: {len(same)} failed attempts with the current strategy. "
            "Do not retry the same approach. Gather new evidence, then record a different approach with "
            f"`task strategy {tid} \"...\"`, or escalate.",
            EXIT_GUARD,
        )
    print(f"{tid} attempt {len(same)}/{limit} recorded")


def cmd_task_strategy(args, directory):
    with locked(directory):
        state = load(directory)
        tid, task = get(state, "tasks", args.id)
        cap = state["budget"].get("max_strategies", DEFAULT_MAX_STRATEGIES)
        if task.get("strategies", 0) >= cap:
            raise CliError(
                f"STRATEGY LIMIT {tid}: {cap} strategies already tried. Escalate with the evidence log "
                "(templates/escalation.md) instead of trying another approach.", EXIT_GUARD)
        task["strategies"] = task.get("strategies", 0) + 1
        task["strategy"] = one_line(args.text)
        state["log"].append({"at": now(), "text": f"{tid} new strategy: {task['strategy']}"})
        save(directory, state)
    print(f"{tid} strategy set; retry budget reset")


def cmd_simple_add(bucket, prefix):
    def handler(args, directory):
        with locked(directory):
            state = load(directory)
            item_id = next_id(state, prefix, bucket)
            entry = {"text": one_line(args.text), "at": now()}
            if bucket == "decisions":
                entry["why"] = one_line(args.why)
            state[bucket][item_id] = entry
            save(directory, state)
        print(f"{item_id} recorded")

    return handler


def cmd_milestone(args, directory):
    with locked(directory):
        state = load(directory)
        criteria = [c.strip().upper() for c in (args.criteria or "").split(",") if c.strip()]
        for c in criteria:
            if c not in state["criteria"]:
                raise CliError(f"criterion {c} does not exist")
        mid = next_id(state, "M", "milestones")
        state["milestones"][mid] = {"title": one_line(args.title), "criteria": criteria, "at": now()}
        save(directory, state)
    print(f"{mid} added")


def cmd_ask(args, directory):
    """A question only the owner can answer, with the default the work proceeds on meanwhile."""
    with locked(directory):
        state = load(directory)
        if not args.default.strip():
            raise CliError("`ask` requires --default: the option you recommend and will assume", EXIT_EVIDENCE)
        blocks = [get(state, "tasks", t.strip())[0] for t in (args.blocks or "").split(",") if t.strip()]
        if blocks and not args.because:
            raise CliError(
                "a question may hold work back only for: " + "; ".join(f"`{k}` ({v})" for k, v in BLOCK_REASONS.items())
                + ". Pass --because <one of these>. Anything else is yours to decide: drop --blocks, proceed on the "
                "default, and the gate reports it as an assumption the owner can overrule.", EXIT_GUARD)
        if args.because and not blocks:
            raise CliError("--because explains why tasks must wait: give --blocks too, or drop it")
        qid = next_id(state, "Q", "questions")
        state["questions"][qid] = {"text": one_line(args.text), "default": one_line(args.default), "blocks": blocks,
                                   "status": "open", "at": now()}
        if args.because:
            state["questions"][qid]["because"] = args.because
        for tid in blocks:
            task = state["tasks"][tid]
            if task["status"] in ("verified", "dropped"):
                raise CliError(f"{tid} is already {task['status']}: a question cannot block it")
            waiting = [q for q, x in open_questions(state).items() if tid in x.get("blocks", [])]
            task.update(status="blocked", note=f"waiting on {', '.join(waiting)} (latest: {one_line(args.text)})"
                        if len(waiting) > 1 else f"waiting on {qid}: {one_line(args.text)}")
        state["log"].append({"at": now(), "text": f"{qid} asked: {one_line(args.text)}"})
        save(directory, state)
    print(f"{qid} recorded" + (f"; blocked {', '.join(blocks)}" if blocks else "; nothing blocked: continue on the default"))


def cmd_answer(args, directory):
    with locked(directory):
        state = load(directory)
        qid, q = get(state, "questions", args.id)
        if args.accept == bool(args.text):
            raise CliError("give the owner's answer, or --accept if they took the recommended default (not both)")
        if q["status"] != "open":
            raise CliError(f"{qid} was already answered: {q.get('answer')}. A change of mind is a new `decide`.")
        q.update(status="answered", answer=q["default"] if args.accept else one_line(args.text), answered=now())
        did = next_id(state, "D", "decisions")
        state["decisions"][did] = {"text": f"{q['text']} -> {q['answer']}", "why": f"owner answer to {qid}", "at": now()}
        freed = []
        for tid in q.get("blocks", []):
            task = state["tasks"][tid]
            still = [o for o, x in open_questions(state).items() if tid in x.get("blocks", [])]
            if task["status"] == "blocked" and not still:
                task.update(status="pending", note=f"unblocked by {qid}: {q['answer']}")
                freed.append(tid)
        state["log"].append({"at": now(), "text": f"{qid} answered: {q['answer']}"})
        save(directory, state)
    print(f"{qid} answered, recorded as {did}" + (f"; unblocked {', '.join(freed)}" if freed else ""))


READ_ONLY_COMMANDS = ("status", "resume", "ready", "gate", "sessions", "harvest", "events", "branches", "batch")


def cmd_batch(args, directory):
    """Several updates in one call, all or nothing. In a read-only shell this returns all their journal lines at
    once, so a milestone costs two tool calls instead of two per step."""
    global _REPLAY
    parser = build_parser()
    with locked(directory):
        state = None
        with contextlib.suppress(CliError):
            state = load(directory)
        total = state.pop("_journal_total", 0) if state else len(journal_lines(directory))
        records = []
        for text in args.commands:
            argv = shlex.split(text)
            try:
                with contextlib.redirect_stderr(None):
                    sub = parser.parse_args(argv)
            except SystemExit:
                raise CliError(f"batch: cannot parse `{text}` - nothing was saved") from None
            if sub.command in READ_ONLY_COMMANDS:
                raise CliError(f"batch takes updates only, not `{sub.command}` - nothing was saved")
            _REPLAY = {"state": state}
            try:
                sub.fn(sub, directory)
            except CliError as exc:
                raise CliError(f"batch stopped at `{text}`: {exc} - nothing was saved", exc.code) from exc
            finally:
                state, _REPLAY = _REPLAY["state"], None
            rec = {"at": now(), "argv": argv}
            if getattr(sub, "recorded_fingerprint", None) is not None:
                rec["fingerprint"] = sub.recorded_fingerprint
            if getattr(sub, "recorded", None):
                rec["recorded"] = sub.recorded
            if getattr(sub, "post_exit", 0):
                args.post_exit = sub.post_exit
            records.append(rec)
        args.batch_records = records
        state["_journal_total"] = total
        save(directory, state)


def cmd_next(args, directory):
    with locked(directory):
        state = load(directory)
        if args.clear == bool(args.actions):
            raise CliError("give one or more actions, or --clear (not both)")
        state["next"] = [one_line(a) for a in args.actions]
        save(directory, state)
    print(f"{len(state['next'])} next action(s) set")


def cmd_log(args, directory):
    with locked(directory):
        state = load(directory)
        state["log"].append({"at": now(), "text": one_line(args.text)})
        save(directory, state)
    print("logged")


def cmd_status(args, directory):
    print(render(load(directory)), end="")


def ready_tasks(state):
    return [
        tid
        for tid, t in state["tasks"].items()
        if t["status"] == "pending" and all(state["tasks"][d]["status"] in DEP_MET for d in t["depends"])
    ]


def cmd_ready(args, directory):
    state = load(directory)
    ids = ready_tasks(state)
    if not ids:
        print("no ready tasks")
    for tid in ids:
        print(f"{tid} {state['tasks'][tid]['title']}")


def cmd_resume(args, directory):
    state = load(directory)
    tasks = state["tasks"]

    def section(title, ids):
        lines = [f"## {title}"]
        lines += [_task_line(t, tasks[t]) for t in ids] or ["- none"]
        return lines

    by = lambda *s: [t for t, x in tasks.items() if x["status"] in s]  # noqa: E731
    root = project_root(directory)
    drifted = {t: drift(root, x) for t, x in tasks.items()}
    drifted = {t: files for t, files in drifted.items() if files}
    open_criteria = [c for c, x in state["criteria"].items() if x["status"] not in ("verified", "dropped")]
    out = [
        f"# Resume brief ({state['updated']})",
        "_This brief assumes the `autonomous-supervisor` skill is loaded. If you have not loaded it in this session, "
        "load it now (Skill tool) before acting: the rules for what you may redo, edit and claim are there._",
        f"**Objective:** {state['objective']}",
        f"**Effort so far:** {metrics(state)}",
        "",
        *((["## Waiting on the owner - ask these once, together, with the defaults; meanwhile do everything not blocked",
            *[_question_line(q, x) for q, x in open_questions(state).items()], ""]) if open_questions(state) else []),
        *((["## Milestones (mini-goals, in order)", *_milestone_lines(state), ""]) if state.get("milestones") else []),
        *section("Do not redo - verified and unchanged (leave their files alone: an edit there must be re-verified "
                 "and recorded)", [t for t in by("verified") if t not in drifted]),
        "",
        "## Changed since verification - re-verify before relying on these",
        *([f"- **{t}** {tasks[t]['title']}: {', '.join(files)}" for t, files in drifted.items()] or ["- none"]),
        "",
        *section("In flight - collect reports or check liveness before re-dispatching", by("running")),
        "",
        *section("Reported done - needs verification", by("done")),
        "",
        *section("Blocked", by("blocked")),
        "",
        *section("Ready to start", ready_tasks(state)),
        "",
        "## Open acceptance criteria",
        *([f"- **{c}** {state['criteria'][c]['text']}" for c in open_criteria] or ["- none"]),
        "",
        "## Binding decisions",
        *([f"- **{d}** {x['text']} - why: {x['why']}" for d, x in state["decisions"].items()] or ["- none"]),
        "",
        "## Next actions",
        *([f"{i}. {a}" for i, a in enumerate(state["next"], 1)] or ["- none recorded: derive from sections above"]),
    ]
    movable = ready_tasks(state) + by("running", "done")
    if movable and (by("blocked") or open_questions(state)):
        out += ["", f"## Not a stopping point\n- {', '.join(movable)} are not blocked: keep working. The owner is asked "
                    "once, in one message, never as a reason to pause."]
    manual = directory / "MANUAL.md"
    if manual.exists() and manual.read_text(encoding="utf-8").strip():
        out += ["", "## Manual notes (written by hand when the CLI could not write - reconcile into the CLI now)",
                manual.read_text(encoding="utf-8").strip()]
    print("\n".join(out))


def roadmap_gaps(state):
    """Holes in the plan itself: the gate can only be trusted on a roadmap where everything connects."""
    gaps = []
    criteria, tasks, milestones = state["criteria"], state["tasks"], state.get("milestones", {})
    if milestones:
        grouped = {c for m in milestones.values() for c in m["criteria"]}
        loose = [c for c, x in criteria.items() if c not in grouped and x["status"] != "dropped"]
        if loose:
            gaps.append(f"roadmap gap: {', '.join(loose)} belong to no mini-goal (add them to one, or drop them)")
        empty = [m for m, x in milestones.items() if not x["criteria"]]
        if empty:
            gaps.append(f"roadmap gap: mini-goal {', '.join(empty)} has no criteria, so nothing proves it")
    if tasks and milestones:  # a project planned as mini-goals: every task must lead somewhere
        aimless = [t for t, x in tasks.items() if not x.get("criteria") and x["status"] != "dropped"]
        if aimless:
            gaps.append(f"roadmap gap: {', '.join(aimless)} serve no criterion (link them, or drop them as out of scope)")
    return gaps


def cmd_gate(args, directory):
    state = load(directory)
    tasks, criteria = state["tasks"], state["criteria"]
    scope = None
    if args.milestone:  # judge one mini-goal: its criteria and the tasks that serve them
        scope, milestone = get(state, "milestones", args.milestone)
        criteria = {c: criteria[c] for c in milestone["criteria"]}
        tasks = {t: x for t, x in tasks.items() if set(x.get("criteria", [])) & set(criteria)}
        if not criteria:
            raise CliError(f"{scope} has no criteria - add them with `criterion add ... --milestone {scope}`")
    blocked = [(t, x) for t, x in tasks.items() if x["status"] == "blocked"]
    unverified_criteria = [c for c, x in criteria.items() if x["status"] not in ("verified", "dropped")]
    root = project_root(directory)
    drifted = {t: drift(root, x) for t, x in tasks.items()}
    open_tasks = [t for t, x in tasks.items() if x["status"] in OPEN_TASK_STATES and x["status"] != "blocked"]
    problems = []
    if not criteria:
        problems.append("no acceptance criteria defined - completion cannot be judged")
    tag = lambda c: f" [{criteria[c]['source']}]" if criteria[c].get("source") else ""  # noqa: E731
    problems += [
        f"{c}{tag(c)} could not be verified here (neither passed nor failed): {criteria[c]['text']} - needs: "
        f"{criteria[c].get('reason', '?')}" if criteria[c]["status"] == "unverifiable"
        else f"{c}{tag(c)} not verified ({criteria[c]['status']}): {criteria[c]['text']}"
        for c in unverified_criteria
    ]
    problems += [f"{t} is `{tasks[t]['status']}`, not verified: {tasks[t]['title']}" for t in open_tasks]
    # Recorded next actions mean work is still planned. Either it is out-of-scope
    # follow-up (then `next --clear`) or the criteria don't cover the full scope.
    problems += [f"{t} verified, but files changed since: {', '.join(f)} - re-verify" for t, f in drifted.items() if f]
    if scope is None:
        problems += [f"next action still recorded: {a} (do it, add it as a task, or `next --clear`)" for a in state["next"]]
    label = f"MILESTONE {scope} " if scope else ""
    asked = open_questions(state)
    if args.recheck:  # run every recorded check again now: a check that passed last week proves nothing today
        for c, x in criteria.items():
            if x["status"] == "verified" and x.get("check"):
                ran = run_check(x["check"], root, args.timeout)
                if ran["exit"] != 0:
                    problems.append(f"{c} check fails now: `{x['check']}` -> exit {ran['exit']}: {ran['tail']} "
                                    f"(fix it, then `criterion verify {c} --run \"{x['check']}\"`)")
    if scope is None:
        problems += roadmap_gaps(state)
        lowered, base = open_guard_findings(state, root)
        if lowered is None:
            problems.append(f"the quality-bar guard could not run against {base[:12]} (run `guard` to see why); "
                            "an unchecked diff is not a clean one")
        else:
            problems += [f"quality bar lowered - {rule}: {f}: {text} (fix it, or `guard --accept --reason \"...\"`)"
                         for rule, f, text in lowered]
    # Work that nothing holds back. While any exists, a blocked or partial verdict is not a reason to stop.
    movable = [t for t in ready_tasks(state) if t in tasks] + [t for t, x in tasks.items() if x["status"] in ("running", "done")]
    if blocked:
        print(f"{label}BLOCKED")
        for t, x in blocked:
            print(f"- {t} {x['title']}: {x.get('note') or 'no reason recorded'}")
        for q, x in asked.items():
            if set(x.get("blocks", [])) & {t for t, _ in blocked}:
                print(f"- ask the owner {q}: {x['text']} (recommended: {x['default']})")
        for p in problems:
            print(f"- {p}")
        if movable:
            print(f"NOT A STOPPING POINT: {', '.join(movable)} are not blocked. Continue them; raise the blocked items "
                  "with the owner once, in one message, when this work is done or at a natural report.")
        raise SystemExit(EXIT_BLOCKED)
    if problems:
        print(f"{label}PARTIALLY COMPLETE")
        for p in problems:
            print(f"- {p}")
        raise SystemExit(EXIT_PARTIAL)
    dropped = {c: x for c, x in criteria.items() if x["status"] == "dropped"}
    criteria = {c: x for c, x in criteria.items() if x["status"] != "dropped"}
    if scope:
        print(f"MILESTONE {scope} VERIFIED ({len(criteria)} criteria). This is one mini-goal: "
              "only the project `gate` decides completion.")
    else:
        assumed = f" on {len(asked)} unconfirmed assumption(s), listed below" if asked else ""
        print(f"VERIFIED COMPLETE{assumed} ({len(criteria)} criteria - this verdict covers exactly these; "
              "confirm they span the whole agreed scope)")
    for c, x in criteria.items():
        src = f" [{x['source']}]" if x.get("source") else ""
        print(f"- {c}{src} {x['text']}: {x['evidence']}")
    for c, x in dropped.items():
        print(f"- excluded {c} {x['text']}: {x['reason']}")
    for q, x in ({} if scope else asked).items():
        print(f"- assumed, owner has not answered {q}: {x['text']} -> {x['default']}")
    by_tool = [c for c, x in criteria.items() if x.get("check")]
    print(f"Proof: {len(by_tool)} of {len(criteria)} criteria rest on a check the tool ran itself"
          + (f"; {len(criteria) - len(by_tool)} rest on the agent's own statement "
             f"({', '.join(c for c in criteria if c not in by_tool)})" if len(by_tool) < len(criteria) else "")
          + ("" if args.recheck or not by_tool else ". `gate --recheck` runs them again now"))
    if scope is None:
        done_m = [m for m in milestone_progress(state) if m[4]]
        live_tasks = [t for t in tasks.values() if t["status"] != "dropped"]
        print(f"Roadmap: {len(done_m)}/{len(state.get('milestones', {}))} mini-goals, {len(criteria)}/{len(criteria)} criteria, "
              f"{len(live_tasks)}/{len(live_tasks)} tasks verified; nothing planned is left undone")
    print(f"Effort: {metrics(state)}")


# --------------------------------------------------------------------------- #
# Audit mode: reconstruct requirements from past Claude Code sessions
# --------------------------------------------------------------------------- #
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "private-key"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "anthropic-key"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "api-key"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github-token"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "github-token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws-key"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "slack-token"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"), "bearer-token"),
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|(?:access[_-]?|auth[_-]?)?token)\b(\s*[:=]\s*)\S+"), "credential"),
]
NOISE_PREFIXES = ("<task-notification", "<system-reminder", "Stop hook feedback", "Caveat:", "<local-command",
                  "[Request interrupted", "<command-stdout", "Base directory for this skill",
                  # harness messages seen in real cloud sessions (they carry no origin field):
                  "Your response above was stopped", "Your response above was cut off",
                  "This session is being continued from a previous conversation",
                  "<artifact-content-authored-by-others", "Goal check-in:", "(Re-invocation of /")
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def redact(text):
    for pattern, label in SECRET_PATTERNS:
        if label == "credential":
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED {label}]", text)
        else:
            text = pattern.sub(f"[REDACTED {label}]", text)
    return text


def encode_project(path):
    return "".join(c if c.isalnum() else "-" for c in str(path))


def _first_cwd(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for _, line in zip(range(50), handle):
                try:
                    cwd = json.loads(line).get("cwd")
                except (json.JSONDecodeError, AttributeError):
                    continue
                if cwd:
                    return cwd
    except OSError:
        return None
    return None


def find_transcripts(project, explicit=None):
    """Top-level *.jsonl session files for this project (subagent transcripts live in subfolders)."""
    if explicit:
        folder = Path(explicit).expanduser()
        return sorted(folder.glob("*.jsonl")) if folder.is_dir() else [], [str(folder)]
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    found = {}
    direct = base / encode_project(project)
    for f in direct.glob("*.jsonl") if direct.is_dir() else []:
        found[f.resolve()] = f
    if base.is_dir():  # folder naming differs across versions/platforms: also match on the recorded cwd
        for f in base.glob("*/*.jsonl"):
            if f.resolve() not in found and _first_cwd(f) == str(project):
                found[f.resolve()] = f
    return sorted(found.values()), [str(base)]


def _text_of(content):
    if isinstance(content, str):
        return content, False
    parts, has_tool_result = [], False
    for block in content or []:
        kind = block.get("type") if isinstance(block, dict) else None
        if kind == "text":
            parts.append(block.get("text", ""))
        elif kind == "image":
            parts.append("[image attached]")
        elif kind == "tool_result":
            has_tool_result = True
    return "\n".join(p for p in parts if p), has_tool_result


def _is_human(rec, text):
    if rec.get("toolUseResult") is not None or rec.get("isMeta") or rec.get("isSidechain"):
        return False
    origin = rec.get("origin")
    if isinstance(origin, dict) and origin.get("kind"):
        return origin["kind"] == "human"
    return not text.lstrip().startswith(NOISE_PREFIXES)  # older transcripts carry no origin field


def _is_summary(text):
    """The agent's own summary of everything before a context reset. It lists the user's messages so far:
    the cheapest index of a long session, and a lead like any other claim."""
    return SUMMARY_MARK in text[:1500]


def parse_session(path):
    session = {"id": path.stem, "start": None, "end": None, "prompts": [], "claim": None, "skipped": 0,
               "summaries": []}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                session["skipped"] += 1
                continue
            if not isinstance(rec, dict) or rec.get("type") not in ("user", "assistant"):
                continue
            ts = rec.get("timestamp") or ""
            if ts:
                session["start"] = min(filter(None, [session["start"], ts]))
                session["end"] = max(filter(None, [session["end"], ts]))
            text, has_tool_result = _text_of((rec.get("message") or {}).get("content"))
            if rec["type"] == "assistant":
                if text.strip() and not rec.get("isSidechain"):
                    session["claim"] = text.strip()
                continue
            text = SYSTEM_REMINDER.sub("", text).strip()
            if _is_summary(text):
                session["summaries"].append((ts, text))
            elif text and not has_tool_result and _is_human(rec, text):
                session["prompts"].append((ts, text))
    return session


def _clip(text, limit):
    text = redact(text)
    return text if len(text) <= limit else text[:limit] + f"\n…[truncated {len(text) - limit} chars]"


def load_extra(paths, sessions):
    """Merge sessions collected elsewhere (cloud, other machines) from JSONL lines:
    {"kind":"session","id":..,"title":..,"start":..,"end":..,"status":..,"note":..}
    {"kind":"prompt","session":..,"timestamp":..,"text":..}   {"kind":"claim","session":..,"text":..}"""
    by_id = {s["id"]: s for s in sessions}
    skipped = 0
    for path in paths or []:
        try:
            lines = Path(path).expanduser().read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            raise CliError(f"cannot read --extra file {path}: {exc.strerror}") from exc
        for line in filter(str.strip, lines):
            try:
                rec = json.loads(line)
                sid = str(rec.get("session") or rec["id"])
            except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
                skipped += 1
                continue
            s = by_id.setdefault(sid, {"id": sid, "start": None, "end": None, "prompts": [], "claim": None,
                                       "skipped": 0, "known": True, "summaries": []})
            kind = rec.get("kind", "prompt")
            if kind == "session":
                s.update(known=True, title=rec.get("title"), status=rec.get("status"), note=rec.get("note"),
                         start=rec.get("start") or s["start"], end=rec.get("end") or s["end"])
            elif kind == "claim":
                s["claim"] = str(rec.get("text", "")).strip() or s["claim"]
            elif kind == "summary":
                if str(rec.get("text", "")).strip():
                    s.setdefault("summaries", []).append((rec.get("timestamp") or "", str(rec["text"]).strip()))
            elif str(rec.get("text", "")).strip():
                ts = rec.get("timestamp") or ""
                s["prompts"].append((ts, str(rec["text"]).strip()))
                if ts:
                    s["start"] = min(filter(None, [s["start"], ts]))
                    s["end"] = max(filter(None, [s["end"], ts]))
    return list(by_id.values()), skipped


def load_sessions(args):
    project = Path(args.project or Path.cwd()).resolve()
    files, searched = find_transcripts(project, args.transcripts)
    sessions = [parse_session(f) for f in files]
    sessions = [s for s in sessions if s["prompts"] or s["claim"] or s["summaries"]]
    sessions, args.extra_skipped = load_extra(getattr(args, "extra", None), sessions)
    for s in sessions:
        s["prompts"].sort(key=lambda p: p[0])
    sessions.sort(key=lambda s: s["start"] or "")
    if not sessions:
        raise CliError(
            f"no session transcripts found for {project} (searched: {', '.join(searched)}). Audit coverage is limited "
            "to the repository itself; ask the user for exported chats or other requirement sources, or pass "
            "--transcripts DIR.", EXIT_NO_SOURCES)
    return project, sessions, searched


def cmd_sessions(args, directory):
    _, sessions, _ = load_sessions(args)
    for s in sessions:
        first = one_line(redact(s["prompts"][0][1]))[:90] if s["prompts"] else (
            f"(prompts NOT read) {one_line(redact(s.get('title') or ''))}" if s.get("known") else "(no human prompt)")
        print(f"{s['id']}  {(s['start'] or '?')[:16]} -> {(s['end'] or '?')[:16]}  "
              f"prompts: {len(s['prompts'])}  first: \"{first}\"")


def cmd_harvest(args, directory):
    project, sessions, searched = load_sessions(args)
    unread = [s for s in sessions if not s["prompts"]]
    summarised = [s for s in unread if s.get("summaries")]  # no typed prompt read, but the agent's own summary was
    sessions = ([s for s in sessions if s["prompts"]] + summarised
                + [s for s in unread if s["claim"] and not s.get("known") and not s.get("summaries")])
    unread = [s for s in unread if s.get("known") and not s.get("summaries")]
    skipped = sum(s["skipped"] for s in sessions) + args.extra_skipped
    with_status = [s for s in sessions + unread if s.get("status")]
    tally = {}
    for s in with_status:
        tally[one_line(s["status"]).lower()] = tally.get(one_line(s["status"]).lower(), 0) + 1
    total = sum(len(s["prompts"]) for s in sessions)
    out = [
        "# Requirement harvest",
        "",
        f"_Generated {now()} by `supervisor.py harvest` from {len(sessions)} session(s) and {total} human prompt(s) "
        f"for `{project}`. Secrets are redacted; this file is git-ignored._",
        "",
        "> **How to use:** every prompt below may carry requirements. Record each one with "
        "`criterion add \"...\" --source H#`. A later prompt can change an earlier one - record that with `decide`. "
        "Final claims are leads, not evidence: verify every criterion against the code as it is now.",
        "",
        "## Coverage",
        f"- Searched: {', '.join(searched)}",
        f"- Sessions read: {len(sessions)}; human prompts: {total}; {skipped} unreadable line(s) skipped",
        *([f"- {len(summarised)} session(s) are covered only by the agent's own continuation summary, not by the "
           "prompts as typed: wording and anything the summary left out are NOT covered"] if summarised else []),
        *([f"- **{len(unread)} known session(s) whose prompts were not read** (listed below): anything asked only "
           "there is NOT covered by this audit"] if unread else []),
        *([f"- Final status of the {len(with_status)} known session(s): "
           + ", ".join(f"{k} {v}" for k, v in sorted(tally.items()))] if with_status else []),
        "- **Not covered:** chats outside this machine's Claude Code history (claude.ai, other computers, cloud "
        "sessions), issue trackers, and anything said outside a chat. Ask for them or say the audit excludes them.",
    ]
    n = 0
    for i, s in enumerate(sessions, 1):
        out += ["", f"## Session {i} - `{s['id']}` ({(s['start'] or '?')[:16]} -> {(s['end'] or '?')[:16]})"]
        for ts, text in s["prompts"]:
            n += 1
            quoted = "\n".join("> " + line if line else ">" for line in _clip(text, args.max_chars).splitlines())
            out += ["", f"### H{n} - {ts[:16]}", quoted]
        for ts, text in sorted(s.get("summaries") or [])[-1:]:  # each summary restates the earlier ones
            quoted = "\n".join("> " + line if line else ">" for line in _clip(text, args.max_summary_chars).splitlines())
            out += ["", f"**Continuation summary written by the agent at {ts[:16] or '?'}** (a lead, not evidence; "
                        "its list of user messages is an index of what was asked before that point):", quoted]
        if s["claim"]:
            claim = "\n".join("> " + line if line else ">" for line in _clip(s["claim"], 3000).splitlines())
            out += ["", f"**Final claim at end of session {i}** (a lead, not evidence):", claim]
    if unread:
        cell = lambda v: one_line(redact(str(v or "-"))).replace("|", "/")  # noqa: E731
        out += ["", "## Sessions known, prompts NOT read", "",
                "| Session | Title | Start -> end | Final status | Waiting on / note |", "|---|---|---|---|---|"]
        out += [f"| `{s['id']}` | {cell(s.get('title'))} | {(s['start'] or '?')[:16]} -> {(s['end'] or '?')[:16]} | "
                f"{cell(s.get('status'))} | {cell(s.get('note'))} |" for s in unread]
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(directory / "harvest.md", "\n".join(out) + "\n")
    ignore = directory / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if "harvest.md" not in existing.split():
        atomic_write(ignore, existing + ("" if not existing or existing.endswith("\n") else "\n") + "harvest.md\n")
    print(f"harvested {total} human prompt(s) from {len(sessions)} session(s) -> {directory}/harvest.md"
          + (f"; {len(unread)} more session(s) known but NOT read" if unread else ""))


def _json_values(raw):
    """Every top-level JSON value in a text that may wrap them in other content (host-saved tool results)."""
    decoder, pos = json.JSONDecoder(strict=False), 0  # real dumps carry raw newlines in strings
    while True:
        starts = [i for i in (raw.find("{", pos), raw.find("[", pos)) if i >= 0]
        if not starts:
            return
        try:
            value, end = decoder.raw_decode(raw, min(starts))
            yield value
            pos = end
        except json.JSONDecodeError:
            pos = min(starts) + 1


def _messages(node, ts=None):
    """Walk any JSON shape and yield (timestamp, wrapper, message) for each {message: {role, content}}."""
    if isinstance(node, dict):
        ts = node.get("created_at") or node.get("timestamp") or ts
        message = node.get("message")
        if isinstance(message, dict) and message.get("role") in ("user", "assistant") and "content" in message:
            yield ts, node, message
        for value in node.values():
            yield from _messages(value, ts)
    elif isinstance(node, list):
        for value in node:
            yield from _messages(value, ts)
    elif isinstance(node, str) and '"message"' in node and len(node) > 200:
        for value in _json_values(node):  # some hosts save the events as a JSON string inside a text block
            yield from _messages(value, ts)


def cmd_events(args, directory):
    """Turn saved session-event dumps (e.g. large `list_events` results) into --extra lines, copied exactly."""
    prompts, summaries, said = {}, {}, {}
    for path in args.files:
        try:
            raw = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise CliError(f"cannot read {path}: {exc.strerror}") from exc
        for value in _json_values(raw):
            for ts, wrapper, message in _messages(value):
                text, has_tool_result = _text_of(message["content"])
                if message["role"] == "assistant":
                    if text.strip():
                        said[(ts or "", len(said))] = text.strip()
                    continue
                text = SYSTEM_REMINDER.sub("", text).strip()
                if _is_summary(text):
                    summaries[(ts or "", text)] = None
                elif text and not has_tool_result and "tool_use_result" not in wrapper and _is_human(wrapper, text):
                    prompts[(ts or "", text)] = None
    # A session that ends in automatic check-ins closes with "nothing changed": keep the last three messages,
    # so the last real status is not lost behind them.
    closing = [said[k] for k in sorted(said)][-3:]
    claim = "\n---\n".join(t[:1400] for t in closing) if closing else None
    if not prompts and claim is None and not summaries:
        raise CliError("no session events found in the given file(s): expected JSON containing "
                       '{"message": {"role": ..., "content": ...}} objects')
    lines = [json.dumps({"kind": "prompt", "session": args.session, "timestamp": ts, "text": text}, ensure_ascii=False)
             for ts, text in sorted(prompts)]
    lines += [json.dumps({"kind": "summary", "session": args.session, "timestamp": ts, "text": text}, ensure_ascii=False)
              for ts, text in sorted(summaries)]
    if claim:
        lines.append(json.dumps({"kind": "claim", "session": args.session, "text": claim}, ensure_ascii=False))
    with open(args.out, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"{len(prompts)} typed prompt(s)" + (" + final claim" if claim else "")
          + (f" + {len(summaries)} continuation summary(ies): read the newest before paging further back"
             if summaries else "") + f" for {args.session} -> {args.out}")


def cmd_branches(args, directory):
    """Where does the latest work live? The default branch is not always it."""
    root = str(Path(args.project or Path.cwd()))

    def git(*argv):
        return subprocess.run(["git", "-C", root, *argv], capture_output=True, text=True)

    if git("rev-parse", "--git-dir").returncode != 0:
        raise CliError(f"{root} is not a git repository")
    notes = []
    shallow = lambda: git("rev-parse", "--is-shallow-repository").stdout.strip() == "true"  # noqa: E731
    if args.fetch:
        if shallow() and git("fetch", "--quiet", "--unshallow", "origin").returncode != 0:
            notes.append("could not fetch the full history: ahead/behind counts stop at the shallow boundary and "
                         "are upper bounds, not true counts.")
        fetched = git("fetch", "--quiet", "origin", "+refs/heads/*:refs/remotes/origin/*")
        if fetched.returncode != 0:
            notes.append(f"fetch failed: {one_line(fetched.stderr)[:160]}")
    default = git("symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD").stdout.strip() \
        or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    fmt = "%(refname)\t%(committerdate:iso-strict)\t%(subject)\t%(committerdate:unix)"
    refs = {}
    for line in git("for-each-ref", f"--format={fmt}", "refs/remotes", "refs/heads").stdout.splitlines():
        ref, date, subject, stamp = (line.split("\t") + ["", "", "0"])[:4]
        if ref.endswith("/HEAD"):
            continue
        short = ref.replace("refs/remotes/", "").replace("refs/heads/", "")
        name = short.split("/", 1)[1] if ref.startswith("refs/remotes/") and "/" in short else short
        if ref.startswith("refs/remotes/") or name not in refs:  # prefer the remote's view of a branch
            refs[name] = (short, date, subject, int(stamp) if stamp.isdigit() else 0)
    rows = []
    default_name = default.split("/", 1)[1] if default.startswith("origin/") else default
    for name, (short, date, subject, stamp) in refs.items():
        if short == default or name == default_name:
            continue
        counts = git("rev-list", "--left-right", "--count", f"{default}...{short}").stdout.split()
        behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)
        if ahead == 0:
            state = "merged"
        elif git("diff", "--quiet", default, short).returncode == 0:
            state = "merged (same content)"
        else:
            state = "unmerged"
        rows.append((ahead, behind, name, date, state, subject, stamp))
    rows.sort(key=lambda r: (r[6], r[0]), reverse=True)  # newest first (by instant, not by local-time text)
    print(f"default branch: {default}  ({len(rows) + 1} branch(es) known locally)")
    print("| Branch | Ahead | Behind | Last commit | State | Last subject |\n|---|---|---|---|---|---|")
    for ahead, behind, name, date, state, subject, _ in rows:
        print(f"| {name} | {ahead} | {behind} | {date[:10]} | {state} | {one_line(subject)[:60].replace('|', '/')} |")
    unmerged = [r for r in rows if r[4] == "unmerged"]
    if unmerged:
        top = unmerged[0]
        biggest = max(unmerged, key=lambda r: r[0])
        also = "" if biggest is top else (f" Largest divergence: {biggest[2]}, {biggest[0]} ahead "
                                          f"(last commit {biggest[3][:10]}).")
        print(f"\nLATEST WORK: {top[2]} is {top[0]} commit(s) ahead of {default} (last commit {top[3][:10]}). "
              f"{len(unmerged)} unmerged branch(es).{also} The default branch may not hold the newest state: "
              "audit the latest branch too, and report built-but-unmerged work as unmerged, not as missing.")
    if shallow() and not args.fetch:
        notes.append("shallow clone: other branches may not be fetched, and ahead/behind counts stop at the shallow "
                     "boundary, so they can be far too high. Re-run with --fetch for true counts (or --remote to only "
                     "list what the remote has).")
    if args.remote or len(rows) == 0:
        listed = git("ls-remote", "--heads", "origin")
        if listed.returncode == 0:
            remote = [line.split("refs/heads/", 1)[1] for line in listed.stdout.splitlines() if "refs/heads/" in line]
            known = {v[0].split("/", 1)[1] for v in refs.values() if v[0].startswith("origin/")}
            missing = [b for b in remote if b not in known]
            if missing:
                notes.append(f"{len(missing)} branch(es) on the remote are NOT fetched locally: {', '.join(missing[:30])}"
                             " - run `branches --fetch`.")
        elif args.remote:
            notes.append(f"could not list the remote: {one_line(listed.stderr)[:160]}")
    for note in notes:
        print(f"\nWARNING: {note}")


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(prog="supervisor.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="create project memory")
    s.add_argument("--objective", required=True)
    s.add_argument("--max-parallel", type=int, default=3, help="max tasks running at once (default 3)")
    s.add_argument("--max-attempts", type=int, default=3, help="failed attempts per strategy before forced change (default 3)")
    s.add_argument("--max-strategies", type=int, default=DEFAULT_MAX_STRATEGIES, help="strategies per task before escalation (default 3)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("criterion", help="add | verify | fail an acceptance criterion")
    s.add_argument("action", choices=("add", "verify", "fail", "drop", "unverifiable"))
    s.add_argument("items", nargs="+", help="one or more criterion texts (add) or ids (verify/fail)")
    s.add_argument("--evidence", help="command run + observed result")
    s.add_argument("--reason", help="drop: why it is out of scope; unverifiable: what is needed to check it")
    s.add_argument("--source", help="where the requirement came from, e.g. H3 (harvest prompt id) or brief.md")
    s.add_argument("--milestone", help="add: the mini-goal (M#) these criteria belong to")
    s.add_argument("--run", metavar="COMMAND", help="verify: the tool runs this check itself and records exit code and "
                   "output; exit 0 verifies, anything else marks the criterion failed (exit 3)")
    s.add_argument("--timeout", type=int, default=600, help="seconds allowed for --run (default 600)")
    s.set_defaults(fn=cmd_criterion)

    s = sub.add_parser("milestone", help="add a mini-goal: an ordered slice of the project with its own gate")
    s.add_argument("action", choices=("add",))
    s.add_argument("title", help="the observable outcome of this mini-goal")
    s.add_argument("--criteria", help="comma-separated existing criterion ids (or use `criterion add --milestone`)")
    s.set_defaults(fn=cmd_milestone)
    s = sub.add_parser("ask", help="record a question only the owner can answer, with the default you proceed on")
    s.add_argument("text")
    s.add_argument("--default", required=True, help="the option you recommend and assume until answered")
    s.add_argument("--blocks", help="comma-separated task ids that cannot proceed on the default (they become blocked)")
    s.add_argument("--because", choices=sorted(BLOCK_REASONS),
                   help="required with --blocks: the only reasons work may wait for the owner")
    s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("answer", help="record the owner's answer: becomes a binding decision and unblocks tasks")
    s.add_argument("id")
    s.add_argument("text", nargs="?")
    s.add_argument("--accept", action="store_true", help="the owner accepted the recommended default")
    s.set_defaults(fn=cmd_answer)

    task = sub.add_parser("task", help="manage tasks").add_subparsers(dest="task_cmd", required=True)
    s = task.add_parser("add")
    s.add_argument("title")
    s.add_argument("--owner")
    s.add_argument("--depends", help="comma-separated task ids")
    s.add_argument("--criteria", help="comma-separated criterion ids this task serves")
    s.add_argument("--files", help="comma-separated paths/globs this task owns")
    s.set_defaults(fn=cmd_task_add)
    s = task.add_parser("set")
    s.add_argument("id")
    s.add_argument("status", choices=TASK_STATES)
    s.add_argument("--owner")
    s.add_argument("--evidence")
    s.add_argument("--note")
    s.add_argument("--force", action="store_true", help="override start guards deliberately")
    s.set_defaults(fn=cmd_task_set)
    s = task.add_parser("attempt", help="record a failed attempt")
    s.add_argument("id")
    s.add_argument("--note", required=True)
    s.set_defaults(fn=cmd_task_attempt)
    s = task.add_parser("strategy", help="record a new approach (resets retry budget)")
    s.add_argument("id")
    s.add_argument("text")
    s.set_defaults(fn=cmd_task_strategy)

    s = sub.add_parser("decide", help="record a decision")
    s.add_argument("text")
    s.add_argument("--why", required=True)
    s.set_defaults(fn=cmd_simple_add("decisions", "D"))
    s = sub.add_parser("risk", help="record a risk")
    s.add_argument("text")
    s.set_defaults(fn=cmd_simple_add("risks", "R"))
    s = sub.add_parser("next", help="replace the next-actions list (or --clear it when finished)")
    s.add_argument("actions", nargs="*")
    s.add_argument("--clear", action="store_true", help="empty the list - required before the gate can pass")
    s.set_defaults(fn=cmd_next)
    s = sub.add_parser("log", help="append a milestone note")
    s.add_argument("text")
    s.set_defaults(fn=cmd_log)
    for name, fn, text in (
        ("sessions", cmd_sessions, "list past Claude Code sessions for this project (audit mode)"),
        ("harvest", cmd_harvest, "extract every human prompt + final claims from past sessions into harvest.md"),
    ):
        s = sub.add_parser(name, help=text)
        s.add_argument("--transcripts", help="folder of session *.jsonl files (default: Claude Code history)")
        s.add_argument("--project", help="project path the sessions ran in (default: current directory)")
        s.add_argument("--max-chars", type=int, default=4000, help="truncate each prompt to this length")
        s.add_argument("--max-summary-chars", type=int, default=25000, help="truncate a continuation summary to this length")
        s.add_argument("--extra", action="append", metavar="FILE.jsonl",
                       help="sessions collected elsewhere (cloud, other machines); see references/audit.md")
        s.set_defaults(fn=fn)
    s = sub.add_parser("events", help="audit: extract typed prompts from saved session-event dumps into --extra lines")
    s.add_argument("files", nargs="+", help="files holding session events as JSON (wrapper text around it is fine)")
    s.add_argument("--session", required=True, help="id of the session these events belong to")
    s.add_argument("--out", required=True, help="JSONL file to append to; pass it to `harvest --extra`")
    s.set_defaults(fn=cmd_events)
    s = sub.add_parser("branches", help="audit: every branch vs the default branch (ahead/behind, merged?)")
    s.add_argument("--project", help="repository path (default: current directory)")
    s.add_argument("--fetch", action="store_true", help="fetch all remote branches first (updates remote-tracking refs only)")
    s.add_argument("--remote", action="store_true", help="also list branches the remote has that are not fetched")
    s.set_defaults(fn=cmd_branches)
    for name, fn, text in (
        ("status", cmd_status, "print MEMORY.md"),
        ("resume", cmd_resume, "print a resume brief after an interruption"),
        ("ready", cmd_ready, "list pending tasks whose dependencies are verified"),
    ):
        sub.add_parser(name, help=text).set_defaults(fn=fn)
    s = sub.add_parser("batch", help="several updates in one call, all or nothing (each argument is one command line)")
    s.add_argument("commands", nargs="+", help='e.g. "task set T1 verified --evidence \'test_core OK\'" "criterion verify AC1 --evidence ..."')
    s.set_defaults(fn=cmd_batch)
    s = sub.add_parser("guard", help="quality-bar guard: bar-lowering moves in the diff since the project started")
    s.add_argument("--base", help="commit or branch to compare with (default: HEAD when the project was initialised)")
    s.add_argument("--accept", action="store_true", help="accept the current findings as right, with --reason")
    s.add_argument("--reason", help="why lowering the bar here is right (recorded as a decision)")
    s.set_defaults(fn=cmd_guard)
    s = sub.add_parser("gate", help="completion gate: VERIFIED COMPLETE / PARTIALLY COMPLETE / BLOCKED")
    s.add_argument("--recheck", action="store_true", help="run every recorded check again before judging")
    s.add_argument("--timeout", type=int, default=600, help="seconds allowed per recheck (default 600)")
    s.add_argument("--milestone", help="judge one mini-goal (M#) instead of the whole project")
    s.set_defaults(fn=cmd_gate)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        args.fn(args, state_dir())
        if getattr(args, "post_exit", 0):
            return args.post_exit
    except ReadOnlyState as exc:
        if args.command in ("harvest",):
            raise OSError(str(exc)) from exc
        rec = {"at": now(), "argv": raw}
        if getattr(args, "recorded_fingerprint", None) is not None:
            rec["fingerprint"] = args.recorded_fingerprint
        if getattr(args, "recorded", None):
            rec["recorded"] = args.recorded
        lines = getattr(args, "batch_records", None) or [rec]
        print(
            f"READ-ONLY SHELL ({exc}): valid, but this shell cannot save it. Append exactly these {len(lines)} line(s) to "
            f"{state_dir()}/journal.jsonl with your file-writing tool (create the file if needed), then go on. The "
            "next command only sees lines already in the file, so do not chain updates with `&&` here: put several "
            "in one `batch \"cmd\" \"cmd\"` call and append all its lines at once. `resume`, `status` and `gate` read "
            "the journal, so the guards and the gate still work; MEMORY.md is refreshed when a shell can write.\n"
            + "\n".join(json.dumps(r, ensure_ascii=False) for r in lines),
            file=sys.stderr,
        )
        return EXIT_UNWRITABLE
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except BrokenPipeError:  # the reader (head, grep -q) closed the pipe: not an error, and not a memory problem
        with contextlib.suppress(OSError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except OSError as exc:
        print(
            f"error: cannot write project memory in {state_dir()}/ ({exc.strerror or exc}). The shell is probably "
            "sandboxed or the filesystem is read-only. Fallback: record progress (task status, evidence, decisions, "
            "next actions) in .supervisor/MANUAL.md with your file-writing tool, following templates/memory.md "
            "from the autonomous-supervisor skill; `resume` shows it and the CLI never overwrites it. Apply the "
            "guards yourself and tell the user the gate is manual this session. Do not hand-edit state.json.",
            file=sys.stderr,
        )
        return EXIT_UNWRITABLE
    return 0


if __name__ == "__main__":
    sys.exit(main())
