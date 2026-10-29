# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import importlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from scenario_package.loader import GenerationResult, LegacyInputs, ScenarioPackage
from scenario_package.manifest import ManifestError
from scenario_package.plugins import validate_plugin
from scenario_package import cli


FIXTURE = Path(__file__).parent / "fixtures" / "helloviya-simple"


class ScenarioPackageTests(unittest.TestCase):
    def test_legacy_configuration_merge_and_priority(self):
        repository_root = Path(__file__).parent.parent
        framework_python = str(repository_root / "framework/python")
        if framework_python not in sys.path:
            sys.path.insert(0, framework_python)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            global_config = root / "global.yaml"
            workload_config = root / "workload.yaml"
            build_path = root / "build"
            global_config.write_text(
                "global-config:\n  value: base\n  inherited: true\n",
                encoding="utf-8",
            )
            workload_config.write_text(
                "workload-definition:\n  value: workload\n  added: true\n",
                encoding="utf-8",
            )
            build_path.mkdir()
            original_argv = sys.argv
            sys.argv = [
                "loadConfiguration.py",
                "-g",
                str(global_config),
                "-w",
                str(workload_config),
                "-p",
                str(build_path),
            ]
            try:
                configuration = importlib.import_module("loadConfiguration")
                merged = configuration.merge_yaml_files(
                    str(global_config),
                    str(workload_config),
                    None,
                    "workload-definition",
                )
            finally:
                sys.argv = original_argv

            self.assertEqual(merged["value"], "workload")
            self.assertTrue(merged["inherited"])
            self.assertTrue(merged["added"])

        from frameworkLib import Framework

        self.assertEqual(
            Framework.get_value_with_priority("value", {"value": "override"}, merged, {}),
            "override",
        )
        self.assertEqual(
            Framework.get_value_with_priority("value", {}, merged, {}), "workload"
        )
        self.assertIsNone(Framework.get_value_with_priority("missing", {}, {}, {}))

    def test_fixture_resolves_to_existing_package_paths(self):
        package = ScenarioPackage(FIXTURE)

        layout, manifest = package.scenario("helloviya-simple")

        self.assertEqual(manifest.identifier, "helloviya-simple")
        self.assertEqual(manifest.runtime, "locust")
        self.assertEqual(len(manifest.entrypoints), 2)
        self.assertTrue((layout.scenario_root / "tests/logonoff.py").is_file())
        self.assertTrue(
            (layout.package_root / "workload-definitions/helloviya-simple.yaml").is_file()
        )
        self.assertTrue((layout.resources_root / "data/class.csv").is_file())

        summary = next(
            item for item in package.scenario_summaries() if item.identifier == "helloviya-simple"
        )
        self.assertEqual(
            summary.entrypoints,
            (Path("tests/logonoff.py"), Path("tests/createcompute.py")),
        )

    def test_prepare_writes_legacy_generator_inputs(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            inputs = package.prepare("helloviya-simple", Path(directory), Path("framework"))

            self.assertTrue(inputs.global_config.is_file())
            self.assertTrue(inputs.workload_definition.is_file())
            self.assertEqual(inputs.workload_definition.name, "helloviya-simple.yaml")
            self.assertEqual(inputs.generated_root, Path(directory).resolve() / "generated")
            self.assertIn("scenarios-base-location", inputs.global_config.read_text())

    def test_prepare_includes_execution_settings(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificates = root / "trustedcerts.pem"
            certificates.write_text("certificate", encoding="utf-8")
            inputs = package.prepare(
                "helloviya-simple",
                root / "prepared",
                Path("framework"),
                hostname="https://viya.example.com",
                trusted_certs=certificates,
                namespace="naaprod",
            )

            global_config = yaml.safe_load(inputs.global_config.read_text())

        values = global_config["global-config"]
        self.assertEqual(values["hostname"], "https://viya.example.com")
        self.assertEqual(values["trusted-certs"], str(certificates))
        self.assertEqual(values["namespace"], "naaprod")
        self.assertNotIn("kube-config", values)

    def test_workload_resolves_by_spec_name_file_name_and_path(self):
        package = ScenarioPackage(FIXTURE)
        expected = FIXTURE / "workload-definitions/helloviya-simple.yaml"

        for selector in (
            "helloviya-simple",
            "helloviya-simple.yaml",
            expected,
        ):
            workload = package.workload_definition(selector)
            self.assertEqual(workload.path, expected)
            self.assertEqual(workload.spec_names, ("helloviya-simple",))
            self.assertEqual(
                workload.scenario_configs, ("helloviya-simple/scenario-config.yaml",)
            )

    def test_unknown_workload_lists_available_workloads(self):
        package = ScenarioPackage(FIXTURE)

        with self.assertRaisesRegex(ManifestError, "Available workloads: helloviya-simple"):
            package.workload_definition("missing-workload")

    def test_synthesize_workload_definition_writes_single_test_spec(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            definition_path = package.synthesize_workload_definition(
                "helloviya-simple",
                "createcompute.py",
                output_root,
                users=3,
                spawn_rate=2,
                iterations=5,
            )

            self.assertEqual(
                definition_path,
                output_root.resolve() / "workload-definitions/helloviya-simple-createcompute-wrkld-def.yaml",
            )
            data = yaml.safe_load(definition_path.read_text())

            # Resulting definition is directly consumable by workload_definition().
            definition = package.workload_definition(definition_path)
            self.assertEqual(definition.spec_names, ("helloviya-simple-createcompute",))

        spec = data["workload-definitions"]["workload-definition-specs"][0]
        self.assertEqual(spec["name"], "helloviya-simple-createcompute")
        resource_spec = spec["custom-resource-spec"]
        self.assertEqual(resource_spec["config-map-name"], "helloviya-simple-createcompute-map")
        workload = resource_spec["workloads"][0]
        self.assertEqual(workload["scenario-config"], "helloviya-simple/scenario-config.yaml")
        self.assertEqual(workload["path"], "helloviya-simple/tests")
        self.assertEqual(workload["task"], "createcompute.py")
        self.assertEqual(workload["users"], 3)
        self.assertEqual(workload["worker-replicas"], 3)
        self.assertEqual(workload["spawn-rate"], 2)
        self.assertEqual(workload["iterations"], 5)

    def test_synthesize_workload_definition_omits_unset_fields(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            definition_path = package.synthesize_workload_definition(
                "helloviya-simple", "createcompute.py", Path(directory)
            )
            data = yaml.safe_load(definition_path.read_text())

        workload = data["workload-definitions"]["workload-definition-specs"][0][
            "custom-resource-spec"
        ]["workloads"][0]
        self.assertNotIn("users", workload)
        self.assertNotIn("worker-replicas", workload)
        self.assertNotIn("spawn-rate", workload)
        self.assertNotIn("iterations", workload)

    def test_synthesize_workload_definition_rejects_unknown_test(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ManifestError, "Available tests: tests/logonoff.py"):
                package.synthesize_workload_definition(
                    "helloviya-simple", "missing.py", Path(directory)
                )

    def test_synthesize_workload_definition_rejects_unknown_scenario(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ManifestError, "not included"):
                package.synthesize_workload_definition(
                    "missing-scenario", "createcompute.py", Path(directory)
                )

    def test_workload_referencing_missing_scenario_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            shutil.copytree(FIXTURE, root)
            definition = root / "workload-definitions/helloviya-simple.yaml"
            definition.write_text(
                definition.read_text(encoding="utf-8").replace(
                    "helloviya-simple/scenario-config.yaml",
                    "missing-scenario/scenario-config.yaml",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "missing scenario config"):
                ScenarioPackage(root).workload_definition("helloviya-simple")

    def test_workload_referencing_missing_task_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            shutil.copytree(FIXTURE, root)
            definition = root / "workload-definitions/helloviya-simple.yaml"
            definition.write_text(
                definition.read_text(encoding="utf-8").replace(
                    "task: logonoff.py", "task: missing.py"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "missing task file"):
                ScenarioPackage(root).workload_definition("helloviya-simple")

    def test_prepared_inputs_match_legacy_generator_output(self):
        package = ScenarioPackage(FIXTURE)
        repository_root = Path(__file__).parent.parent
        generator = repository_root / "framework/python/createWorkloadDefinitions.py"
        framework_root = repository_root / "framework"
        legacy_workload = (
            repository_root
            / "validation-scenarios/workload-definitions/helloviya-simple-wrkld-def.yaml"
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_inputs = package.prepare(
                "helloviya-simple", root / "package", framework_root
            )
            legacy_global_config = root / "legacy-global-config.yaml"
            with legacy_global_config.open("w", encoding="utf-8") as stream:
                yaml.safe_dump(
                    {
                        "global-config": {
                            "framework-base-location": str(framework_root),
                            "scenarios-base-location": str(
                                repository_root / "validation-scenarios/scenarios"
                            ),
                            "generated-base-location": str(root / "legacy-generated"),
                        }
                    },
                    stream,
                    sort_keys=False,
                )
            environment = os.environ.copy()
            environment["frameworkDefaultsFullPath"] = str(
                framework_root / "framework-defaults.yaml"
            )

            for global_config, workload_config in (
                (legacy_global_config, legacy_workload),
                (package_inputs.global_config, package_inputs.workload_definition),
            ):
                subprocess.run(
                    [
                        sys.executable,
                        str(generator),
                        "-g",
                        str(global_config),
                        "-w",
                        str(workload_config),
                        "-l",
                        "WARNING",
                    ],
                    check=True,
                    cwd=repository_root,
                    env=environment,
                    capture_output=True,
                    text=True,
                )

            legacy_output = root / "legacy-generated/helloviya-simple/helloviya-simple.yaml"
            package_output = root / "package/generated/helloviya-simple/helloviya-simple.yaml"
            self.assertEqual(legacy_output.read_text(), package_output.read_text())

    def test_generate_runs_existing_workload_generator(self):
        package = ScenarioPackage(FIXTURE)
        repository_root = Path(__file__).parent.parent

        with tempfile.TemporaryDirectory() as directory:
            result = package.generate(
                "helloviya-simple", Path(directory), repository_root / "framework"
            )

            generated_file = (
                result.generated_workload_root
                / "helloviya-simple/helloviya-simple.yaml"
            )
            self.assertTrue(generated_file.is_file())
            generated = yaml.safe_load(generated_file.read_text())
            workloads = generated["workload-definition"]["custom-resource-spec"]["workloads"]
            self.assertEqual(
                [workload["name"] for workload in workloads],
                ["logonoff", "createcompute"],
            )

    def test_generate_applies_runtime_settings(self):
        package = ScenarioPackage(FIXTURE)
        repository_root = Path(__file__).parent.parent

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            users_file = root / "users.csv"
            users_file.write_text("username,password\ntest-user,test-password\n", encoding="utf-8")
            overrides = root / "overrides.yaml"
            overrides.write_text("workload-overrides:\n  users: 2\n", encoding="utf-8")

            result = package.generate(
                "helloviya-simple",
                root / "output",
                repository_root / "framework",
                hostname="https://viya.example.com",
                users_file=users_file,
                workload_overrides=overrides,
                log_level="DEBUG",
            )

            workload_root = result.generated_workload_root / "helloviya-simple"
            runner = workload_root / "build/runCreateWorkloadArtifacts.sh"
            custom_resource = workload_root / "resources/k8s-cr-logonoff.yaml"
            generated = yaml.safe_load(
                (workload_root / "helloviya-simple.yaml").read_text()
            )
            runner_contents = runner.read_text()
            custom_resource_contents = custom_resource.read_text()
            run_workload_contents = (workload_root / "runWorkload.sh").read_text()

            self.assertTrue((workload_root / "build/createWorkloadArtifacts.sh").is_file())
            self.assertTrue((workload_root / "build/setVariables.sh").is_file())
            self.assertTrue((workload_root / "resources/users.csv").is_file())
            self.assertTrue((workload_root / "deployTaskResourcesAsConfigMap.sh").is_file())
            # Each generated file has exactly one location; the legacy artifacts/ folder is gone.
            self.assertFalse((workload_root / "artifacts").exists())
            self.assertFalse((workload_root / "runCreateWorkloadArtifacts.sh").exists())
            self.assertFalse((workload_root / "createWorkloadArtifacts.sh").exists())

        self.assertIn(f"{workload_root / 'build/createWorkloadArtifacts.sh'}", runner_contents)
        self.assertIn(f"-u {users_file}", runner_contents)
        self.assertIn("--host https://viya.example.com", custom_resource_contents)
        self.assertIn(str(workload_root / "resources/k8s-cr-logonoff.yaml"), run_workload_contents)
        self.assertNotIn("/artifacts", run_workload_contents)
        self.assertEqual(
            generated["workload-definition"]["custom-resource-spec"]["workloads"][0]["users"],
            2,
        )

    def test_run_workload_executes_flattened_generated_script(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            generated_root = Path(directory) / "generated"
            workload_root = generated_root / "helloviya-simple"
            workload_root.mkdir(parents=True)
            marker = Path(directory) / "run-marker.txt"
            script = workload_root / "runWorkload.sh"
            script.write_text(
                f"#!/usr/bin/env bash\npwd > {marker}\nexit 7\n",
                encoding="utf-8",
            )
            script.chmod(0o755)

            exit_code = package.run_workload("helloviya-simple", generated_root)

            self.assertEqual(exit_code, 7)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), str(workload_root.resolve()))

    def test_run_workload_falls_back_to_legacy_artifacts_script(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            generated_root = Path(directory) / "generated"
            artifacts_root = generated_root / "helloviya-simple" / "artifacts"
            artifacts_root.mkdir(parents=True)
            marker = Path(directory) / "legacy-marker.txt"
            script = artifacts_root / "runWorkload.sh"
            script.write_text(
                f"#!/usr/bin/env bash\npwd > {marker}\n",
                encoding="utf-8",
            )
            script.chmod(0o755)

            exit_code = package.run_workload("helloviya-simple", generated_root)

            self.assertEqual(exit_code, 0)
            self.assertTrue(marker.is_file())

    def test_run_workload_uses_spec_name_for_wrkld_def_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_root = root / "package"
            shutil.copytree(FIXTURE, package_root)
            definition = package_root / "workload-definitions/helloviya-simple.yaml"
            definition.rename(package_root / "workload-definitions/helloviya-simple-wrkld-def.yaml")
            generated_root = root / "generated"
            workload_root = generated_root / "helloviya-simple"
            workload_root.mkdir(parents=True)
            marker = root / "run-marker.txt"
            script = workload_root / "runWorkload.sh"
            script.write_text(
                f"#!/usr/bin/env bash\npwd > {marker}\n",
                encoding="utf-8",
            )
            script.chmod(0o755)

            exit_code = ScenarioPackage(package_root).run_workload(
                "helloviya-simple-wrkld-def.yaml", generated_root
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), str(workload_root.resolve()))

    def test_cli_run_executes_generated_workload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            workload_root = output / "generated" / "helloviya-simple"
            workload_root.mkdir(parents=True)
            marker = root / "cli-run-marker.txt"
            script = workload_root / "runWorkload.sh"
            script.write_text(
                f"#!/usr/bin/env bash\npwd > {marker}\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            config = root / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  output:\n"
                f"    destination: {output}\n"
                "  framework-root: framework\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )

            # `run` always regenerates first; stub generate() so this test exercises the
            # CLI's run_workload() wiring without invoking the real generator subprocess.
            fake_result = GenerationResult(
                inputs=LegacyInputs(
                    global_config=output / "global-config.yaml",
                    workload_definition=FIXTURE / "workload-definitions/helloviya-simple.yaml",
                    generated_root=output / "generated",
                ),
                generated_workload_root=output / "generated",
            )
            with patch.object(ScenarioPackage, "generate", return_value=fake_result):
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "--config",
                        str(config),
                        "run",
                        str(FIXTURE),
                        "-w",
                        "helloviya-simple",
                        "--plugin-version",
                        "2026.06.1",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), str(workload_root.resolve()))

    def test_prepare_backs_up_existing_generated_directory(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            existing_generated = output_root / "generated"
            existing_generated.mkdir(parents=True)
            (existing_generated / "old_file.txt").write_text("old content", encoding="utf-8")

            inputs = package.prepare("helloviya-simple", output_root, Path("framework"))

            self.assertTrue(inputs.generated_root.is_dir())
            self.assertFalse((inputs.generated_root / "old_file.txt").exists())

            backups = list(output_root.glob("generated-[0-9]*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "old_file.txt").is_file())

    def test_unknown_scenario_is_rejected(self):
        package = ScenarioPackage(FIXTURE)

        with self.assertRaisesRegex(ManifestError, "is not included"):
            package.scenario("missing-scenario")

    def test_parent_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release-manifest.yaml").write_text(
                """name: test
version: 0.1.0
viya-cadence: '2026.06'
repository: test
scenarios:
  - id: test
    path: ../outside
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "safe relative path"):
                ScenarioPackage(root)

    def test_missing_entrypoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
            config = root / "scenarios/helloviya-simple/scenario-manifest.yaml"
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    "tests/logonoff.py", "tests/missing.py"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "entrypoint does not exist"):
                ScenarioPackage(root).scenario("helloviya-simple")

    def test_resource_mapping_requires_a_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release-manifest.yaml").write_text(
                """name: test
version: 0.1.0
viya-cadence: '2026.06'
repository: test
scenarios:
  - id: test
    path: scenarios/test
""",
                encoding="utf-8",
            )
            scenario_root = root / "scenarios/test"
            scenario_root.mkdir(parents=True)
            (scenario_root / "scenario-manifest.yaml").write_text(
                """id: test
display-name: Test
runtime: locust
entrypoint: tests/test.py
required-resources:
  - data-artifact: missing-path
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "must contain 'path'"):
                ScenarioPackage(root).scenario("test")


class PluginCommonDependencyTests(unittest.TestCase):
    """`plugin-common` dependencies resolve against the plugin (package) root."""

    repository_root = Path(__file__).parent.parent
    framework_root = repository_root / "framework"

    def _plugin(self, root: Path, dependency: dict, library: str = "plugin_helpers.py") -> Path:
        shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
        common_dir = root / "scenarios/common"
        common_dir.mkdir(parents=True, exist_ok=True)
        (common_dir / library).write_text("VALUE = 1\n", encoding="utf-8")
        config = root / "scenarios/helloviya-simple/scenario-config.yaml"
        values = yaml.safe_load(config.read_text(encoding="utf-8"))
        values["scenario-config"]["dependencies"].append(dependency)
        config.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
        return root

    @staticmethod
    def _dependency(path: str = "scenarios/common", file: str = "plugin_helpers.py") -> dict:
        return {"type": "plugin-common", "path": path, "file": file}

    def test_prepare_writes_plugin_base_location(self):
        package = ScenarioPackage(FIXTURE)

        with tempfile.TemporaryDirectory() as directory:
            inputs = package.prepare("helloviya-simple", Path(directory), self.framework_root)
            values = yaml.safe_load(inputs.global_config.read_text())["global-config"]

        self.assertEqual(values["plugin-base-location"], str(FIXTURE.resolve()))

    def test_generate_includes_plugin_common_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = self._plugin(root / "plugin", self._dependency())
            result = ScenarioPackage(plugin).generate(
                "helloviya-simple", root / "output", self.framework_root
            )
            workload_root = result.generated_workload_root / "helloviya-simple"
            generated = yaml.safe_load((workload_root / "helloviya-simple.yaml").read_text())
            config_map_script = (workload_root / "deployTaskResourcesAsConfigMap.sh").read_text()

        modules = generated["workload-definition"]["custom-resource-spec"]["custom-modules"]
        expected = str(plugin.resolve() / "scenarios/common/plugin_helpers.py")
        self.assertIn({"type": "plugin-common", "file": expected}, modules)
        self.assertIn("common", {module["type"] for module in modules})
        self.assertIn(f"--from-file={expected}", config_map_script)

    def test_generate_rejects_file_name_collision_with_cli_common(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = self._plugin(
                root / "plugin",
                self._dependency(file="studio_actions.py"),
                library="studio_actions.py",
            )

            with self.assertRaisesRegex(ManifestError, "Workload generator failed"):
                ScenarioPackage(plugin).generate(
                    "helloviya-simple", root / "output", self.framework_root, log_level="ERROR"
                )

    def test_missing_plugin_common_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = self._plugin(Path(directory), self._dependency(file="missing.py"))

            with self.assertRaisesRegex(ManifestError, "plugin-common dependency does not exist"):
                ScenarioPackage(plugin).scenario("helloviya-simple")
            errors = validate_plugin(plugin)

        self.assertEqual(len(errors), 1)
        self.assertIn("plugin-common dependency does not exist", errors[0])

    def test_unsafe_plugin_common_path_is_rejected(self):
        for unsafe in ("../outside", "/etc"):
            with self.subTest(path=unsafe), tempfile.TemporaryDirectory() as directory:
                plugin = self._plugin(Path(directory), self._dependency(path=unsafe))

                with self.assertRaisesRegex(ManifestError, "safe relative path"):
                    ScenarioPackage(plugin).scenario("helloviya-simple")

    def test_generator_defaults_plugin_root_to_scenarios_parent(self):
        generator = self.framework_root / "python/createWorkloadDefinitions.py"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = self._plugin(root / "plugin", self._dependency()).resolve()
            global_config = root / "global-config.yaml"
            global_config.write_text(
                yaml.safe_dump(
                    {
                        "global-config": {
                            "framework-base-location": str(self.framework_root),
                            "scenarios-base-location": str(plugin / "scenarios"),
                            "generated-base-location": str(root / "generated"),
                        }
                    }
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["frameworkDefaultsFullPath"] = str(
                self.framework_root / "framework-defaults.yaml"
            )
            subprocess.run(
                [
                    sys.executable,
                    str(generator),
                    "-g",
                    str(global_config),
                    "-w",
                    str(plugin / "workload-definitions/helloviya-simple.yaml"),
                    "-l",
                    "WARNING",
                ],
                check=True,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
            )
            generated = yaml.safe_load(
                (root / "generated/helloviya-simple/helloviya-simple.yaml").read_text()
            )

        modules = generated["workload-definition"]["custom-resource-spec"]["custom-modules"]
        self.assertIn(
            {
                "type": "plugin-common",
                "file": str(plugin.resolve() / "scenarios/common/plugin_helpers.py"),
            },
            modules,
        )


if __name__ == "__main__":
    unittest.main()
