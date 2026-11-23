# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve packaged and legacy scenario layouts into common filesystem paths."""

from datetime import datetime
import json
import os
import site
import signal
import subprocess
import sys
import sysconfig
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from .manifest import (
    EXECUTION_TARGET_KUBERNETES,
    EXECUTION_TARGET_LOCAL,
    EXECUTION_TARGETS,
    ManifestError,
    ReleaseManifest,
    ScenarioManifest,
    read_execution_targets,
    read_plugin_common_dependencies,
    safe_relative_path,
)

WORKLOAD_DEFINITIONS_DIRECTORY = "workload-definitions"
RUN_WORKLOAD_SCRIPT = "runWorkload.sh"
RUN_WORKLOAD_LOCAL_SCRIPT = "runWorkloadLocal.sh"
LOCUST_OVERRIDE_ENV = "SAS_VALIDATION_LOCUST"


def local_locust_executable() -> Optional[Path]:
    """The locust script installed for the interpreter running sas-validation, if any.

    Checked in the interpreter's scripts directory, then the per-user one (pip --user),
    so local runs use the same environment the dependency checks inspected.
    """
    names = ("locust.exe", "locust") if os.name == "nt" else ("locust",)
    directories = [sysconfig.get_path("scripts")]
    if site.ENABLE_USER_SITE:
        scheme = f"{os.name}_user"
        if scheme in sysconfig.get_scheme_names():
            directories.append(sysconfig.get_path("scripts", scheme))
    for directory in directories:
        if not directory:
            continue
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    return None


@dataclass(frozen=True)
class PackageLayout:
    package_root: Path
    scenario_root: Path
    workload_definitions_root: Path
    resources_root: Path
    framework_root: Optional[Path] = None


@dataclass(frozen=True)
class LegacyInputs:
    global_config: Path
    workload_definition: Path
    generated_root: Path


@dataclass(frozen=True)
class WorkloadDefinition:
    """A runnable workload: one or more scenarios plus their execution settings."""

    name: str
    path: Path
    spec_names: tuple[str, ...]
    scenario_configs: tuple[str, ...]


@dataclass(frozen=True)
class WorkloadSummary:
    """A workload spec as shown by discovery commands; never raises on bad input."""

    name: str
    description: Optional[str]
    source: Path
    scenario_configs: tuple[str, ...]
    error: Optional[str] = None


@dataclass(frozen=True)
class ScenarioSummary:
    identifier: str
    display_name: Optional[str]
    path: Path
    entrypoints: tuple[Path, ...] = ()
    error: Optional[str] = None


