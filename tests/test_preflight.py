# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the preflight environment inspection."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "framework/python"))

from scenario_package import cli, preflight  # noqa: E402
from scenario_package.preflight import cluster_checks, core, k8s, report  # noqa: E402
from scenario_package.preflight.core import Check, PreflightContext, Status, fail, ok, warn  # noqa: E402


class ApiError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


def _missing(*_args, **_kwargs):
    raise ApiError(404)


class FakeKube:
    """Stands in for KubeClients; every accessor raises 404 unless configured."""

    def __init__(self, **overrides):
        self.calls = []
        api = SimpleNamespace(
            list_namespace=lambda **_: SimpleNamespace(items=[]),
            read_namespace=_missing,
            read_namespaced_secret=_missing,
            read_namespaced_service_account=_missing,
            read_cluster_role=_missing,
            read_cluster_role_binding=_missing,
            read_namespaced_role=_missing,
            read_namespaced_role_binding=_missing,
            read_namespaced_deployment=_missing,
            list_deployment_for_all_namespaces=lambda **_: SimpleNamespace(items=[]),
            read_custom_resource_definition=_missing,
            list_node=lambda: SimpleNamespace(items=[]),
            list_namespaced_resource_quota=lambda _ns: SimpleNamespace(items=[]),
        )
        for name, value in overrides.items():
            setattr(api, name, value)
        self.core = api
        self.apps = api
        self.rbac = api
        self.extensions = api


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def _context(**kwargs):
    defaults = dict(
        namespace="testing",
        hostname="https://viya.example.com",
        config_path=Path("sas-validation.yaml"),
        environ={"KUBECONFIG": "/tmp/kubeconfig"},
        kube_factory=lambda _context: FakeKube(),
    )
    defaults.update(kwargs)
    return PreflightContext(**defaults)


def _operators(*namespaces, ready=2):
    """list_deployment_for_all_namespaces stub returning operator Deployments."""
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name=k8s.OPERATOR_NAME, namespace=namespace),
            status=SimpleNamespace(ready_replicas=ready),
        )
        for namespace in namespaces
    ]
    return lambda **_: SimpleNamespace(items=items)


class CheckRunnerTests(unittest.TestCase):
    def test_dependents_are_skipped_when_a_requirement_fails(self):
        checks = [
            Check("a", "client", "A", lambda _: fail("broken")),
            Check("b", "client", "B", lambda _: ok("never runs"), requires=("a",)),
        ]
        findings = core.run_checks(checks, _context())
        self.assertEqual(Status.FAIL, findings[0].result.status)
        self.assertEqual(Status.SKIPPED, findings[1].result.status)
        self.assertIn("depends on: a", findings[1].result.detail)

    def test_a_raising_check_fails_instead_of_aborting_the_run(self):
        def explode(_context):
            raise RuntimeError("boom")

        findings = core.run_checks(
            [Check("a", "client", "A", explode), Check("b", "client", "B", lambda _: ok("fine"))],
            _context(),
        )
        self.assertEqual(Status.FAIL, findings[0].result.status)
        self.assertIn("RuntimeError: boom", findings[0].result.detail)
        self.assertEqual(Status.OK, findings[1].result.status)

    def test_exit_code_is_one_only_when_something_failed(self):
        context = _context()
        passing = core.run_checks([Check("a", "client", "A", lambda _: ok("fine"))], context)
        warning = core.run_checks([Check("a", "client", "A", lambda _: warn("meh"))], context)
        failing = core.run_checks([Check("a", "client", "A", lambda _: fail("broken"))], context)
        self.assertEqual(0, core.exit_code(passing))
        self.assertEqual(0, core.exit_code(warning))
        self.assertEqual(1, core.exit_code(failing))


