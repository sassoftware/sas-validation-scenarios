# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for running workloads with Locust on this machine (sas-validation run --local)."""

import base64
import gzip
import importlib.util
import io
import json
import os
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml
import psutil
from typer.testing import CliRunner

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "framework/python"))

from scenario_package import cli, preflight  # noqa: E402
from scenario_package.config import load_scenario_package_defaults  # noqa: E402
from scenario_package.loader import ScenarioPackage  # noqa: E402
from scenario_package.manifest import ManifestError, ScenarioManifest  # noqa: E402
from scenario_package.preflight import core, local_checks  # noqa: E402
from scenario_package.preflight.core import PreflightContext, Status  # noqa: E402

FIXTURE = REPOSITORY_ROOT / "tests/fixtures/helloviya-simple"
FRAMEWORK = REPOSITORY_ROOT / "framework"
TEMPLATES = FRAMEWORK / "python/templates"
LOCAL_GENERATOR = FRAMEWORK / "python/createLocalArtifacts.py"
BASH = shutil.which("bash")


def _plugin(root: Path, extra_dependencies=(), execution_targets=None) -> Path:
    """Copy the fixture plugin, keeping only the framework 'common' files that exist."""
    shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
    config = root / "scenarios/helloviya-simple/scenario-config.yaml"
    values = yaml.safe_load(config.read_text(encoding="utf-8"))
    common_root = FRAMEWORK / "execution/common"
    values["scenario-config"]["dependencies"] = [
        dependency
        for dependency in values["scenario-config"]["dependencies"]
        if dependency.get("type") != "common" or (common_root / dependency["file"]).is_file()
    ] + list(extra_dependencies)
    if execution_targets is not None:
        values["scenario-config"]["execution-targets"] = execution_targets
    config.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
    return root


def _users_file(root: Path) -> Path:
    path = root / "users.csv"
    path.write_text("user1,pass1\nuser2,pass2\n", encoding="utf-8")
    return path


class LocalGenerationTests(unittest.TestCase):
    def _generate(self, root: Path, local_options=None, extra_dependencies=(), trusted_certs=None,
                  users_file=True):
        plugin = _plugin(root / "plugin", extra_dependencies)
        return ScenarioPackage(plugin).generate(
            "helloviya-simple",
            root / "output",
            FRAMEWORK,
            hostname="https://viya.example.com/",
            trusted_certs=trusted_certs,
            namespace=None,
            users_file=_users_file(root) if users_file else None,
            log_level="ERROR",
            execution_target="local",
            local_options=local_options,
        ).generated_workload_root / "helloviya-simple"

    def test_stages_sources_and_creates_only_the_local_script(self):
        with tempfile.TemporaryDirectory() as directory:
            workload_root = self._generate(Path(directory))
            staged = sorted(path.name for path in (workload_root / "local/src").iterdir())
            script = workload_root / "runWorkloadLocal.sh"
            contents = script.read_text()
            subprocess.run([BASH, "-n", str(script)], check=True)
            executable = os.access(script, os.X_OK)
            kubernetes_artifacts = [
                path.name
                for path in workload_root.rglob("*")
                if path.name in ("runWorkload.sh", "deployTaskResourcesAsConfigMap.sh")
                or path.name.startswith("k8s-cr-")
            ]
            global_config = yaml.safe_load((Path(directory) / "output/global-config.yaml").read_text())

        self.assertTrue(executable)
        self.assertEqual([], kubernetes_artifacts)
        for name in ("createcompute.py", "logonoff.py", "events.py", "exception.py",
                     "scenario_utils.py", "users.csv"):
            self.assertIn(name, staged)
        self.assertEqual("local", global_config["global-config"]["execution-target"])
        self.assertIn("ALL_WORKLOADS=(logonoff createcompute)", contents)
        self.assertIn("--locustfile logonoff.py --host https://viya.example.com --headless --users 1", contents)
        self.assertIn("--processes 1", contents)
        self.assertNotIn("--csv", contents)
        self.assertIn('HEADLESS="${SAS_VALIDATION_HEADLESS:-true}"', contents)
        self.assertNotIn("kubectl", contents)

    def test_headed_and_processes_options(self):
        with tempfile.TemporaryDirectory() as directory:
            contents = (
                self._generate(Path(directory), local_options={"headed": True, "processes": 3})
                / "runWorkloadLocal.sh"
            ).read_text()

        self.assertIn('HEADLESS="${SAS_VALIDATION_HEADLESS:-false}"', contents)
        self.assertIn("--processes 3", contents)

    def test_artifact_generation_reaps_its_log_writer_on_success_and_failure(self):
        real_tee = shutil.which("tee")
        self.assertIsNotNone(real_tee)
        for users_file in (True, False):
            with self.subTest(users_file=users_file), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bin_dir = root / "bin"
                bin_dir.mkdir()
                pid_file = root / "tee.pid"
                wrapper = bin_dir / "tee"
                wrapper.write_text(
                    "#!/usr/bin/env bash\n"
                    f'echo "$$" > {shlex.quote(str(pid_file))}\n'
                    f'{shlex.quote(real_tee)} "$@"\n'
                    # Keep the writer observable after EOF even on hosts that reap orphans.
                    "sleep 1\n",
                    encoding="utf-8",
                )
                wrapper.chmod(0o755)
                writer = None
                try:
                    with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}):
                        if users_file:
                            self._generate(root)
                        else:
                            with self.assertRaises(ManifestError):
                                self._generate(root, users_file=False)
                    self.assertTrue(pid_file.exists(), "Generation did not start its log writer")
                    try:
                        writer = psutil.Process(int(pid_file.read_text()))
                    except psutil.NoSuchProcess:
                        continue
                    self.fail(f"Artifact generator left its log writer behind: PID {writer.pid}")
                finally:
                    if writer is not None:
                        try:
                            writer.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            writer.kill()
                            writer.wait(timeout=3)

    def test_generated_dependencies_are_staged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificates = root / "my-ca.pem"
            certificates.write_text("certificate", encoding="utf-8")
            workload_root = self._generate(
                root,
                extra_dependencies=[{"type": "config-json"}, {"type": "trusted-certs"}],
                trusted_certs=certificates,
            )
            src = workload_root / "local/src"
            profile = json.loads((src / "config.json").read_text())
            pem = (src / "trustedcerts.pem").read_text()

        self.assertEqual("https://viya.example.com", profile["Default"]["sas-endpoint"])
        self.assertEqual("certificate", pem)

    def test_users_file_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ManifestError, "failed"):
                self._generate(Path(directory), users_file=False)

    def test_kubernetes_generation_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = _plugin(root / "plugin")
            workload_root = ScenarioPackage(plugin).generate(
                "helloviya-simple", root / "output", FRAMEWORK,
                hostname="https://viya.example.com", namespace="testing", log_level="ERROR",
            ).generated_workload_root / "helloviya-simple"
            global_config = yaml.safe_load((root / "output/global-config.yaml").read_text())

            self.assertTrue((workload_root / "runWorkload.sh").is_file())
            self.assertFalse((workload_root / "runWorkloadLocal.sh").exists())
            self.assertFalse((workload_root / "local").exists())
        self.assertNotIn("execution-target", global_config["global-config"])

    def test_unknown_execution_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ManifestError, "Unknown execution target"):
                ScenarioPackage(_plugin(root / "plugin")).prepare(
                    "helloviya-simple", root / "output", FRAMEWORK, execution_target="cloud"
                )


