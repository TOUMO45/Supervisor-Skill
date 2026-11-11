"""Behavioural tests for skills/autonomous-supervisor/scripts/supervisor.py.

Run:  python3 -m unittest discover -s tests -v
The CLI is exercised as a subprocess, exactly as an agent would call it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "autonomous-supervisor" / "scripts" / "supervisor.py"


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args, expect=0):
        proc = subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=self.dir,
            capture_output=True,
            text=True,
        )
        if expect is not None:
            self.assertEqual(
                proc.returncode,
                expect,
                f"args={args}\nstdout={proc.stdout}\nstderr={proc.stderr}",
            )
        return proc

    def state(self):
        return json.loads((self.dir / ".supervisor" / "state.json").read_text())

    def init(self, *extra, expect=0):
        return self.run_cli("init", "--objective", "Ship a CSV-to-Markdown CLI", *extra, expect=expect)


class TestInitAndRender(CliTestCase):
    def test_init_creates_state_and_memory(self):
        self.init()
        st = self.state()
        self.assertEqual(st["objective"], "Ship a CSV-to-Markdown CLI")
        memory = (self.dir / ".supervisor" / "MEMORY.md").read_text()
        self.assertIn("Ship a CSV-to-Markdown CLI", memory)

    def test_init_refuses_to_overwrite_existing_project(self):
        self.init()
        proc = self.init(expect=1)
        self.assertIn("already exists", proc.stderr)

    def test_commands_before_init_fail_cleanly(self):
        proc = self.run_cli("status", expect=1)
        self.assertIn("init", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class TestCriteriaAndTasks(CliTestCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_ids_are_sequential(self):
        self.assertIn("AC1", self.run_cli("criterion", "add", "Converts CSV").stdout)
        self.assertIn("AC2", self.run_cli("criterion", "add", "Has README").stdout)
        self.assertIn("T1", self.run_cli("task", "add", "Scaffold").stdout)
        self.assertIn("D1", self.run_cli("decide", "stdlib only", "--why", "zero deps").stdout)

    def test_verify_requires_evidence(self):
        self.run_cli("criterion", "add", "Converts CSV")
        proc = self.run_cli("criterion", "verify", "AC1", expect=2)
        self.assertIn("evidence", proc.stderr.lower())
        self.run_cli("criterion", "verify", "AC1", "--evidence", "pytest: 5 passed")
        self.assertEqual(self.state()["criteria"]["AC1"]["status"], "verified")

    def test_task_verified_requires_evidence_but_done_does_not(self):
        self.run_cli("task", "add", "Scaffold")
        self.run_cli("task", "set", "T1", "done", "--note", "agent says done")
        self.assertEqual(self.state()["tasks"]["T1"]["status"], "done")
        self.run_cli("task", "set", "T1", "verified", expect=2)
        self.run_cli("task", "set", "T1", "verified", "--evidence", "ls src/ shows files")
        self.assertEqual(self.state()["tasks"]["T1"]["status"], "verified")

    def test_batch_add_and_verify_criteria_in_one_call(self):
        out = self.run_cli("criterion", "add", "Parses", "Escapes", "Aligns").stdout
        for cid in ("AC1", "AC2", "AC3"):
            self.assertIn(cid, out)
        self.run_cli("criterion", "verify", "AC1", "ac2", "--evidence", "test_escape_pipe OK")
        crit = self.state()["criteria"]
        self.assertEqual([crit[c]["status"] for c in ("AC1", "AC2", "AC3")], ["verified", "verified", "pending"])

    def test_batch_verify_is_all_or_nothing(self):
        self.run_cli("criterion", "add", "Parses")
        self.run_cli("criterion", "verify", "AC1", "AC9", "--evidence", "x", expect=1)
        self.assertEqual(self.state()["criteria"]["AC1"]["status"], "pending")

    def test_unknown_id_is_an_error(self):
        proc = self.run_cli("task", "set", "T9", "running", expect=1)
        self.assertIn("T9", proc.stderr)

    def test_dependency_must_exist(self):
        proc = self.run_cli("task", "add", "Report", "--depends", "T7", expect=1)
        self.assertIn("T7", proc.stderr)


class TestGuards(CliTestCase):
    def setUp(self):
        super().setUp()
        self.init("--max-parallel", "2", "--max-attempts", "2")

    def test_cannot_start_task_with_unverified_dependency(self):
        self.run_cli("task", "add", "Scaffold")
        self.run_cli("task", "add", "Feature", "--depends", "T1")
        proc = self.run_cli("task", "set", "T2", "running", expect=3)
        self.assertIn("T1", proc.stdout + proc.stderr)
        self.run_cli("task", "set", "T1", "verified", "--evidence", "ok")
        self.run_cli("task", "set", "T2", "running")

    def test_parallel_limit_enforced(self):
        for name in ("A", "B", "C"):
            self.run_cli("task", "add", name)
        self.run_cli("task", "set", "T1", "running")
        self.run_cli("task", "set", "T2", "running")
        proc = self.run_cli("task", "set", "T3", "running", expect=3)
        self.assertIn("parallel", (proc.stdout + proc.stderr).lower())

    def test_file_ownership_overlap_detected(self):
        self.run_cli("task", "add", "Routes", "--files", "src/routes/*.ts")
        self.run_cli("task", "add", "Shortener route", "--files", "src/routes/shorten.ts")
        self.run_cli("task", "add", "Docs", "--files", "docs/")
        self.run_cli("task", "set", "T1", "running")
        proc = self.run_cli("task", "set", "T2", "running", expect=3)
        self.assertIn("T1", proc.stdout + proc.stderr)
        self.run_cli("task", "set", "T3", "running")  # no overlap

    def test_retry_limit_forces_strategy_change(self):
        self.run_cli("task", "add", "Fix redirect")
        self.run_cli("task", "attempt", "T1", "--note", "regex tweak 1")
        proc = self.run_cli("task", "attempt", "T1", "--note", "regex tweak 2", expect=3)
        out = proc.stdout + proc.stderr
        self.assertIn("RETRY LIMIT", out)
        self.assertEqual(len(self.state()["tasks"]["T1"]["attempts"]), 2)

    def test_new_strategy_resets_retry_budget(self):
        self.run_cli("task", "add", "Fix redirect")
        self.run_cli("task", "attempt", "T1", "--note", "tweak 1")
        self.run_cli("task", "attempt", "T1", "--note", "tweak 2", expect=3)
        self.run_cli("task", "strategy", "T1", "Trace request through router with logging")
        self.run_cli("task", "attempt", "T1", "--note", "instrumented router")
        st = self.state()["tasks"]["T1"]
        self.assertEqual(st["strategy"], "Trace request through router with logging")
        self.assertEqual(len(st["attempts"]), 3)

    def test_force_overrides_guard(self):
        for name in ("A", "B", "C"):
            self.run_cli("task", "add", name)
        self.run_cli("task", "set", "T1", "running")
        self.run_cli("task", "set", "T2", "running")
        self.run_cli("task", "set", "T3", "running", "--force")


class TestResumeAndGate(CliTestCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.run_cli("criterion", "add", "Import works")
        self.run_cli("criterion", "add", "Report works")
        self.run_cli("task", "add", "Import", "--criteria", "AC1")
        self.run_cli("task", "add", "Report", "--criteria", "AC2", "--depends", "T1")
        self.run_cli("task", "add", "README", "--depends", "T2")

    def test_resume_brief_separates_done_inflight_ready(self):
        self.run_cli("task", "set", "T1", "verified", "--evidence", "6 passed")
        self.run_cli("criterion", "verify", "AC1", "--evidence", "6 passed")
        self.run_cli("task", "set", "T2", "running", "--owner", "backend-agent")
        self.run_cli("next", "Collect T2 report")
        out = self.run_cli("resume").stdout
        self.assertIn("Do not redo", out)
        self.assertIn("T1", out)
        self.assertIn("In flight", out)
        self.assertIn("backend-agent", out)
        self.assertIn("Collect T2 report", out)

    def test_ready_lists_only_unblocked_pending_tasks(self):
        out = self.run_cli("ready").stdout
        self.assertIn("T1", out)
        self.assertNotIn("T2", out)

    def test_gate_partial_when_criteria_unverified(self):
        proc = self.run_cli("gate", expect=10)
        self.assertIn("PARTIALLY COMPLETE", proc.stdout)
        self.assertIn("AC1", proc.stdout)

    def test_gate_blocked_when_blocker_exists(self):
        self.run_cli("task", "set", "T1", "blocked", "--note", "needs API key")
        proc = self.run_cli("gate", expect=20)
        self.assertIn("BLOCKED", proc.stdout)
        self.assertIn("needs API key", proc.stdout)

    def test_gate_rejects_done_but_unverified_task(self):
        for ac in ("AC1", "AC2"):
            self.run_cli("criterion", "verify", ac, "--evidence", "ok")
        for t in ("T1", "T2"):
            self.run_cli("task", "set", t, "verified", "--evidence", "ok")
        self.run_cli("task", "set", "T3", "done")
        proc = self.run_cli("gate", expect=10)
        self.assertIn("T3", proc.stdout)

    def test_gate_verified_complete(self):
        for ac in ("AC1", "AC2"):
            self.run_cli("criterion", "verify", ac, "--evidence", "pytest 12 passed")
        for t in ("T1", "T2", "T3"):
            self.run_cli("task", "set", t, "verified", "--evidence", "ok")
        proc = self.run_cli("gate", expect=0)
        self.assertIn("VERIFIED COMPLETE", proc.stdout)

    def _all_verified(self):
        for ac in ("AC1", "AC2"):
            self.run_cli("criterion", "verify", ac, "--evidence", "ok")
        for t in ("T1", "T2", "T3"):
            self.run_cli("task", "set", t, "verified", "--evidence", "ok")

    def test_gate_not_complete_while_next_actions_remain(self):
        # Regression: a session that scoped criteria to its own slice got VERIFIED
        # COMPLETE while its next-actions list still held the deferred CLI work.
        self._all_verified()
        self.run_cli("next", "Build the CLI entry point")
        proc = self.run_cli("gate", expect=10)
        self.assertIn("next action", proc.stdout.lower())
        self.assertIn("Build the CLI entry point", proc.stdout)

    def test_next_clear_empties_list_and_unblocks_gate(self):
        self._all_verified()
        self.run_cli("next", "Build the CLI entry point")
        self.run_cli("next", "--clear")
        self.assertEqual(self.state()["next"], [])
        self.run_cli("gate", expect=0)

    def test_next_without_actions_or_clear_is_usage_error(self):
        self.run_cli("next", expect=1)

    def test_dropped_task_does_not_block_gate(self):
        for ac in ("AC1", "AC2"):
            self.run_cli("criterion", "verify", ac, "--evidence", "ok")
        for t in ("T1", "T2"):
            self.run_cli("task", "set", t, "verified", "--evidence", "ok")
        self.run_cli("task", "set", "T3", "dropped", "--note", "out of scope")
        self.run_cli("gate", expect=0)


class TestDurability(CliTestCase):
    def test_memory_md_rerendered_and_state_is_valid_json_after_every_write(self):
        self.init()
        self.run_cli("criterion", "add", "Works")
        self.run_cli("decide", "Use argparse", "--why", "no deps")
        self.run_cli("risk", "Large CSVs may be slow")
        self.run_cli("log", "Milestone 1 reached")
        memory = (self.dir / ".supervisor" / "MEMORY.md").read_text()
        for needle in ("Works", "Use argparse", "no deps", "Large CSVs", "Milestone 1"):
            self.assertIn(needle, memory)
        self.state()  # parses
        leftovers = [p.name for p in (self.dir / ".supervisor").iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])

    def test_custom_directory_via_env(self):
        env_dir = self.dir / "custom"
        proc = subprocess.run(
            [sys.executable, str(CLI), "init", "--objective", "x"],
            cwd=self.dir,
            capture_output=True,
            text=True,
            env={**os.environ, "SUPERVISOR_DIR": str(env_dir)},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((env_dir / "state.json").exists())

    def test_newlines_in_text_do_not_break_markdown_structure(self):
        self.init()
        self.run_cli("decide", "line1\n## Injected heading", "--why", "x")
        memory = (self.dir / ".supervisor" / "MEMORY.md").read_text()
        self.assertNotIn("\n## Injected heading", memory)


if __name__ == "__main__":
    unittest.main()


class TestUpgrades(CliTestCase):
    """v1.1 upgrades: drift detection, strategy cap, criterion drop, liveness, metrics, concurrency."""

    def setUp(self):
        super().setUp()
        self.init("--max-attempts", "1")
        (self.dir / "src").mkdir()
        (self.dir / "src" / "core.py").write_text("x = 1\n")

    def test_verified_task_whose_files_change_is_flagged_and_blocks_gate(self):
        self.run_cli("criterion", "add", "Core works")
        self.run_cli("task", "add", "Core", "--files", "src/*.py", "--criteria", "AC1")
        self.run_cli("task", "set", "T1", "verified", "--evidence", "test_core OK")
        self.run_cli("criterion", "verify", "AC1", "--evidence", "test_core OK")
        self.run_cli("gate", expect=0)
        (self.dir / "src" / "core.py").write_text("x = 2  # edited after verification\n")
        out = self.run_cli("resume").stdout
        self.assertIn("changed since verification", out.lower())
        self.assertIn("src/core.py", out)
        proc = self.run_cli("gate", expect=10)
        self.assertIn("T1", proc.stdout)
        # re-verifying refreshes the fingerprint
        self.run_cli("task", "set", "T1", "verified", "--evidence", "test_core OK again")
        self.run_cli("gate", expect=0)

    def test_new_file_matching_owned_glob_counts_as_drift(self):
        self.run_cli("task", "add", "Core", "--files", "src/")
        self.run_cli("task", "set", "T1", "verified", "--evidence", "ok")
        (self.dir / "src" / "extra.py").write_text("y = 1\n")
        self.assertIn("src/extra.py", self.run_cli("resume").stdout)

    def test_strategy_cap_forces_escalation(self):
        self.run_cli("task", "add", "Fix")
        for i in (1, 2, 3):
            self.run_cli("task", "strategy", "T1", f"approach {i}")
        proc = self.run_cli("task", "strategy", "T1", "approach 4", expect=3)
        self.assertIn("STRATEGY LIMIT", proc.stderr)

    def test_criterion_drop_requires_reason_and_is_excluded_from_gate(self):
        self.run_cli("criterion", "add", "Core works", "Excel input")
        self.run_cli("criterion", "verify", "AC1", "--evidence", "ok")
        self.run_cli("criterion", "drop", "AC2", expect=2)
        self.run_cli("criterion", "drop", "AC2", "--reason", "needs third-party package")
        proc = self.run_cli("gate", expect=0)
        self.assertIn("excluded", proc.stdout.lower())
        self.assertIn("needs third-party package", proc.stdout)

    def test_resume_shows_running_since(self):
        self.run_cli("task", "add", "Core")
        self.run_cli("task", "set", "T1", "running", "--owner", "worker-1")
        self.assertIn("running since", self.run_cli("resume").stdout)

    def test_metrics_reported_in_status_and_gate(self):
        self.run_cli("task", "add", "Core")
        self.run_cli("task", "set", "T1", "running")
        self.run_cli("task", "attempt", "T1", "--note", "nope", expect=3)
        out = self.run_cli("status").stdout
        self.assertIn("dispatches: 1", out)
        self.assertIn("failed attempts: 1", out)

    def test_concurrent_writers_do_not_lose_updates(self):
        procs = [
            subprocess.Popen([sys.executable, str(CLI), "task", "add", f"job {i}"], cwd=self.dir,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(20)
        ]
        for p in procs:
            _, err = p.communicate()
            self.assertEqual(p.returncode, 0, err)
        self.assertEqual(len(self.state()["tasks"]), 20)


class TestSelfOwnedWork(CliTestCase):
    """Dogfooding found the parallel limit counted the supervisor's own task."""

    def setUp(self):
        super().setUp()
        self.init("--max-parallel", "2")
        for name in ("A", "B", "Integration", "C"):
            self.run_cli("task", "add", name)

    def test_supervisor_owned_task_does_not_consume_agent_slot(self):
        self.run_cli("task", "set", "T1", "running", "--owner", "worker-a")
        self.run_cli("task", "set", "T2", "running", "--owner", "worker-b")
        self.run_cli("task", "set", "T3", "running", "--owner", "supervisor")
        proc = self.run_cli("task", "set", "T4", "running", "--owner", "worker-c", expect=3)
        self.assertIn("parallel", proc.stderr.lower())

    def test_self_owned_task_still_checked_for_file_overlap(self):
        self.run_cli("task", "add", "Core", "--files", "src/core.py")
        self.run_cli("task", "add", "Core again", "--files", "src/core.py")
        self.run_cli("task", "set", "T5", "running", "--owner", "worker-a")
        self.run_cli("task", "set", "T6", "running", "--owner", "self", expect=3)


