# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import io
import json
import os
import shutil
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from typer.testing import CliRunner

from scenario_package import cli, plugins
from scenario_package.config import load_scenario_package_defaults
from scenario_package.loader import ScenarioPackage, installed_packages
from scenario_package.manifest import ManifestError
from scenario_package.providers import (
    GitHubReleaseProvider,
    ProviderError,
    ReleaseAsset,
    ReleaseSummary,
    RepositoryAlias,
)

FIXTURE = Path(__file__).parent / "fixtures" / "helloviya-simple"
PLATFORM = RepositoryAlias("platform", "github-release", "org/platform")
FRAUD = RepositoryAlias("fraud", "github-release", "org/fraud")
REPOSITORIES_YAML = (
    "default-repository: platform\n"
    "scenario-repositories:\n"
    "  platform: {provider: github-release, repository: org/platform}\n"
    "  fraud: {provider: github-release, repository: org/fraud}\n"
)


def _install_fixture(
    destination: Path,
    alias: RepositoryAlias,
    version: str,
    *,
    with_record: bool = True,
    folder: str = None,
    manifest_repository: str = None,
) -> Path:
    """Copy the fixture as an installed plugin of a given repo and version."""
    parent = destination / alias.name if with_record else destination
    root = parent / (folder or f"plugin-{version}")
    shutil.copytree(FIXTURE, root)
    manifest = root / "release-manifest.yaml"
    contents = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    contents["version"] = version
    contents["repository"] = manifest_repository or alias.repository
    manifest.write_text(yaml.safe_dump(contents), encoding="utf-8")
    if with_record:
        asset = ReleaseAsset(alias, version, "plugin.tar.gz", "https://example/plugin.tar.gz")
        plugins.write_install_record(root, alias, asset, version)
    return root


def _release(alias, version, **kwargs):
    return ReleaseSummary(alias, version, **kwargs)


def _invoke(directory: Path, *argv, repositories_yaml: str = REPOSITORIES_YAML, input=None):
    repositories = directory / "repositories.yaml"
    repositories.write_text(repositories_yaml, encoding="utf-8")
    config = directory / "sas-validation.yaml"
    if not config.exists():
        config.write_text("sas-validation: {}\n", encoding="utf-8")
    return CliRunner().invoke(
        cli.app,
        ["--config", str(config), "--repositories", str(repositories), *argv],
        input=input,
    )


class VersionTests(unittest.TestCase):
    def test_normalize_strips_v_prefix(self):
        self.assertEqual(plugins.normalize_version("v2026.09"), "2026.09")
        self.assertEqual(plugins.normalize_version(" 2026.09.1 "), "2026.09.1")
        self.assertEqual(plugins.normalize_version("vnext"), "vnext")

    def test_parse_cadence_and_patch(self):
        self.assertEqual(plugins.parse_version("2026.09"), plugins.CadenceVersion("2026.09", 0))
        self.assertEqual(plugins.parse_version("v2026.09.2"), plugins.CadenceVersion("2026.09", 2))
        self.assertIsNone(plugins.parse_version("0.1.0"))
        self.assertIsNone(plugins.parse_version("latest"))


class InstallRecordTests(unittest.TestCase):
    def test_record_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = ReleaseAsset(PLATFORM, "v2026.09", "p.tar.gz", "https://example/p")
            written = plugins.write_install_record(root, PLATFORM, asset, "2026.09")
            self.assertEqual(plugins.read_install_record(root), written)
            self.assertEqual(written.repo, "platform")
            self.assertEqual(written.tag, "v2026.09")

    def test_unreadable_record_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / plugins.INSTALL_RECORD_FILENAME).write_text("- not a mapping\n", encoding="utf-8")
            self.assertIsNone(plugins.read_install_record(root))


