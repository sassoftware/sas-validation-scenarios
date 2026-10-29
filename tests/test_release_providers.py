# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import unittest
from urllib.request import Request

from scenario_package.providers import (
    GitHubReleaseProvider,
    GitLabReleaseProvider,
    ProviderError,
    RepositoryAlias,
    candidate_tags,
    create_provider,
)


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def __call__(self, request: Request) -> bytes:
        self.request = request
        return json.dumps(self.payload).encode("utf-8")


class ReleaseProviderTests(unittest.TestCase):
    def test_github_resolves_curated_asset(self):
        transport = FakeTransport(
            {
                "assets": [
                    {
                        "name": "scenario-0.1.0.tar.gz",
                        "browser_download_url": "https://download.example/scenario.tar.gz",
                    }
                ]
            }
        )
        repository = RepositoryAlias("public", "github-release", "org/project")

        asset = GitHubReleaseProvider(repository, transport=transport).find_asset(
            "0.1.0", "scenario-0.1.0.tar.gz"
        )

        self.assertEqual(asset.url, "https://download.example/scenario.tar.gz")
        self.assertIn("releases/tags/0.1.0", transport.request.full_url)

    def test_gitlab_uses_private_token_header(self):
        transport = FakeTransport(
            {
                "assets": {
                    "links": [
                        {
                            "name": "scenario.tar.gz",
                            "url": "https://gitlab.example/upload/a",
                            "direct_asset_url": "https://gitlab.example/direct/a",
                        }
                    ]
                }
            }
        )
        repository = RepositoryAlias("internal", "gitlab-release", "group/project")

        asset = GitLabReleaseProvider(
            repository, token="test-token", transport=transport
        ).find_asset("0.1.0", "scenario.tar.gz")

        self.assertEqual(asset.url, "https://gitlab.example/direct/a")
        self.assertEqual(transport.request.get_header("Private-token"), "test-token")

    def test_gitlab_falls_back_to_url_when_direct_asset_url_is_missing(self):
        transport = FakeTransport(
            {
                "assets": {
                    "links": [
                        {"name": "scenario.tar.gz", "url": "https://gitlab.example/fallback"}
                    ]
                }
            }
        )
        repository = RepositoryAlias("internal", "gitlab-release", "group/project")

        asset = GitLabReleaseProvider(repository, transport=transport).find_asset(
            "0.1.0", "scenario.tar.gz"
        )

        self.assertEqual(asset.url, "https://gitlab.example/fallback")

    def test_missing_asset_is_rejected(self):
        transport = FakeTransport({"assets": []})
        repository = RepositoryAlias("public", "github-release", "org/project")

        with self.assertRaisesRegex(ProviderError, "does not contain asset"):
            create_provider(repository, transport=transport).find_asset(
                "0.1.0", "missing.tar.gz"
            )

    def test_gitlab_uses_configured_base_url(self):
        transport = FakeTransport({"assets": {"links": []}})
        repository = RepositoryAlias(
            "internal", "gitlab-release", "group/project", base_url="https://gitlab.internal"
        )

        with self.assertRaisesRegex(ProviderError, "does not contain asset"):
            GitLabReleaseProvider(repository, transport=transport).find_asset(
                "0.1.0", "scenario.tar.gz"
            )
        self.assertIn("https://gitlab.internal/api/v4/projects/", transport.request.full_url)

    def test_unknown_provider_is_rejected(self):
        repository = RepositoryAlias("unknown", "other", "org/project")

        with self.assertRaisesRegex(ProviderError, "Unsupported release provider"):
            create_provider(repository)


