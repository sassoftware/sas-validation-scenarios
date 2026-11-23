"""Behavioral tests for the generated runWorkload.sh status/verdict logic.

The script is generated with createRunWorkloadScript.py and executed against stub
`kubectl`, `yq` and `sleep` commands so no cluster is required.
"""

import base64
import gzip
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import psutil

REPOSITORY_ROOT = Path(__file__).parent.parent
FRAMEWORK = REPOSITORY_ROOT / "framework"
GENERATOR = FRAMEWORK / "python" / "createRunWorkloadScript.py"
TEMPLATES = FRAMEWORK / "python" / "templates"
BASH = shutil.which("bash")

KUBECTL_STUB = r"""#!/usr/bin/env bash
echo "kubectl $*" >> "$STUB_CALLS"
args=" $* "
state_dir="$(dirname "$STUB_CALLS")"
case "$args" in
  *" get namespace "*)
    if [ -n "$STUB_MISSING_NS" ]; then
      echo 'Error from server (NotFound): namespaces "validation-scenarios" not found' >&2; exit 1
    fi
    echo "validation-scenarios Active"; exit 0 ;;
  *" api-resources "*)
    [ -z "$STUB_NO_CRD" ] && echo "locusttests.locust.io"; exit 0 ;;
  *" apply "*)
    [ -n "$STUB_APPLY_FAIL" ] && { echo "error: resource mapping not found" >&2; exit 1; }
    exit 0 ;;
  *"--for=condition=ready"*) exit 0 ;;
  *" get pod -l job-name="*"-test-master "*"containerStatuses"*)
    name=$(echo "$args" | sed -E 's/.*job-name=([^ ]+)-test-master.*/\1/')
    echo "locust-metrics-exporter="; echo "$name-test-master=${STUB_MASTER_EXIT-}"; exit 0 ;;
  *" get pod -l job-name="*"-test-master "*)
    if [ -n "$STUB_PODS_AFTER" ]; then
      counter="$state_dir/pods-polls"
      n=$(( $(cat "$counter" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$counter"
      [ "$n" -le "$STUB_PODS_AFTER" ] && exit 0
    fi
    name=$(echo "$args" | sed -E 's/.*job-name=([^ ]+)-test-master.*/\1/'); echo "$name-test-master-abc"; exit 0 ;;
  *" get pod -l job-name="*"-test-worker "*)
    name=$(echo "$args" | sed -E 's/.*job-name=([^ ]+)-test-worker.*/\1/'); echo "$name-test-worker-def"; exit 0 ;;
  *" logs "*)
    [ -n "$STUB_NO_LOGS" ] && exit 1
    case "$args" in
      *" -f "*) echo "live capture (partial)"; exit 0 ;;
      *"-test-master"*)
        echo "[INFO] The last worker quit, stopping test."
        echo "Duration of the Total test run: 0:01:05.069188"
        echo "Type     Name   # reqs      # fails"
        echo "Error report"
        echo "# occurrences      Error"
        [ -n "$STUB_LOG_ERROR" ] && echo "Traceback (most recent call last): boom"
        [ -z "$STUB_NO_RESULTS" ] && cat "$STUB_RESULTS_FILE"
        exit 0 ;;
      *) echo "worker log"; exit 0 ;;
    esac ;;
  *" get locusttests.locust.io,pod"*) echo "NAME STATUS"; exit 0 ;;
  *" get locusttests.locust.io "*)
    if [ -n "$STUB_PHASE_SEQUENCE" ]; then
      name=$(echo "$args" | sed -E 's/.*locusttests\.locust\.io ([^ ]+)\.test.*/\1/')
      counter="$state_dir/phase-$name"
      n=$(( $(cat "$counter" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$counter"
      phase=$(echo "$STUB_PHASE_SEQUENCE" | tr ',' '\n' | sed -n "${n}p")
      [ -z "$phase" ] && phase=$(echo "$STUB_PHASE_SEQUENCE" | tr ',' '\n' | tail -1)
      echo "$phase"; exit 0
    fi
    echo "${STUB_PHASE-Succeeded}"; exit 0 ;;
  *" get job "*"-test-worker "*"failed"*) echo "${STUB_WORKER_FAILED-}"; exit 0 ;;
  *" get job "*) exit 0 ;;
  *" delete "*) exit 0 ;;
esac
exit 0
"""


def encode_csv(text):
    return base64.b64encode(gzip.compress(text.encode("utf-8"), mtime=0)).decode("ascii")