class TestSelfDescribingMemory(CliTestCase):
    """Evals showed fresh agents found .supervisor/ but didn't know a skill/CLI goes with it."""

    def test_memory_md_tells_a_fresh_agent_how_to_resume(self):
        self.init()
        memory = (self.dir / ".supervisor" / "MEMORY.md").read_text()
        self.assertIn("autonomous-supervisor", memory)
        self.assertIn(f"{CLI.resolve()} resume", memory)

    def test_state_json_records_cli_path(self):
        self.init()
        self.assertEqual(self.state()["cli"], str(CLI.resolve()))


class TestUnwritableMemory(CliTestCase):
    """Eval sandbox made the workspace read-only to the shell: the CLI died with a raw OSError."""

    def test_unwritable_state_dir_gives_actionable_error_not_traceback(self):
        blocker = self.dir / "not-a-dir"
        blocker.write_text("x")
        proc = subprocess.run(
            [sys.executable, str(CLI), "init", "--objective", "x"], cwd=self.dir,
            capture_output=True, text=True, env={**os.environ, "SUPERVISOR_DIR": str(blocker / "sub")},
        )
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("cannot write", proc.stderr)
        self.assertIn("templates/memory.md", proc.stderr)

    def test_manual_notes_survive_rerender_and_are_shown_on_resume(self):
        self.init()
        notes = self.dir / ".supervisor" / "MANUAL.md"
        notes.write_text("T2 verified by hand: test_cli 8 OK (CLI was read-only)\n")
        self.run_cli("log", "milestone")  # re-render must not touch MANUAL.md
        self.assertIn("T2 verified by hand", notes.read_text())
        out = self.run_cli("resume").stdout
        self.assertIn("Manual notes", out)
        self.assertIn("T2 verified by hand", out)
        self.assertIn("MANUAL.md", (self.dir / ".supervisor" / "MEMORY.md").read_text())

    def test_unwritable_error_points_to_manual_notes_file(self):
        blocker = self.dir / "not-a-dir"
        blocker.write_text("x")
        proc = subprocess.run(
            [sys.executable, str(CLI), "init", "--objective", "x"], cwd=self.dir,
            capture_output=True, text=True, env={**os.environ, "SUPERVISOR_DIR": str(blocker / "sub")},
        )
        self.assertIn("MANUAL.md", proc.stderr)