class RunWorkloadSelectionTests(unittest.TestCase):
    def _generated(self, root: Path, names):
        generated = root / "generated" / "helloviya-simple"
        generated.mkdir(parents=True)
        for name in names:
            script = generated / name
            script.write_text(f"#!/usr/bin/env bash\necho {name}\nexit 7\n", encoding="utf-8")
            script.chmod(0o755)
        return root / "generated"

    def test_local_runs_the_local_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = ScenarioPackage(_plugin(root / "plugin"))
            generated = self._generated(root, ["runWorkload.sh", "runWorkloadLocal.sh"])
            with patch("scenario_package.loader.subprocess.Popen") as popen:
                popen.return_value.wait.return_value = 7
                popen.return_value.poll.return_value = 7
                self.assertEqual(7, package.run_workload("helloviya-simple", generated, local=True))
                self.assertTrue(popen.call_args[0][0][0].endswith("runWorkloadLocal.sh"))
            with patch("scenario_package.loader.subprocess.run") as run:
                run.return_value = SimpleNamespace(returncode=7)
                package.run_workload("helloviya-simple", generated)
                self.assertTrue(run.call_args[0][0][0].endswith("/runWorkload.sh"))

    def test_missing_local_script_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = ScenarioPackage(_plugin(root / "plugin"))
            generated = self._generated(root, ["runWorkload.sh"])
            with self.assertRaisesRegex(ManifestError, "local workload script does not exist"):
                package.run_workload("helloviya-simple", generated, local=True)


class ExecutionTargetsTests(unittest.TestCase):
    def test_scenarios_restricted_to_kubernetes_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage(_plugin(Path(directory) / "plugin", execution_targets=["kubernetes"]))
            self.assertEqual(
                ["helloviya-simple/scenario-config.yaml"],
                package.unsupported_scenarios("helloviya-simple", "local"),
            )
            self.assertEqual([], package.unsupported_scenarios("helloviya-simple", "kubernetes"))

    def test_scenarios_without_targets_run_everywhere(self):
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage(_plugin(Path(directory) / "plugin"))
            self.assertEqual([], package.unsupported_scenarios("helloviya-simple", "local"))

    def test_invalid_targets_make_the_plugin_invalid(self):
        from scenario_package.plugins import validate_plugin

        with tempfile.TemporaryDirectory() as directory:
            plugin = _plugin(Path(directory) / "plugin", execution_targets=["cloud"])
            errors = validate_plugin(plugin)
        self.assertTrue(any("unknown value(s) cloud" in error for error in errors), errors)

    def test_manifest_parses_and_validates_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario-config.yaml"
            base = {"id": "x", "display-name": "X", "runtime": "locust", "entrypoints": ["tests/a.py"]}
            path.write_text(yaml.safe_dump({"scenario-config": dict(base, **{"execution-targets": "local"})}))
            manifest = ScenarioManifest.from_file(path)
            self.assertEqual(["local"], manifest.execution_targets)
            self.assertTrue(manifest.supports_target("local"))
            self.assertFalse(manifest.supports_target("kubernetes"))

            path.write_text(yaml.safe_dump({"scenario-config": dict(base, **{"execution-targets": ["cloud"]})}))
            with self.assertRaisesRegex(ManifestError, "unknown value"):
                ScenarioManifest.from_file(path)

            path.write_text(yaml.safe_dump({"scenario-config": base}))
            self.assertIsNone(ScenarioManifest.from_file(path).execution_targets)


