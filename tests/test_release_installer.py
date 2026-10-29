# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from scenario_package.providers import ProviderError

from scenario_package.installer import InstallError, ReleaseInstaller
from scenario_package.providers import GitHubReleaseProvider, RepositoryAlias


class FakeTransport:
    def __init__(self, metadata, archive):
        self.metadata = metadata
        self.archive = archive
        self.downloads = 0

    def __call__(self, request):
        if "api.github.com" in request.full_url:
            return json.dumps(self.metadata).encode("utf-8")
        self.downloads += 1
        return self.archive


def archive_bytes(member_name="package/release-manifest.yaml", content=b"name: test\n"):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return stream.getvalue()


class ReleaseInstallerTests(unittest.TestCase):
    def test_install_downloads_verifies_and_extracts_asset(self):
        archive = archive_bytes()
        transport = FakeTransport(
            {
                "assets": [
                    {"name": "scenario.tar.gz", "browser_download_url": "https://download.example/a"}
                ]
            },
            archive,
        )
        provider = GitHubReleaseProvider(
            RepositoryAlias("test", "github-release", "org/project"),
            transport=transport,
        )
        installer = ReleaseInstaller(provider)
        with tempfile.TemporaryDirectory() as destination:
            installer.install(
                "0.1.0",
                "scenario.tar.gz",
                Path(destination),
                hashlib.sha256(archive).hexdigest(),
            )
            self.assertEqual(
                (Path(destination) / "package/release-manifest.yaml").read_bytes(),
                b"name: test\n",
            )

    def test_checksum_mismatch_is_rejected(self):
        archive = archive_bytes()
        transport = FakeTransport(
            {"assets": [{"name": "scenario.tar.gz", "browser_download_url": "https://download.example/a"}]},
            archive,
        )
        provider = GitHubReleaseProvider(
            RepositoryAlias("test", "github-release", "org/project"),
            transport=transport,
        )
        installer = ReleaseInstaller(provider)

        with self.assertRaisesRegex(InstallError, "Checksum mismatch"):
            installer.install("0.1.0", "scenario.tar.gz", Path(tempfile.mkdtemp()), "0" * 64)

    def test_download_error_identifies_asset_stage(self):
        archive = archive_bytes()
        transport = FakeTransport(
            {"assets": [{"name": "scenario.tar.gz", "browser_download_url": "https://download.example/a"}]},
            archive,
        )
        provider = GitHubReleaseProvider(
            RepositoryAlias("test", "github-release", "org/project"),
            transport=transport,
        )
        original_transport = provider.transport

        def failing_asset_transport(request):
            if "api.github.com" in request.full_url:
                return original_transport(request)
            raise ProviderError("HTTP Error 404: Not Found")

        provider.transport = failing_asset_transport
        installer = ReleaseInstaller(provider)

        with self.assertRaisesRegex(InstallError, "Unable to download release asset"):
            installer.install("0.1.0", "scenario.tar.gz", Path(tempfile.mkdtemp()))

    def test_install_always_downloads_and_leaves_no_archive(self):
        archive = archive_bytes()
        transport = FakeTransport(
            {"assets": [{"name": "scenario.tar.gz", "browser_download_url": "https://download.example/a"}]},
            archive,
        )
        provider = GitHubReleaseProvider(
            RepositoryAlias("test", "github-release", "org/project"),
            transport=transport,
        )
        installer = ReleaseInstaller(provider)
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            installer.install("0.1.0", "scenario.tar.gz", first)
            installer.install("0.1.0", "scenario.tar.gz", second)
            self.assertEqual(
                sorted(str(p.relative_to(directory)) for p in Path(directory).rglob("*") if p.is_file()),
                ["first/package/release-manifest.yaml", "second/package/release-manifest.yaml"],
            )

        self.assertEqual(transport.downloads, 2)

    def test_path_traversal_is_rejected(self):
        archive = archive_bytes("../outside.txt")
        transport = FakeTransport(
            {"assets": [{"name": "scenario.tar.gz", "browser_download_url": "https://download.example/a"}]},
            archive,
        )
        provider = GitHubReleaseProvider(
            RepositoryAlias("test", "github-release", "org/project"),
            transport=transport,
        )
        installer = ReleaseInstaller(provider)

        with self.assertRaisesRegex(InstallError, "escapes installation directory"):
            installer.install("0.1.0", "scenario.tar.gz", Path(tempfile.mkdtemp()))


if __name__ == "__main__":
    unittest.main()