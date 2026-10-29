# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from scenario_package import cli
from scenario_package.loader import ScenarioPackage, installed_packages


FIXTURE = Path(__file__).parent / "fixtures" / "helloviya-simple"

_runner = CliRunner()


def _run(argv):
    result = _runner.invoke(cli.app, argv)
    assert result.exit_code == 0, result.output
    return result.output


class InstalledPackagesTests(unittest.TestCase):
    def test_packages_are_enumerated_and_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "second")
            shutil.copytree(FIXTURE, destination / "first")
            (destination / "not-a-package").mkdir()

            packages, broken = installed_packages(destination)

        self.assertEqual(len(packages), 2)
        self.assertEqual(broken, [])
        self.assertEqual(
            [package.release.version for package in packages],
            sorted(package.release.version for package in packages),
        )

    def test_missing_destination_is_not_an_error(self):
        self.assertEqual(installed_packages(Path("/nonexistent/packages")), ([], []))

    def test_unreadable_manifest_is_reported_as_broken(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "broken")
            (destination / "broken" / "release-manifest.yaml").write_text(
                "schema-version: \"1\"\n", encoding="utf-8"
            )

            packages, broken = installed_packages(destination)

        self.assertEqual(packages, [])
        self.assertEqual(len(broken), 1)
        self.assertTrue(broken[0].error)


class SummaryTests(unittest.TestCase):
    def test_workload_summaries_include_description_and_scenarios(self):
        summaries = ScenarioPackage(FIXTURE).workload_summaries()

        self.assertTrue(summaries)
        summary = next(item for item in summaries if item.name == "helloviya-simple")
        self.assertIsNone(summary.error)
        self.assertTrue(summary.scenario_configs)
        self.assertEqual(summary.source.parent.name, "workload-definitions")

    def test_malformed_definition_becomes_an_error_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            shutil.copytree(FIXTURE, root)
            (root / "workload-definitions" / "broken-wrkld-def.yaml").write_text(
                "workload-definitions:\n  workload-definition-specs: []\n",
                encoding="utf-8",
            )

            summaries = ScenarioPackage(root).workload_summaries()

        broken = next(item for item in summaries if item.name == "broken-wrkld-def")
        self.assertIn("non-empty list", broken.error)

    def test_scenario_summaries_report_missing_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            shutil.copytree(FIXTURE, root)
            package = ScenarioPackage(root)
            identifier = package.release.scenarios[0].identifier
            shutil.rmtree(root / package.release.scenarios[0].path)

            summaries = ScenarioPackage(root).scenario_summaries()

        summary = next(item for item in summaries if item.identifier == identifier)
        self.assertIsNotNone(summary.error)