class ConfigTests(unittest.TestCase):
    def test_users_file_is_resolved_relative_to_the_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text("sas-validation:\n  execution:\n    users-file: users.csv\n")
            defaults = load_scenario_package_defaults(config)
        self.assertEqual(Path(directory) / "users.csv", defaults.users_file)


def encode_csv(text):
    return base64.b64encode(gzip.compress(text.encode("utf-8"), mtime=0)).decode("ascii")


LOCUST_STUB = r"""#!/usr/bin/env bash
{
  echo "args: $*"
  echo "cwd: $PWD"
  echo "headless: $SAS_VALIDATION_HEADLESS"
  echo "users_file: $SAS_VALIDATION_USERS_FILE"
} >> "$STUB_CALLS"
if [ -n "$STUB_TREE_FILE" ]; then
  "$STUB_PYTHON" -c 'import os, time; from pathlib import Path; Path(os.environ["STUB_TREE_FILE"]).write_text(str(os.getpid())); time.sleep(60)' &
fi
if [ -n "$STUB_HANG" ]; then
  trap 'echo terminated >> "$STUB_CALLS"; exit 143' TERM
  while :; do sleep 0.2; done
fi
echo "Duration of the Total test run: 0:00:05.123"
[ -n "$STUB_LOG_ERROR" ] && echo "Traceback (most recent call last): boom"
[ -z "$STUB_NO_RESULTS" ] && cat "$STUB_RESULTS_FILE"
exit ${STUB_EXIT:-0}
"""