STATS_CSV = "Type,Name,Request Count,Failure Count\nGET,/x,5,0\n,Aggregated,5,0\n"
FAILURES_HEADER = "Method,Name,Error,Occurrences\n"
EXCEPTIONS_CSV = "Count,Message,Traceback,Nodes\n"


@unittest.skipIf(BASH is None or os.name == "nt", "bash is required")
class RunWorkloadScriptTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.output = self.root / "workload"
        self.resources = self.output / "resources"
        self.resources.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.log"

        self._write_exec(self.bin / "kubectl", KUBECTL_STUB)
        self._write_exec(self.bin / "yq", "#!/usr/bin/env bash\necho '--users 3'\n")
        self._write_exec(self.bin / "sleep", '#!/usr/bin/env bash\necho "sleep $*" >> "$STUB_CALLS"\nexit 0\n')
        self.deploy = self.output / "deployTaskResourcesAsConfigMap.sh"
        self._write_exec(self.deploy, "#!/usr/bin/env bash\nexit ${STUB_DEPLOY_RC:-0}\n")

        self.results = self.root / "master-results.txt"
        self._write_results()

        self.workloads = ["wl-a", "wl-b"]
        for name in self.workloads:
            (self.resources / f"k8s-cr-{name}.yaml").write_text("kind: LocustTest\n")
        self._generate()

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _write_exec(path, content):
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        path.chmod(0o755)

    def _write_results(self, failure_rows=False, exit_code=0):
        failures = FAILURES_HEADER + ("GET,/x,500,3\n" if failure_rows else "")
        self.results.write_text(
            f"SAS_VALIDATION_RESULT stats {encode_csv(STATS_CSV)}\n"
            f"SAS_VALIDATION_RESULT failures {encode_csv(failures)}\n"
            f"SAS_VALIDATION_RESULT exceptions {encode_csv(EXCEPTIONS_CSV)}\n"
            f"SAS_VALIDATION_RESULT exit_code {exit_code}\n"
        )

    def _generate(self, timeout="60s"):
        spec = {
            "namespace": "validation-scenarios",
            "config-map-name": "wl-map",
            "timeout": timeout,
            "workloads": [{"name": name, "task": f"{name}.py"} for name in self.workloads],
        }
        env = dict(
            os.environ,
            frameworkResourcesLocation=str(FRAMEWORK),
            hostname="https://viya.example.com",
            customResourceSpec=json.dumps(spec),
            frameworkDefaults="{}",
        )
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                "-t", str(TEMPLATES / "run-workload.sh.template"),
                "-ht", str(TEMPLATES / "run-workload-log-header.sh.template"),
                "-r", str(self.resources),
                "-o", str(self.output),
            ],
            check=True,
            env=env,
            capture_output=True,
        )
        self.script = self.output / "runWorkload.sh"

    def _run(self, **stub_env):
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", STUB_CALLS=str(self.calls),
                   STUB_RESULTS_FILE=str(self.results))
        env.update({key: str(value) for key, value in stub_env.items()})
        completed = subprocess.run(
            [BASH, str(self.script)],
            cwd=self.output,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return completed, completed.stdout + completed.stderr

    def test_generated_script_is_valid_bash(self):
        subprocess.run([BASH, "-n", str(self.script)], check=True)
        contents = self.script.read_text()
        self.assertIn("ALL_WORKLOADS=(wl-a wl-b)", contents)
        self.assertIn("|| fail_infra", contents)
        self.assertIn("print_summary", contents)

    def test_run_reaps_its_log_writer_on_success_failure_and_interruption(self):
        real_tee = shutil.which("tee")
        real_sleep = shutil.which("sleep")
        self.assertIsNotNone(real_tee)
        self.assertIsNotNone(real_sleep)
        self._write_exec(
            self.bin / "sleep",
            '#!/usr/bin/env bash\n'
            f'if [ "$1" = "0.1" ]; then exec {shlex.quote(real_sleep)} "$@"; fi\n',
        )
        self._write_exec(
            self.deploy,
            '#!/usr/bin/env bash\n'
            '[ -n "$STUB_INTERRUPT" ] && kill -TERM "$PPID"\n'
            'exit 0\n',
        )
        cases = [
            ({}, 0, False),
            ({"STUB_MISSING_NS": "1"}, 2, False),
            ({"STUB_INTERRUPT": "1"}, 130, False),
            ({}, 0, True),
        ]
        for stub_env, expected_rc, stalled in cases:
            with self.subTest(stub_env=stub_env, stalled=stalled):
                pid_file = self.root / "tee.pid"
                self._write_exec(
                    self.bin / "tee",
                    '#!/usr/bin/env bash\n'
                    f'echo "$$" > {shlex.quote(str(pid_file))}\n'
                    f'{shlex.quote(real_tee)} "$@"\n'
                    # Keep the writer observable after EOF even on hosts that reap orphans.
                    f'exec {shlex.quote(real_sleep)} {30 if stalled else 0.5}\n',
                )
                writer = None
                try:
                    env = dict(
                        os.environ,
                        PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        STUB_CALLS=str(self.calls),
                        STUB_RESULTS_FILE=str(self.results),
                        **stub_env,
                    )
                    # A file, unlike communicate()'s pipe, does not wait for orphaned writers.
                    with tempfile.TemporaryFile(mode="w+") as captured:
                        completed = subprocess.run(
                            [BASH, str(self.script)], cwd=self.output, env=env,
                            stdout=captured, stderr=subprocess.STDOUT, timeout=60,
                        )
                        captured.seek(0)
                        output = captured.read()
                    self.assertTrue(pid_file.exists(), "Run did not start its log writer")
                    try:
                        writer = psutil.Process(int(pid_file.read_text()))
                    except psutil.NoSuchProcess:
                        pass
                    self.assertIsNone(writer, "Run left its log writer behind")
                    self.assertEqual(completed.returncode, expected_rc, output)
                    logs = list((self.output / "execution-logs").glob("runWorkload_*.log"))
                    self.assertTrue(logs)
                    marker = "Interrupted." if stub_env.get("STUB_INTERRUPT") else "WORKLOAD SUMMARY"
                    self.assertTrue(any(marker in log.read_text() for log in logs))
                    self.assertEqual("forcing the run log writer" in output, stalled, output)
                finally:
                    if writer is not None:
                        try:
                            writer.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            writer.kill()
                            writer.wait(timeout=3)

    def test_healthy_run_passes(self):
        completed, output = self._run()
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("wl-a TESTS PASSED", output)
        self.assertIn("wl-b TESTS PASSED", output)
        self.assertIn("OVERALL: PASSED", output)
        calls = self.calls.read_text()
        self.assertIn("kubectl -n validation-scenarios delete configmap wl-map", calls)
        # A stale configmap is removed before deploying, and again by the EXIT trap.
        self.assertEqual(calls.count("delete configmap wl-map"), 2)

    def test_no_fixed_pauses_and_short_phase_poll(self):
        completed, output = self._run(STUB_PHASE_SEQUENCE="Running,Running,Succeeded")
        self.assertEqual(completed.returncode, 0, output)
        sleeps = [line for line in self.calls.read_text().splitlines() if line.startswith("sleep ")]
        self.assertIn("sleep 2", sleeps)
        self.assertEqual(sorted(set(sleeps)), ["sleep 2"], sleeps)

    def test_waits_for_pods_to_exist_before_ready_wait(self):
        completed, output = self._run(STUB_PODS_AFTER=3)
        self.assertEqual(completed.returncode, 0, output)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(calls.count("sleep 1"), 3, calls)
        first_ready = next(i for i, c in enumerate(calls) if "--for=condition=ready" in c)
        last_poll_sleep = max(i for i, c in enumerate(calls) if c == "sleep 1")
        self.assertLess(last_poll_sleep, first_ready)
        self.assertIn("wl-a TESTS PASSED", output)

    def test_summary_reports_durations(self):
        completed, output = self._run()
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("DURATIONS (H:MM:SS)", output)
        self.assertRegex(output, r"wl-a\s+0:01:05\s+\d+:\d{2}:\d{2}")
        self.assertRegex(output, r"wl-b\s+0:01:05\s+\d+:\d{2}:\d{2}")
        self.assertRegex(output, r"TOTAL RUN\s+\d+:\d{2}:\d{2}")

    def test_aborted_workload_has_elapsed_but_no_test_run(self):
        completed, output = self._run(STUB_APPLY_FAIL=1)
        self.assertEqual(completed.returncode, 2, output)
        self.assertRegex(output, r"wl-a\s+-\s+\d+:\d{2}:\d{2}")
        self.assertIn("TOTAL RUN", output)

    def test_results_are_decoded_from_master_log_without_kubectl_cp(self):
        completed, output = self._run()
        self.assertEqual(completed.returncode, 0, output)
        self.assertNotIn(" cp ", self.calls.read_text())
        stats = self.output / "results" / "3-wl-a.csv"
        failures = self.output / "execution-logs" / "3-wl-a-failures.csv"
        self.assertEqual(stats.read_text(), STATS_CSV)
        self.assertEqual(failures.read_text(), FAILURES_HEADER)
        merged = (self.output / "execution-logs" / "wl-a_merged.log").read_text()
        self.assertNotIn("SAS_VALIDATION_RESULT", merged)

    def test_cr_is_deleted_only_after_logs_are_fetched(self):
        self._run()
        calls = self.calls.read_text().splitlines()
        fetch = max(i for i, c in enumerate(calls) if " logs wl-a-test-master-abc -c " in c)
        delete = next(i for i, c in enumerate(calls) if "delete -f" in c and "k8s-cr-wl-a" in c)
        self.assertLess(fetch, delete)

    def test_missing_namespace_aborts_without_passing(self):
        completed, output = self._run(STUB_MISSING_NS=1)
        self.assertEqual(completed.returncode, 2, output)
        self.assertNotIn("TESTS PASSED", output)
        self.assertIn("INFRASTRUCTURE ERROR", output)
        self.assertIn("NOT RUN", output)
        self.assertNotIn(" apply ", self.calls.read_text())

    def test_missing_crd_aborts(self):
        completed, output = self._run(STUB_NO_CRD=1)
        self.assertEqual(completed.returncode, 2, output)
        self.assertIn("locusttests.locust.io", output)
        self.assertNotIn("TESTS PASSED", output)

    def test_configmap_deploy_failure_aborts(self):
        completed, output = self._run(STUB_DEPLOY_RC=1)
        self.assertEqual(completed.returncode, 2, output)
        self.assertIn("Failed to deploy configmap", output)

    def test_apply_failure_marks_error_and_aborts(self):
        completed, output = self._run(STUB_APPLY_FAIL=1)
        self.assertEqual(completed.returncode, 2, output)
        self.assertRegex(output, r"wl-a\s+ERROR")
        self.assertRegex(output, r"wl-b\s+NOT RUN")
        self.assertNotIn("TESTS PASSED", output)

    def test_failure_rows_fail_the_workload(self):
        self._write_results(failure_rows=True)
        completed, output = self._run()
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("wl-a TESTS FAILED", output)
        self.assertIn("failure row(s)", output)
        self.assertIn("OVERALL: FAILED", output)

    def test_master_failed_phase_fails_the_workload(self):
        self._write_results(exit_code=1)
        completed, output = self._run(STUB_PHASE="Failed")
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("Locust master failed (LocustTest phase: Failed, exit code 1)", output)

    def test_nonzero_published_exit_code_fails_the_workload(self):
        self._write_results(exit_code=1)
        completed, output = self._run()
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("Locust master reported exit code 1", output)

    def test_master_finishing_later_passes(self):
        completed, output = self._run(STUB_PHASE_SEQUENCE="Pending,Running,Running,Succeeded")
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("wl-a TESTS PASSED", output)
        self.assertNotIn("did not finish", output)

    def test_master_stuck_running_fails_after_workload_timeout(self):
        self._generate(timeout="0s")
        completed, output = self._run(STUB_PHASE="Running")
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("Locust test did not finish within 0s (LocustTest phase: Running)", output)

    def test_missing_published_results_fail_the_workload(self):
        completed, output = self._run(STUB_NO_RESULTS=1)
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("master did not publish results", output)
        self.assertNotIn("TESTS PASSED", output)

    def test_master_container_exit_decides_when_operator_phase_is_stuck(self):
        # locust-k8s-operator <= 2.2.3: the exporter container never exits, so the phase stays Pending.
        completed, output = self._run(STUB_PHASE="Pending", STUB_MASTER_EXIT=0)
        self.assertEqual(completed.returncode, 0, output)
        self.assertIn("wl-a LocustTest phase: Succeeded", output)
        self.assertIn("OVERALL: PASSED", output)

    def test_master_container_nonzero_exit_fails_when_operator_phase_is_stuck(self):
        self._write_results(exit_code=1)
        completed, output = self._run(STUB_PHASE="Pending", STUB_MASTER_EXIT=1)
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("Locust master failed", output)

    def test_failed_worker_pods_fail_the_workload(self):
        completed, output = self._run(STUB_WORKER_FAILED=1)
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("worker job reported 1 failed pod(s)", output)

    def test_error_lines_in_logs_fail_the_workload(self):
        completed, output = self._run(STUB_LOG_ERROR=1)
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("error line(s) in pod logs", output)

    def test_missing_logs_is_not_a_pass(self):
        completed, output = self._run(STUB_NO_LOGS=1)
        self.assertEqual(completed.returncode, 1, output)
        self.assertIn("no Locust master log was collected", output)
        self.assertNotIn("TESTS PASSED", output)


if __name__ == "__main__":
    unittest.main()