class DiscoveryCommandTests(unittest.TestCase):
    def test_packages_list_resource_command(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "one")

            output = _run(["plugins", "list", "--destination", str(destination)])

        self.assertIn(str(destination / "one"), output)

    def test_list_packages_groups_by_package(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "one")

            output = _run(["plugins", "list", "--destination", str(destination)])

        self.assertIn("scenarios", output)
        self.assertIn(str(destination / "one"), output)

    def test_list_workloads_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "one")

            payload = json.loads(
                _run(["workloads", "list", "--destination", str(destination), "--json"])
            )

        self.assertEqual(len(payload), 1)
        workload = payload[0]["workloads"][0]
        self.assertEqual(
            set(workload), {"name", "description", "source", "scenarios", "error"}
        )

    def test_list_workloads_copy_writes_to_custom_workloads_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "packages"
            shutil.copytree(FIXTURE, destination / "one")
            config = root / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  custom-workloads:\n"
                "    location: custom-workloads\n",
                encoding="utf-8",
            )

            output = _run(
                [
                    "--config",
                    str(config),
                    "workloads",
                    "list",
                    "--destination",
                    str(destination),
                    "--copy",
                    "helloviya-simple",
                ]
            )

            self.assertIn("copied_workload_definition=", output)
            self.assertTrue((root / "custom-workloads/helloviya-simple.yaml").is_file())

    def test_list_workloads_copy_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "packages"
            shutil.copytree(FIXTURE, destination / "one")
            custom_workloads = root / "custom-workloads"
            custom_workloads.mkdir()
            (custom_workloads / "helloviya-simple.yaml").write_text("existing\n", encoding="utf-8")
            config = root / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  custom-workloads:\n"
                "    location: custom-workloads\n",
                encoding="utf-8",
            )

            result = _runner.invoke(
                cli.app,
                [
                    "--config",
                    str(config),
                    "workloads",
                    "list",
                    "--destination",
                    str(destination),
                    "--copy",
                    "helloviya-simple",
                ],
            )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("already exists", result.output)

    def test_list_workloads_copy_supports_json_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "packages"
            shutil.copytree(FIXTURE, destination / "one")
            config = root / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  custom-workloads:\n"
                "    location: custom-workloads\n",
                encoding="utf-8",
            )

            payload = json.loads(
                _run(
                    [
                        "--config",
                        str(config),
                        "workloads",
                        "list",
                        "--destination",
                        str(destination),
                        "--copy",
                        "helloviya-simple",
                        "--json",
                    ]
                )
            )

        self.assertEqual(payload["copied"], str(root / "custom-workloads/helloviya-simple.yaml"))
        self.assertTrue(payload["source"].endswith("workload-definitions/helloviya-simple.yaml"))

    def test_list_scenarios_reports_manifest_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "one")

            payload = json.loads(
                _run(["scenarios", "list", "--destination", str(destination), "--json"])
            )

        identifiers = [item["id"] for item in payload[0]["scenarios"]]
        self.assertIn("helloviya-simple", identifiers)
        scenario = next(
            item for item in payload[0]["scenarios"] if item["id"] == "helloviya-simple"
        )
        self.assertEqual(scenario["tests"], ["tests/logonoff.py", "tests/createcompute.py"])

    def test_list_scenarios_displays_manifest_entrypoints(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "one")

            output = _run(["scenarios", "list", "--destination", str(destination)])

        self.assertIn("test: tests/logonoff.py", output)
        self.assertIn("test: tests/createcompute.py", output)

    def test_scenario_filter_excludes_unrelated_workloads(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(FIXTURE, destination / "one")

            payload = json.loads(
                _run(
                    [
                        "workloads",
                        "list",
                        "--destination",
                        str(destination),
                        "--scenario",
                        "no-such-scenario",
                        "--json",
                    ]
                )
            )

        self.assertEqual(payload[0]["workloads"], [])

    def test_empty_cache_reports_a_hint_without_failing(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"

            output = _run(["plugins", "list", "--destination", str(destination)])

        self.assertIn("No installed plugins found", output)


class ConfigDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self._cwd = Path.cwd()
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name).resolve()
        self.addCleanup(self._directory.cleanup)
        self.addCleanup(os.chdir, self._cwd)

    def _write_config(self, directory: Path, destination: str = "installed-packages") -> Path:
        config = directory / "sas-validation.yaml"
        config.write_text(
            "sas-validation:\n"
            "  installed-plugins:\n"
            f"    destination: {destination}\n",
            encoding="utf-8",
        )
        return config

    def test_plugins_list_from_subdirectory_uses_project_config(self):
        self._write_config(self.root)
        shutil.copytree(FIXTURE, self.root / "installed-packages" / "one")
        subdirectory = self.root / "generated-workloads" / "nested"
        subdirectory.mkdir(parents=True)
        os.chdir(subdirectory)

        payload = json.loads(_run(["plugins", "list", "--json"]))

        self.assertEqual(len(payload), 1)
        self.assertEqual(Path(payload[0]["root"]).resolve(), self.root / "installed-packages" / "one")

    def test_nearest_config_wins_and_repositories_prefer_config_directory(self):
        self._write_config(self.root)
        project = self.root / "project"
        (project / "sub").mkdir(parents=True)
        self._write_config(project)
        (self.root / "scenario-repositories.yaml").write_text("outer\n", encoding="utf-8")
        (project / "scenario-repositories.yaml").write_text("inner\n", encoding="utf-8")
        os.chdir(project / "sub")

        package_config = cli._config_path(None, cli.PACKAGE_CONFIG_FILENAME)
        repositories_config = cli._config_path(
            None, cli.REPOSITORIES_CONFIG_FILENAME, package_config.parent
        )

        self.assertEqual(package_config.resolve(), project / "sas-validation.yaml")
        self.assertEqual(repositories_config.resolve(), project / "scenario-repositories.yaml")

    def test_explicit_config_overrides_discovery(self):
        self._write_config(self.root)
        explicit = self.root / "other.yaml"
        os.chdir(self.root)

        self.assertEqual(cli._config_path(explicit, cli.PACKAGE_CONFIG_FILENAME), explicit)

    def test_missing_config_explains_default_destination(self):
        os.chdir(self.root)
        result = _runner.invoke(
            cli.app,
            ["plugins", "list"],
            env={"XDG_CACHE_HOME": str(self.root / "cache"), "HOME": str(self.root)},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("No installed plugins found", result.output)
        self.assertIn("no sas-validation.yaml was found", result.output)


if __name__ == "__main__":
    unittest.main()