@dataclass(frozen=True)
class GenerationResult:
    inputs: LegacyInputs
    generated_workload_root: Path


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        import yaml
    except ImportError as error:
        raise ManifestError("PyYAML is required to read workload definitions") from error
    try:
        with path.open("r", encoding="utf-8") as stream:
            values = yaml.safe_load(stream)
    except OSError as error:
        raise ManifestError(f"Unable to read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise ManifestError(f"Invalid YAML in {path}: {error}") from error
    if not isinstance(values, Mapping):
        raise ManifestError(f"{path} must contain a YAML mapping")
    return values


def _workload_specs(path: Path) -> List[Mapping[str, Any]]:
    values = _load_yaml_mapping(path)
    root = values.get("workload-definitions")
    if not isinstance(root, Mapping):
        raise ManifestError(f"{path}: 'workload-definitions' must be a mapping")
    specs = root.get("workload-definition-specs")
    if not isinstance(specs, list) or not specs:
        raise ManifestError(
            f"{path}: 'workload-definition-specs' must be a non-empty list"
        )
    for index, spec in enumerate(specs):
        if not isinstance(spec, Mapping):
            raise ManifestError(
                f"{path}: 'workload-definition-specs[{index}]' must be a mapping"
            )
    return specs


class ScenarioPackage:
    """Load a package without changing the existing workload generator."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.release = ReleaseManifest.from_file(self.root / "release-manifest.yaml")

    def scenario(self, identifier: str) -> tuple[PackageLayout, ScenarioManifest]:
        reference = next(
            (item for item in self.release.scenarios if item.identifier == identifier),
            None,
        )
        if reference is None:
            raise ManifestError(
                f"{self.root / 'release-manifest.yaml'}: scenario '{identifier}' is not included"
            )

        scenario_root = self.root / reference.path
        if not scenario_root.is_dir():
            raise ManifestError(f"Scenario directory does not exist: {scenario_root}")

        manifest_path = scenario_root / "scenario-manifest.yaml"
        if not manifest_path.is_file():
            manifest_path = scenario_root / "scenario-config.yaml"
        manifest = ScenarioManifest.from_file(manifest_path)
        if manifest.identifier != identifier:
            raise ManifestError(
                f"{manifest_path}: id '{manifest.identifier}' does not match '{identifier}'"
            )

        layout = PackageLayout(
            package_root=self.root,
            scenario_root=scenario_root,
            workload_definitions_root=self.root / "workload-definitions",
            resources_root=self.root / "resources",
        )
        self._validate_files(layout, manifest, manifest_path)
        self._validate_plugin_common(layout, manifest, manifest_path)
        config_path = scenario_root / "scenario-config.yaml"
        if config_path != manifest_path and config_path.is_file():
            read_execution_targets(config_path)
        return layout, manifest

    def synthesize_workload_definition(
        self,
        scenario_id: str,
        test: str,
        output_root: Path,
        *,
        users: Optional[int] = None,
        spawn_rate: Optional[int] = None,
        iterations: Optional[int] = None,
    ) -> Path:
        """Build an ephemeral single-test workload definition for ad hoc `run --scenario/--test`."""
        layout, manifest = self.scenario(scenario_id)

        # Prefer scenario-config.yaml: it carries the "dependencies" list the generator
        # reads for config-map assembly, which scenario-manifest.yaml does not.
        manifest_filename = "scenario-config.yaml"
        if not (layout.scenario_root / manifest_filename).is_file():
            manifest_filename = "scenario-manifest.yaml"

        matches = [entry for entry in manifest.entrypoints if entry.name == Path(test).name]
        if not matches:
            available = ", ".join(str(entry) for entry in manifest.entrypoints) or "none"
            raise ManifestError(
                f"Scenario '{scenario_id}' has no test '{test}'. Available tests: {available}"
            )
        entrypoint = matches[0]
        scenario_relative = layout.scenario_root.relative_to(self.root / "scenarios")

        workload_entry: Dict[str, Any] = {
            "name": Path(test).stem,
            "scenario-config": str(scenario_relative / manifest_filename),
            "path": str(scenario_relative / entrypoint.parent),
            "task": entrypoint.name,
        }
        if users is not None:
            # Worker replicas always track the requested user count for ad hoc runs.
            workload_entry["users"] = users
            workload_entry["worker-replicas"] = users
        if spawn_rate is not None:
            workload_entry["spawn-rate"] = spawn_rate
        if iterations is not None:
            workload_entry["iterations"] = iterations

        name = f"{scenario_id}-{Path(test).stem}"
        data = {
            "workload-definitions": {
                "workload-definition-specs": [
                    {
                        "name": name,
                        "description": f"Ad hoc run of {entrypoint.name} in {scenario_id}",
                        "custom-resource-spec": {
                            "config-map-name": f"{name}-map",
                            "k8s-operator": "locust-k8s-operator.yaml",
                            "workloads": [workload_entry],
                        },
                    }
                ]
            }
        }

        try:
            import yaml
        except ImportError as error:
            raise ManifestError(
                "PyYAML is required to synthesize workload definitions"
            ) from error

        definitions_dir = output_root.resolve() / "workload-definitions"
        definitions_dir.mkdir(parents=True, exist_ok=True)
        definition_path = definitions_dir / f"{name}-wrkld-def.yaml"
        with definition_path.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)
        return definition_path

    def workload_definition_files(self) -> List[Path]:
        root = self.root / WORKLOAD_DEFINITIONS_DIRECTORY
        if not root.is_dir():
            return []
        return sorted(item for item in root.iterdir() if item.suffix in {".yaml", ".yml"})

    def available_workloads(self) -> List[str]:
        names = []
        for option in self.workload_definition_files():
            try:
                specs = _workload_specs(option)
            except ManifestError:
                continue
            for spec in specs:
                name = spec.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name)
        return names

    def workload_summaries(self) -> List[WorkloadSummary]:
        """Describe every workload spec for listing; unparseable files become error rows."""
        summaries: List[WorkloadSummary] = []
        for option in self.workload_definition_files():
            try:
                specs = _workload_specs(option)
            except ManifestError as error:
                summaries.append(
                    WorkloadSummary(
                        name=option.stem,
                        description=None,
                        source=option,
                        scenario_configs=(),
                        error=str(error),
                    )
                )
                continue
            for spec in specs:
                name = spec.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                description = spec.get("description")
                resource_spec = spec.get("custom-resource-spec")
                configs: List[str] = []
                if isinstance(resource_spec, Mapping):
                    workloads = resource_spec.get("workloads")
                    if isinstance(workloads, list):
                        for entry in workloads:
                            if not isinstance(entry, Mapping):
                                continue
                            value = entry.get("scenario-config")
                            if isinstance(value, str) and value.strip():
                                configs.append(value)
                summaries.append(
                    WorkloadSummary(
                        name=name,
                        description=description if isinstance(description, str) else None,
                        source=option,
                        scenario_configs=tuple(dict.fromkeys(configs)),
                    )
                )
        return summaries

    def scenario_summaries(self) -> List[ScenarioSummary]:
        """Describe every scenario listed in the release manifest; never raises."""
        summaries: List[ScenarioSummary] = []
        for reference in self.release.scenarios:
            try:
                _, manifest = self.scenario(reference.identifier)
            except ManifestError as error:
                summaries.append(
                    ScenarioSummary(
                        identifier=reference.identifier,
                        display_name=None,
                        path=Path(reference.path),
                        error=str(error),
                    )
                )
                continue
            summaries.append(
                ScenarioSummary(
                    identifier=reference.identifier,
                    display_name=manifest.display_name,
                    path=Path(reference.path),
                    entrypoints=tuple(manifest.entrypoints),
                )
            )
        return summaries

    def workload_definition(self, selector: Union[str, Path]) -> WorkloadDefinition:
        """Resolve and validate a workload definition by spec name, file name, or path."""
        path = self._resolve_workload_definition(selector)
        spec_names = []
        scenario_configs = []
        for index, spec in enumerate(_workload_specs(path)):
            name = spec.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ManifestError(
                    f"{path}: 'workload-definition-specs[{index}].name' is required"
                )
            spec_names.append(name)
            resource_spec = spec.get("custom-resource-spec")
            if not isinstance(resource_spec, Mapping):
                raise ManifestError(f"{path}: '{name}' must define 'custom-resource-spec'")
            workloads = resource_spec.get("workloads")
            if not isinstance(workloads, list) or not workloads:
                raise ManifestError(
                    f"{path}: '{name}' must define a non-empty 'workloads' list"
                )
            for position, entry in enumerate(workloads):
                if not isinstance(entry, Mapping):
                    raise ManifestError(
                        f"{path}: '{name}.workloads[{position}]' must be a mapping"
                    )
                scenario_configs.append(
                    self._validate_workload(path, name, position, entry)
                )
        return WorkloadDefinition(
            name=path.stem,
            path=path,
            spec_names=tuple(spec_names),
            scenario_configs=tuple(dict.fromkeys(scenario_configs)),
        )

    def _resolve_workload_definition(self, selector: Union[str, Path]) -> Path:
        candidate = Path(selector)
        if candidate.is_file():
            return candidate.resolve()
        if candidate.name != str(selector):
            raise ManifestError(f"Workload definition file does not exist: {selector}")

        root = self.root / WORKLOAD_DEFINITIONS_DIRECTORY
        for name in (
            str(selector),
            f"{selector}.yaml",
            f"{selector}.yml",
            f"{selector}-wrkld-def.yaml",
        ):
            option = root / name
            if option.is_file():
                return option

        for option in self.workload_definition_files():
            try:
                specs = _workload_specs(option)
            except ManifestError:
                continue
            if any(spec.get("name") == str(selector) for spec in specs):
                return option

        available = ", ".join(sorted(self.available_workloads())) or "none"
        raise ManifestError(
            f"Workload '{selector}' was not found in {self.root}. Available workloads: {available}"
        )

    def _validate_workload(
        self, path: Path, spec_name: str, position: int, workload: Mapping[str, Any]
    ) -> str:
        location = f"{path}: '{spec_name}.workloads[{position}]'"
        scenarios_root = self.root / "scenarios"

        scenario_config = workload.get("scenario-config")
        if not isinstance(scenario_config, str) or not scenario_config.strip():
            raise ManifestError(f"{location} requires 'scenario-config'")
        config_path = scenarios_root / safe_relative_path(
            scenario_config, "scenario-config", path
        )
        if not config_path.is_file():
            raise ManifestError(
                f"{location} references a missing scenario config: {config_path}"
            )

        workload_path = workload.get("path")
        task = workload.get("task")
        if not isinstance(workload_path, str) or not workload_path.strip():
            raise ManifestError(f"{location} requires 'path'")
        if not isinstance(task, str) or not task.strip():
            raise ManifestError(f"{location} requires 'task'")
        task_path = (
            scenarios_root / safe_relative_path(workload_path, "path", path) / task
        )
        if not task_path.is_file():
            raise ManifestError(f"{location} references a missing task file: {task_path}")

        return scenario_config

    def unsupported_scenarios(self, workload: Union[str, Path], target: str) -> List[str]:
        """Scenario configs used by the workload whose 'execution-targets' exclude the target."""
        definition = self.workload_definition(workload)
        scenarios_root = self.root / "scenarios"
        unsupported = []
        for scenario_config in definition.scenario_configs:
            config_path = scenarios_root / scenario_config
            # The scenario-config.yaml and a sibling scenario-manifest.yaml can both declare targets.
            candidates = [config_path, config_path.parent / "scenario-manifest.yaml"]
            for candidate in dict.fromkeys(candidates):
                if not candidate.is_file():
                    continue
                targets = read_execution_targets(candidate)
                if targets is not None and target not in targets:
                    unsupported.append(scenario_config)
                    break
        return unsupported

    def prepare(
        self,
        workload: Union[str, Path],
        output_root: Path,
        framework_root: Path,
        hostname: Optional[str] = None,
        trusted_certs: Optional[Path] = None,
        namespace: Optional[str] = None,
        execution_target: str = EXECUTION_TARGET_KUBERNETES,
        local_options: Optional[Mapping[str, Any]] = None,
    ) -> LegacyInputs:
        """Write configuration files consumable by the existing generator."""
        if execution_target not in EXECUTION_TARGETS:
            raise ManifestError(
                f"Unknown execution target '{execution_target}'; expected {' or '.join(EXECUTION_TARGETS)}"
            )
        definition = self.workload_definition(workload)
        try:
            import yaml
        except ImportError as error:
            raise ManifestError("PyYAML is required to prepare generator inputs") from error

        output_root = output_root.resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        generated_root = output_root / "generated"
        if generated_root.exists():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            generated_root.rename(output_root / f"generated-{timestamp}")
        generated_root.mkdir(parents=True, exist_ok=True)

        workload_definition = definition.path

        global_config = output_root / "global-config.yaml"
        values: Dict[str, Any] = {
            "global-config": {
                "framework-base-location": str(framework_root.resolve()),
                "scenarios-base-location": str((self.root / "scenarios").resolve()),
                "plugin-base-location": str(self.root),
                "generated-base-location": str(generated_root),
            }
        }
        if hostname is not None:
            values["global-config"]["hostname"] = hostname
        if namespace is not None:
            values["global-config"]["namespace"] = namespace
        if trusted_certs is not None:
            values["global-config"]["trusted-certs"] = str(trusted_certs)
        if execution_target != EXECUTION_TARGET_KUBERNETES:
            values["global-config"]["execution-target"] = execution_target
        if execution_target == EXECUTION_TARGET_LOCAL:
            options = dict(local_options or {})
            values["global-config"]["local-execution"] = {
                "headed": bool(options.get("headed", False)),
                "processes": options.get("processes"),
            }
        with global_config.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(values, stream, sort_keys=False)

        description = {
            "package-root": str(self.root),
            "workload": definition.name,
            "workload-specs": list(definition.spec_names),
            "scenario-configs": list(definition.scenario_configs),
            "global-config": str(global_config),
            "workload-definition": str(workload_definition),
            "generated-root": str(generated_root),
            "execution-target": execution_target,
        }
        (generated_root / "resolved-inputs.json").write_text(
            json.dumps(description, indent=2) + "\n", encoding="utf-8"
        )
        return LegacyInputs(global_config, workload_definition, generated_root)

    def generate(
        self,
        workload: Union[str, Path],
        output_root: Path,
        framework_root: Path,
        hostname: Optional[str] = None,
        trusted_certs: Optional[Path] = None,
        namespace: Optional[str] = None,
        users_file: Optional[Path] = None,
        workload_overrides: Optional[Path] = None,
        log_level: str = "INFO",
        execution_target: str = EXECUTION_TARGET_KUBERNETES,
        local_options: Optional[Mapping[str, Any]] = None,
    ) -> GenerationResult:
        """Prepare a package and run the existing workload-definition generator."""
        inputs = self.prepare(
            workload,
            output_root,
            framework_root,
            hostname=hostname,
            trusted_certs=trusted_certs,
            namespace=namespace,
            execution_target=execution_target,
            local_options=local_options,
        )
        generator = framework_root.resolve() / "python" / "createWorkloadDefinitions.py"
        defaults = framework_root.resolve() / "framework-defaults.yaml"
        if not generator.is_file():
            raise ManifestError(f"Generator does not exist: {generator}")
        if not defaults.is_file():
            raise ManifestError(f"Framework defaults do not exist: {defaults}")

        environment = os.environ.copy()
        environment["frameworkDefaultsFullPath"] = str(defaults)
        interpreter_directory = str(Path(sys.executable).parent)
        environment["PATH"] = os.pathsep.join(
            [interpreter_directory, environment.get("PATH", "")]
        )
        try:
            command = [
                sys.executable,
                str(generator),
                "-g",
                str(inputs.global_config),
                "-w",
                str(inputs.workload_definition),
                "-l",
                log_level,
            ]
            if users_file is not None:
                command.extend(["-u", str(users_file)])
            if workload_overrides is not None:
                command.extend(["-o", str(workload_overrides)])
            subprocess.run(
                command,
                check=True,
                cwd=inputs.generated_root.parent,
                env=environment,
            )
        except OSError as error:
            raise ManifestError(f"Unable to run workload generator: {error}") from error
        except subprocess.CalledProcessError as error:
            raise ManifestError(
                f"Workload generator failed with exit code {error.returncode}"
            ) from error

        run_all_script = inputs.generated_root / "runAllCreateWorkloadArtifacts.sh"
        if run_all_script.is_file():
            try:
                subprocess.run(
                    [str(run_all_script)],
                    check=True,
                    cwd=run_all_script.parent,
                    env=environment,
                )
            except OSError as error:
                raise ManifestError(f"Unable to execute artifact creation script: {error}") from error
            except subprocess.CalledProcessError as error:
                raise ManifestError(
                    f"Artifact creation failed with exit code {error.returncode}"
                ) from error

        return GenerationResult(
            inputs=inputs,
            generated_workload_root=inputs.generated_root,
        )

    def run_workload(
        self, workload: Union[str, Path], generated_root: Path, local: bool = False
    ) -> int:
        """Run the generated workload script and return its process exit code."""
        definition = self.workload_definition(workload)
        selector = str(workload)
        if selector in definition.spec_names:
            workload_name = selector
        elif len(definition.spec_names) == 1:
            workload_name = definition.spec_names[0]
        else:
            names = ", ".join(definition.spec_names)
            raise ManifestError(
                f"Workload definition '{selector}' contains multiple workloads: {names}. "
                "Select a workload by spec name."
            )
        script_name = RUN_WORKLOAD_LOCAL_SCRIPT if local else RUN_WORKLOAD_SCRIPT
        script = generated_root.resolve() / workload_name / script_name
        if not script.is_file():
            alternative = generated_root.resolve() / workload_name / "artifacts" / script_name
            if not local and alternative.is_file():
                script = alternative
            elif local:
                raise ManifestError(
                    f"Generated local workload script does not exist: {script}. "
                    "Generate the workload with 'sas-validation run --local'."
                )
            else:
                raise ManifestError(
                    f"Generated workload script does not exist: {script}. "
                    "Run 'sas-validation generate' first or use 'sas-validation run --generate'."
                )
        if not os.access(script, os.X_OK):
            raise ManifestError(f"Generated workload script is not executable: {script}")

        environment = os.environ.copy()
        interpreter_directory = str(Path(sys.executable).parent)
        environment["PATH"] = os.pathsep.join(
            [interpreter_directory, environment.get("PATH", "")]
        )
        if local and not environment.get(LOCUST_OVERRIDE_ENV):
            locust = local_locust_executable()
            if locust is not None:
                environment[LOCUST_OVERRIDE_ENV] = str(locust)
        try:
            if local:
                process = subprocess.Popen([str(script)], cwd=script.parent, env=environment)
                previous = {}

                def forward_signal(signum, _frame):
                    try:
                        process.send_signal(signum)
                    except ProcessLookupError:
                        pass

                try:
                    if threading.current_thread() is threading.main_thread():
                        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                            previous[sig] = signal.signal(sig, forward_signal)
                    return process.wait()
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=25)
                        except subprocess.TimeoutExpired as error:
                            process.kill()
                            process.wait()
                            raise ManifestError(
                                "Local runner did not stop; use 'sas-validation cleanup --local --list' "
                                "to recover tracked processes"
                            ) from error
            completed = subprocess.run(
                [str(script)],
                check=False,
                cwd=script.parent,
                env=environment,
            )
        except OSError as error:
            raise ManifestError(f"Unable to execute workload script: {error}") from error
        return completed.returncode

    @staticmethod
    def _validate_files(
        layout: PackageLayout, manifest: ScenarioManifest, manifest_path: Path
    ) -> None:
        for entrypoint in manifest.entrypoints:
            path = layout.scenario_root / entrypoint
            if not path.is_file():
                raise ManifestError(f"{manifest_path}: entrypoint does not exist: {path}")
        for definition in manifest.workload_definitions:
            path = layout.package_root / definition
            if not path.is_file():
                raise ManifestError(
                    f"{manifest_path}: workload definition does not exist: {path}"
                )
        for resource in manifest.required_resources:
            path = layout.package_root / resource
            if not path.is_file() and not path.is_dir():
                raise ManifestError(f"{manifest_path}: resource does not exist: {path}")

    @staticmethod
    def _validate_plugin_common(
        layout: PackageLayout, manifest: ScenarioManifest, manifest_path: Path
    ) -> None:
        # The generator reads dependencies from scenario-config.yaml, even when the
        # scenario metadata came from scenario-manifest.yaml.
        config_path = layout.scenario_root / "scenario-config.yaml"
        dependencies_path = manifest_path
        files = manifest.plugin_common
        if manifest_path != config_path and config_path.is_file():
            dependencies_path = config_path
            files = read_plugin_common_dependencies(config_path)
        for dependency in files:
            path = layout.package_root / dependency
            if not path.is_file():
                raise ManifestError(
                    f"{dependencies_path}: plugin-common dependency does not exist: {path}"
                )


@dataclass(frozen=True)
class BrokenPackage:
    root: Path
    error: str


def installed_packages(
    destination: Path,
) -> tuple[List["ScenarioPackage"], List[BrokenPackage]]:
    """Enumerate installed plugins, sorted by name/version.

    Plugins live either directly below destination (legacy flat layout) or one level deeper,
    below a repository alias directory (``<destination>/<repo-alias>/<plugin>``).
    """
    if not destination.is_dir():
        return [], []

    candidates: List[Path] = []
    for child in sorted(destination.iterdir()):
        if not child.is_dir():
            continue
        if (child / "release-manifest.yaml").is_file():
            candidates.append(child)
            continue
        candidates.extend(
            grandchild
            for grandchild in sorted(child.iterdir())
            if grandchild.is_dir() and (grandchild / "release-manifest.yaml").is_file()
        )

    packages: List[ScenarioPackage] = []
    broken: List[BrokenPackage] = []
    for candidate in candidates:
        try:
            packages.append(ScenarioPackage(candidate))
        except ManifestError as error:
            broken.append(BrokenPackage(root=candidate, error=str(error)))
    packages.sort(key=lambda item: (item.release.name, item.release.version))
    return packages, broken