# --------------------------------------------------------------------------- #
# v1.2 audit mode: reconstruct requirements from past Claude Code sessions
# --------------------------------------------------------------------------- #
def _rec(kind, ts, session, cwd, content, **extra):
    """One transcript record shaped like Claude Code's ~/.claude/projects/*.jsonl."""
    rec = {"type": kind, "timestamp": ts, "sessionId": session, "cwd": cwd,
           "isSidechain": False, "uuid": f"{session}-{ts}"}
    if kind == "user":
        rec["message"] = {"role": "user", "content": content}
        rec.update(extra)
    else:
        rec["message"] = {"role": "assistant", "content": content}
    return json.dumps(rec)


def human(ts, session, cwd, text):
    return _rec("user", ts, session, cwd, text, origin={"kind": "human"}, promptSource="sdk")


def write_session(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(records) + "\n")


class TestHarvest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.dir / "proj"
        self.project.mkdir()
        self.config = self.dir / "claude-config"
        cwd = str(self.project.resolve())
        encoded = "".join(c if c.isalnum() else "-" for c in cwd)
        self.tdir = self.config / "projects" / encoded
        a, b = "aaaa-1111", "bbbb-2222"
        write_session(self.tdir / f"{a}.jsonl", [
            human("2026-01-01T10:00:00Z", a, cwd, "Build csvmd per brief.md. Stdlib only."),
            _rec("assistant", "2026-01-01T10:00:05Z", a, cwd,
                 [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]),
            _rec("user", "2026-01-01T10:00:06Z", a, cwd,
                 [{"type": "tool_result", "content": "NOISE tool output that is not a requirement"}],
                 toolUseResult={"stdout": "x"}),
            _rec("user", "2026-01-01T10:00:07Z", a, cwd, "Base directory for this skill: /x", isMeta=True),
            _rec("user", "2026-01-01T10:00:08Z", a, cwd,
                 "<task-notification>\n<task-id>t1</task-id>\nagent finished</task-notification>",
                 origin={"kind": "task-notification"}),
            human("2026-01-01T10:05:00Z", a, cwd,
                  "Also: a missing input file must exit with code 3. My key is sk-ant-api03-AbCdEf1234567890XyZ_abcdef"),
            _rec("assistant", "2026-01-01T10:09:00Z", a, cwd,
                 [{"type": "text", "text": "Core done. CLI deferred to next session."}]),
        ])
        write_session(self.tdir / f"{b}.jsonl", [
            human("2026-01-02T09:00:00Z", b, cwd,
                  [{"type": "image", "source": {}}, {"type": "text", "text": "Continue the project and finish it."}]),
            _rec("assistant", "2026-01-02T09:30:00Z", b, cwd,
                 [{"type": "text", "text": "csvmd is finished, all tests pass."}]),
        ])
        # a subagent transcript must be ignored
        write_session(self.tdir / a / "subagents" / "agent-x.jsonl", [
            human("2026-01-01T10:01:00Z", a, cwd, "SUBAGENT BRIEF should not appear"),
        ])

    def harvest(self, *args, expect=0):
        return subprocess.run(
            [sys.executable, str(CLI), "harvest", *args], cwd=self.project, capture_output=True, text=True,
            env={**os.environ, "CLAUDE_CONFIG_DIR": str(self.config)},
        ), expect

    def run_harvest(self, *args, expect=0):
        proc, _ = self.harvest(*args)
        self.assertEqual(proc.returncode, expect, proc.stderr)
        return proc

    def test_harvest_extracts_only_human_prompts_in_order(self):
        self.run_harvest()
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertIn("H1", text)
        self.assertIn("Build csvmd per brief.md", text)
        self.assertIn("missing input file must exit with code 3", text)
        self.assertIn("Continue the project and finish it.", text)
        self.assertLess(text.index("Build csvmd"), text.index("exit with code 3"))
        self.assertLess(text.index("exit with code 3"), text.index("Continue the project"))
        for noise in ("NOISE tool output", "Base directory for this skill", "task-notification", "SUBAGENT BRIEF"):
            self.assertNotIn(noise, text)

    def test_harvest_records_final_claim_per_session_and_coverage(self):
        self.run_harvest()
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertIn("csvmd is finished, all tests pass.", text)
        self.assertIn("2 session", text)
        self.assertIn("3 human prompt", text)

    def test_harvest_redacts_secrets_and_keeps_digest_out_of_git(self):
        self.run_harvest()
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertNotIn("sk-ant-api03-AbCdEf1234567890XyZ_abcdef", text)
        self.assertIn("[REDACTED", text)
        self.assertIn("harvest.md", (self.project / ".supervisor" / ".gitignore").read_text())

    def test_harvest_finds_sessions_by_cwd_when_folder_name_differs(self):
        renamed = self.config / "projects" / "some-other-name"
        self.tdir.rename(renamed)
        self.run_harvest()
        self.assertIn("Build csvmd", (self.project / ".supervisor" / "harvest.md").read_text())

    def test_harvest_explicit_transcripts_dir(self):
        moved = self.dir / "exported"
        self.tdir.rename(moved)
        self.run_harvest("--transcripts", str(moved))
        self.assertIn("Build csvmd", (self.project / ".supervisor" / "harvest.md").read_text())

    def test_harvest_with_no_sessions_exits_5_with_coverage_warning(self):
        proc = self.run_harvest("--transcripts", str(self.dir / "nowhere"), expect=5)
        self.assertIn("no session transcripts", proc.stderr.lower())

    def test_harvest_truncates_very_long_prompts(self):
        cwd = str(self.project.resolve())
        write_session(self.tdir / "cccc-3333.jsonl", [human("2026-01-03T09:00:00Z", "cccc-3333", cwd, "Z" * 9000)])
        self.run_harvest("--max-chars", "500")
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertNotIn("Z" * 600, text)
        self.assertIn("truncated", text)

    def test_markdown_headings_inside_prompts_cannot_break_digest_structure(self):
        # Real transcripts showed pasted specs ("## Vision") leaking in as digest sections.
        cwd = str(self.project.resolve())
        write_session(self.tdir / "dddd-4444.jsonl",
                      [human("2026-01-04T09:00:00Z", "dddd-4444", cwd, "Spec:\n## Vision\nShip it")])
        self.run_harvest()
        lines = (self.project / ".supervisor" / "harvest.md").read_text().splitlines()
        self.assertNotIn("## Vision", lines)
        self.assertIn("> ## Vision", lines)

    def test_sessions_lists_each_session_with_first_prompt(self):
        proc = subprocess.run([sys.executable, str(CLI), "sessions"], cwd=self.project, capture_output=True,
                              text=True, env={**os.environ, "CLAUDE_CONFIG_DIR": str(self.config)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("aaaa-1111", proc.stdout)
        self.assertIn("bbbb-2222", proc.stdout)
        self.assertIn("Build csvmd", proc.stdout)

    def test_criterion_source_is_recorded_and_shown_by_gate(self):
        subprocess.run([sys.executable, str(CLI), "init", "--objective", "audit"], cwd=self.project, check=True,
                       capture_output=True)
        subprocess.run([sys.executable, str(CLI), "criterion", "add", "Missing file exits 3", "--source", "H2"],
                       cwd=self.project, check=True, capture_output=True)
        state = json.loads((self.project / ".supervisor" / "state.json").read_text())
        self.assertEqual(state["criteria"]["AC1"]["source"], "H2")
        out = subprocess.run([sys.executable, str(CLI), "gate"], cwd=self.project, capture_output=True, text=True).stdout
        self.assertIn("[H2]", out)


# --------------------------------------------------------------------------- #
# v1.3: gaps found by the ECCode audit
# --------------------------------------------------------------------------- #
class TestUnverifiable(CliTestCase):
    """'Not yet proven' is not 'failed': ECCode's central claim had to be recorded as failed."""

    def setUp(self):
        super().setUp()
        self.init()
        self.run_cli("criterion", "add", "Core works", "Beats a bare agent on correctness")
        self.run_cli("criterion", "verify", "AC1", "--evidence", "test_core OK")

    def test_unverifiable_requires_reason(self):
        proc = self.run_cli("criterion", "unverifiable", "AC2", expect=2)
        self.assertIn("reason", proc.stderr.lower())

    def test_unverifiable_is_neither_passed_nor_failed(self):
        self.run_cli("criterion", "unverifiable", "AC2", "--reason", "needs paid model runs")
        self.assertEqual(self.state()["criteria"]["AC2"]["status"], "unverifiable")
        proc = self.run_cli("gate", expect=10)
        self.assertIn("PARTIALLY COMPLETE", proc.stdout)
        self.assertIn("could not be verified here", proc.stdout)
        self.assertIn("needs paid model runs", proc.stdout)
        self.assertNotIn("(failed)", proc.stdout)

    def test_unverifiable_shown_in_status_and_resume(self):
        self.run_cli("criterion", "unverifiable", "AC2", "--reason", "needs paid model runs")
        self.assertIn("needs paid model runs", self.run_cli("status").stdout)
        self.assertIn("AC2", self.run_cli("resume").stdout)


def _git(cwd, *args, date=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
                   cwd=cwd, check=True, capture_output=True, env=env)


class TestBranches(CliTestCase):
    """ECCode's default branch was 284 commits behind the real latest work, and the clone hid it."""

    def setUp(self):
        super().setUp()
        work = self.dir / "work"
        work.mkdir()
        _git(work, "init", "-q")
        (work / "a.txt").write_text("1\n")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "base")
        _git(work, "branch", "old/merged")
        (work / "a.txt").write_text("2\n")
        _git(work, "commit", "-qam", "main moves on")
        _git(work, "checkout", "-q", "-b", "feature/x")
        for i in range(3):
            (work / f"f{i}.txt").write_text("x\n")
            _git(work, "add", "-A")
            _git(work, "commit", "-q", "-m", f"feature step {i}")
        _git(work, "checkout", "-q", "main")
        self.origin = self.dir / "origin.git"
        _git(self.dir, "clone", "-q", "--bare", str(work), str(self.origin))
        self.full = self.dir / "full"
        _git(self.dir, "clone", "-q", f"file://{self.origin}", str(self.full))
        self.shallow = self.dir / "shallow"
        _git(self.dir, "clone", "-q", "--depth", "1", f"file://{self.origin}", str(self.shallow))

    def branches(self, cwd, *args, expect=0):
        proc = subprocess.run([sys.executable, str(CLI), "branches", *args], cwd=cwd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, expect, proc.stderr)
        return proc

    def test_lists_ahead_behind_and_flags_most_advanced(self):
        out = self.branches(self.full).stdout
        self.assertIn("default branch: origin/main", out)
        row = next(line for line in out.splitlines() if "feature/x" in line and "|" in line)
        self.assertIn("| 3 |", row)          # ahead
        self.assertIn("unmerged", row)
        self.assertIn("LATEST WORK", out)
        self.assertIn("feature/x is 3 commit(s) ahead", out)
        merged = next(line for line in out.splitlines() if "old/merged" in line and "|" in line)
        self.assertIn("merged", merged)
        self.assertNotIn("unmerged", merged)

    def test_shallow_clone_warns_and_lists_unfetched_branches_unasked(self):
        # With no other branch known locally, the remote is consulted automatically: this is the trap.
        out = self.branches(self.shallow).stdout
        self.assertIn("shallow", out.lower())
        self.assertIn("NOT fetched", out)
        self.assertIn("feature/x", out)
        self.assertNotIn("LATEST WORK", out)  # nothing can be compared until it is fetched

    def test_remote_flag_lists_unfetched_branches_in_a_partial_clone(self):
        _git(self.shallow, "fetch", "-q", "origin", "+refs/heads/old/merged:refs/remotes/origin/old/merged")
        self.assertNotIn("feature/x", self.branches(self.shallow).stdout)
        self.assertIn("feature/x", self.branches(self.shallow, "--remote").stdout)

    def test_fetch_makes_hidden_branches_visible(self):
        out = self.branches(self.shallow, "--fetch").stdout
        self.assertIn("feature/x is 3 commit(s) ahead", out)

    def test_latest_work_is_the_most_recent_unmerged_branch_not_the_longest(self):
        # ECCode: an October side line was 441 commits ahead; the real latest work (November) was 284 ahead.
        repo = self.dir / "dated"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "a.txt").write_text("1\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base", date="2026-01-01T10:00:00")
        _git(repo, "checkout", "-q", "-b", "old/long")
        for i in range(5):
            (repo / f"o{i}.txt").write_text("x\n")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", f"old {i}", date="2026-02-01T10:00:00")
        _git(repo, "checkout", "-q", "main")
        _git(repo, "checkout", "-q", "-b", "new/short")
        (repo / "n.txt").write_text("x\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "new work", date="2026-06-01T10:00:00")
        _git(repo, "checkout", "-q", "main")
        out = self.branches(repo).stdout
        latest = next(line for line in out.splitlines() if line.startswith("LATEST WORK"))
        self.assertIn("new/short", latest)
        self.assertIn("2026-06-01", latest)
        rows = [line for line in out.splitlines() if line.startswith("| ") and "/" in line]
        self.assertLess(rows.index(next(r for r in rows if "new/short" in r)),
                        rows.index(next(r for r in rows if "old/long" in r)))
        self.assertIn("old/long", out[out.index("LATEST WORK"):])  # the bigger, older line is still mentioned

    def test_not_a_git_repository_is_a_clean_error(self):
        plain = self.dir / "plain"
        plain.mkdir()
        proc = self.branches(plain, expect=1)
        self.assertIn("not a git repository", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class TestHarvestExtra(CliTestCase):
    """ECCode's 22 sessions lived in the cloud: harvest saw none of them."""

    def setUp(self):
        super().setUp()
        self.project = self.dir / "proj"
        self.project.mkdir()
        self.extra = self.dir / "cloud.jsonl"
        lines = [
            {"kind": "session", "id": "session_A", "title": "Toolkit build", "start": "2026-10-07T20:35:00Z",
             "end": "2026-10-08T10:05:00Z", "status": "blocked", "note": "needs API key token=abc123SECRETabc"},
            {"kind": "session", "id": "session_B", "title": "Stage 1 freeze", "start": "2026-11-09T18:59:00Z",
             "end": "2026-11-09T19:55:00Z", "status": "completed", "note": "Q-1..Q-5 await answers"},
            {"kind": "prompt", "session": "session_B", "timestamp": "2026-11-09T19:00:00Z",
             "text": "Freeze the base. Do not push without asking."},
            {"kind": "claim", "session": "session_B", "text": "Base frozen at fd344d5."},
        ]
        self.extra.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")

    def harvest(self, *args, expect=0):
        proc = subprocess.run(
            [sys.executable, str(CLI), "harvest", "--transcripts", str(self.dir / "none"), *args],
            cwd=self.project, capture_output=True, text=True)
        self.assertEqual(proc.returncode, expect, proc.stderr)
        return proc

    def test_extra_sessions_are_merged_numbered_and_redacted(self):
        self.harvest("--extra", str(self.extra))
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertIn("### H1", text)
        self.assertIn("Do not push without asking", text)
        self.assertIn("Base frozen at fd344d5", text)
        self.assertNotIn("abc123SECRETabc", text)

    def test_sessions_without_prompts_are_listed_as_not_covered(self):
        self.harvest("--extra", str(self.extra))
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertIn("prompts NOT read", text)
        section = text[text.index("prompts NOT read"):]
        self.assertIn("session_A", section)
        self.assertIn("Toolkit build", section)
        self.assertIn("blocked", section)
        self.assertIn("1 known session(s) whose prompts were not read", text)
        self.assertIn("1 unreadable line", text)

    def test_coverage_counts_sessions_by_final_status(self):
        # A hand count of "sessions waiting on the user" was wrong in a real audit (13 said, 14 true).
        self.harvest("--extra", str(self.extra))
        text = (self.project / ".supervisor" / "harvest.md").read_text()
        self.assertIn("Final status of the 2 known session(s): blocked 1, completed 1", text)

    def test_without_extra_and_without_local_history_still_exits_5(self):
        self.harvest(expect=5)


class TestEventsImport(CliTestCase):
    """A subagent had to retype long prompts from cloud session events; a parser copies them exactly."""

    def setUp(self):
        super().setUp()
        def ev(ts, role, content, **extra):
            return {"created_at": ts, role: {"uuid": ts, "internal_anthropic_catchall": {
                "message": {"role": role, "content": content}, **extra}}}
        page = {"ccr": {"data": [
            ev("2026-11-09T20:03:05Z", "user", "MASTER PROMPT: write addendum 3.\nDo not push.", client_platform="desktop_app"),
            ev("2026-11-09T20:04:00Z", "assistant", [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]),
            ev("2026-11-09T20:04:01Z", "user", [{"type": "tool_result", "content": "NOISE output"}], tool_use_result={"stdout": "NOISE"}),
            ev("2026-11-09T20:05:00Z", "user", "<task-notification>\nagent finished</task-notification>"),
            ev("2026-11-09T20:12:24Z", "user", "I authorize the push", client_platform="android"),
            ev("2026-11-09T20:12:37Z", "assistant", [{"type": "text", "text": "Pushed: origin/s4-add3/base is at 475b532."}]),
        ]}}
        self.page = self.dir / "page1.txt"
        self.page.write_text('<other-session nonce="x">\nwrapper text\n' + json.dumps(page) + "\n</other-session>")
        self.page2 = self.dir / "page2.txt"   # overlapping page: same first prompt again
        self.page2.write_text(json.dumps({"ccr": {"data": page["ccr"]["data"][:1]}}))
        self.out = self.dir / "cloud.jsonl"

    def test_extracts_typed_prompts_exactly_and_last_claim(self):
        self.run_cli("events", str(self.page), str(self.page2), "--session", "session_X", "--out", str(self.out))
        recs = [json.loads(line) for line in self.out.read_text().splitlines()]
        prompts = [r for r in recs if r["kind"] == "prompt"]
        self.assertEqual([p["text"] for p in prompts],
                         ["MASTER PROMPT: write addendum 3.\nDo not push.", "I authorize the push"])
        self.assertEqual(prompts[0]["timestamp"], "2026-11-09T20:03:05Z")
        self.assertTrue(all(r["session"] == "session_X" for r in recs))
        claims = [r for r in recs if r["kind"] == "claim"]
        self.assertEqual(len(claims), 1)
        self.assertIn("475b532", claims[0]["text"])
        self.assertNotIn("NOISE", self.out.read_text())
        self.assertNotIn("task-notification", self.out.read_text())

    def test_output_feeds_harvest_extra(self):
        self.run_cli("events", str(self.page), "--session", "session_X", "--out", str(self.out))
        proj = self.dir / "proj"
        proj.mkdir()
        proc = subprocess.run([sys.executable, str(CLI), "harvest", "--transcripts", str(self.dir / "none"),
                               "--extra", str(self.out)], cwd=proj, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        text = (proj / ".supervisor" / "harvest.md").read_text()
        self.assertIn("### H2", text)
        self.assertIn("I authorize the push", text)

    def test_raw_newlines_inside_strings_are_tolerated(self):
        # A real cloud page had unescaped line breaks inside message text; strict JSON rejects that.
        raw = '{"ccr":{"data":[{"created_at":"2026-10-07T22:50:00Z","user":{"message":{"role":"user","content":"line one\nline two"}}}]}}'
        raw = raw.replace("\\n", "\n")          # make the newline a raw control character
        self.assertIn("\n", raw)
        page = self.dir / "rawnl.txt"
        page.write_text(raw)
        self.run_cli("events", str(page), "--session", "session_Y", "--out", str(self.out))
        rec = json.loads(self.out.read_text().splitlines()[0])
        self.assertEqual(rec["text"], "line one\nline two")

    def test_events_nested_as_a_json_string_inside_a_text_block(self):
        # A second real save format: [{"type":"text","text":"<wrapper>{...events JSON...}</wrapper>"}]
        inner = json.loads(self.page.read_text().split("\n", 2)[2].rsplit("\n", 1)[0])
        wrapped = [{"type": "text", "text": '<other-session nonce="n">\nnote:\n    ' + json.dumps(inner) + "\n</other-session>"}]
        page = self.dir / "toolu_x.json"
        page.write_text(json.dumps(wrapped, indent=2))
        self.run_cli("events", str(page), "--session", "session_Z", "--out", str(self.out))
        recs = [json.loads(line) for line in self.out.read_text().splitlines()]
        self.assertEqual([r["text"] for r in recs if r["kind"] == "prompt"],
                         ["MASTER PROMPT: write addendum 3.\nDo not push.", "I authorize the push"])

    def test_file_without_events_is_a_clean_error(self):
        bad = self.dir / "bad.txt"
        bad.write_text("no json here")
        proc = self.run_cli("events", str(bad), "--session", "s", "--out", str(self.out), expect=1)
        self.assertIn("no session events", proc.stderr)


class TestClosedPipe(CliTestCase):
    """`supervisor.py branches | grep -q ...` printed a false "cannot write project memory" error."""

    def test_reader_closing_the_pipe_early_is_not_reported_as_a_memory_error(self):
        self.init()
        for i in range(30):
            self.run_cli("log", f"milestone {i}")
        proc = subprocess.Popen([sys.executable, str(CLI), "status"], cwd=self.dir, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env={**os.environ, "PYTHONUNBUFFERED": "1"})
        proc.stdout.close()                       # the reader goes away before anything is written
        err = proc.stderr.read().decode()
        proc.stderr.close()
        self.assertEqual(proc.wait(), 0, err)
        self.assertNotIn("cannot write project memory", err)
        self.assertNotIn("Traceback", err)
