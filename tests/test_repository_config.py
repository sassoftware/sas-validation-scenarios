# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
import shutil
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from scenario_package import cli
from scenario_package.config import (
    load_repository_aliases,
    load_repository_config,
    load_scenario_package_defaults,
)
from scenario_package.manifest import ManifestError
from scenario_package.providers import RepositoryAlias


class RepositoryConfigTests(unittest.TestCase):
    def test_loads_public_and_internal_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "repositories.yaml"
            config.write_text(
                """scenario-repositories:
  sas-public:
    provider: github-release
    repository: org/public-scenarios
    visibility: public
  sas-internal-test:
    provider: gitlab-release
    repository: group/test-scenarios
    visibility: internal
    base-url: https://gitlab.internal.example
""",
                encoding="utf-8",
            )

            aliases = load_repository_aliases(config)

        self.assertEqual(aliases["sas-public"].provider, "github-release")
        self.assertEqual(
            aliases["sas-internal-test"].base_url,
            "https://gitlab.internal.example",
        )

    def test_missing_repository_section_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "repositories.yaml"
            config.write_text("other: value\n", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "scenario-repositories"):
                load_repository_aliases(config)

    def test_loads_configured_default_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "repositories.yaml"
            config.write_text(
                "default-repository: sas-public\n"
                "scenario-repositories:\n"
                "  sas-public: {provider: github-release, repository: org/project}\n",
                encoding="utf-8",
            )

            repository_config = load_repository_config(config)

        self.assertEqual(repository_config.default_repository, "sas-public")
        self.assertIn("sas-public", repository_config.aliases)

    def test_default_repository_must_name_configured_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "repositories.yaml"
            config.write_text(
                "default-repository: missing\n"
                "scenario-repositories:\n"
                "  sas-public: {provider: github-release, repository: org/project}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "default repository alias 'missing'"):
                load_repository_config(config)


class ScenarioPackageDefaultsTests(unittest.TestCase):
    def test_loads_scenario_package_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "scenario-repositories.yaml"
            config.write_text(
                "sas-validation:\n"
                "  framework-root: framework\n"
                "  installed-packages:\n"
                "    destination: ~/.cache/sas-validation/packages\n"
                "  output:\n"
                "    destination: validation-scenarios/generated\n"
                "scenario-repositories: {}\n",
                encoding="utf-8",
            )
            defaults = load_scenario_package_defaults(config)

        self.assertIsNotNone(defaults.framework_root)
        self.assertIsNotNone(defaults.destination)
        self.assertIsNotNone(defaults.output)

    def test_scenario_package_defaults_absent_returns_none_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "scenario-repositories.yaml"
            config.write_text("scenario-repositories: {}\n", encoding="utf-8")
            defaults = load_scenario_package_defaults(config)

        self.assertIsNone(defaults.framework_root)
        self.assertIsNone(defaults.destination)
        self.assertIsNone(defaults.output)

    def test_scenario_package_relative_paths_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "scenario-repositories.yaml"
            config.write_text(
                "sas-validation:\n  framework-root: framework\n",
                encoding="utf-8",
            )
            defaults = load_scenario_package_defaults(config)

        self.assertEqual(defaults.framework_root, Path(directory) / "framework")

    def test_custom_workloads_location_is_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  custom-workloads:\n"
                "    location: custom-workloads\n",
                encoding="utf-8",
            )

            defaults = load_scenario_package_defaults(config)

        self.assertEqual(defaults.custom_workloads, Path(directory) / "custom-workloads")

    def test_custom_workloads_section_must_be_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n  custom-workloads: custom-workloads\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "custom-workloads"):
                load_scenario_package_defaults(config)

    def test_custom_workloads_location_must_be_non_empty_string(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n  custom-workloads:\n    location: ''\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "custom-workloads.location"):
                load_scenario_package_defaults(config)

    def test_scenario_package_tilde_expanded(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "scenario-repositories.yaml"
            config.write_text(
                "sas-validation:\n  installed-packages:\n    destination: ~/.cache/sas-validation/packages\n",
                encoding="utf-8",
            )
            defaults = load_scenario_package_defaults(config)

        self.assertEqual(
            defaults.destination,
            Path("~/.cache/sas-validation/packages").expanduser(),
        )

    def test_old_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text("scenario-package:\n  framework-root: framework\n", encoding="utf-8")

            with self.assertRaisesRegex(ManifestError, "no longer supported"):
                load_scenario_package_defaults(config)

    def test_loads_execution_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificates = root / "trustedcerts.pem"
            certificates.write_text("certificate", encoding="utf-8")
            config = root / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n"
                "    namespace: naaprod\n"
                "    trusted-certs: trustedcerts.pem\n",
                encoding="utf-8",
            )

            defaults = load_scenario_package_defaults(config)

        self.assertEqual(defaults.hostname, "https://viya.example.com")
        self.assertEqual(defaults.trusted_certs, certificates)
        self.assertEqual(defaults.namespace, "naaprod")

    def test_execution_hostname_must_be_https(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n  execution:\n    hostname: http://viya.example.com\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ManifestError, "must be an HTTPS URL"):
                load_scenario_package_defaults(config)


class CliConfigurationTests(unittest.TestCase):
    def test_default_package_destination_uses_platform_cache(self):
        with patch.object(cli, "user_cache_path", return_value=Path("/cache/sas-validation")):
            destination = cli._default_package_destination()

        self.assertEqual(destination, Path("/cache/sas-validation/packages"))

    def test_installed_package_is_selected_by_workload(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(fixture, destination / "helloviya-simple")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                package = cli._installed_package_for_workload("helloviya-simple")

        self.assertEqual(package, (destination / "helloviya-simple").resolve())

    def test_multiple_installed_packages_require_a_path(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(fixture, destination / "first")
            shutil.copytree(fixture, destination / "second")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                with self.assertRaisesRegex(ManifestError, "Multiple installed plugins"):
                    cli._installed_package_for_workload("helloviya-simple")

    def _copy_fixture_with_version(self, fixture: Path, destination: Path, version: str) -> None:
        shutil.copytree(fixture, destination)
        manifest = destination / "release-manifest.yaml"
        contents = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        contents["version"] = version
        manifest.write_text(yaml.safe_dump(contents), encoding="utf-8")

    def test_package_version_selects_among_multiple_installed_packages(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            self._copy_fixture_with_version(fixture, destination / "first", "2026.01.1")
            self._copy_fixture_with_version(fixture, destination / "second", "2026.06.1")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                package = cli._installed_package_for_workload("helloviya-simple", "2026.06.1")

        self.assertEqual(package, (destination / "second").resolve())

    def test_package_version_with_no_match_lists_available_versions(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            self._copy_fixture_with_version(fixture, destination / "first", "2026.01.1")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                with self.assertRaisesRegex(ManifestError, "at version '9999.99.9'"):
                    cli._installed_package_for_workload("helloviya-simple", "9999.99.9")

    def test_package_version_still_ambiguous_lists_names_and_versions(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            self._copy_fixture_with_version(fixture, destination / "first", "2026.06.1")
            self._copy_fixture_with_version(fixture, destination / "second", "2026.06.1")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                with self.assertRaisesRegex(ManifestError, "Multiple installed plugins"):
                    cli._installed_package_for_workload("helloviya-simple", "2026.06.1")

    def test_run_generate_only_uses_conventional_tool_configuration(self):
        repository_root = Path(__file__).parent.parent

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            (root / "sas-validation.yaml").write_text(
                "sas-validation:\n"
                f"  framework-root: {repository_root / 'framework'}\n"
                "  output:\n"
                f"    destination: {output}\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )
            package = repository_root / "tests/fixtures/helloviya-simple"

            with patch.object(Path, "cwd", return_value=root):
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "run",
                        str(package),
                        "-w",
                        "helloviya-simple",
                        "--plugin-version",
                        "2026.06.1",
                        "--generate-only",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            global_config = yaml.safe_load((output / "global-config.yaml").read_text())

        self.assertEqual(
            global_config["global-config"]["hostname"], "https://viya.example.com"
        )

    def test_run_package_version_is_optional(self):
        repository_root = Path(__file__).parent.parent
        package = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sas-validation.yaml").write_text(
                "sas-validation:\n"
                f"  framework-root: {repository_root / 'framework'}\n"
                "  output:\n"
                f"    destination: {root / 'output'}\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )
            with patch.object(Path, "cwd", return_value=root):
                result = CliRunner().invoke(
                    cli.app,
                    ["run", str(package), "-w", "helloviya-simple", "--generate-only"],
                )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("Missing option", result.output)

    def test_installed_package_is_selected_by_scenario(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            shutil.copytree(fixture, destination / "helloviya-simple")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                package = cli._installed_package_for_scenario("helloviya-simple")

        self.assertEqual(package, (destination / "helloviya-simple").resolve())

    def test_installed_package_for_scenario_reports_missing_match(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "packages"
            destination.mkdir()

            with patch.object(cli, "_default_package_destination", return_value=destination):
                with self.assertRaisesRegex(ManifestError, "No installed plugin"):
                    cli._installed_package_for_scenario("missing-scenario")

    def test_run_generates_ad_hoc_single_test_workload(self):
        repository_root = Path(__file__).parent.parent

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            (root / "sas-validation.yaml").write_text(
                "sas-validation:\n"
                f"  framework-root: {repository_root / 'framework'}\n"
                "  output:\n"
                f"    destination: {output}\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )
            package = repository_root / "tests/fixtures/helloviya-simple"

            with patch.object(Path, "cwd", return_value=root):
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "run",
                        str(package),
                        "--scenario",
                        "helloviya-simple",
                        "--test",
                        "createcompute.py",
                        "--users",
                        "1",
                        "--plugin-version",
                        "2026.06.1",
                        "--generate-only",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            definition = yaml.safe_load(
                (
                    output
                    / "workload-definitions/helloviya-simple-createcompute-wrkld-def.yaml"
                ).read_text()
            )

        workload = definition["workload-definitions"]["workload-definition-specs"][0][
            "custom-resource-spec"
        ]["workloads"][0]
        self.assertEqual(workload["users"], 1)
        self.assertEqual(workload["worker-replicas"], 1)

    def test_run_generates_custom_workload_from_configured_location(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom_workloads = root / "custom-workloads"
            custom_workloads.mkdir()
            shutil.copy2(
                fixture / "workload-definitions/helloviya-simple.yaml",
                custom_workloads / "helloviya-simple.yaml",
            )
            output = root / "output"
            (root / "sas-validation.yaml").write_text(
                "sas-validation:\n"
                f"  framework-root: {repository_root / 'framework'}\n"
                "  custom-workloads:\n"
                "    location: custom-workloads\n"
                "  output:\n"
                f"    destination: {output}\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )

            with patch.object(Path, "cwd", return_value=root):
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "run",
                        str(fixture),
                        "--custom-workload",
                        "helloviya-simple",
                        "--plugin-version",
                        "2026.06.1",
                        "--generate-only",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue((output / "generated/helloviya-simple/runWorkload.sh").is_file())

    def test_run_generates_custom_workload_from_local_file_without_location_config(self):
        repository_root = Path(__file__).parent.parent
        fixture = repository_root / "tests/fixtures/helloviya-simple"
        workload_file = fixture / "workload-definitions/helloviya-simple.yaml"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            (root / "sas-validation.yaml").write_text(
                "sas-validation:\n"
                f"  framework-root: {repository_root / 'framework'}\n"
                "  output:\n"
                f"    destination: {output}\n"
                "  execution:\n"
                "    hostname: https://viya.example.com\n",
                encoding="utf-8",
            )

            with patch.object(Path, "cwd", return_value=root):
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "run",
                        str(fixture),
                        "--custom-workload",
                        str(workload_file),
                        "--plugin-version",
                        "2026.06.1",
                        "--generate-only",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue((output / "generated/helloviya-simple/runWorkload.sh").is_file())

    def test_run_rejects_workload_definition_with_scenario(self):
        result = CliRunner().invoke(
            cli.app,
            [
                "run",
                "-w",
                "helloviya-simple",
                "--scenario",
                "helloviya-simple",
                "--test",
                "createcompute.py",
                "--plugin-version",
                "2026.06.1",
            ],
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not both", result.output)

    def test_run_rejects_scenario_without_test(self):
        result = CliRunner().invoke(
            cli.app,
            ["run", "--scenario", "helloviya-simple", "--plugin-version", "2026.06.1"],
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("must be provided together", result.output)

