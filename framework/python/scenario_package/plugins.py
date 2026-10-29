# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin bookkeeping: install records, repository matching, status, uninstall, and validation.

A plugin is a scenario release package. An installed plugin is identified by the repository
alias it came from plus its version, because several repositories may publish plugins for the
same SAS Viya cadence.
"""

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

import yaml

from .loader import ScenarioPackage
from .manifest import ManifestError
from .providers import ReleaseAsset, ReleaseSummary, RepositoryAlias

INSTALL_RECORD_FILENAME = ".sas-validation-plugin.yaml"

STATUS_INSTALLED = "installed"
STATUS_UPDATE_AVAILABLE = "update-available"
STATUS_MARKERS = {STATUS_INSTALLED: "*", STATUS_UPDATE_AVAILABLE: "^", None: " "}
STATUS_LEGEND = (
    "* installed and current   ^ installed, newer version in repository   "
    "(blank) available, not installed"
)

_VERSION_PATTERN = re.compile(r"^(\d{4}\.\d{2})(?:\.(\d+))?$")


@dataclass(frozen=True)
class InstallRecord:
    repo: str
    provider: str
    repository: str
    tag: str
    version: str
    asset: Optional[str] = None
    base_url: Optional[str] = None
    installed_at: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "repo": self.repo,
            "provider": self.provider,
            "repository": self.repository,
            "base-url": self.base_url,
            "tag": self.tag,
            "version": self.version,
            "asset": self.asset,
            "installed-at": self.installed_at,
        }


@dataclass(frozen=True)
class CadenceVersion:
    cadence: str
    patch: int


def normalize_version(value: str) -> str:
    """Strip whitespace and a leading 'v' from a release tag or version."""
    value = value.strip()
    if len(value) > 1 and value[0] in "vV" and value[1].isdigit():
        return value[1:]
    return value


def parse_version(value: str) -> Optional[CadenceVersion]:
    """Parse ``YYYY.MM[.PATCH]``; a missing patch counts as 0. Returns None if unparseable."""
    match = _VERSION_PATTERN.match(normalize_version(value))
    if match is None:
        return None
    return CadenceVersion(match.group(1), int(match.group(2) or 0))


def write_install_record(
    plugin_root: Path, repository: RepositoryAlias, asset: ReleaseAsset, version: str
) -> InstallRecord:
    record = InstallRecord(
        repo=repository.name,
        provider=repository.provider,
        repository=repository.repository,
        base_url=repository.base_url,
        tag=asset.version,
        version=version,
        asset=asset.name,
        installed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    (plugin_root / INSTALL_RECORD_FILENAME).write_text(
        yaml.safe_dump(record.as_dict(), sort_keys=False), encoding="utf-8"
    )
    return record


def read_install_record(plugin_root: Path) -> Optional[InstallRecord]:
    """Return the install record, or None when it is missing or unreadable."""
    path = plugin_root / INSTALL_RECORD_FILENAME
    if not path.is_file():
        return None
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(values, Mapping):
        return None
    required = {key: values.get(key) for key in ("repo", "provider", "repository", "tag", "version")}
    if not all(isinstance(value, str) and value for value in required.values()):
        return None

    def optional(key: str) -> Optional[str]:
        value = values.get(key)
        return value if isinstance(value, str) else None

    return InstallRecord(
        **required,
        asset=optional("asset"),
        base_url=optional("base-url"),
        installed_at=optional("installed-at"),
    )


def belongs_to_repo(package: ScenarioPackage, alias: RepositoryAlias) -> bool:
    """True when the installed plugin came from this repository alias.

    Uses the install record when present; plugins installed before records existed fall back
    to comparing the manifest's 'repository' field with the alias's repository path.
    """
    record = read_install_record(package.root)
    if record is not None:
        return record.repo == alias.name
    return package.release.repository == alias.repository


def plugin_repos(package: ScenarioPackage, aliases: Mapping[str, RepositoryAlias]) -> List[str]:
    """Repository aliases an installed plugin is attributed to (usually one, possibly none)."""
    record = read_install_record(package.root)
    if record is not None:
        return [record.repo]
    return [name for name, alias in aliases.items() if belongs_to_repo(package, alias)]


def installed_version(package: ScenarioPackage) -> str:
    """Normalized version of an installed plugin, preferring the installed release tag."""
    record = read_install_record(package.root)
    if record is not None:
        return normalize_version(record.tag)
    return normalize_version(package.release.version)


def matches_version(package: ScenarioPackage, version: str) -> bool:
    wanted = normalize_version(version)
    record = read_install_record(package.root)
    candidates = {normalize_version(package.release.version)}
    if record is not None:
        candidates.add(normalize_version(record.tag))
        candidates.add(normalize_version(record.version))
    return wanted in candidates


def filter_by_repo(
    packages: Iterable[ScenarioPackage], alias: Optional[RepositoryAlias]
) -> List[ScenarioPackage]:
    if alias is None:
        return list(packages)
    return [package for package in packages if belongs_to_repo(package, alias)]


def release_statuses(
    releases: Sequence[ReleaseSummary],
    installed: Iterable[ScenarioPackage],
    alias: RepositoryAlias,
) -> List[Optional[str]]:
    """Status for each release, in order: 'installed', 'update-available', or None.

    'update-available' means this version is installed and the repository has a higher patch
    for the same cadence. Draft and pre-release versions never count as a newer version.
    """
    installed_versions = {
        installed_version(package) for package in installed if belongs_to_repo(package, alias)
    }
    stable = [
        parsed
        for parsed in (
            parse_version(release.version)
            for release in releases
            if not release.draft and not release.prerelease
        )
        if parsed is not None
    ]
    statuses: List[Optional[str]] = []
    for release in releases:
        if normalize_version(release.version) not in installed_versions:
            statuses.append(None)
            continue
        parsed = parse_version(release.version)
        newer = parsed is not None and any(
            other.cadence == parsed.cadence and other.patch > parsed.patch for other in stable
        )
        statuses.append(STATUS_UPDATE_AVAILABLE if newer else STATUS_INSTALLED)
    return statuses


def find_installed_plugins(
    packages: Iterable[ScenarioPackage], alias: RepositoryAlias, version: str
) -> List[ScenarioPackage]:
    return [
        package
        for package in packages
        if belongs_to_repo(package, alias) and matches_version(package, version)
    ]


def find_broken_plugins(broken: Iterable, alias: RepositoryAlias, version: str) -> List[Path]:
    """Roots of plugins with an unloadable manifest whose install record matches repo and version."""
    wanted = normalize_version(version)
    roots = []
    for entry in broken:
        record = read_install_record(entry.root)
        if record is not None and record.repo == alias.name and wanted in {
            normalize_version(record.tag),
            normalize_version(record.version),
        }:
            roots.append(entry.root)
    return roots


def plugin_root_from_entries(entries: Sequence[Path]) -> Path:
    """Pick the plugin directory from the top-level entries an archive extracted."""
    roots = [entry for entry in entries if (entry / "release-manifest.yaml").is_file()]
    if len(roots) == 1:
        return roots[0]
    raise ManifestError(
        "The release archive must contain exactly one top-level directory holding "
        f"release-manifest.yaml; found {len(roots)}"
    )


def remove_plugin(plugin_root: Path, destination: Path) -> None:
    """Delete an installed plugin directory, and its repository folder if left empty."""
    destination = destination.resolve()
    plugin_root = plugin_root.resolve()
    if plugin_root == destination or destination not in plugin_root.parents:
        raise ManifestError(
            f"Refusing to remove {plugin_root}: it is not inside the plugin destination {destination}"
        )
    if not (plugin_root / "release-manifest.yaml").is_file():
        raise ManifestError(f"Not an installed plugin (no release-manifest.yaml): {plugin_root}")
    shutil.rmtree(plugin_root)
    parent = plugin_root.parent
    if parent != destination and not any(parent.iterdir()):
        parent.rmdir()


def remove_entries(entries: Iterable[Path]) -> None:
    for entry in entries:
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def validate_plugin(plugin_root: Path) -> List[str]:
    """Return every problem found in an installed plugin; an empty list means it is valid."""
    try:
        package = ScenarioPackage(plugin_root)
    except ManifestError as error:
        return [str(error)]
    errors = [
        f"scenario '{summary.identifier}': {summary.error}"
        for summary in package.scenario_summaries()
        if summary.error is not None
    ]
    errors.extend(
        f"workload '{summary.name}': {summary.error}"
        for summary in package.workload_summaries()
        if summary.error is not None
    )
    return errors
