# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structured loading and validation of scenario package manifests."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


class ManifestError(ValueError):
    """Raised when a scenario package manifest is invalid."""


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        import yaml
    except ImportError as error:
        raise ManifestError(
            "PyYAML is required to read scenario manifests; install the package "
            "with `pip install -e .`"
        ) from error

    try:
        with path.open("r", encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except OSError as error:
        raise ManifestError(f"Unable to read manifest {path}: {error}") from error
    except yaml.YAMLError as error:
        raise ManifestError(f"Invalid YAML in {path}: {error}") from error

    if not isinstance(value, Mapping):
        raise ManifestError(f"Manifest {path} must contain a YAML mapping")
    return value


def _required_string(values: Mapping[str, Any], key: str, path: Path) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{path}: '{key}' must be a non-empty string")
    return value


def safe_relative_path(value: str, field: str, manifest_path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError(
            f"{manifest_path}: '{field}' must be a safe relative path: {value}"
        )
    return candidate


PLUGIN_COMMON_DEPENDENCY = "plugin-common"


def plugin_common_dependencies(values: Mapping[str, Any], path: Path) -> List[Path]:
    """Return the package-root-relative files of every `plugin-common` dependency."""
    raw_dependencies = values.get("dependencies")
    if raw_dependencies is None:
        return []
    if not isinstance(raw_dependencies, list):
        raise ManifestError(f"{path}: 'dependencies' must be a list")

    files = []
    for index, dependency in enumerate(raw_dependencies):
        if not isinstance(dependency, Mapping):
            continue
        if dependency.get("type") != PLUGIN_COMMON_DEPENDENCY:
            continue
        location = f"dependencies[{index}]"
        dependency_path = dependency.get("path")
        dependency_file = dependency.get("file")
        if not isinstance(dependency_path, str) or not dependency_path.strip():
            raise ManifestError(f"{path}: '{location}.path' must be a non-empty string")
        if not isinstance(dependency_file, str) or not dependency_file.strip():
            raise ManifestError(f"{path}: '{location}.file' must be a non-empty string")
        files.append(
            safe_relative_path(
                str(Path(dependency_path) / dependency_file), location, path
            )
        )
    return files


def read_plugin_common_dependencies(path: Path) -> List[Path]:
    values = _load_yaml(path)
    if "scenario-config" in values:
        values = values["scenario-config"]
    if not isinstance(values, Mapping):
        raise ManifestError(f"{path}: scenario metadata must be a mapping")
    return plugin_common_dependencies(values, path)


@dataclass(frozen=True)
class ScenarioReference:
    identifier: str
    path: Path


@dataclass(frozen=True)
class ReleaseManifest:
    name: str
    version: str
    viya_cadence: str
    repository: str
    scenarios: List[ScenarioReference]
    schema_version: str = "1"

    @classmethod
    def from_file(cls, path: Path) -> "ReleaseManifest":
        values = _load_yaml(path)
        schema_version = str(values.get("schema-version", "1"))
        if schema_version != "1":
            raise ManifestError(
                f"{path}: unsupported schema-version '{schema_version}'; expected '1'"
            )

        raw_scenarios = values.get("scenarios")
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise ManifestError(f"{path}: 'scenarios' must be a non-empty list")

        scenarios = []
        identifiers = set()
        for index, raw_scenario in enumerate(raw_scenarios):
            field = f"scenarios[{index}]"
            if not isinstance(raw_scenario, Mapping):
                raise ManifestError(f"{path}: '{field}' must be a mapping")
            identifier = _required_string(raw_scenario, "id", path)
            if identifier in identifiers:
                raise ManifestError(f"{path}: duplicate scenario id '{identifier}'")
            identifiers.add(identifier)
            scenario_path = safe_relative_path(
                _required_string(raw_scenario, "path", path),
                f"{field}.path",
                path,
            )
            scenarios.append(ScenarioReference(identifier, scenario_path))

        return cls(
            name=_required_string(values, "name", path),
            version=_required_string(values, "version", path),
            viya_cadence=_required_string(values, "viya-cadence", path),
            repository=_required_string(values, "repository", path),
            scenarios=scenarios,
            schema_version=schema_version,
        )


@dataclass(frozen=True)
class ScenarioManifest:
    identifier: str
    display_name: str
    runtime: str
    entrypoints: List[Path]
    workload_definitions: List[Path]
    required_resources: List[Path]
    plugin_common: List[Path] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path) -> "ScenarioManifest":
        values = _load_yaml(path)
        if "scenario-config" in values:
            values = values["scenario-config"]
        if not isinstance(values, Mapping):
            raise ManifestError(f"{path}: scenario metadata must be a mapping")

        raw_entrypoints = values.get("entrypoints", values.get("entrypoint"))
        if isinstance(raw_entrypoints, str):
            raw_entrypoints = [raw_entrypoints]
        if not isinstance(raw_entrypoints, list) or not raw_entrypoints:
            raise ManifestError(f"{path}: 'entrypoint' or 'entrypoints' is required")

        entrypoints = [
            safe_relative_path(value, "entrypoints", path)
            for value in raw_entrypoints
            if isinstance(value, str)
        ]
        if len(entrypoints) != len(raw_entrypoints):
            raise ManifestError(f"{path}: every entrypoint must be a string")

        raw_workloads = values.get("workload-definitions", [])
        if isinstance(raw_workloads, str):
            raw_workloads = [raw_workloads]
        if not isinstance(raw_workloads, list):
            raise ManifestError(f"{path}: 'workload-definitions' must be a list")
        workload_definitions = [
            safe_relative_path(value, "workload-definitions", path)
            for value in raw_workloads
            if isinstance(value, str)
        ]
        if len(workload_definitions) != len(raw_workloads):
            raise ManifestError(f"{path}: every workload definition must be a string")

        raw_resources = values.get("required-resources", [])
        if not isinstance(raw_resources, list):
            raise ManifestError(f"{path}: 'required-resources' must be a list")
        required_resources = []
        for index, value in enumerate(raw_resources):
            resource_path: Optional[str]
            if isinstance(value, str):
                resource_path = value
            elif isinstance(value, Mapping):
                resource_path = value.get("path")
                if resource_path is None:
                    raise ManifestError(
                        f"{path}: 'required-resources[{index}]' must contain 'path'"
                    )
            else:
                raise ManifestError(
                    f"{path}: 'required-resources[{index}]' must be a string or mapping"
                )
            if not isinstance(resource_path, str):
                raise ManifestError(
                    f"{path}: 'required-resources[{index}].path' must be a string"
                )
            required_resources.append(
                safe_relative_path(resource_path, "required-resources", path)
            )

        return cls(
            identifier=_required_string(values, "id", path),
            display_name=_required_string(values, "display-name", path),
            runtime=_required_string(values, "runtime", path),
            entrypoints=entrypoints,
            workload_definitions=workload_definitions,
            required_resources=required_resources,
            plugin_common=plugin_common_dependencies(values, path),
        )