class ApplyFixesTests(unittest.TestCase):
    def test_shared_fix_key_runs_once_for_all_of_its_checks(self):
        state = {"installed": False, "calls": 0}

        def install(_context):
            state["installed"] = True
            state["calls"] += 1
            return "installed"

        def probe(_context):
            return ok("present") if state["installed"] else fail("absent", fixable=True)

        checks = [
            Check("a", "cluster", "A", probe, fix=install, fix_key="shared"),
            Check("b", "cluster", "B", probe, fix=install, fix_key="shared"),
        ]
        context = _context()
        findings = core.apply_fixes(checks, core.run_checks(checks, context), context)
        self.assertEqual(1, state["calls"])
        self.assertTrue(all(finding.result.status is Status.OK for finding in findings))
        self.assertEqual("installed", findings[1].fix_applied)

    def test_fixing_a_requirement_unblocks_checks_that_were_skipped(self):
        state = {"namespace": False, "operator": False}

        checks = [
            Check(
                "cluster.namespace",
                "cluster",
                "Namespace",
                lambda _: ok("present") if state["namespace"] else fail("absent", fixable=True),
                fix=lambda _: state.__setitem__("namespace", True) or "created namespace",
            ),
            Check(
                "cluster.operator",
                "cluster",
                "Operator",
                lambda _: ok("present") if state["operator"] else fail("absent", fixable=True),
                fix=lambda _: state.__setitem__("operator", True) or "installed operator",
                requires=("cluster.namespace",),
            ),
        ]
        context = _context()
        first_pass = core.run_checks(checks, context)
        self.assertEqual(Status.SKIPPED, first_pass[1].result.status)

        findings = core.apply_fixes(checks, first_pass, context)
        self.assertTrue(all(finding.result.status is Status.OK for finding in findings))
        self.assertEqual("installed operator", findings[1].fix_applied)

    def test_a_failing_fix_is_reported_and_does_not_raise(self):
        def explode(_context):
            raise RuntimeError("no permission")

        checks = [Check("a", "cluster", "A", lambda _: fail("absent", fixable=True), fix=explode)]
        context = _context()
        findings = core.apply_fixes(checks, core.run_checks(checks, context), context)
        self.assertEqual(Status.FAIL, findings[0].result.status)
        self.assertIn("RuntimeError: no permission", findings[0].fix_error)

    def test_on_fix_callbacks_fire_once_per_remediation_key_with_timing(self):
        state = {"installed": False}

        def install(_context):
            state["installed"] = True
            return "installed"

        def probe(_context):
            return ok("present") if state["installed"] else fail("absent", fixable=True)

        checks = [
            Check("a", "cluster", "A", probe, fix=install, fix_key="shared"),
            Check("b", "cluster", "B", probe, fix=install, fix_key="shared"),
        ]
        starts = []
        completions = []
        context = _context()
        core.apply_fixes(
            checks,
            core.run_checks(checks, context),
            context,
            on_fix_start=lambda key, group: starts.append((key, [c.identifier for c in group])),
            on_fix_complete=lambda key, group, applied, error, elapsed: completions.append(
                (key, applied, error, elapsed)
            ),
        )
        self.assertEqual([("shared", ["a", "b"])], starts)
        self.assertEqual(1, len(completions))
        key, applied, error, elapsed = completions[0]
        self.assertEqual("shared", key)
        self.assertEqual("installed", applied)
        self.assertIsNone(error)
        self.assertGreaterEqual(elapsed, 0)


class StreamCommandTests(unittest.TestCase):
    def test_streams_lines_and_returns_a_completed_process(self):
        lines = []
        completed = core.stream_command(["/bin/sh", "-c", "printf 'a\\nb\\n'"], 5.0, lines.append)
        self.assertEqual(["a", "b"], lines)
        self.assertEqual(0, completed.returncode)
        self.assertEqual("a\nb\n", completed.stdout)


class SelectChecksTests(unittest.TestCase):
    def test_the_viya_group_is_not_registered(self):
        groups = {check.group for check in preflight.select_checks(())}
        self.assertEqual({"client", "cluster"}, groups)
        self.assertNotIn("viya", preflight.GROUPS)

    def test_selecting_a_group_pulls_in_its_prerequisites(self):
        identifiers = [check.identifier for check in preflight.select_checks(["cluster"])]
        self.assertIn("cluster.crd", identifiers)
        self.assertIn("client.kubeconfig", identifiers)
        self.assertIn("client.config", identifiers)
        self.assertNotIn("client.yq", identifiers)