class TarAssetAutoDiscoveryTests(unittest.TestCase):
    def test_github_auto_discovers_single_tar_asset(self):
        transport = FakeTransport(
            {
                "assets": [
                    {
                        "name": "scenarios-0.1.0.tar.gz",
                        "browser_download_url": "https://download.example/scenarios.tar.gz",
                    },
                    {"name": "checksums.txt", "browser_download_url": "https://download.example/checksums.txt"},
                ]
            }
        )
        repository = RepositoryAlias("public", "github-release", "org/project")

        asset = GitHubReleaseProvider(repository, transport=transport).find_tar_asset("0.1.0")

        self.assertEqual(asset.name, "scenarios-0.1.0.tar.gz")
        self.assertEqual(asset.url, "https://download.example/scenarios.tar.gz")

    def test_gitlab_auto_discovers_single_tar_asset(self):
        transport = FakeTransport(
            {
                "assets": {
                    "links": [
                        {
                            "name": "scenarios-0.1.0.tar.gz",
                            "direct_asset_url": "https://gitlab.example/direct/scenarios.tar.gz",
                        }
                    ]
                }
            }
        )
        repository = RepositoryAlias("internal", "gitlab-release", "group/project")

        asset = GitLabReleaseProvider(repository, transport=transport).find_tar_asset("0.1.0")

        self.assertEqual(asset.name, "scenarios-0.1.0.tar.gz")
        self.assertEqual(asset.url, "https://gitlab.example/direct/scenarios.tar.gz")

    def test_multiple_tar_assets_require_explicit_asset_name(self):
        transport = FakeTransport(
            {
                "assets": [
                    {"name": "full-0.1.0.tar.gz", "browser_download_url": "https://example.com/full.tar.gz"},
                    {"name": "lite-0.1.0.tar.gz", "browser_download_url": "https://example.com/lite.tar.gz"},
                ]
            }
        )
        repository = RepositoryAlias("public", "github-release", "org/project")

        with self.assertRaisesRegex(ProviderError, r"multiple .tar\.gz assets.*--asset"):
            GitHubReleaseProvider(repository, transport=transport).find_tar_asset("0.1.0")

    def test_no_tar_assets_raises_error(self):
        transport = FakeTransport(
            {
                "assets": [
                    {"name": "checksums.txt", "browser_download_url": "https://example.com/checksums.txt"},
                ]
            }
        )
        repository = RepositoryAlias("public", "github-release", "org/project")

        with self.assertRaisesRegex(ProviderError, "contains no .tar.gz asset"):
            GitHubReleaseProvider(repository, transport=transport).find_tar_asset("0.1.0")


