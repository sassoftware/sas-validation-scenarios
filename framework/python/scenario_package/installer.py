# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Download and safely install curated scenario release assets."""

import hashlib
import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .providers import ProviderError, ReleaseAsset, ReleaseProvider


class InstallError(RuntimeError):
    """Raised when a release asset cannot be installed safely."""


@dataclass(frozen=True)
class InstallResult:
    destination: Path
    asset: ReleaseAsset
    entries: Tuple[Path, ...]


class ReleaseInstaller:
    """Download a release asset and extract it. Assets are always fetched fresh; nothing is cached."""

    def __init__(self, provider: ReleaseProvider):
        self.provider = provider

    def install(
        self,
        version: str,
        asset_name: Optional[str],
        destination: Path,
        expected_sha256: Optional[str] = None,
    ) -> InstallResult:
        if asset_name is not None:
            asset = self.provider.find_asset(version, asset_name)
        else:
            asset = self.provider.find_tar_asset(version)
        with tempfile.TemporaryDirectory(prefix="sas-validation-download-") as download_dir:
            archive = self._download(asset, expected_sha256, Path(download_dir))
            destination = destination.resolve()
            destination.mkdir(parents=True, exist_ok=True)
            entries = self._extract_safely(archive, destination)
        return InstallResult(destination, asset, tuple(entries))

    def _download(self, asset: ReleaseAsset, expected_sha256: Optional[str], download_dir: Path) -> Path:
        try:
            content = self.provider.transport(self.provider._download_request(asset.url))
        except ProviderError as error:
            raise InstallError(
                f"Unable to download release asset '{asset.name}' from {asset.url}: {error}"
            ) from error
        except OSError as error:
            raise InstallError(f"Unable to download release asset '{asset.name}': {error}") from error
        if expected_sha256:
            digest = hashlib.sha256(content).hexdigest()
            if digest.lower() != expected_sha256.lower():
                raise InstallError(
                    f"Checksum mismatch for '{asset.name}': expected {expected_sha256}, got {digest}"
                )
        archive = download_dir / Path(asset.name).name
        archive.write_bytes(content)
        return archive

    @staticmethod
    def _extract_safely(archive: Path, destination: Path) -> List[Path]:
        """Extract archive into destination and return the top-level entries it created."""
        try:
            with tarfile.open(archive, mode="r:*") as tar:
                members = tar.getmembers()
                for member in members:
                    if member.issym() or member.islnk():
                        raise InstallError(
                            f"Archive links are not allowed: {member.name}"
                        )
                    if not member.isdir() and not member.isfile():
                        raise InstallError(
                            f"Archive member type is not supported: {member.name}"
                        )
                    target = (destination / member.name).resolve()
                    if os.path.commonpath((str(destination), str(target))) != str(destination):
                        raise InstallError(
                            f"Archive member escapes installation directory: {member.name}"
                        )
                with tempfile.TemporaryDirectory(dir=destination) as temporary:
                    temporary_root = Path(temporary)
                    for member in members:
                        target = temporary_root / member.name
                        if member.isdir():
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        source = tar.extractfile(member)
                        if source is None:
                            raise InstallError(f"Unable to read archive member: {member.name}")
                        with source, target.open("wb") as stream:
                            stream.write(source.read())
                    children = sorted(Path(temporary).iterdir())
                    for child in children:
                        target = destination / child.name
                        if target.exists():
                            raise InstallError(f"Installation target already exists: {target}")
                    created = []
                    for child in children:
                        target = destination / child.name
                        child.rename(target)
                        created.append(target)
                    return created
        except (tarfile.TarError, OSError) as error:
            if isinstance(error, InstallError):
                raise
            raise InstallError(f"Unable to extract release asset '{archive.name}': {error}") from error