class ClientCheckTests(unittest.TestCase):
    def _finding(self, identifier, context):
        checks = [check for check in preflight.all_checks() if check.identifier == identifier]
        return core.run_checks(checks, context)[0]

    def test_missing_kubeconfig_fails(self):
        finding = self._finding("client.kubeconfig", _context(environ={}))
        self.assertEqual(Status.FAIL, finding.result.status)
        self.assertIn("KUBECONFIG is not set", finding.result.detail)

    def test_kubeconfig_pointing_at_a_missing_file_fails(self):
        finding = self._finding(
            "client.kubeconfig", _context(environ={"KUBECONFIG": "/no/such/kubeconfig"})
        )
        self.assertEqual(Status.FAIL, finding.result.status)
        self.assertIn("do not exist", finding.result.detail)

    def test_kubeconfig_is_accepted_when_the_file_exists(self):
        with tempfile.NamedTemporaryFile() as handle:
            finding = self._finding(
                "client.kubeconfig", _context(environ={"KUBECONFIG": handle.name})
            )
        self.assertEqual(Status.OK, finding.result.status)

    def test_missing_namespace_and_hostname_are_reported_together(self):
        finding = self._finding("client.config", _context(namespace=None, hostname=None))
        self.assertEqual(Status.FAIL, finding.result.status)
        self.assertIn("execution.namespace", finding.result.detail)
        self.assertIn("execution.hostname", finding.result.detail)

    def test_a_broken_config_file_is_reported_verbatim(self):
        finding = self._finding("client.config", _context(config_error="bad yaml"))
        self.assertEqual(Status.FAIL, finding.result.status)
        self.assertEqual("bad yaml", finding.result.detail)

    def test_a_required_binary_that_is_absent_fails(self):
        finding = self._finding("client.kubectl", _context(which=lambda _: None))
        self.assertEqual(Status.FAIL, finding.result.status)

    def test_an_optional_binary_that_is_absent_only_warns(self):
        finding = self._finding("client.yq", _context(which=lambda _: None))
        self.assertEqual(Status.WARN, finding.result.status)

    def test_missing_required_modules_fail(self):
        finding = self._finding(
            "client.python-modules", _context(module_available=lambda name: name != "kubernetes")
        )
        self.assertEqual(Status.FAIL, finding.result.status)
        self.assertIn("kubernetes", finding.result.detail)