class ListReleasesTests(unittest.TestCase):
    def test_github_lists_release_metadata(self):
        transport = FakeTransport([
            {
                "tag_name": "0.2.0",
                "name": "Platform scenarios",
                "body": "June release",
                "html_url": "https://github.com/org/project/releases/tag/0.2.0",
                "published_at": "2026-06-15T12:00:00Z",
                "assets": [
                    {
                        "name": "scenario.tar.gz",
                        "browser_download_url": "https://download.example/scenario.tar.gz",
                        "size": 123,
                        "download_count": 4,
                    }
                ],
            },
            {"tag_name": "0.1.0"},
        ])
        repository = RepositoryAlias("public", "github-release", "org/project")

        versions = GitHubReleaseProvider(repository, transport=transport).list_releases()

        self.assertEqual([version.version for version in versions], ["0.2.0", "0.1.0"])
        self.assertEqual(versions[0].name, "Platform scenarios")
        self.assertEqual(versions[0].assets[0]["size"], 123)
        self.assertIn("/repos/org/project/releases?per_page=100", transport.request.full_url)

    def test_gitlab_lists_releases(self):
        transport = FakeTransport([
            {"tag_name": "0.2.0"},
            {"tag_name": "0.1.0"},
        ])
        repository = RepositoryAlias(
            "internal", "gitlab-release", "group/project", base_url="https://gitlab.example"
        )

        versions = GitLabReleaseProvider(
            repository, token="tok", transport=transport
        ).list_releases()

        self.assertEqual([version.version for version in versions], ["0.2.0", "0.1.0"])
        self.assertIn("group%2Fproject/releases?per_page=100", transport.request.full_url)

    def test_empty_release_list_returns_empty(self):
        transport = FakeTransport([])
        repository = RepositoryAlias("public", "github-release", "org/project")

        versions = GitHubReleaseProvider(repository, transport=transport).list_releases()

        self.assertEqual(versions, [])

    def test_malformed_releases_response_is_rejected(self):
        transport = FakeTransport({"error": "not a list"})
        repository = RepositoryAlias("public", "github-release", "org/project")

        with self.assertRaisesRegex(ProviderError, "is not an array"):
            GitHubReleaseProvider(repository, transport=transport).list_releases()

    def test_missing_github_release_reports_version_and_repository(self):
        repository = RepositoryAlias("platform", "github-release", "org/project")

        with self.assertRaises(ProviderError) as raised:
            GitHubReleaseProvider(repository, transport=NotFoundTransport()).find_tar_asset("2026.09")

        message = str(raised.exception)
        self.assertEqual(raised.exception.status, 404)
        self.assertIn("Release '2026.09' was not found in repository 'platform' (org/project)", message)
        self.assertNotIn("access token", message)

    def test_missing_gitlab_release_without_token_mentions_private_access(self):
        repository = RepositoryAlias(
            "private", "gitlab-release", "group/project", visibility="private"
        )

        with self.assertRaises(ProviderError) as raised:
            GitLabReleaseProvider(repository, transport=NotFoundTransport()).find_tar_asset("2026.09")

        message = str(raised.exception)
        self.assertEqual(raised.exception.status, 404)
        self.assertIn("Release '2026.09' was not found in repository 'private' (group/project)", message)
        self.assertIn("access token", message)

    def test_non_404_release_errors_are_unchanged(self):
        repository = RepositoryAlias("platform", "github-release", "org/project")
        transport = NotFoundTransport(status=500, message="Release request failed: boom")

        with self.assertRaisesRegex(ProviderError, "^Release request failed: boom$"):
            GitHubReleaseProvider(repository, transport=transport).find_tar_asset("2026.09")

    def test_candidate_tags_try_given_form_then_alternate(self):
        self.assertEqual(candidate_tags("2026.09"), ["2026.09", "v2026.09"])
        self.assertEqual(candidate_tags(" v2026.09.1 "), ["v2026.09.1", "2026.09.1"])
        self.assertEqual(candidate_tags("latest"), ["latest"])

    def test_bare_version_resolves_v_prefixed_tag(self):
        repository = RepositoryAlias("platform", "gitlab-release", "group/project")
        transport = TagTransport("v2026.09")

        asset = GitLabReleaseProvider(repository, transport=transport).find_tar_asset("2026.09")

        self.assertEqual(asset.version, "v2026.09")
        self.assertEqual([url.rsplit("/", 1)[1] for url in transport.requested], ["2026.09", "v2026.09"])

    def test_v_prefixed_version_resolves_bare_tag(self):
        repository = RepositoryAlias("platform", "github-release", "org/project")
        transport = TagTransport("2026.09")

        asset = GitHubReleaseProvider(repository, transport=transport).find_tar_asset("v2026.09")

        self.assertEqual(asset.version, "2026.09")

    def test_exact_tag_needs_one_request(self):
        repository = RepositoryAlias("platform", "github-release", "org/project")
        transport = TagTransport("v2026.09")

        GitHubReleaseProvider(repository, transport=transport).find_tar_asset("v2026.09")

        self.assertEqual(len(transport.requested), 1)

    def test_non_404_error_does_not_try_alternate_tag(self):
        repository = RepositoryAlias("platform", "github-release", "org/project")
        transport = TagTransport("v2026.09", failure_status=500)

        with self.assertRaises(ProviderError) as raised:
            GitHubReleaseProvider(repository, transport=transport).find_tar_asset("2026.09")

        self.assertEqual(raised.exception.status, 500)
        self.assertEqual(len(transport.requested), 1)


class TagTransport:
    """Serves one release tag; every other tag fails with ``failure_status``."""

    def __init__(self, tag, failure_status=404):
        self.tag = tag
        self.failure_status = failure_status
        self.requested = []

    def __call__(self, request: Request) -> bytes:
        self.requested.append(request.full_url)
        if not request.full_url.endswith(f"/{self.tag}"):
            raise ProviderError("Release request failed", status=self.failure_status)
        if "gitlab" in request.full_url:
            payload = {"assets": {"links": [{"name": "p.tar.gz", "url": "https://example/p"}]}}
        else:
            payload = {"assets": [{"name": "p.tar.gz", "browser_download_url": "https://example/p"}]}
        return json.dumps(payload).encode("utf-8")


class NotFoundTransport:
    def __init__(self, status=404, message="Release request failed: HTTP Error 404: Not Found"):
        self.status = status
        self.message = message

    def __call__(self, request: Request) -> bytes:
        raise ProviderError(self.message, status=self.status)


if __name__ == "__main__":
    unittest.main()