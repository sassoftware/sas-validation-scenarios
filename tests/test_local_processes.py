"""Real subprocess lifecycle tests; no SAS credentials or browser installation needed."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import psutil
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "framework/python"))

from scenario_package import cli, local_processes as processes


@unittest.skipUnless(os.name == "posix", "Local runs require macOS or Linux")
class LocalProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patch = patch.object(processes, "user_state_path", return_value=self.root)
        self.patch.start()
        self.children = []
        self.logs = []
        self.pid_files = []

    def tearDown(self):
        for path in self.pid_files:
            if path.exists():
                for item in self.read_pids(path):
                    process = processes.matching_process(item)
                    if process is not None:
                        process.kill()
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
        for stream in self.logs:
            stream.close()
        self.patch.stop()
        self.temporary.cleanup()

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.02)
        self.fail("Timed out waiting for subprocess readiness")

    def read_pids(self, path):
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def start_run(self, exit_code=None, detached=False, with_parent=False, grace=0.4):
        pid_file = self.root / f"{uuid4()}.pids"
        self.pid_files.append(pid_file)
        write_pid = (
            "import json, os, signal, time, psutil; from pathlib import Path; "
            f"p=Path({str(pid_file)!r}); "
            "me=psutil.Process(); "
            "f=p.open('a'); f.write(json.dumps({'pid':me.pid,'created':me.create_time(),"
            "'group':os.getpgid(me.pid)})+'\\n'); f.close(); "
        )
        grandchild = write_pid + "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        worker = (
            write_pid + "import subprocess, sys; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"subprocess.Popen([sys.executable,'-c',{grandchild!r}]); time.sleep(60)"
        )
        task = (
            write_pid + "import subprocess, sys; "
            f"subprocess.Popen([sys.executable,'-c',{worker!r}],start_new_session={detached!r}); "
            "time.sleep(0.8); " + (f"sys.exit({exit_code})" if exit_code is not None else "time.sleep(60)")
        )
        launcher = (
            "import sys; from pathlib import Path; "
            "from scenario_package import local_processes as p; "
            f"p.user_state_path=lambda _:Path({str(self.root)!r}); "
            f"sys.exit(p.supervise([sys.executable,'-c',{task!r}],grace={grace!r}))"
        )
        output = (self.root / f"{uuid4()}.log").open("w+")
        self.logs.append(output)
        if with_parent:
            launcher = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable,'-c',{launcher!r}]); time.sleep(60)"
            )
        child = subprocess.Popen(
            [sys.executable, "-c", launcher], stdout=output, stderr=output,
            env=dict(os.environ, PYTHONPATH=str(ROOT / "framework/python")),
        )
        self.children.append(child)
        self.wait_for(lambda: pid_file.exists() and len(self.read_pids(pid_file)) == 3)
        members = self.read_pids(pid_file)
        records = self.wait_for(lambda: [
            record for record in processes.list_runs()
            if {item["pid"] for item in members}.issubset(
                {item["pid"] for item in record["members"]})
        ])
        return child, pid_file, records[0]["run_id"]

    def assert_gone(self, pid_file):
        for item in self.read_pids(pid_file):
            self.assertIsNone(processes.matching_process(item), f"Process survived: {item}")

    def test_success_and_failure_remove_stubborn_orphan_descendants(self):
        for exit_code in (0, 7):
            with self.subTest(exit_code=exit_code):
                started = time.monotonic()
                child, pid_file, run_id = self.start_run(exit_code=exit_code)
                self.assertEqual(exit_code, child.wait(timeout=6))
                self.assertGreaterEqual(time.monotonic() - started, 0.4)
                self.assertLess(time.monotonic() - started, 6)
                self.assert_gone(pid_file)
                self.assertFalse(processes.record_path(run_id).exists())

    def test_interrupt_signals_preserve_status_and_cleanup(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                child, pid_file, _ = self.start_run()
                child.send_signal(sig)
                self.assertEqual(128 + sig, child.wait(timeout=6))
                self.assert_gone(pid_file)

    def test_production_grace_period_before_forced_shutdown(self):
        self.assertEqual(15, processes.GRACE_SECONDS)
        child, pid_file, _ = self.start_run(grace=processes.GRACE_SECONDS)
        started = time.monotonic()
        child.terminate()
        self.assertEqual(143, child.wait(timeout=21))
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 15)
        self.assertLess(elapsed, 21)
        self.assert_gone(pid_file)

    def test_recorded_detached_descendants_are_cleaned(self):
        child, pid_file, _ = self.start_run(exit_code=7, detached=True)
        self.assertEqual(7, child.wait(timeout=6))
        self.assert_gone(pid_file)

    def test_parent_loss_triggers_automatic_cleanup(self):
        parent, pid_file, run_id = self.start_run(with_parent=True)
        supervisor = processes.read_record(run_id)
        self.pid_files.append(self.root / "supervisor.pid")
        self.pid_files[-1].write_text(json.dumps(next(
            item for item in supervisor["members"] if item["pid"] == supervisor["group"])) + "\n")
        parent.kill()
        parent.wait(timeout=5)
        self.wait_for(lambda: not processes.record_path(run_id).exists())
        self.assert_gone(pid_file)

    def test_manual_recovery_after_supervisor_killed_preserves_other_run(self):
        first, first_pids, run_id = self.start_run()
        second, second_pids, _ = self.start_run()
        first.kill()
        first.wait(timeout=5)
        processes.cleanup_run(run_id, grace=0.3)
        self.assert_gone(first_pids)
        self.assertIsNone(second.poll())
        self.assertTrue(all(processes.matching_process(item) for item in self.read_pids(second_pids)))
        second.terminate()
        second.wait(timeout=5)
        self.assert_gone(second_pids)

    def test_stale_identity_cannot_target_reused_pid(self):
        run_id = str(uuid4())
        me = processes.identity(psutil.Process())
        me["created"] -= 100
        record = {"run_id": run_id, "uid": os.getuid(), "group": os.getpgid(0),
                  "cwd": str(self.root), "members": [me]}
        processes.record_path(run_id).write_text(json.dumps(record))
        with patch.object(processes, "signal_members") as send:
            processes.cleanup_run(run_id, grace=0)
        send.assert_not_called()
        self.assertFalse(processes.record_path(run_id).exists())

    def test_invalid_records_are_reported(self):
        run_id = str(uuid4())
        processes.record_path(run_id).write_text("[]")
        result = CliRunner().invoke(cli.app, ["cleanup", "--local", "--run-id", run_id])
        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Invalid ownership record", result.output)

    def test_cli_previews_and_requires_explicit_stop_confirmation(self):
        child, pid_file, run_id = self.start_run()
        runner = CliRunner()
        preview = runner.invoke(cli.app, ["cleanup", "--local", "--run-id", run_id])
        self.assertEqual(0, preview.exit_code, preview.output)
        self.assertIn("Preview only", preview.output)
        self.assertIsNone(child.poll())
        declined = runner.invoke(
            cli.app, ["cleanup", "--local", "--run-id", run_id, "--stop"], input="n\n")
        self.assertEqual(0, declined.exit_code, declined.output)
        self.assertIsNone(child.poll())
        listed = runner.invoke(cli.app, ["cleanup", "--local", "--list"])
        self.assertEqual(0, listed.exit_code, listed.output)
        self.assertIn(run_id, listed.output)
        stopped = runner.invoke(
            cli.app, ["cleanup", "--local", "--run-id", run_id, "--stop", "--yes"])
        self.assertEqual(0, stopped.exit_code, stopped.output)
        child.wait(timeout=5)
        self.assert_gone(pid_file)


if __name__ == "__main__":
    unittest.main()