class ClusterCheckTests(unittest.TestCase):
    def _result(self, function, context):
        return function(context)

    def test_a_missing_namespace_is_fixable(self):
        result = cluster_checks._namespace(_context())
        self.assertEqual(Status.FAIL, result.status)
        self.assertTrue(result.fixable)

    def test_an_existing_namespace_passes(self):
        context = _context(
            kube_factory=lambda _: FakeKube(read_namespace=lambda name: SimpleNamespace(name=name))
        )
        self.assertEqual(Status.OK, cluster_checks._namespace(context).status)

    def test_the_operator_deployment_must_exist_and_be_ready(self):
        result = cluster_checks._operator_deployment(_context())
        self.assertEqual(Status.FAIL, result.status)
        self.assertIn("installed in 'testing'", result.detail)

        context = _context(
            kube_factory=lambda _: FakeKube(
                list_deployment_for_all_namespaces=_operators("testing", ready=0)
            )
        )
        result = cluster_checks._operator_deployment(context)
        self.assertEqual(Status.FAIL, result.status)
        self.assertFalse(result.fixable)
        self.assertIn("kubectl -n testing describe", result.remedy)

        context = _context(
            kube_factory=lambda _: FakeKube(
                list_deployment_for_all_namespaces=_operators("testing")
            )
        )
        result = cluster_checks._operator_deployment(context)
        self.assertEqual(Status.OK, result.status)
        self.assertIn("testing/locust-operator", result.detail)

    def test_an_operator_in_another_namespace_only_warns_and_is_not_reinstalled(self):
        context = _context(
            kube_factory=lambda _: FakeKube(
                list_deployment_for_all_namespaces=_operators("locust-operator")
            )
        )
        result = cluster_checks._operator_deployment(context)
        self.assertEqual(Status.WARN, result.status)
        self.assertFalse(result.fixable)
        self.assertIn("locust-operator/locust-operator", result.detail)
        self.assertIn("uninstall-locust-k8s-operator.sh locust-operator", result.remedy)

    def test_operators_in_several_namespaces_warn(self):
        context = _context(
            kube_factory=lambda _: FakeKube(
                list_deployment_for_all_namespaces=_operators("locust-operator", "testing")
            )
        )
        result = cluster_checks._operator_deployment(context)
        self.assertEqual(Status.WARN, result.status)
        self.assertIn("locust-operator, testing", result.detail)

    def test_the_operator_is_installed_into_the_testing_namespace(self):
        calls = []

        def run_command(command, _timeout):
            calls.append(list(command))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        context = _context(framework_root=Path("/fw"), run_command=run_command)
        applied = cluster_checks._install_operator(context)
        self.assertEqual(
            [["/fw/locust-k8s/install-locust-k8s-operator.sh", "testing", "/tmp/kubeconfig"]],
            calls,
        )
        self.assertIn("'testing'", applied)

    def test_an_existing_operator_is_repaired_in_place(self):
        calls = []
        context = _context(
            framework_root=Path("/fw"),
            run_command=lambda command, _t: calls.append(list(command))
            or SimpleNamespace(returncode=0, stdout="", stderr=""),
            kube_factory=lambda _: FakeKube(
                list_deployment_for_all_namespaces=_operators("locust-operator")
            ),
        )
        cluster_checks._install_operator(context)
        self.assertEqual("locust-operator", calls[0][1])

    def test_install_refuses_when_operators_run_in_several_other_namespaces(self):
        context = _context(
            framework_root=Path("/fw"),
            run_command=lambda *_: self.fail("must not install"),
            kube_factory=lambda _: FakeKube(
                list_deployment_for_all_namespaces=_operators("a", "b")
            ),
        )
        with self.assertRaises(k8s.KubeError):
            cluster_checks._install_operator(context)

    def test_the_cluster_role_binding_must_point_at_the_running_operator(self):
        binding = SimpleNamespace(
            subjects=[
                SimpleNamespace(
                    kind="ServiceAccount", name=k8s.OPERATOR_NAME, namespace="locust-operator"
                )
            ]
        )

        def context_for(*namespaces):
            return _context(
                kube_factory=lambda _: FakeKube(
                    read_cluster_role=lambda _name: SimpleNamespace(),
                    read_cluster_role_binding=lambda _name: binding,
                    list_deployment_for_all_namespaces=_operators(*namespaces),
                )
            )

        self.assertEqual(Status.OK, cluster_checks._cluster_rbac(context_for("locust-operator")).status)
        self.assertEqual(Status.OK, cluster_checks._cluster_rbac(context_for()).status)
        result = cluster_checks._cluster_rbac(context_for("testing"))
        self.assertEqual(Status.FAIL, result.status)
        self.assertIn("runs in 'testing'", result.detail)

    def test_a_legacy_operator_in_the_testing_namespace_only_warns(self):
        self.assertEqual(Status.OK, cluster_checks._legacy_operator(_context()).status)
        seen = []
        context = _context(
            kube_factory=lambda _: FakeKube(
                read_namespaced_deployment=lambda name, ns: seen.append((name, ns))
                or SimpleNamespace()
            )
        )
        result = cluster_checks._legacy_operator(context)
        self.assertEqual(Status.WARN, result.status)
        self.assertEqual([(k8s.LEGACY_OPERATOR_NAME, "testing")], seen)
        self.assertIn("kubectl -n testing delete", result.remedy)

    def test_the_crd_must_serve_the_api_version_the_generator_emits(self):
        crd = SimpleNamespace(
            spec=SimpleNamespace(versions=[SimpleNamespace(name="v1", served=True)])
        )
        with tempfile.TemporaryDirectory() as directory:
            framework_root = Path(directory)
            template = framework_root / cluster_checks.CUSTOM_RESOURCE_TEMPLATE
            template.parent.mkdir(parents=True)
            template.write_text("apiVersion: locust.io/v2\n", encoding="utf-8")
            context = _context(
                framework_root=framework_root,
                kube_factory=lambda _: FakeKube(
                    read_custom_resource_definition=lambda _name: crd
                ),
            )
            result = cluster_checks._crd(context)
            self.assertEqual(Status.FAIL, result.status)
            self.assertIn("serves v1", result.detail)
            self.assertIn("install-locust-k8s-operator.sh", result.remedy)

            template.write_text("apiVersion: locust.io/v1\n", encoding="utf-8")
            self.assertEqual(Status.OK, cluster_checks._crd(context).status)

    def test_the_users_secret_is_only_fixable_when_a_users_file_is_given(self):
        result = cluster_checks._users_secret(_context())
        self.assertEqual(Status.WARN, result.status)
        self.assertFalse(result.fixable)
        with tempfile.TemporaryDirectory() as directory:
            users = Path(directory) / "users.csv"
            users.write_text("user1,password1\n", encoding="utf-8")
            result = cluster_checks._users_secret(_context(users_file=users))
        self.assertTrue(result.fixable)

    def test_a_populated_users_secret_reports_the_user_count(self):
        secret = SimpleNamespace(
            data={k8s.SECRET_KEY: __import__("base64").b64encode(
                json.dumps({"a": "1", "b": "2"}).encode("utf-8")
            ).decode("utf-8")}
        )
        context = _context(
            kube_factory=lambda _: FakeKube(read_namespaced_secret=lambda _name, _ns: secret)
        )
        result = cluster_checks._users_secret(context)
        self.assertEqual(Status.OK, result.status)
        self.assertIn("2 user(s)", result.detail)

    def test_missing_secrets_reader_rbac_is_a_warning_not_a_failure(self):
        result = cluster_checks._secrets_reader_rbac(_context())
        self.assertEqual(Status.WARN, result.status)
        self.assertTrue(result.fixable)

    def test_capacity_warns_when_no_node_can_host_a_locust_pod(self):
        node = SimpleNamespace(
            spec=SimpleNamespace(taints=None),
            status=SimpleNamespace(allocatable={"cpu": "500m", "memory": "512Mi"}),
        )
        context = _context(
            kube_factory=lambda _: FakeKube(list_node=lambda: SimpleNamespace(items=[node]))
        )
        result = cluster_checks._capacity(context)
        self.assertEqual(Status.WARN, result.status)
        self.assertIn("no schedulable node", result.detail)


