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