@unittest.skipIf(BASH is None or os.name == "nt", "bash is required")
class RunWorkloadLocalScriptTests(unittest.TestCase):
    """runWorkloadLocal.sh is executed against a stub `locust`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.output = self.root / "workload"
        self.resources = self.output / "resources"
        self.resources.mkdir(parents=True)
        (self.resources / "users.csv").write_text("user1,pass1\n")
        self.scenarios = self.root / "scenarios"
        (self.scenarios / "demo/tests").mkdir(parents=True)
        for name in ("wl-a", "wl-b"):
            (self.scenarios / "demo/tests" / f"{name}.py").write_text("# task\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls.log"
        self.results = self.root / "results.txt"
        stub = self.bin / "locust"
        stub.write_text(textwrap.dedent(LOCUST_STUB))
        stub.chmod(0o755)
        self._write_results()
        self._generate()

    def tearDown(self):
        self._tmp.cleanup()

    def _write_results(self, failure_rows=False):
        failures = "Method,Name,Error,Occurrences\n" + ("GET,/x,500,3\n" if failure_rows else "")
        self.results.write_text(
            f"SAS_VALIDATION_RESULT stats {encode_csv('Type,Name\nGET,/x\n')}\n"
            f"SAS_VALIDATION_RESULT failures {encode_csv(failures)}\n"
            f"SAS_VALIDATION_RESULT exceptions {encode_csv('Count,Message\n')}\n"
            "SAS_VALIDATION_RESULT exit_code 0\n"
        )

    def _generate(self, timeout="60s", local_execution=None):
        spec = {
            "timeout": timeout,
            "workloads": [
                {"name": name, "path": "demo/tests", "task": f"{name}.py", "users": 2,
                 "spawn-rate": 1, "iterations": 1, "run-time": "5m"}
                for name in ("wl-a", "wl-b")
            ],
            "custom-modules": [],
        }
        env = dict(
            os.environ,
            scenariosLocationFullPath=str(self.scenarios),
            hostname="https://viya.example.com",
            customResourceSpec=json.dumps(spec),
            localExecution=json.dumps(local_execution or {"headed": False, "processes": None}),
        )
        subprocess.run(
            [sys.executable, str(LOCAL_GENERATOR),
             "-t", str(TEMPLATES / "run-workload-local.sh.template"),
             "-ht", str(TEMPLATES / "run-workload-local-header.sh.template"),
             "-r", str(self.resources), "-o", str(self.output)],
            check=True, env=env, capture_output=True,
        )
        self.script = self.output / "runWorkloadLocal.sh"

    def _environment(self, **stub_env):
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                   STUB_CALLS=str(self.calls), STUB_RESULTS_FILE=str(self.results))
        env.pop("SAS_VALIDATION_HEADLESS", None)
        env.update({key: str(value) for key, value in stub_env.items()})
        return env

    def _run(self, **stub_env):
        env = self._environment(**stub_env)
        completed = subprocess.run([BASH, str(self.script)], cwd=self.output, env=env,
                                   capture_output=True, text=True, timeout=90)
        return completed, completed.stdout + completed.stderr

    def test_healthy_run_passes_and_collects_results(self):
        completed, output = self._run()
        self.assertEqual(0, completed.returncode, output)
        self.assertIn("wl-a TESTS PASSED", output)
        self.assertIn("wl-b TESTS PASSED", output)
        self.assertIn("OVERALL: PASSED", output)
        self.assertNotIn("SAS_VALIDATION_RESULT", output)
        self.assertEqual("Type,Name\nGET,/x\n", (self.output / "results/2-wl-a.csv").read_text())
        self.assertTrue((self.output / "execution-logs/2-wl-b-failures.csv").is_file())
        calls = self.calls.read_text()
        self.assertIn("args: --locustfile wl-a.py --host https://viya.example.com --headless --users 2 "
                      "--spawn-rate 1 --iterations 1 --run-time 5m --processes 2 --only-summary", calls)
        self.assertIn(f"cwd: {self.output / 'local/src'}", calls)
        self.assertIn("headless: true", calls)
        self.assertIn("users_file: " + str(self.output / "local/src/users.csv"), calls)

    def test_headless_can_be_overridden_when_running(self):
        completed, output = self._run(SAS_VALIDATION_HEADLESS="false")
        self.assertEqual(0, completed.returncode, output)
        self.assertIn("headless: false", self.calls.read_text())

    def test_failure_rows_fail_the_workload(self):
        self._write_results(failure_rows=True)
        completed, output = self._run()
        self.assertEqual(1, completed.returncode, output)
        self.assertIn("failure row(s)", output)
        self.assertIn("OVERALL: FAILED", output)

    def test_nonzero_locust_exit_fails_the_workload(self):
        completed, output = self._run(STUB_EXIT=1)
        self.assertEqual(1, completed.returncode, output)
        self.assertIn("Locust exited with code 1", output)

    def test_missing_results_fail_the_workload(self):
        completed, output = self._run(STUB_NO_RESULTS=1)
        self.assertEqual(1, completed.returncode, output)
        self.assertIn("did not publish results", output)

    def test_error_lines_fail_the_workload(self):
        completed, output = self._run(STUB_LOG_ERROR=1)
        self.assertEqual(1, completed.returncode, output)
        self.assertIn("error line(s) in the Locust log", output)

    def test_missing_locust_aborts(self):
        completed, output = self._run(SAS_VALIDATION_LOCUST=str(self.root / "no-such-locust"))
        self.assertEqual(2, completed.returncode, output)
        self.assertIn("ENVIRONMENT ERROR", output)
        self.assertIn("NOT RUN", output)

    def test_timeout_stops_locust(self):
        self._generate(timeout="2s")
        pid_file = self.root / "browser.pid"
        completed, output = self._run(
            STUB_HANG=1, STUB_TREE_FILE=pid_file, STUB_PYTHON=sys.executable)
        self.assertEqual(1, completed.returncode, output)
        self.assertIn("did not finish within 2s", output)
        self.assertIn("terminated", self.calls.read_text())
        self.assertTrue(pid_file.exists(), output)
        try:
            process = psutil.Process(int(pid_file.read_text()))
        except psutil.NoSuchProcess:
            return
        self.assertEqual(psutil.STATUS_ZOMBIE, process.status(), "Browser process survived timeout")

    def test_direct_script_interrupt_cleans_children_and_logging_helpers(self):
        pid_file = self.root / "browser.pid"
        process = subprocess.Popen(
            [BASH, str(self.script)], cwd=self.output,
            env=self._environment(STUB_HANG=1, STUB_TREE_FILE=pid_file, STUB_PYTHON=sys.executable),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        descendants = []
        try:
            deadline = time.monotonic() + 8
            while not pid_file.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(pid_file.exists(), "Locust stub did not start its browser child")
            descendants = psutil.Process(process.pid).children(recursive=True)
            process.send_signal(signal.SIGTERM)
            output, _ = process.communicate(timeout=25)
            self.assertEqual(130, process.returncode, output)
            self.assertNotIn("wl-b TESTS", output)
            for child in descendants:
                self.assertFalse(child.is_running() and child.status() != psutil.STATUS_ZOMBIE,
                                 f"Leaked helper/worker PID {child.pid}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for child in descendants:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            if process.stdout is not None:
                process.stdout.close()

    def test_previous_logs_are_kept(self):
        self._run()
        self._run()
        kept = [path.name for path in self.output.iterdir() if path.name.startswith("execution-logs-")]
        self.assertEqual(1, len(kept))


def _load_scenario_utils():
    stubs = {name: ModuleType(name) for name in (
        "locust_plugins", "locust_plugins.csvreader", "kubernetes", "kubernetes.client",
        "kubernetes.client.rest")}
    stubs["locust_plugins.csvreader"].CSVReader = MagicMock()
    stubs["kubernetes"].client = MagicMock()
    stubs["kubernetes"].config = MagicMock()
    stubs["kubernetes.client.rest"].ApiException = type("ApiException", (Exception,), {})
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(
            "scenario_utils_local", FRAMEWORK / "execution/common/scenario_utils.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class ScenarioUtilsLocalTests(unittest.TestCase):
    def test_users_file_env_is_used_without_kubernetes(self):
        module = _load_scenario_utils()
        manager = module.UsersManager()
        module.config.load_incluster_config.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            users = Path(directory) / "users.csv"
            users.write_text("user1,pass1\nuser2,pass2\n")
            with patch.dict(os.environ, {"SAS_VALIDATION_USERS_FILE": str(users)}), \
                    patch.object(manager, "get_users_from_k8s_secret") as secret:
                self.assertEqual([["user1", "pass1"], ["user2", "pass2"]], manager.get_user_list())
                secret.assert_not_called()
        module.config.load_incluster_config.assert_not_called()

    def test_kubernetes_client_is_created_for_the_secret(self):
        module = _load_scenario_utils()
        manager = module.UsersManager()
        api = module.client.CoreV1Api.return_value
        api.read_namespaced_secret.return_value = SimpleNamespace(
            data={"users-file-dict": base64.b64encode(b'{"u": "p"}').decode()}
        )
        self.assertEqual([["u", "p"]], manager.get_users_from_k8s_secret("s", "ns", "users-file-dict"))
        module.config.load_incluster_config.assert_called_once()


class EventsHeadlessTests(unittest.TestCase):
    def _headless(self, value):
        sys.path.insert(0, str(REPOSITORY_ROOT / "tests"))
        try:
            import test_events_results as events_tests
        finally:
            sys.path.pop(0)
        environment = {} if value is None else {"SAS_VALIDATION_HEADLESS": value}
        with patch.dict(sys.modules, events_tests._stub_modules()), \
                patch.dict(os.environ, environment, clear=False):
            if value is None:
                os.environ.pop("SAS_VALIDATION_HEADLESS", None)
            with patch("sys.stdout", new=io.StringIO()):
                module = events_tests._load_events()
            return module.PlaywrightUser.headless

    def test_headless_by_default(self):
        self.assertTrue(self._headless(None))
        self.assertTrue(self._headless("true"))

    def test_headed_when_disabled(self):
        for value in ("false", "0", "no", "OFF"):
            with self.subTest(value=value):
                self.assertFalse(self._headless(value))


class LocalPreflightTests(unittest.TestCase):
    def _finding(self, identifier, context):
        checks = [check for check in preflight.all_checks() if check.identifier == identifier]
        return core.run_checks(checks, context)[0]

    def test_local_group_is_opt_in(self):
        self.assertIn("local", preflight.GROUPS)
        default_groups = {check.group for check in preflight.select_checks(())}
        self.assertNotIn("local", default_groups)
        selected = {check.identifier for check in preflight.select_checks(["local"])}
        self.assertEqual(
            {"local.python-version", "local.config", "local.python-modules", "local.browser",
             "local.users-file", "local.viya-reachable"},
            selected,
        )

    def test_python_version_warns_below_3_10(self):
        with patch.object(local_checks.sys, "version_info", (3, 9, 18)):
            result = local_checks._python_version(PreflightContext())
        self.assertEqual(Status.WARN, result.status)
        self.assertIn("Python 3.9 is older than 3.10", result.detail)
        self.assertEqual("Use Python 3.10 or newer for local runs", result.remedy)
        self.assertFalse(result.fixable)
        with patch.object(local_checks.sys, "version_info", (3, 12, 0)):
            self.assertEqual(Status.OK, local_checks._python_version(PreflightContext()).status)

    def _failed_install(self, output, version=(3, 12, 0)):
        context = PreflightContext(
            module_available=lambda name: False,
            run_command=lambda command, timeout: SimpleNamespace(returncode=1, stdout=output, stderr=""),
        )
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(local_checks.tempfile, "tempdir", directory), \
                patch.object(local_checks.sys, "version_info", version), \
                patch.object(local_checks.platform, "machine", return_value="aarch64"):
            with self.assertRaises(RuntimeError) as raised:
                local_checks._install_modules(context)
            message = str(raised.exception)
            log = Path(message.split("full pip output: ")[1].rstrip(")"))
            self.assertEqual(output, log.read_text())
        return message

    def test_wheel_build_failure_is_summarized(self):
        output = ("  subprocess.CalledProcessError: Command '(cd deps/libev && sh ./configure)'\n"
                  "  ERROR: Failed building wheel for gevent\n"
                  "error: failed-wheel-build-for-install\n")
        old = self._failed_install(output, version=(3, 9, 18))
        self.assertIn("pip could not build gevent from source "
                      "(no prebuilt package for Python 3.9 on aarch64); use Python 3.10 or newer", old)
        self.assertNotIn("\n", old)
        new = self._failed_install(output)
        self.assertIn("a C compiler and the Python development headers are needed", new)

    def test_other_pip_failures_report_the_last_error_line(self):
        message = self._failed_install(
            "Collecting locust\nERROR: Could not find a version that satisfies the requirement locust\n")
        self.assertIn("pip install exited 1: ERROR: Could not find a version", message)

    def test_missing_modules_are_fixable_with_pip(self):
        commands = []
        context = PreflightContext(
            module_available=lambda name: name in ("dotenv",),
            run_command=lambda command, timeout: commands.append(command) or SimpleNamespace(
                returncode=0, stdout="", stderr=""),
        )
        finding = self._finding("local.python-modules", context)
        self.assertEqual(Status.FAIL, finding.result.status)
        self.assertTrue(finding.fixable)
        self.assertIn("locust_plugins", finding.result.detail)
        result = local_checks._install_modules(context)
        self.assertEqual(
            [sys.executable, "-m", "pip", "install", "--prefer-binary",
             "locust", "locust-plugins[playwright]", "playwright"],
            commands[0],
        )
        self.assertIn("installed", result)

    def test_browser_check_and_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            browser = Path(directory) / "chrome"
            missing = PreflightContext(run_command=lambda command, timeout: SimpleNamespace(
                returncode=0, stdout=str(browser) + "\n", stderr=""))
            result = local_checks._browsers(missing)
            self.assertEqual(Status.FAIL, result.status)
            self.assertTrue(result.fixable)
            browser.write_text("")
            self.assertEqual(Status.OK, local_checks._browsers(missing).status)

        commands = []
        context = PreflightContext(run_command=lambda command, timeout: commands.append(command) or
                                   SimpleNamespace(returncode=0, stdout="", stderr=""))
        local_checks._install_browser(context)
        self.assertEqual([sys.executable, "-m", "playwright", "install", "chromium"], commands[0])

    def test_driver_missing_shared_library_is_reported_and_not_fixable(self):
        node_error = ("/venv/lib/python3.14/site-packages/playwright/driver/node: error while loading "
                      "shared libraries: libatomic.so.1: cannot open shared object file: No such file\n")
        commands = []

        def run(command, timeout):
            commands.append(command)
            if command[1] == "-c":
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr="Exception: Connection closed while reading from the driver\n")
            return SimpleNamespace(returncode=127, stdout="", stderr=node_error)

        result = local_checks._browsers(PreflightContext(run_command=run))
        self.assertEqual(Status.FAIL, result.status)
        self.assertFalse(result.fixable)
        self.assertIn("the Playwright driver cannot start: the system library libatomic.so.1 is missing",
                      result.detail)
        self.assertIn("Install the system package that provides libatomic.so.1", result.remedy)
        self.assertEqual([sys.executable, "-m", "playwright", "--version"], commands[1])

        install = PreflightContext(run_command=lambda command, timeout: SimpleNamespace(
            returncode=127, stdout="", stderr=node_error))
        with self.assertRaisesRegex(RuntimeError, "system library libatomic.so.1 is missing"):
            local_checks._install_browser(install)

    def test_other_browser_install_failures_report_the_last_line(self):
        context = PreflightContext(run_command=lambda command, timeout: SimpleNamespace(
            returncode=1, stdout="Downloading...\n", stderr="Error: download failed\n"))
        with self.assertRaisesRegex(RuntimeError, "^playwright install exited 1: Error: download failed$"):
            local_checks._install_browser(context)

    def test_users_file_from_option_or_configuration(self):
        self.assertEqual(Status.FAIL, self._finding("local.users-file", PreflightContext()).result.status)
        with tempfile.TemporaryDirectory() as directory:
            users = _users_file(Path(directory))
            for context in (PreflightContext(users_file=users), PreflightContext(configured_users_file=users)):
                finding = self._finding("local.users-file", context)
                self.assertEqual(Status.OK, finding.result.status)
                self.assertIn("2 user(s)", finding.result.detail)
            finding = self._finding(
                "local.users-file", PreflightContext(configured_users_file=Path(directory) / "absent.csv"))
            self.assertEqual(Status.FAIL, finding.result.status)

    def test_configuration_needs_only_a_hostname(self):
        finding = self._finding("local.config", PreflightContext(hostname="https://viya.example.com"))
        self.assertEqual(Status.OK, finding.result.status)
        finding = self._finding("local.config", PreflightContext(config_path=Path("x.yaml")))
        self.assertEqual(Status.FAIL, finding.result.status)


class RunLocalCliTests(unittest.TestCase):
    def _invoke(self, root: Path, arguments, users_file_config=True, plugin_targets=None):
        plugin = _plugin(root / "plugin", execution_targets=plugin_targets)
        users = _users_file(root)
        config = root / "sas-validation.yaml"
        config.write_text(
            "sas-validation:\n"
            f"  framework-root: {FRAMEWORK}\n"
            "  output:\n"
            f"    destination: {root / 'output'}\n"
            "  execution:\n"
            "    hostname: https://viya.example.com\n"
            + (f"    users-file: {users}\n" if users_file_config else ""),
            encoding="utf-8",
        )
        return CliRunner().invoke(
            cli.app, ["--config", str(config), "run", str(plugin), *arguments]
        )

    def test_headed_and_processes_require_local(self):
        with tempfile.TemporaryDirectory() as directory:
            for option in (["--headed"], ["--processes", "2"]):
                result = self._invoke(Path(directory), ["-w", "helloviya-simple", *option])
                self.assertNotEqual(0, result.exit_code)
                self.assertIn("require --local", result.output)

    def test_local_requires_a_users_file(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._invoke(Path(directory), ["-w", "helloviya-simple", "--local"],
                                  users_file_config=False)
        self.assertEqual(2, result.exit_code)
        self.assertIn("needs a users file", result.output)

    def test_local_generate_only_uses_configured_users_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._invoke(root, ["-w", "helloviya-simple", "--local", "--processes", "2",
                                         "--generate-only", "--log-level", "WARNING"])
            workload_root = root / "output/generated/helloviya-simple"
            script = (workload_root / "runWorkloadLocal.sh").read_text()
            staged_users = (workload_root / "local/src/users.csv").read_text()
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("--processes 2", script)
        self.assertEqual("user1,pass1\nuser2,pass2\n", staged_users)

    def test_local_runs_the_local_script(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ScenarioPackage, "run_workload", return_value=0) as run, \
                    patch.object(cli, "_ensure_local_dependencies") as ensure:
                result = self._invoke(Path(directory), ["-w", "helloviya-simple", "--local",
                                                        "--log-level", "WARNING"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertTrue(run.call_args.kwargs["local"])
        ensure.assert_called_once_with(False)

    def test_yes_is_passed_to_the_dependency_check(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ScenarioPackage, "run_workload", return_value=0), \
                    patch.object(cli, "_ensure_local_dependencies") as ensure:
                result = self._invoke(Path(directory), ["-w", "helloviya-simple", "--local", "--yes",
                                                        "--log-level", "WARNING"])
        self.assertEqual(0, result.exit_code, result.output)
        ensure.assert_called_once_with(True)

    def test_generate_only_skips_the_dependency_check(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(cli, "_ensure_local_dependencies") as ensure:
                result = self._invoke(Path(directory), ["-w", "helloviya-simple", "--local",
                                                        "--generate-only", "--log-level", "WARNING"])
        self.assertEqual(0, result.exit_code, result.output)
        ensure.assert_not_called()

    def test_missing_dependencies_abort_before_generating(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(cli, "_ensure_local_dependencies", side_effect=cli.typer.Exit(2)), \
                    patch.object(ScenarioPackage, "generate") as generate:
                result = self._invoke(root, ["-w", "helloviya-simple", "--local"])
        self.assertEqual(2, result.exit_code)
        generate.assert_not_called()

    def test_yes_requires_local(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._invoke(Path(directory), ["-w", "helloviya-simple", "--yes"])
        self.assertNotEqual(0, result.exit_code)
        self.assertIn("require --local", result.output)

    def test_kubernetes_only_scenarios_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._invoke(Path(directory), ["-w", "helloviya-simple", "--local"],
                                  plugin_targets=["kubernetes"])
        self.assertEqual(2, result.exit_code)
        self.assertIn("can only run in Kubernetes", result.output)

    def test_headed_warns_for_many_users(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._invoke(Path(directory), [
                "--scenario", "helloviya-simple", "--test", "logonoff.py", "--users", "4",
                "--local", "--headed", "--generate-only", "--log-level", "WARNING"])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("--headed opens one browser window per user (4)", result.output)


class EnsureLocalDependenciesTests(unittest.TestCase):
    """cli._ensure_local_dependencies with the local dependency checks stubbed."""

    def setUp(self):
        self.installed = {"modules": False, "browser": False}
        self.driver_broken = False
        self.fix_calls = []

        def python_modules(context):
            if self.installed["modules"]:
                return core.ok("installed")
            return core.fail("missing python modules: locust", remedy="pip", fixable=True)

        def browser(context):
            if self.driver_broken:
                return core.fail("the Playwright driver cannot start: the system library "
                                 "libatomic.so.1 is missing",
                                 remedy="Install the system package that provides libatomic.so.1")
            if self.installed["browser"]:
                return core.ok("/browser")
            return core.fail("browser missing", remedy="playwright install", fixable=True)

        def fix(kind, error=None):
            def apply(context):
                self.fix_calls.append(kind)
                if error:
                    raise RuntimeError(error)
                self.installed[kind] = True
                return f"installed {kind}"
            return apply

        self.fix = fix
        self.checks = lambda modules_error=None: [
            core.Check("local.python-modules", "local", "Locust and Playwright modules",
                       python_modules, fix=fix("modules", modules_error), fix_summary="pip install"),
            core.Check("local.browser", "local", "Playwright browser", browser,
                       fix=fix("browser"), requires=("local.python-modules",),
                       fix_summary="playwright install"),
        ]

    def _ensure(self, assume_yes=False, answer=None, modules_error=None, version=None):
        output = io.StringIO()
        errors = io.StringIO()
        version_patch = (patch.object(local_checks.sys, "version_info", version)
                         if version else patch.object(local_checks, "RECOMMENDED_PYTHON", (3, 0)))
        with patch.object(local_checks, "dependency_checks",
                          return_value=self.checks(modules_error)), \
                patch.object(cli, "_confirm", return_value=answer) as confirm, \
                version_patch, patch("sys.stdout", output), patch("sys.stderr", errors):
            try:
                cli._ensure_local_dependencies(assume_yes)
                code = None
            except cli.typer.Exit as error:
                code = error.exit_code
        self.errors = errors.getvalue()
        return code, output.getvalue(), confirm

    def test_ready_environment_is_silent(self):
        self.installed.update(modules=True, browser=True)
        code, output, confirm = self._ensure()
        self.assertIsNone(code)
        self.assertEqual("", output)
        confirm.assert_not_called()
        self.assertEqual([], self.fix_calls)

    def test_unfixable_browser_aborts_without_prompting(self):
        self.installed["modules"] = True
        self.driver_broken = True
        code, _, confirm = self._ensure()
        self.assertEqual(2, code)
        confirm.assert_not_called()
        self.assertEqual([], self.fix_calls)
        self.assertIn("complete this manually first: Playwright browser: the Playwright driver "
                      "cannot start", self.errors)
        self.assertIn("Install the system package that provides libatomic.so.1", self.errors)

    def test_unfixable_browser_found_after_installing_modules_aborts(self):
        def install_modules_breaks_driver(context):
            self.fix_calls.append("modules")
            self.installed["modules"] = True
            self.driver_broken = True
            return "installed modules"

        checks = self.checks()
        checks[0].fix = install_modules_breaks_driver
        with patch.object(local_checks, "dependency_checks", return_value=checks), \
                patch.object(local_checks, "RECOMMENDED_PYTHON", (3, 0)), \
                patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()) as errors:
            with self.assertRaises(cli.typer.Exit) as raised:
                cli._ensure_local_dependencies(True)
        self.assertEqual(2, raised.exception.exit_code)
        self.assertEqual(["modules"], self.fix_calls)
        self.assertIn("libatomic.so.1", errors.getvalue())

    def test_declining_aborts_without_installing(self):
        code, output, confirm = self._ensure(answer=False)
        self.assertEqual(2, code)
        confirm.assert_called_once()
        self.assertEqual([], self.fix_calls)
        self.assertIn("missing python modules: locust", output)

    def test_accepting_installs_modules_then_browser(self):
        code, output, _ = self._ensure(answer=True)
        self.assertIsNone(code, output)
        self.assertEqual(["modules", "browser"], self.fix_calls)

    def test_yes_skips_the_prompt(self):
        code, _, confirm = self._ensure(assume_yes=True)
        self.assertIsNone(code)
        confirm.assert_not_called()
        self.assertEqual(["modules", "browser"], self.fix_calls)

    def test_failed_install_aborts(self):
        code, output, _ = self._ensure(assume_yes=True, modules_error="pip exploded")
        self.assertEqual(2, code)
        self.assertEqual(["modules"], self.fix_calls)
        self.assertIn("failed", output)
        self.assertIn("pip exploded", output)
        self.assertIn("still missing (Locust and Playwright modules, Playwright browser); "
                      "see the error above", self.errors)
        self.assertNotIn("pip exploded", self.errors)

    def test_old_python_is_warned_about_without_blocking(self):
        code, output, _ = self._ensure(assume_yes=True, version=(3, 9, 18))
        self.assertIsNone(code)
        self.assertIn("WARNING: Python 3.9 is older than 3.10", output)
        self.assertIn("Use Python 3.10 or newer for local runs.", output)

    def test_current_python_is_not_warned_about(self):
        _, output, _ = self._ensure(assume_yes=True, version=(3, 12, 0))
        self.assertNotIn("WARNING", output)

    def test_dependency_checks_are_the_fixable_local_checks(self):
        self.assertEqual(
            ["local.python-modules", "local.browser"],
            [check.identifier for check in local_checks.dependency_checks()],
        )

    def test_module_install_refreshes_import_caches(self):
        context = PreflightContext(
            module_available=lambda name: False,
            run_command=lambda command, timeout: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        with patch.object(local_checks.importlib, "invalidate_caches") as invalidate:
            local_checks._install_modules(context)
        invalidate.assert_called_once()


class LocalLocustResolutionTests(unittest.TestCase):
    def _run(self, root: Path, environ, locust):
        package = ScenarioPackage(_plugin(root / "plugin"))
        generated = root / "generated" / "helloviya-simple"
        generated.mkdir(parents=True)
        script = generated / "runWorkloadLocal.sh"
        script.write_text('#!/usr/bin/env bash\necho "$SAS_VALIDATION_LOCUST" > locust.txt\n')
        script.chmod(0o755)
        with patch.dict(os.environ, environ, clear=False), \
                patch("scenario_package.loader.local_locust_executable", return_value=locust):
            if "SAS_VALIDATION_LOCUST" not in environ:
                os.environ.pop("SAS_VALIDATION_LOCUST", None)
            package.run_workload("helloviya-simple", root / "generated", local=True)
        return (generated / "locust.txt").read_text().strip()

    def test_interpreter_locust_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self._run(Path(directory), {}, Path("/venv/bin/locust"))
        self.assertEqual("/venv/bin/locust", value)

    def test_explicit_override_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self._run(Path(directory), {"SAS_VALIDATION_LOCUST": "/custom/locust"},
                              Path("/venv/bin/locust"))
        self.assertEqual("/custom/locust", value)

    def test_falls_back_to_path_when_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self._run(Path(directory), {}, None)
        self.assertEqual("", value)

    def test_finds_locust_in_the_scripts_directory(self):
        from scenario_package import loader
        with tempfile.TemporaryDirectory() as directory:
            locust = Path(directory) / "locust"
            locust.write_text("#!/bin/sh\n")
            locust.chmod(0o755)
            with patch.object(loader.sysconfig, "get_path", return_value=directory), \
                    patch.object(loader.site, "ENABLE_USER_SITE", False):
                self.assertEqual(locust, loader.local_locust_executable())
            locust.chmod(0o644)
            with patch.object(loader.sysconfig, "get_path", return_value=directory), \
                    patch.object(loader.site, "ENABLE_USER_SITE", False):
                self.assertIsNone(loader.local_locust_executable())


if __name__ == "__main__":
    unittest.main()