class QuantityTests(unittest.TestCase):
    def test_cpu_and_memory_suffixes(self):
        self.assertEqual(2.0, k8s.parse_quantity("2000m", True))
        self.assertEqual(4.0, k8s.parse_quantity("4", True))
        self.assertEqual(1024 * 1024**2, k8s.parse_quantity("1024Mi", False))
        self.assertEqual(0.0, k8s.parse_quantity(None, False))


class ViyaCheckTests(unittest.TestCase):
    def test_the_viya_checks_are_not_registered(self):
        identifiers = [check.identifier for check in preflight.all_checks()]
        self.assertFalse([name for name in identifiers if name.startswith("viya.")])


class ReportTests(unittest.TestCase):
    def _findings(self):
        checks = [
            Check("a", "client", "A", lambda _: ok("fine")),
            Check(
                "b",
                "cluster",
                "B",
                lambda _: fail("absent", remedy="create it", fixable=True),
                fix=lambda _: "created",
            ),
            Check("c", "viya", "C", lambda _: fail("broken", remedy="ask an admin")),
        ]
        return core.run_checks(checks, _context())

    def test_fixable_and_manual_items_are_listed_separately(self):
        text = "\n".join(report.render(self._findings(), fixed=False))
        self.assertIn("Fixable automatically (1)", text)
        self.assertIn("b: create it", text)
        self.assertIn("Complete these manually (1)", text)
        self.assertIn("c: ask an admin", text)

    def test_a_failed_fix_is_listed_as_manual_not_fixable(self):
        findings = self._findings()
        findings[1].fix_error = "RuntimeError: pip could not build gevent from source"
        text = "\n".join(report.render(findings, fixed=True))
        self.assertNotIn("Fixable automatically", text)
        self.assertIn("Complete these manually (2)", text)
        self.assertIn("b: create it", text)
        self.assertIn("fix failed: RuntimeError: pip could not build gevent", text)

    def test_json_output_carries_status_and_fixability(self):
        payload = report.as_json(self._findings())
        self.assertEqual(["a", "b", "c"], [entry["id"] for entry in payload])
        self.assertEqual("fail", payload[1]["status"])
        self.assertTrue(payload[1]["fixable"])
        self.assertFalse(payload[2]["fixable"])

    def test_a_fix_that_does_not_resolve_the_check_is_not_reported_as_fixed(self):
        checks = [
            Check(
                "a",
                "cluster",
                "A",
                lambda _: fail("still broken", fixable=True),
                fix=lambda _: "ran installer",
            )
        ]
        context = _context()
        findings = core.apply_fixes(checks, core.run_checks(checks, context), context)
        text = "\n".join(report.render(findings, fixed=True))
        self.assertNotIn("fixed: ran installer", text)
        self.assertIn("fix ran but the check still reports FAIL: ran installer", text)

    def test_render_plan_discloses_cascading_fixes(self):
        state = {"namespace": False}
        checks = [
            Check(
                "cluster.namespace",
                "cluster",
                "Testing namespace",
                lambda _: ok("present")
                if state["namespace"]
                else fail("absent", remedy="kubectl create namespace testing", fixable=True),
                fix=lambda _: None,
                fix_summary="Create the Kubernetes namespace",
            ),
            Check(
                "cluster.crd",
                "cluster",
                "LocustTest CRD",
                lambda _: ok("present"),
                fix=lambda _: None,
                requires=("cluster.namespace",),
                fix_key="install-operator",
                fix_summary="Install/upgrade the locust-k8s-operator",
            ),
            Check(
                "cluster.cluster-rbac",
                "cluster",
                "Operator cluster RBAC",
                lambda _: ok("present"),
                fix=lambda _: None,
                requires=("cluster.namespace",),
                fix_key="install-operator",
                fix_summary="Install/upgrade the locust-k8s-operator",
            ),
        ]
        findings = core.run_checks(checks, _context())
        text = "\n".join(report.render_plan(findings, _context()))
        self.assertIn("Create the Kubernetes namespace", text)
        self.assertIn("also unblocks these checks", text)
        self.assertIn("Install/upgrade the locust-k8s-operator", text)
        self.assertIn("LocustTest CRD", text)
        self.assertIn("Operator cluster RBAC", text)

    def test_render_plan_omits_cascade_items_that_arent_actually_fixable(self):
        state = {"namespace": False}
        checks = [
            Check(
                "cluster.namespace",
                "cluster",
                "Testing namespace",
                lambda _: ok("present")
                if state["namespace"]
                else fail("absent", remedy="kubectl create namespace testing", fixable=True),
                fix=lambda _: None,
                fix_summary="Create the Kubernetes namespace",
            ),
            Check(
                "cluster.users-secret",
                "cluster",
                "Test user credentials secret",
                lambda _: ok("present"),
                fix=lambda _: None,
                requires=("cluster.namespace",),
                fix_summary="Store test user credentials",
                fix_available=lambda context: context.users_file is not None,
            ),
        ]
        findings = core.run_checks(checks, _context())

        without_users_file = "\n".join(report.render_plan(findings, _context()))
        self.assertNotIn("Store test user credentials", without_users_file)

        with_users_file = "\n".join(
            report.render_plan(findings, _context(users_file=Path("users.csv")))
        )
        self.assertIn("Store test user credentials", with_users_file)

    def test_operator_checks_share_the_same_fix_summary(self):
        checks = {check.identifier: check for check in cluster_checks.checks()}
        keys = ("cluster.crd", "cluster.cluster-rbac", "cluster.operator-deployment")
        summaries = {checks[key].fix_summary for key in keys}
        self.assertEqual({cluster_checks.INSTALL_OPERATOR_SUMMARY}, summaries)


