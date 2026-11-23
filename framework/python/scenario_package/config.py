# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration for scenario release repository aliases."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from .manifest import ManifestError, _load_yaml, _required_string
from .providers import RepositoryAlias


@dataclass
class ScenarioPackageDefaults:
    framework_root: Optional[Path]
    destination: Optional[Path]
    custom_workloads: Optional[Path]
    output: Optional[Path]
    hostname: Optional[str]
    trusted_certs: Optional[Path]
    namespace: Optional[str] = None
    users_file: Optional[Path] = None


@dataclass
class ScenarioRepositories:
    aliases: dict[str, RepositoryAlias]
    default_repository: Optional[str]


def _resolve_path(raw_value: str, base: Path) -> Path:
    p = Path(raw_value).expanduser()
    return p if p.is_absolute() else base / p


def load_scenario_package_defaults(path: Path) -> ScenarioPackageDefaults:
    values = _load_yaml(path)
    if "scenario-package" in values and "sas-validation" not in values:
        raise ManifestError(
            f"{path}: 'scenario-package' is no longer supported; use 'sas-validation'"
        )
    raw = values.get("sas-validation")
    if raw is None:
        return ScenarioPackageDefaults(
            framework_root=None,
            destination=None,
            custom_workloads=None,
            output=None,
            hostname=None,
            trusted_certs=None,
            namespace=None,
        )
    if not isinstance(raw, Mapping):
        raise ManifestError(f"{path}: 'sas-validation' must be a mapping")
    base = path.parent

    def _optional_path(section: Mapping[str, Any], section_name: str, key: str) -> Optional[Path]:
        value = section.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(
                f"{path}: 'sas-validation.{section_name}.{key}' must be a non-empty string"
            )
        return _resolve_path(value, base)

    framework_root = raw.get("framework-root")
    if framework_root is not None:
        if not isinstance(framework_root, str) or not framework_root.strip():
            raise ManifestError(f"{path}: 'sas-validation.framework-root' must be a non-empty string")
        framework_root = _resolve_path(framework_root, base)

    installed_section = "installed-plugins" if "installed-plugins" in raw else "installed-packages"
    installed_plugins = raw.get(installed_section, {})
    if not isinstance(installed_plugins, Mapping):
        raise ManifestError(f"{path}: 'sas-validation.{installed_section}' must be a mapping")

    custom_workloads = raw.get("custom-workloads", {})
    if not isinstance(custom_workloads, Mapping):
        raise ManifestError(f"{path}: 'sas-validation.custom-workloads' must be a mapping")

    output = raw.get("output", {})
    if not isinstance(output, Mapping):
        raise ManifestError(f"{path}: 'sas-validation.output' must be a mapping")

    execution = raw.get("execution", {})
    if not isinstance(execution, Mapping):
        raise ManifestError(f"{path}: 'sas-validation.execution' must be a mapping")

    hostname = execution.get("hostname")
    if hostname is not None:
        if not isinstance(hostname, str) or not hostname.strip():
            raise ManifestError(
                f"{path}: 'sas-validation.execution.hostname' must be a non-empty string"
            )
        parsed_hostname = urlparse(hostname)
        if parsed_hostname.scheme != "https" or not parsed_hostname.netloc:
            raise ManifestError(
                f"{path}: 'sas-validation.execution.hostname' must be an HTTPS URL"
            )

    namespace = execution.get("namespace")
    if namespace is not None and (not isinstance(namespace, str) or not namespace.strip()):
        raise ManifestError(
            f"{path}: 'sas-validation.execution.namespace' must be a non-empty string"
        )

    trusted_certs = execution.get("trusted-certs")
    if trusted_certs is not None:
        if not isinstance(trusted_certs, str) or not trusted_certs.strip():
            raise ManifestError(
                f"{path}: 'sas-validation.execution.trusted-certs' must be a non-empty string"
            )
        trusted_certs = _resolve_path(trusted_certs, base)
        if not trusted_certs.is_file():
            raise ManifestError(
                f"{path}: trusted certificates file does not exist: {trusted_certs}"
            )

    return ScenarioPackageDefaults(
        framework_root=framework_root,
        destination=_optional_path(installed_plugins, installed_section, "destination"),
        custom_workloads=_optional_path(custom_workloads, "custom-workloads", "location"),
        output=_optional_path(output, "output", "destination"),
        hostname=hostname,
        trusted_certs=trusted_certs,
        namespace=namespace,
        users_file=_optional_path(execution, "execution", "users-file"),
    )


def load_repository_config(path: Path) -> ScenarioRepositories:
    values = _load_yaml(path)
    raw_repositories = values.get("scenario-repositories")
    if not isinstance(raw_repositories, Mapping):
        raise ManifestError(f"{path}: 'scenario-repositories' must be a mapping")

    aliases = {}
    for name, raw_repository in raw_repositories.items():
        if not isinstance(name, str) or not name.strip():
            raise ManifestError(f"{path}: repository alias names must be non-empty strings")
        if not isinstance(raw_repository, Mapping):
            raise ManifestError(f"{path}: repository alias '{name}' must be a mapping")
        provider = _required_string(raw_repository, "provider", path)
        repository = _required_string(raw_repository, "repository", path)
        visibility = raw_repository.get("visibility", "public")
        if not isinstance(visibility, str) or not visibility.strip():
            raise ManifestError(f"{path}: repository alias '{name}' has invalid visibility")
        base_url = raw_repository.get("base-url")
        if base_url is not None and (
            not isinstance(base_url, str) or not base_url.strip()
        ):
            raise ManifestError(f"{path}: repository alias '{name}' has invalid base-url")
        aliases[name] = RepositoryAlias(
            name=name,
            provider=provider,
            repository=repository,
            visibility=visibility,
            base_url=base_url,
        )

    default_repository = values.get("default-repository")
    if "default-repository" in values:
        if not isinstance(default_repository, str) or not default_repository.strip():
            raise ManifestError(f"{path}: 'default-repository' must be a non-empty string")
        if default_repository not in aliases:
            raise ManifestError(
                f"{path}: default repository alias '{default_repository}' is not configured"
            )

    return ScenarioRepositories(aliases, default_repository)


def load_repository_aliases(path: Path) -> dict[str, RepositoryAlias]:
    return load_repository_config(path).aliases