class RepoMatchingTests(unittest.TestCase):
    def test_record_decides_the_repo_even_when_manifest_disagrees(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _install_fixture(
                Path(directory), FRAUD, "2026.09", manifest_repository=PLATFORM.repository
            )
            package = ScenarioPackage(root)
            self.assertTrue(plugins.belongs_to_repo(package, FRAUD))
            self.assertFalse(plugins.belongs_to_repo(package, PLATFORM))

    def test_legacy_plugin_matches_by_manifest_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _install_fixture(Path(directory), PLATFORM, "2026.09", with_record=False)
            package = ScenarioPackage(root)
            self.assertTrue(plugins.belongs_to_repo(package, PLATFORM))
            self.assertFalse(plugins.belongs_to_repo(package, FRAUD))
            self.assertEqual(
                plugins.plugin_repos(package, {"platform": PLATFORM, "fraud": FRAUD}), ["platform"]
            )


class DiscoveryLayoutTests(unittest.TestCase):
    def test_flat_and_repo_folder_layouts_are_both_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            legacy = _install_fixture(destination, PLATFORM, "2026.08", with_record=False)
            nested = _install_fixture(destination, FRAUD, "2026.09")

            packages, broken = installed_packages(destination)

        self.assertEqual(broken, [])
        self.assertEqual(
            sorted(package.root for package in packages), sorted([legacy.resolve(), nested.resolve()])
        )


class ReleaseStatusTests(unittest.TestCase):
    def test_markers_for_current_outdated_and_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            _install_fixture(destination, PLATFORM, "2026.08")
            _install_fixture(destination, PLATFORM, "2026.09")
            installed, _ = installed_packages(destination)
            releases = [
                _release(PLATFORM, "2026.09.1"),
                _release(PLATFORM, "2026.09"),
                _release(PLATFORM, "2026.08"),
                _release(PLATFORM, "2026.07"),
            ]
            statuses = plugins.release_statuses(releases, installed, PLATFORM)

        self.assertEqual(
            statuses,
            [None, plugins.STATUS_UPDATE_AVAILABLE, plugins.STATUS_INSTALLED, None],
        )

    def test_newer_cadence_does_not_mark_update(self):
        with tempfile.TemporaryDirectory() as directory:
            _install_fixture(Path(directory), PLATFORM, "2026.09")
            installed, _ = installed_packages(Path(directory))
            statuses = plugins.release_statuses(
                [_release(PLATFORM, "2026.10"), _release(PLATFORM, "2026.09")], installed, PLATFORM
            )

        self.assertEqual(statuses, [None, plugins.STATUS_INSTALLED])

    def test_v_prefixed_tags_match_installed_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            _install_fixture(Path(directory), PLATFORM, "2026.09", with_record=False)
            installed, _ = installed_packages(Path(directory))
            statuses = plugins.release_statuses(
                [_release(PLATFORM, "v2026.09.1"), _release(PLATFORM, "v2026.09")],
                installed,
                PLATFORM,
            )

        self.assertEqual(statuses, [None, plugins.STATUS_UPDATE_AVAILABLE])

    def test_draft_and_prerelease_are_not_newer_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            _install_fixture(Path(directory), PLATFORM, "2026.09")
            installed, _ = installed_packages(Path(directory))
            statuses = plugins.release_statuses(
                [
                    _release(PLATFORM, "2026.09.2", draft=True),
                    _release(PLATFORM, "2026.09.1", prerelease=True),
                    _release(PLATFORM, "2026.09"),
                ],
                installed,
                PLATFORM,
            )

        self.assertEqual(statuses, [None, None, plugins.STATUS_INSTALLED])

    def test_unparseable_versions_match_exactly_and_never_show_update(self):
        with tempfile.TemporaryDirectory() as directory:
            _install_fixture(Path(directory), PLATFORM, "0.1.0")
            installed, _ = installed_packages(Path(directory))
            statuses = plugins.release_statuses(
                [_release(PLATFORM, "0.2.0"), _release(PLATFORM, "0.1.0")], installed, PLATFORM
            )

        self.assertEqual(statuses, [None, plugins.STATUS_INSTALLED])

    def test_same_cadence_in_another_repo_is_not_marked(self):
        with tempfile.TemporaryDirectory() as directory:
            _install_fixture(Path(directory), PLATFORM, "2026.09")
            installed, _ = installed_packages(Path(directory))
            statuses = plugins.release_statuses([_release(FRAUD, "2026.09")], installed, FRAUD)

        self.assertEqual(statuses, [None])


class ListRepoPluginsCommandTests(unittest.TestCase):
    def _providers(self, releases_by_repo, failures=()):
        def create(alias, token=None):
            provider = Mock()
            if alias.name in failures:
                provider.list_releases.side_effect = ProviderError("Release request failed: HTTP 404")
            else:
                provider.list_releases.return_value = releases_by_repo.get(alias.name, [])
            return provider

        return create

    def test_lists_every_configured_repository_with_status_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            _install_fixture(destination, PLATFORM, "2026.09")
            releases = {
                "platform": [
                    _release(PLATFORM, "2026.09.1", name="Patch", url="https://example/r/1"),
                    _release(PLATFORM, "2026.09"),
                ],
                "fraud": [_release(FRAUD, "2026.09", name="Fraud September")],
            }
            with patch.object(cli, "create_provider", side_effect=self._providers(releases)):
                result = _invoke(
                    root, "plugins", "list-repo-plugins", "--destination", str(destination)
                )

        self.assertEqual(result.exit_code, 0, result.output)
        lines = result.output.splitlines()
        self.assertIn("Repository: platform (github-release org/platform)", lines)
        self.assertIn("Repository: fraud (github-release org/fraud)", lines)
        self.assertIn("  2026.09.1  Patch", lines)
        self.assertIn("    url: https://example/r/1", lines)
        self.assertIn("^ 2026.09", lines)
        self.assertIn("  2026.09  Fraud September", lines)
        self.assertTrue(any(line.startswith("Status: * installed") for line in lines))

    def test_repo_option_limits_to_one_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(
                cli, "create_provider", side_effect=self._providers({})
            ) as create_provider:
                result = _invoke(
                    root,
                    "plugins",
                    "list-repo-plugins",
                    "--repo",
                    "fraud",
                    "--destination",
                    str(root / "plugins"),
                )

        self.assertEqual(result.exit_code, 0, result.output)
        create_provider.assert_called_once_with(FRAUD, token=None)
        self.assertNotIn("Repository: platform", result.output)

    def test_failing_repository_is_reported_and_others_still_listed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            releases = {"fraud": [_release(FRAUD, "2026.09")]}
            with patch.object(
                cli, "create_provider", side_effect=self._providers(releases, failures={"platform"})
            ):
                result = _invoke(
                    root, "plugins", "list-repo-plugins", "--destination", str(root / "plugins")
                )

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("  ERROR: Release request failed: HTTP 404", result.output)
        self.assertIn("  2026.09", result.output)

    def test_json_groups_plugins_by_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            _install_fixture(destination, FRAUD, "2026.09")
            releases = {
                "platform": [_release(PLATFORM, "2026.09")],
                "fraud": [_release(FRAUD, "2026.09")],
            }
            with patch.object(cli, "create_provider", side_effect=self._providers(releases)):
                result = _invoke(
                    root,
                    "plugins",
                    "list-repo-plugins",
                    "--destination",
                    str(destination),
                    "--json",
                )

        self.assertEqual(result.exit_code, 0, result.output)
        payload = {entry["repo"]: entry for entry in json.loads(result.output)}
        self.assertIsNone(payload["platform"]["plugins"][0]["status"])
        self.assertEqual(payload["fraud"]["plugins"][0]["status"], "installed")
        self.assertTrue(payload["fraud"]["plugins"][0]["installed"])
        self.assertIn("assets", payload["fraud"]["plugins"][0])

    def test_unknown_repo_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _invoke(Path(directory), "plugins", "list-repo-plugins", "--repo", "missing")

        self.assertEqual(result.exit_code, 2)
        self.assertIn("is not configured", result.output)

    def test_missing_gitlab_token_is_reported_with_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {}, clear=True), patch(
                "scenario_package.credentials.glab_token", return_value=None
            ), patch("scenario_package.credentials.git_credential_token", return_value=None):
                result = _invoke(
                    root,
                    "plugins",
                    "list-repo-plugins",
                    "--destination",
                    str(root / "plugins"),
                    repositories_yaml=(
                        "scenario-repositories:\n"
                        "  internal: {provider: gitlab-release, repository: group/project}\n"
                    ),
                )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("SAS_VALIDATION_RELEASE_TOKEN", result.output)
        self.assertIn("glab auth login --hostname gitlab.com", result.output)