class PreflightCommandTests(unittest.TestCase):
    def _invoke(self, config: Path, *argv):
        result = CliRunner().invoke(
            cli.app, ["--config", str(config), "preflight", *argv]
        )
        return result.exit_code, result.output

    def test_a_missing_configuration_is_reported_as_a_finding_not_a_usage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._invoke(
                Path(directory) / "sas-validation.yaml", "--group", "client"
            )
        self.assertEqual(1, code)
        self.assertIn("sas-validation.yaml", output)
        self.assertIn("configuration file does not exist", output)

    def test_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            _code, output = self._invoke(
                Path(directory) / "sas-validation.yaml", "--group", "client", "--json"
            )
        payload = json.loads(output)
        self.assertTrue(any(entry["id"] == "client.config" for entry in payload))

    def test_fix_without_confirmation_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  execution:\n"
                "    namespace: testing\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )
            with patch("builtins.input", return_value="n"):
                code, output = self._invoke(config, "--group", "client", "--fix")
        self.assertEqual(1 if "FAIL" in output else 0, code)
        self.assertIn("Nothing to fix automatically.", output)


class LoadUsersCommandTests(unittest.TestCase):
    def _invoke(self, config: Path, *argv):
        result = CliRunner().invoke(
            cli.app, ["--config", str(config), "users", "load", *argv]
        )
        return result.exit_code, result.output

    def test_namespace_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / "users.csv"
            users_file.write_text("alice,password123\n", encoding="utf-8")
            code, output = self._invoke(
                Path(directory) / "sas-validation.yaml",
                "--users-file", str(users_file),
            )
        self.assertEqual(2, code)

    def test_users_file_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._invoke(
                Path(directory) / "sas-validation.yaml",
                "--namespace", "testing",
            )
        self.assertEqual(2, code)

    def test_users_file_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._invoke(
                Path(directory) / "sas-validation.yaml",
                "--namespace", "testing",
                "--users-file", str(Path(directory) / "nonexistent.csv"),
            )
        self.assertEqual(2, code)

    def test_successful_load_with_mock_kube(self):
        """Test successful users file loading with mocked Kubernetes."""
        with tempfile.TemporaryDirectory() as directory:
            users_file = Path(directory) / "users.csv"
            users_file.write_text("alice,password123\nbob,secret456\n", encoding="utf-8")
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  execution:\n"
                "    namespace: testing\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )
            
            # Mock the kube factory to return a fake kube client
            fake_kube = FakeKube()
            fake_kube.core.create_namespaced_secret = lambda *_args, **_kwargs: None
            
            def mock_kube_factory(context):
                return fake_kube
            
            with patch.object(preflight.PreflightContext, "kube", mock_kube_factory):
                code, output = self._invoke(
                    config,
                    "--namespace", "testing",
                    "--users-file", str(users_file),
                )
        
        self.assertEqual(0, code)
        self.assertIn("Successfully loaded 2 user(s)", output)
        self.assertIn("validation-scenarios", output)


FAKE_KUBECTL = """#!/bin/bash
echo "$*" >> "$FAKE_KUBECTL_LOG"
if [ "$1" = "apply" ]; then cat > "$FAKE_KUBECTL_APPLIED"; fi
exit 0
"""


class InstallScriptTests(unittest.TestCase):
    SCRIPT = REPOSITORY_ROOT / "framework" / cluster_checks.INSTALL_SCRIPT

    def _run(self, *args):
        import os
        import subprocess

        with tempfile.TemporaryDirectory() as directory:
            bin_dir = Path(directory)
            kubectl = bin_dir / "kubectl"
            kubectl.write_text(FAKE_KUBECTL, encoding="utf-8")
            kubectl.chmod(0o755)
            log, applied = bin_dir / "log", bin_dir / "applied.yaml"
            env = dict(
                os.environ,
                PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                FAKE_KUBECTL_LOG=str(log),
                FAKE_KUBECTL_APPLIED=str(applied),
            )
            completed = subprocess.run(
                ["bash", str(self.SCRIPT), *args],
                env=env, capture_output=True, text=True, check=False,
            )
            return (
                completed,
                log.read_text(encoding="utf-8") if log.exists() else "",
                applied.read_text(encoding="utf-8") if applied.exists() else "",
            )

    def test_the_manifest_is_applied_to_the_requested_namespace(self):
        completed, log, applied = self._run("validation-scenarios", "/tmp/kubeconfig")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual(4, applied.count("namespace: validation-scenarios"))
        self.assertNotIn("namespace: locust-operator", applied)
        self.assertIn("-n validation-scenarios rollout status deployment/locust-operator", log)

    def test_the_default_namespace_is_kept_without_a_namespace_argument(self):
        completed, _log, applied = self._run("/tmp/kubeconfig")
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual(4, applied.count("namespace: locust-operator"))

    def test_an_invalid_namespace_is_rejected(self):
        completed, log, _applied = self._run("Bad/NS", "/tmp/kubeconfig")
        self.assertEqual(1, completed.returncode)
        self.assertIn("not a valid Kubernetes namespace", completed.stdout)
        self.assertEqual("", log)


if __name__ == "__main__":
    unittest.main()