class ListReposCommandTests(unittest.TestCase):
    def test_lists_aliases_and_marks_default(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _invoke(Path(directory), "plugins", "list-repos")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("platform (default)", result.output)
        self.assertIn("org/fraud", result.output)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _invoke(Path(directory), "plugins", "list-repos", "--json")

        payload = json.loads(result.output)
        self.assertEqual([row["name"] for row in payload], ["platform", "fraud"])
        self.assertTrue(payload[0]["default"])
        self.assertFalse(payload[1]["default"])


def _fixture_archive(top_level: str) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        archive.add(FIXTURE, arcname=top_level)
    return stream.getvalue()


class FakeTransport:
    def __init__(self, tag, archive):
        self.tag = tag
        self.archive = archive
        self.requested = []

    def __call__(self, request):
        if "api.github.com" in request.full_url:
            self.requested.append(request.full_url)
            if not request.full_url.endswith(f"/releases/tags/{self.tag}"):
                raise ProviderError("Release request failed: HTTP Error 404: Not Found", status=404)
            return json.dumps(
                {
                    "tag_name": self.tag,
                    "assets": [
                        {"name": "plugin.tar.gz", "browser_download_url": "https://download.example/p"}
                    ],
                }
            ).encode("utf-8")
        return self.archive


class InstallCommandTests(unittest.TestCase):
    def _install(self, root, *extra, archive=None, tag="0.1.0", version=None):
        archive = archive if archive is not None else _fixture_archive("hello-viya-scenarios-0.1.0")

        def create(alias, token=None):
            return GitHubReleaseProvider(alias, transport=FakeTransport(tag, archive))

        with patch.object(cli, "create_provider", side_effect=create), patch.object(
            cli, "user_cache_path", return_value=root / "cache"
        ):
            return _invoke(
                root,
                "plugins",
                "install",
                "--version",
                version if version is not None else tag,
                "--destination",
                str(root / "plugins"),
                *extra,
            )

    def test_bare_version_installs_v_prefixed_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._install(root, tag="v0.1.0", version="0.1.0")
            plugin_root = root / "plugins" / "platform" / "hello-viya-scenarios-0.1.0"
            record = plugins.read_install_record(plugin_root)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Installing plugin version 0.1.0", result.output)
        self.assertEqual(record.tag, "v0.1.0")

    def test_v_prefixed_version_installs_bare_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._install(root, tag="0.1.0", version="v0.1.0")
            plugin_root = root / "plugins" / "platform" / "hello-viya-scenarios-0.1.0"
            record = plugins.read_install_record(plugin_root)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Installing plugin version 0.1.0", result.output)
        self.assertEqual(record.tag, "0.1.0")

    def test_reinstall_is_rejected_whichever_form_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._install(root, tag="v0.1.0", version="v0.1.0")
            second = self._install(root, tag="v0.1.0", version="0.1.0")

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 2)
        self.assertIn("Plugin version '0.1.0' from repository 'platform' is already installed", second.output)

    def test_installs_from_default_repo_into_repo_folder_with_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._install(root)
            plugin_root = root / "plugins" / "platform" / "hello-viya-scenarios-0.1.0"
            record = plugins.read_install_record(plugin_root)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("from repository 'platform'", result.output)
        self.assertIn(f"installed_plugin={plugin_root.resolve()}", result.output)
        self.assertEqual(record.repo, "platform")
        self.assertEqual(record.tag, "0.1.0")
        self.assertEqual(record.asset, "plugin.tar.gz")

    def test_same_plugin_from_two_repos_does_not_collide(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._install(root)
            second = self._install(root, "--repo", "fraud")
            packages, _ = installed_packages(root / "plugins")
            repos = sorted(plugins.read_install_record(package.root).repo for package in packages)

        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertEqual(repos, ["fraud", "platform"])

    def test_reinstalling_same_repo_and_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._install(root)
            result = self._install(root)

        self.assertEqual(result.exit_code, 2)
        self.assertIn("already installed", result.output)
        self.assertIn("plugins uninstall --repo platform --version 0.1.0", result.output)

    def test_flat_archive_is_rejected_and_cleaned_up(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            archive.add(FIXTURE / "release-manifest.yaml", arcname="release-manifest.yaml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self._install(root, archive=stream.getvalue())
            leftovers = list((root / "plugins").rglob("*"))

        self.assertEqual(result.exit_code, 2)
        self.assertIn("exactly one top-level directory", result.output)
        self.assertEqual(leftovers, [])

    def test_requires_repo_when_no_default_is_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _invoke(
                Path(directory),
                "plugins",
                "install",
                "--version",
                "2026.09",
                repositories_yaml=(
                    "scenario-repositories:\n"
                    "  platform: {provider: github-release, repository: org/platform}\n"
                ),
            )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Pass --repo <alias>", result.output)

    def test_unknown_repo_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _invoke(
                Path(directory), "plugins", "install", "--repo", "missing", "--version", "2026.09"
            )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("is not configured", result.output)

    def test_missing_release_explains_and_points_to_available_versions(self):
        def missing(request):
            raise ProviderError("Release request failed: HTTP Error 404: Not Found", status=404)

        def create(alias, token=None):
            return GitHubReleaseProvider(alias, transport=missing)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(cli, "create_provider", side_effect=create), patch.object(
                cli, "user_cache_path", return_value=root / "cache"
            ):
                result = _invoke(
                    root, "plugins", "install", "--version", "2026.09",
                    "--destination", str(root / "plugins"),
                )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Release '2026.09' was not found in repository 'platform'", result.output)
        self.assertIn("plugins list-repo-plugins --repo platform", result.output)


class UninstallCommandTests(unittest.TestCase):
    def test_removes_plugin_from_selected_repo_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            platform_root = _install_fixture(destination, PLATFORM, "2026.09")
            fraud_root = _install_fixture(destination, FRAUD, "2026.09")

            result = _invoke(
                root,
                "plugins",
                "uninstall",
                "--repo",
                "fraud",
                "--version",
                "2026.09",
                "--destination",
                str(destination),
                "--yes",
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(platform_root.is_dir())
            self.assertFalse(fraud_root.exists())
            self.assertFalse((destination / "fraud").exists())

    def test_defaults_to_default_repository_and_confirms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            platform_root = _install_fixture(destination, PLATFORM, "2026.09")

            declined = _invoke(
                root,
                "plugins",
                "uninstall",
                "--version",
                "v2026.09",
                "--destination",
                str(destination),
                input="n\n",
            )
            self.assertEqual(declined.exit_code, 1, declined.output)
            self.assertIn("Aborted", declined.output)
            self.assertTrue(platform_root.is_dir())

            accepted = _invoke(
                root,
                "plugins",
                "uninstall",
                "--version",
                "2026.09",
                "--destination",
                str(destination),
                input="y\n",
            )
            self.assertEqual(accepted.exit_code, 0, accepted.output)
            self.assertFalse(platform_root.exists())

    def test_legacy_plugin_is_matched_by_manifest_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            legacy = _install_fixture(destination, PLATFORM, "2026.08", with_record=False)

            result = _invoke(
                root,
                "plugins",
                "uninstall",
                "--version",
                "2026.08",
                "--destination",
                str(destination),
                "--yes",
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse(legacy.exists())
            self.assertTrue(destination.is_dir())

    def test_no_match_reports_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _install_fixture(root / "plugins", PLATFORM, "2026.09")
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                "--repo",
                "fraud",
                "--version",
                "2026.09",
                "--destination",
                str(root / "plugins"),
                "--yes",
            )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("No plugin version '2026.09' from repository 'fraud'", result.output)

    def test_ambiguous_match_asks_for_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            _install_fixture(destination, PLATFORM, "2026.09", folder="a")
            _install_fixture(destination, PLATFORM, "2026.09", folder="b")
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                "--version",
                "2026.09",
                "--destination",
                str(destination),
                "--yes",
            )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Pass the plugin path", result.output)

    def test_uninstall_by_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            plugin_root = _install_fixture(destination, PLATFORM, "2026.09")
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                str(plugin_root),
                "--destination",
                str(destination),
                "--yes",
                "--json",
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(json.loads(result.output)["removed_plugin"], str(plugin_root.resolve()))
            self.assertFalse(plugin_root.exists())

    def test_path_outside_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "elsewhere" / "plugin"
            shutil.copytree(FIXTURE, outside)
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                str(outside),
                "--destination",
                str(root / "plugins"),
                "--yes",
            )

            self.assertEqual(result.exit_code, 2)
            self.assertIn("not inside the plugin destination", result.output)
            self.assertTrue(outside.is_dir())

    def test_missing_path_suggests_version_option(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            plugin_root = _install_fixture(destination, PLATFORM, "2026.09")
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                "v2026.09",
                "--destination",
                str(destination),
                "--yes",
            )

            self.assertEqual(result.exit_code, 2)
            self.assertIn("No plugin directory at", result.output)
            self.assertIn("plugins uninstall --version v2026.09", result.output)
            self.assertTrue(plugin_root.is_dir())

    def test_path_and_version_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            result = _invoke(
                Path(directory), "plugins", "uninstall", "somewhere", "--version", "2026.09"
            )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not both", result.output)

    def _break_manifest(self, plugin_root: Path) -> None:
        (plugin_root / "release-manifest.yaml").write_text(
            "schema-version: \"1\"\nname: broken\n", encoding="utf-8"
        )

    def test_broken_plugin_can_be_uninstalled_by_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            plugin_root = _install_fixture(destination, PLATFORM, "2026.09")
            self._break_manifest(plugin_root)
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                str(plugin_root),
                "--destination",
                str(destination),
                "--yes",
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse(plugin_root.exists())

    def test_broken_plugin_can_be_uninstalled_by_repo_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            plugin_root = _install_fixture(destination, PLATFORM, "2026.09")
            self._break_manifest(plugin_root)
            result = _invoke(
                root,
                "plugins",
                "uninstall",
                "--repo",
                "platform",
                "--version",
                "2026.09",
                "--destination",
                str(destination),
                "--yes",
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse(plugin_root.exists())


class ValidateCommandTests(unittest.TestCase):
    def test_valid_plugin_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _install_fixture(root / "plugins", PLATFORM, "2026.09")
            result = _invoke(
                root, "plugins", "validate", "--destination", str(root / "plugins")
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("PASS  hello-viya-scenarios 2026.09", result.output)
        self.assertIn("1 plugin(s) validated, 0 failed", result.output)

    def test_missing_scenario_directory_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_root = _install_fixture(root / "plugins", PLATFORM, "2026.09")
            shutil.rmtree(plugin_root / "scenarios" / "helloviya-simple")
            result = _invoke(
                root, "plugins", "validate", "--destination", str(root / "plugins"), "--json"
            )

        self.assertEqual(result.exit_code, 1, result.output)
        payload = json.loads(result.output)
        self.assertFalse(payload[0]["valid"])
        self.assertTrue(any("helloviya-simple" in error for error in payload[0]["errors"]))

    def test_broken_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_root = _install_fixture(root / "plugins", PLATFORM, "2026.09")
            (plugin_root / "release-manifest.yaml").write_text("schema-version: \"1\"\n", encoding="utf-8")
            result = _invoke(root, "plugins", "validate", "--destination", str(root / "plugins"))

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("FAIL", result.output)

    def test_repo_filter_limits_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _install_fixture(root / "plugins", PLATFORM, "2026.09")
            broken = _install_fixture(root / "plugins", FRAUD, "2026.09")
            shutil.rmtree(broken / "scenarios")
            result = _invoke(
                root,
                "plugins",
                "validate",
                "--repo",
                "platform",
                "--destination",
                str(root / "plugins"),
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("1 plugin(s) validated, 0 failed", result.output)

    def test_legacy_name_and_unused_path_are_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_root = _install_fixture(root / "plugins", PLATFORM, "2026.09")
            config = plugin_root / "scenarios" / "helloviya-simple" / "scenario-config.yaml"
            values = yaml.safe_load(config.read_text(encoding="utf-8"))
            values["scenario-config"].setdefault("dependencies", []).extend(
                [
                    {"type": "cli-profile", "path": "framework/execution/common", "file": "config.json"},
                    {"type": "trusted-certs"},
                ]
            )
            config.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
            text = _invoke(root, "plugins", "validate", "--destination", str(root / "plugins"))
            as_json = _invoke(
                root, "plugins", "validate", "--destination", str(root / "plugins"), "--json"
            )

        self.assertEqual(text.exit_code, 0, text.output)
        self.assertIn("PASS", text.output)
        self.assertIn("WARNING:", text.output)
        payload = json.loads(as_json.output)
        self.assertTrue(payload[0]["valid"])
        warnings_ = payload[0]["warnings"]
        self.assertEqual(len(warnings_), 2)
        self.assertIn("type 'cli-profile' is renamed 'config-json'", warnings_[0])
        self.assertIn("(config-json): 'path' and 'file' are not used", warnings_[1])
    def test_list_shows_repo_and_filters_by_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "plugins"
            _install_fixture(destination, PLATFORM, "2026.09")
            _install_fixture(destination, FRAUD, "2026.09")

            everything = _invoke(root, "plugins", "list", "--destination", str(destination))
            fraud_only = _invoke(
                root,
                "plugins",
                "list",
                "--repo",
                "fraud",
                "--destination",
                str(destination),
                "--json",
            )

        self.assertEqual(everything.exit_code, 0, everything.output)
        self.assertIn("repo platform", everything.output)
        self.assertIn("repo fraud", everything.output)
        payload = json.loads(fraud_only.output)
        self.assertEqual([entry["repo"] for entry in payload], ["fraud"])


class RunSelectionTests(unittest.TestCase):
    def test_repo_disambiguates_same_workload_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            _install_fixture(destination, PLATFORM, "2026.09")
            fraud_root = _install_fixture(destination, FRAUD, "2026.09")

            with patch.object(cli, "_default_package_destination", return_value=destination):
                with self.assertRaisesRegex(ManifestError, "--repo"):
                    cli._installed_package_for_workload("helloviya-simple", "2026.09")
                selected = cli._installed_package_for_workload(
                    "helloviya-simple", "2026.09", repo=FRAUD
                )

        self.assertEqual(selected, fraud_root.resolve())


class ConfigKeyTests(unittest.TestCase):
    def test_installed_plugins_key_sets_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n  installed-plugins:\n    destination: my-plugins\n",
                encoding="utf-8",
            )
            defaults = load_scenario_package_defaults(config)

        self.assertEqual(defaults.destination, Path(directory) / "my-plugins")

    def test_installed_plugins_key_wins_over_legacy_key(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "sas-validation.yaml"
            config.write_text(
                "sas-validation:\n"
                "  installed-packages:\n    destination: old\n"
                "  installed-plugins:\n    destination: new\n",
                encoding="utf-8",
            )
            defaults = load_scenario_package_defaults(config)

        self.assertEqual(defaults.destination, Path(directory) / "new")


class RemovedCommandsTests(unittest.TestCase):
    def test_packages_and_releases_groups_are_gone(self):
        for group in ("packages", "releases"):
            result = CliRunner().invoke(cli.app, [group, "list"])
            self.assertNotEqual(result.exit_code, 0)


@unittest.skipUnless(hasattr(time, "tzset"), "time.tzset is required to pin the local time zone")
class LocalTimestampTests(unittest.TestCase):
    def setUp(self):
        self._original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()

    def tearDown(self):
        if self._original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._original_tz
        time.tzset()

    def test_gitlab_timestamp_with_milliseconds(self):
        self.assertEqual(
            cli._local_timestamp("2026-10-20T19:02:06.090Z"), "2026-10-20 15:02:06 EDT"
        )

    def test_github_timestamp(self):
        self.assertEqual(cli._local_timestamp("2026-12-01T18:58:29Z"), "2026-12-01 13:58:29 EST")

    def test_explicit_offset(self):
        self.assertEqual(
            cli._local_timestamp("2026-10-20T21:02:06+02:00"), "2026-10-20 15:02:06 EDT"
        )

    def test_unparseable_value_is_returned_unchanged(self):
        self.assertEqual(cli._local_timestamp("yesterday"), "yesterday")

    def test_release_label_uses_local_time(self):
        release = ReleaseSummary(
            PLATFORM,
            "v2026.08",
            name="Scenario package 2026.08",
            published_at="2026-10-20T19:02:06.090Z",
        )
        self.assertIn("published 2026-10-20 15:02:06 EDT", cli._release_label(release))

    def test_release_label_shows_version_without_tag_prefix(self):
        release = ReleaseSummary(PLATFORM, "v2026.08", name="Scenario package 2026.08")
        self.assertTrue(cli._release_label(release).startswith("2026.08  Scenario package"))

    def test_release_json_has_normalized_version_and_raw_tag(self):
        payload = ReleaseSummary(PLATFORM, "v2026.08").as_dict()
        self.assertEqual(payload["version"], "2026.08")
        self.assertEqual(payload["tag"], "v2026.08")


if __name__ == "__main__":
    unittest.main()
