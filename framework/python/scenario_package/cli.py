# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command-line interface for scenario plugins, environment checks, and workload runs."""

import json
import os
import shutil
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, List, NoReturn, Optional

import typer
from platformdirs import user_cache_path
import psutil

# Suppress harmless urllib3 LibreSSL warning on macOS (urllib3 v2 works fine with LibreSSL,
# just not officially tested against it)
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from . import local_processes, plugins, preflight
from .config import (
    ScenarioPackageDefaults,
    load_repository_config,
    load_scenario_package_defaults,
)
from .credentials import (
    RELEASE_TOKEN_ENV,
    ResolvedToken,
    repository_host,
    resolve_gitlab_token,
)
from .installer import InstallError, ReleaseInstaller
from .loader import ScenarioPackage, installed_packages
from .manifest import ManifestError, safe_relative_path
from .preflight.http import HttpClient
from .providers import ProviderError, RepositoryAlias, create_provider

PACKAGE_CONFIG_FILENAME = "sas-validation.yaml"
REPOSITORIES_CONFIG_FILENAME = "scenario-repositories.yaml"
ALLOWED_LOG_LEVELS = {"WARN", "WARNING", "INFO", "DEBUG"}
# Above this many users, --headed opens an impractical number of browser windows.
HEADED_USERS_WARNING_THRESHOLD = 3

app = typer.Typer(
    no_args_is_help=True,
    help="Install scenario plugins, check the environment, and generate and run Viya validation workloads.",
)
plugins_app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Install, list, and manage scenario plugins. Installed plugins live locally; "
        "repository plugins are available to install from configured repositories."
    ),
)
workloads_app = typer.Typer(
    no_args_is_help=True, help="List workload definitions in installed plugins."
)
scenarios_app = typer.Typer(no_args_is_help=True, help="List scenarios in installed plugins.")
users_app = typer.Typer(no_args_is_help=True, help="Manage the test users used by workloads.")
auth_app = typer.Typer(
    no_args_is_help=True, help="Check which access token is used for private plugin repositories."
)

DESTINATION_HELP = (
    "Directory of installed plugins (default: sas-validation.installed-plugins.destination, "
    "otherwise the user cache directory)"
)
PLUGIN_VERSION_HELP = (
    "Only consider installed plugins at this version, e.g. 2026.08 (a leading 'v' is optional)"
)
REPO_FILTER_HELP = "Only consider installed plugins that came from this repository alias"
REPO_HELP = "Repository alias (default: default-repository in scenario-repositories.yaml)"
JSON_HELP = "Print machine-readable JSON instead of text"


def _default_package_destination() -> Path:
    return user_cache_path("sas-validation") / "packages"


def _select_installed_plugin(
    provides: Callable[[ScenarioPackage], bool],
    description: str,
    version: Optional[str],
    destination: Optional[Path],
    repo: Optional[RepositoryAlias] = None,
) -> Path:
    """Pick the one installed plugin that provides something, narrowed by version and repo."""
    destination = destination or _default_package_destination()
    if not destination.is_dir():
        raise ManifestError(
            f"No installed plugins found in {destination}. "
            "Run 'sas-validation plugins install' or provide a plugin path."
        )

    packages, _ = installed_packages(destination)
    matches = [package for package in packages if provides(package)]
    if version is not None:
        matches = [package for package in matches if plugins.matches_version(package, version)]
    matches = plugins.filter_by_repo(matches, repo)

    if len(matches) == 1:
        return matches[0].root
    if not matches:
        qualifiers = []
        if version is not None:
            qualifiers.append(f"at version '{version}'")
        if repo is not None:
            qualifiers.append(f"from repository '{repo.name}'")
        if qualifiers:
            raise ManifestError(
                f"No installed plugin in {destination} provides {description} "
                f"{' '.join(qualifiers)}. Run 'sas-validation plugins list' to see installed plugins."
            )
        raise ManifestError(
            f"No installed plugin in {destination} provides {description}. "
            "Run 'sas-validation plugins install' or provide a plugin path."
        )
    choices = ", ".join(
        f"{package.release.name} {package.release.version}: {package.root}" for package in matches
    )
    raise ManifestError(
        f"Multiple installed plugins provide {description}: {choices}. "
        "Provide a plugin path, --plugin-version, or --repo to select one."
    )


def _provides_workload(selector) -> Callable[[ScenarioPackage], bool]:
    def provides(package: ScenarioPackage) -> bool:
        try:
            package.workload_definition(selector)
        except ManifestError:
            return False
        return True

    return provides


def _installed_package_for_workload(
    selector: str,
    version: Optional[str] = None,
    destination: Optional[Path] = None,
    repo: Optional[RepositoryAlias] = None,
) -> Path:
    return _select_installed_plugin(
        _provides_workload(selector), f"workload '{selector}'", version, destination, repo
    )


def _installed_package_for_scenario(
    selector: str,
    version: Optional[str] = None,
    destination: Optional[Path] = None,
    repo: Optional[RepositoryAlias] = None,
) -> Path:
    return _select_installed_plugin(
        lambda package: any(
            reference.identifier == selector for reference in package.release.scenarios
        ),
        f"scenario '{selector}'",
        version,
        destination,
        repo,
    )


def _installed_package_for_workload_file(
    workload_definition: Path,
    version: Optional[str] = None,
    destination: Optional[Path] = None,
    repo: Optional[RepositoryAlias] = None,
) -> Path:
    return _select_installed_plugin(
        _provides_workload(workload_definition),
        f"custom workload '{workload_definition}'",
        version,
        destination,
        repo,
    )


def _discovery_scope(
    package: Optional[Path],
    plugin_version: Optional[str],
    destination: Optional[Path],
    repo: Optional[RepositoryAlias] = None,
):
    """Resolve the plugins a `list` invocation should report on."""
    destination = destination or _default_package_destination()
    if package is not None:
        return [ScenarioPackage(package)], [], destination
    packages, broken = installed_packages(destination)
    if plugin_version is not None:
        packages = [pkg for pkg in packages if plugins.matches_version(pkg, plugin_version)]
    if repo is not None:
        packages = plugins.filter_by_repo(packages, repo)
        broken = []
    return packages, broken, destination


def _configured_package_destination(path: Path) -> Optional[Path]:
    if not path.is_file():
        return None
    return load_scenario_package_defaults(path).destination


def _scenario_ids(package: ScenarioPackage, configs) -> List[str]:
    """Map workload 'scenario-config' paths back to release-manifest scenario ids."""
    known = {}
    for reference in package.release.scenarios:
        path = Path(reference.path)
        relative = path.relative_to("scenarios") if path.parts[:1] == ("scenarios",) else path
        known[str(relative)] = reference.identifier
    resolved = [known.get(str(Path(config).parent), str(Path(config).parent)) for config in configs]
    return list(dict.fromkeys(resolved))


def _relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _find_upward(start: Path, filename: str) -> Optional[Path]:
    """Return the nearest `filename` in `start` or one of its parent directories."""
    for directory in (start, *start.parents):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def _config_path(
    value: Optional[Path], filename: str, preferred_dir: Optional[Path] = None
) -> Path:
    """Explicit path, else `filename` in `preferred_dir`, else the nearest one upward from cwd."""
    if value is not None:
        return value
    if preferred_dir is not None and (preferred_dir / filename).is_file():
        return preferred_dir / filename
    cwd = Path.cwd()
    return _find_upward(cwd, filename) or cwd / filename


def _no_plugins_message(ctx: typer.Context, destination: Path) -> str:
    message = f"No installed plugins found in {destination}. Run 'sas-validation plugins install'."
    package_config = ctx.obj.package_config if ctx.obj is not None else None
    if (
        destination == _default_package_destination()
        and package_config is not None
        and not package_config.is_file()
    ):
        message += (
            f" Note: no {PACKAGE_CONFIG_FILENAME} was found in {Path.cwd()} or its parent "
            "directories, so the default plugin directory was used. Run from your project "
            "directory or pass --config."
        )
    return message


def _require_config(path: Path, option: str) -> Path:
    if path.is_file():
        return path
    raise ManifestError(
        f"Configuration file does not exist: {path}. "
        f"Provide {option} or create {path.name} in the current directory or a parent directory"
    )


def _resolve_repository(path: Path, requested_alias: Optional[str]):
    config_path = _require_config(path, "--repositories")
    repository_config = load_repository_config(config_path)
    alias = (
        requested_alias
        if requested_alias is not None
        else repository_config.default_repository
    )
    if alias is None:
        configured = ", ".join(repository_config.aliases) or "none"
        raise ProviderError(
            "No repository selected. Pass --repo <alias> or set "
            f"'default-repository' in {config_path}. Configured aliases: {configured}"
        )
    repository = repository_config.aliases.get(alias)
    if repository is None:
        raise ProviderError(f"Repository alias '{alias}' is not configured in {config_path}")
    return alias, repository


def _release_token(alias: str, repo) -> Optional[ResolvedToken]:
    if repo.provider != "gitlab-release":
        env_token = os.environ.get(RELEASE_TOKEN_ENV)
        return ResolvedToken(env_token, f"environment variable {RELEASE_TOKEN_ENV}") if env_token else None
    token = resolve_gitlab_token(repo)
    if token is None:
        host = repository_host(repo)
        raise ProviderError(
            f"No access token found for GitLab repository '{alias}' ({host}). Do one of:\n"
            f"  - log in with the GitLab CLI: glab auth login --hostname {host}\n"
            f"  - set the environment variable {RELEASE_TOKEN_ENV}"
        )
    return token


def _with_token_hint(error: Exception, token: Optional[ResolvedToken]) -> str:
    message = str(error)
    if token is not None and getattr(error, "status", None) in (401, 403):
        message += (
            f"\nThe token came from {token.source}. If it is expired or lacks the 'read_api' "
            "scope, renew it with 'glab auth login' or update the environment variable"
        )
    return message


def _resolve_defaults(
    defaults: ScenarioPackageDefaults,
    destination: Optional[Path],
    framework_root: Optional[Path],
    output: Optional[Path],
):
    if destination is None:
        destination = defaults.destination
    if framework_root is None:
        framework_root = defaults.framework_root
    if output is None:
        output = defaults.output
    return destination, framework_root, output


def _existing_file(value: Optional[Path], option: str) -> Optional[Path]:
    if value is None:
        return None
    path = value.resolve()
    if not path.is_file():
        raise ManifestError(f"{option} must name an existing file: {value}")
    return path


def _normalized_log_level(value: str) -> str:
    level = value.upper()
    if level not in ALLOWED_LOG_LEVELS:
        supported = ", ".join(sorted(ALLOWED_LOG_LEVELS))
        raise ManifestError(f"--log-level must be one of: {supported}")
    return "WARNING" if level == "WARN" else level


def _require_hostname(defaults: ScenarioPackageDefaults) -> str:
    if defaults.hostname is None:
        raise ManifestError(
            "'sas-validation.execution.hostname' is required for this command"
        )
    return defaults.hostname


def _require_custom_workloads(defaults: ScenarioPackageDefaults) -> Path:
    if defaults.custom_workloads is None:
        raise ManifestError(
            "'sas-validation.custom-workloads.location' is required for this command"
        )
    return defaults.custom_workloads


def _copy_workload_definition(
    package: ScenarioPackage,
    selector: str,
    custom_workloads: Path,
    overwrite: bool,
) -> tuple[Path, Path]:
    definition = package.workload_definition(selector)
    custom_workloads.mkdir(parents=True, exist_ok=True)
    target = custom_workloads / definition.path.name
    if target.exists() and not overwrite:
        raise ManifestError(
            f"Custom workload definition already exists: {target}. Use --overwrite to replace it."
        )
    shutil.copy2(definition.path, target)
    return definition.path, target


def _custom_workload_candidates(selector: str, custom_workloads: Path) -> List[Path]:
    relative = safe_relative_path(selector, "custom workload", custom_workloads)
    return [
        custom_workloads / relative,
        custom_workloads / f"{selector}.yaml",
        custom_workloads / f"{selector}.yml",
        custom_workloads / f"{selector}-wrkld-def.yaml",
    ]


def _resolve_custom_workload(selector: str, custom_workloads: Optional[Path]) -> Path:
    candidate = Path(selector).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    if custom_workloads is None:
        raise ManifestError(
            "'sas-validation.custom-workloads.location' is required to resolve a custom workload by name"
        )
    matches = [path for path in _custom_workload_candidates(selector, custom_workloads) if path.is_file()]
    if matches:
        return matches[0].resolve()
    available = ", ".join(
        sorted(path.name for path in custom_workloads.glob("*.y*ml") if path.is_file())
    ) or "none"
    raise ManifestError(
        f"Custom workload '{selector}' was not found in {custom_workloads}. "
        f"Available custom workloads: {available}"
    )


def _lenient_defaults(path: Path):
    """Load configuration without aborting: preflight reports the problem as a finding."""
    if not path.is_file():
        return None, (
            f"configuration file does not exist: {path}. "
            f"Create ./{path.name} from {path.name}.template"
        )
    try:
        return load_scenario_package_defaults(path), None
    except ManifestError as error:
        return None, str(error)


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    return str(timedelta(seconds=round(seconds)))


def _on_fix_start(key: str, checks: List) -> None:
    print(f"-> {checks[0].fix_description}...", flush=True)


def _on_fix_complete(
    key: str, checks: List, applied: Optional[str], error: Optional[str], elapsed: float
) -> None:
    if error:
        print(f"   failed ({_format_elapsed(elapsed)}): {error}")
    else:
        print(f"   done ({_format_elapsed(elapsed)})")


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=2)


LOCAL_EXTRA_HINT = (
    "Install them with: pip install --prefer-binary -e '.[local]' "
    "(from the sas-validation-scenarios directory), "
    "or run: sas-validation preflight --group local --fix"
)


def _ensure_local_dependencies(assume_yes: bool) -> None:
    """Make sure Locust, Playwright and its browser are available before a local run.

    Missing pieces are installed into the interpreter running sas-validation, after
    confirmation unless assume_yes is set.
    """
    checks = preflight.local_checks.dependency_checks()
    context = preflight.PreflightContext(environ=os.environ, timeout=60.0)
    findings = preflight.run_checks(checks, context)
    failing = [f for f in findings if f.result.status is not preflight.Status.OK]
    if not failing:
        return

    print("Running locally needs Locust and Playwright, but this environment is missing:")
    for finding in failing:
        print(f"  {finding.check.title}: {finding.result.detail}")
    version = preflight.run_checks([preflight.local_checks.python_version_check()], context)[0]
    if version.result.status is not preflight.Status.OK:
        print(f"WARNING: {version.result.detail}. {version.result.remedy}.")
    _abort_on_manual_steps(findings)
    for line in preflight.report.render_plan(findings, context):
        print(line)
    if not assume_yes and not _confirm(
        f"Install them now into {sys.executable}? [y/N] "
    ):
        _fail(f"Run aborted: the local dependencies are missing. {LOCAL_EXTRA_HINT}")

    findings = preflight.apply_fixes(
        checks,
        findings,
        context,
        on_fix_start=_on_fix_start,
        on_fix_complete=_on_fix_complete,
    )
    _abort_on_manual_steps(findings)
    remaining = [f for f in findings if f.result.status is not preflight.Status.OK]
    if remaining:
        titles = ", ".join(f.check.title for f in remaining)
        _fail(
            f"Run aborted: the local dependencies are still missing ({titles}); "
            f"see the error above. {LOCAL_EXTRA_HINT}"
        )


def _abort_on_manual_steps(findings: List) -> None:
    """Stop when a dependency failed in a way the automatic install cannot fix."""
    manual = [
        f for f in findings
        if f.result.status is preflight.Status.FAIL and not f.fixable and not f.fix_error
    ]
    if manual:
        steps = "; ".join(
            f"{f.check.title}: {f.result.detail}. {f.result.remedy or ''}".strip() for f in manual
        )
        _fail(f"Run aborted, complete this manually first: {steps}")


def _run_preflight(args: SimpleNamespace, package_config: Path) -> int:
    defaults, config_error = _lenient_defaults(package_config)
    trusted_certs = defaults.trusted_certs if defaults else None
    context = preflight.PreflightContext(
        namespace=args.namespace or (defaults.namespace if defaults else None),
        hostname=args.hostname or (defaults.hostname if defaults else None),
        trusted_certs=trusted_certs,
        users_file=_existing_file(args.users_file, "--users-file"),
        configured_users_file=defaults.users_file if defaults else None,
        framework_root=args.framework_root or (defaults.framework_root if defaults else None),
        config_path=package_config,
        config_error=config_error,
        timeout=args.timeout,
        environ=os.environ,
        http=HttpClient(trusted_certs, args.timeout),
    )

    checks = preflight.select_checks(args.groups or ())
    findings = preflight.run_checks(checks, context)
    fixed = False
    if args.fix:
        pending = preflight.fixable_findings(findings)
        if not pending:
            print("Nothing to fix automatically.")
        else:
            for line in preflight.report.render_plan(findings, context):
                print(line)
            if args.assume_yes or _confirm("Apply these changes? [y/N] "):
                if getattr(args, "verbose", False):
                    context.run_command = lambda command, timeout: preflight.core.stream_command(
                        command, timeout, lambda line: print(f"    | {line}")
                    )
                findings = preflight.apply_fixes(
                    checks,
                    findings,
                    context,
                    on_fix_start=_on_fix_start,
                    on_fix_complete=_on_fix_complete,
                )
                fixed = True
            else:
                print("Aborted, no changes were made.")

    if args.as_json:
        print(json.dumps(preflight.report.as_json(findings), indent=2))
    else:
        for line in preflight.report.render(findings, fixed):
            print(line)
    return preflight.exit_code(findings)


def _run_load_users(args: SimpleNamespace) -> int:
    """Load a users CSV file into a Kubernetes secret.

    Runs through the same dependency injection layer as preflight for consistency
    and testability.
    """
    users_file = _existing_file(args.users_file, "--users-file")
    if not users_file:
        raise ManifestError(f"users file not found: {args.users_file}")

    context = preflight.PreflightContext(
        namespace=args.namespace,
        users_file=users_file,
        environ=os.environ,
    )

    try:
        from .preflight.k8s import apply_users_secret, users_from_csv

        users = users_from_csv(users_file)
        kube = context.kube()
        apply_users_secret(kube, args.namespace, users)

        print(f"Successfully loaded {len(users)} user(s) into secret '{args.namespace}:validation-scenarios'")
        return 0
    except Exception as error:
        if args.as_json:
            print(json.dumps({"error": str(error)}, indent=2))
        else:
            print(f"ERROR: {error}", flush=True)
        return 1


@app.callback()
def cli(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help=(
            f"Path to {PACKAGE_CONFIG_FILENAME} (default: the nearest {PACKAGE_CONFIG_FILENAME} "
            "in the current directory or its parents)"
        ),
    ),
    repositories: Optional[Path] = typer.Option(
        None,
        "--repositories",
        help=(
            f"Path to {REPOSITORIES_CONFIG_FILENAME} (default: next to {PACKAGE_CONFIG_FILENAME}, "
            "otherwise the nearest one in the current directory or its parents)"
        ),
    ),
) -> None:
    package_config = _config_path(config, PACKAGE_CONFIG_FILENAME)
    preferred_dir = package_config.parent if package_config.is_file() else None
    ctx.obj = SimpleNamespace(
        package_config=package_config,
        repositories_config=_config_path(repositories, REPOSITORIES_CONFIG_FILENAME, preferred_dir),
    )


def _repository_aliases(path: Path) -> dict:
    """Configured repository aliases, or none when the file is missing or invalid."""
    if not path.is_file():
        return {}
    try:
        return load_repository_config(path).aliases
    except ManifestError:
        return {}


def _repo_filter(ctx: typer.Context, repo: Optional[str]) -> Optional[RepositoryAlias]:
    """Resolve an explicit --repo filter; no filter is applied when --repo is omitted."""
    if repo is None:
        return None
    return _resolve_repository(ctx.obj.repositories_config, repo)[1]


def _plugin_destination(ctx: typer.Context, destination: Optional[Path]) -> Path:
    if destination is None:
        destination = _configured_package_destination(ctx.obj.package_config)
    return destination or _default_package_destination()


def _repo_directory_name(alias: str) -> str:
    if alias in {".", ".."} or not all(char.isalnum() or char in "._-" for char in alias):
        raise ProviderError(
            f"Repository alias '{alias}' cannot be used as an install directory name; "
            "use only letters, digits, '.', '_' and '-'"
        )
    return alias


def _list_installed_content(
    ctx: typer.Context,
    target: str,
    package: Optional[Path],
    plugin_version: Optional[str],
    destination: Optional[Path],
    scenario: Optional[str],
    copy_workload: Optional[str],
    overwrite: bool,
    as_json: bool,
    repo: Optional[str] = None,
) -> None:
    """List installed plugins, workloads, or scenarios."""
    if copy_workload is not None and target != "workloads":
        raise typer.BadParameter("--copy can only be used with 'workloads list'")

    try:
        repo_filter = _repo_filter(ctx, repo)
        if destination is None:
            destination = _configured_package_destination(ctx.obj.package_config)
        if copy_workload is not None:
            package_config = _require_config(ctx.obj.package_config, "--config")
            defaults = load_scenario_package_defaults(package_config)
            custom_workloads = _require_custom_workloads(defaults)
            package_path = package
            if package_path is None:
                package_path = _installed_package_for_workload(
                    copy_workload, plugin_version, destination, repo_filter
                )
            source, copied = _copy_workload_definition(
                ScenarioPackage(package_path), copy_workload, custom_workloads, overwrite
            )
            if as_json:
                print(json.dumps({"source": str(source), "copied": str(copied)}, indent=2))
            else:
                print(f"copied_workload_definition={copied}")
            return
        packages_, broken, destination = _discovery_scope(
            package, plugin_version, destination, repo_filter
        )
        listing: List[dict] = []
        if target == "plugins":
            aliases = _repository_aliases(ctx.obj.repositories_config)
            for pkg in packages_:
                repos = plugins.plugin_repos(pkg, aliases)
                listing.append(
                    {
                        "name": pkg.release.name,
                        "version": pkg.release.version,
                        "repo": ", ".join(repos) or None,
                        "viya-cadence": pkg.release.viya_cadence,
                        "root": str(pkg.root),
                        "scenario-count": len(pkg.release.scenarios),
                        "workload-count": len(pkg.workload_summaries()),
                    }
                )
        elif target == "workloads":
            for pkg in packages_:
                rows = [
                    (summary, _scenario_ids(pkg, summary.scenario_configs))
                    for summary in pkg.workload_summaries()
                ]
                if scenario is not None:
                    rows = [row for row in rows if scenario in row[1]]
                listing.append(
                    {
                        "name": pkg.release.name,
                        "version": pkg.release.version,
                        "root": str(pkg.root),
                        "workloads": [
                            {
                                "name": summary.name,
                                "description": summary.description,
                                "source": _relative_to(summary.source, pkg.root),
                                "scenarios": scenarios_,
                                "error": summary.error,
                            }
                            for summary, scenarios_ in rows
                        ],
                    }
                )
        else:
            for pkg in packages_:
                listing.append(
                    {
                        "name": pkg.release.name,
                        "version": pkg.release.version,
                        "root": str(pkg.root),
                        "scenarios": [
                            {
                                "id": summary.identifier,
                                "display-name": summary.display_name,
                                "path": str(summary.path),
                                "tests": [str(entrypoint) for entrypoint in summary.entrypoints],
                                "error": summary.error,
                            }
                            for summary in pkg.scenario_summaries()
                        ],
                    }
                )
        for entry in broken:
            listing.append({"root": str(entry.root), "error": entry.error})
    except (ManifestError, ProviderError, InstallError) as error:
        _fail(str(error))

    if as_json:
        print(json.dumps(listing, indent=2))
        return
    if not listing:
        print(_no_plugins_message(ctx, destination))
        return
    for entry in listing:
        if "name" not in entry:
            print(f"{entry['root']}  ERROR: {entry['error']}")
            continue
        if target == "plugins":
            print(
                f"{entry['name']} {entry['version']}  repo {entry['repo'] or '-'}  "
                f"viya {entry['viya-cadence']}  "
                f"{entry['scenario-count']} scenarios  {entry['workload-count']} workloads"
            )
            print(f"  {entry['root']}")
            continue
        print(f"{entry['name']} {entry['version']}")
        print(f"  {entry['root']}")
        for item in entry.get("workloads", []):
            if item["error"] is not None:
                print(f"  {item['name']}  ERROR: {item['error']}")
                continue
            print(f"  {item['name']}  {item['description'] or ''}")
            print(f"    source: {item['source']}")
            if item["scenarios"]:
                print(f"    scenarios: {', '.join(item['scenarios'])}")
        for item in entry.get("scenarios", []):
            if item["error"] is not None:
                print(f"  {item['id']}  ERROR: {item['error']}")
                continue
            print(f"  {item['id']}  {item['display-name'] or ''}")
            print(f"    path: {item['path']}")
            for test in item["tests"]:
                print(f"    test: {test}")


def _local_timestamp(value: str) -> str:
    """Render an ISO 8601 timestamp in the local time zone, or return it unchanged."""
    text = value.strip()
    if text.endswith(("Z", "z")):
        # Python 3.9's fromisoformat does not accept a trailing "Z".
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _release_label(release) -> str:
    label = release.display_version
    if release.name:
        label += f"  {release.name}"
    if release.published_at:
        label += f"  published {_local_timestamp(release.published_at)}"
    if release.draft:
        label += "  [draft]"
    elif release.prerelease:
        label += "  [pre-release]"
    return label


@plugins_app.command("install")
def plugins_install(
    ctx: typer.Context,
    version: str = typer.Option(
        ...,
        "--version",
        help="Plugin version to install, e.g. 2026.08 (a leading 'v' is optional)",
    ),
    repo: Optional[str] = typer.Option(None, "--repo", help=REPO_HELP),
    destination: Optional[Path] = typer.Option(
        None,
        "--destination",
        help=(
            "Directory to install into (default: sas-validation.installed-plugins.destination, "
            "otherwise the user cache directory)"
        ),
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Install a plugin from a repository. Non-public repositories need a token (see 'auth status')."""
    state = ctx.obj
    token = None
    requested_version = version
    version = plugins.normalize_version(version)
    try:
        destination = _plugin_destination(ctx, destination)
        alias_name, alias = _resolve_repository(state.repositories_config, repo)
        target = destination / _repo_directory_name(alias_name)
        installed, broken = installed_packages(destination)
        existing = [match.root for match in plugins.find_installed_plugins(installed, alias, version)]
        existing += plugins.find_broken_plugins(broken, alias, version)
        if existing:
            raise InstallError(
                f"Plugin version '{version}' from repository '{alias_name}' is already installed "
                f"at {existing[0]}. Remove it first with "
                f"'sas-validation plugins uninstall --repo {alias_name} --version {version}'"
            )
        if not as_json:
            print(f"Installing plugin version {version} from repository '{alias_name}' ({alias.repository})")
        token = _release_token(alias_name, alias)
        provider = create_provider(alias, token=token.value if token else None)
        result = ReleaseInstaller(provider).install(requested_version, None, target, None)
        try:
            plugin_root = plugins.plugin_root_from_entries(result.entries)
        except ManifestError:
            plugins.remove_entries(result.entries)
            if target.is_dir() and not any(target.iterdir()):
                target.rmdir()
            raise
        try:
            plugin_version = ScenarioPackage(plugin_root).release.version
        except ManifestError:
            plugin_version = plugins.normalize_version(result.asset.version)
        plugins.write_install_record(plugin_root, alias, result.asset, plugin_version)
    except (ManifestError, ProviderError, InstallError) as error:
        message = _with_token_hint(error, token)
        if getattr(error, "status", None) == 404:
            message += (
                f"\nRun 'sas-validation plugins list-repo-plugins --repo {alias_name}' "
                "to see the available versions"
            )
        _fail(message)

    if as_json:
        print(
            json.dumps(
                {"installed_plugin": str(plugin_root), "repo": alias_name, "version": plugin_version},
                indent=2,
            )
        )
    else:
        print(f"installed_plugin={plugin_root}")


@plugins_app.command("list")
def plugins_list(
    ctx: typer.Context,
    package: Optional[Path] = typer.Argument(None, help="Report on this installed plugin path only"),
    repo: Optional[str] = typer.Option(None, "--repo", help=REPO_FILTER_HELP),
    plugin_version: Optional[str] = typer.Option(
        None, "--plugin-version", help=PLUGIN_VERSION_HELP
    ),
    destination: Optional[Path] = typer.Option(None, "--destination", help=DESTINATION_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List installed plugins."""
    _list_installed_content(
        ctx,
        target="plugins",
        package=package,
        plugin_version=plugin_version,
        destination=destination,
        scenario=None,
        copy_workload=None,
        overwrite=False,
        as_json=as_json,
        repo=repo,
    )


@plugins_app.command("list-repos")
def plugins_list_repos(
    ctx: typer.Context,
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List the configured plugin repositories."""
    try:
        config_path = _require_config(ctx.obj.repositories_config, "--repositories")
        repository_config = load_repository_config(config_path)
    except ManifestError as error:
        _fail(str(error))

    rows = [
        {
            "name": alias.name,
            "provider": alias.provider,
            "repository": alias.repository,
            "visibility": alias.visibility,
            "base-url": alias.base_url,
            "default": alias.name == repository_config.default_repository,
        }
        for alias in repository_config.aliases.values()
    ]
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No repositories are configured in {config_path}.")
        return
    header = ("NAME", "PROVIDER", "REPOSITORY", "VISIBILITY", "BASE URL")
    table = [header] + [
        (
            f"{row['name']} (default)" if row["default"] else row["name"],
            row["provider"],
            row["repository"],
            row["visibility"],
            row["base-url"] or "-",
        )
        for row in rows
    ]
    widths = [max(len(line[column]) for line in table) for column in range(len(header))]
    for line in table:
        print("  ".join(value.ljust(width) for value, width in zip(line, widths)).rstrip())


@plugins_app.command("list-repo-plugins")
def plugins_list_repo_plugins(
    ctx: typer.Context,
    repo: Optional[str] = typer.Option(
        None, "--repo", help="Only list plugins from this repository alias (default: all repositories)"
    ),
    destination: Optional[Path] = typer.Option(None, "--destination", help=DESTINATION_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List plugins available in the configured repositories and whether they are installed.

    Status: '*' installed and current, '^' installed but the repository has a newer version
    of the same cadence, blank available but not installed.
    """
    try:
        config_path = _require_config(ctx.obj.repositories_config, "--repositories")
        if repo is not None:
            aliases = [_resolve_repository(config_path, repo)[1]]
        else:
            aliases = list(load_repository_config(config_path).aliases.values())
        installed, _ = installed_packages(_plugin_destination(ctx, destination))
    except (ManifestError, ProviderError) as error:
        _fail(str(error))

    results = []
    for alias in aliases:
        token = None
        entry = {
            "repo": alias.name,
            "provider": alias.provider,
            "repository": alias.repository,
            "error": None,
            "plugins": [],
        }
        try:
            token = _release_token(alias.name, alias)
            releases = create_provider(alias, token=token.value if token else None).list_releases()
            statuses = plugins.release_statuses(releases, installed, alias)
            entry["plugins"] = [
                {**release.as_dict(), "status": status, "installed": status is not None}
                for release, status in zip(releases, statuses)
            ]
            entry["_rows"] = list(zip(releases, statuses))
        except (ManifestError, ProviderError, InstallError) as error:
            entry["error"] = _with_token_hint(error, token)
        results.append(entry)

    failed = any(entry["error"] is not None for entry in results)
    if as_json:
        print(json.dumps([{k: v for k, v in entry.items() if k != "_rows"} for entry in results], indent=2))
    elif not results:
        print(f"No repositories are configured in {config_path}.")
    else:
        for index, entry in enumerate(results):
            if index:
                print()
            print(f"Repository: {entry['repo']} ({entry['provider']} {entry['repository']})")
            if entry["error"] is not None:
                first, *rest = entry["error"].splitlines()
                print(f"  ERROR: {first}")
                for line in rest:
                    print(f"  {line}")
                continue
            if not entry["_rows"]:
                print("  No plugins found.")
                continue
            for release, status in entry["_rows"]:
                print(f"{plugins.STATUS_MARKERS[status]} {_release_label(release)}")
                if release.url:
                    print(f"    url: {release.url}")
                if release.assets:
                    print(f"    assets: {', '.join(asset['name'] for asset in release.assets)}")
        print()
        print(f"Status: {plugins.STATUS_LEGEND}")
    if failed:
        raise typer.Exit(code=2)


@plugins_app.command("uninstall")
def plugins_uninstall(
    ctx: typer.Context,
    package: Optional[Path] = typer.Argument(
        None, help="Installed plugin path to remove (instead of --repo/--version)"
    ),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        help="Installed plugin version to remove, e.g. 2026.08 (a leading 'v' is optional)",
    ),
    repo: Optional[str] = typer.Option(None, "--repo", help=REPO_HELP),
    destination: Optional[Path] = typer.Option(None, "--destination", help=DESTINATION_HELP),
    yes: bool = typer.Option(False, "--yes", help="Do not prompt for confirmation"),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Remove an installed plugin, selected by --repo and --version or by its path."""
    if package is not None and (version is not None or repo is not None):
        raise typer.BadParameter("Specify a plugin path or --repo/--version, not both")
    if package is None and version is None:
        raise typer.BadParameter("Specify --version (optionally with --repo) or a plugin path")
    try:
        destination = _plugin_destination(ctx, destination)
        if package is not None:
            target_root = package.resolve()
            if not target_root.is_dir():
                raise ManifestError(
                    f"No plugin directory at {target_root}. The argument to 'plugins uninstall' "
                    f"is an installed plugin path. To remove a plugin by version, run "
                    f"'sas-validation plugins uninstall --version {package}' "
                    f"(add --repo <alias> for a non-default repository)."
                )
        else:
            alias_name, alias = _resolve_repository(ctx.obj.repositories_config, repo)
            installed, broken = installed_packages(destination)
            matches = [match.root for match in plugins.find_installed_plugins(installed, alias, version)]
            matches += plugins.find_broken_plugins(broken, alias, version)
            if not matches:
                raise ManifestError(
                    f"No plugin version '{version}' from repository '{alias_name}' is installed in "
                    f"{destination}. Run 'sas-validation plugins list' to see installed plugins."
                )
            if len(matches) > 1:
                paths = ", ".join(str(match) for match in matches)
                raise ManifestError(
                    f"Multiple installed plugins match version '{version}' from repository "
                    f"'{alias_name}': {paths}. Pass the plugin path to 'plugins uninstall' instead."
                )
            target_root = matches[0]
        try:
            release = ScenarioPackage(target_root).release
            description = f"{release.name} {release.version} at {target_root}"
        except ManifestError:
            description = str(target_root)
        if not yes and not _confirm(f"Remove plugin {description}? [y/N] "):
            print("Aborted, no changes were made.")
            raise typer.Exit(code=1)
        plugins.remove_plugin(target_root, destination)
    except (ManifestError, ProviderError) as error:
        _fail(str(error))

    if as_json:
        print(json.dumps({"removed_plugin": str(target_root)}, indent=2))
    else:
        print(f"removed_plugin={target_root}")


@plugins_app.command("validate")
def plugins_validate(
    ctx: typer.Context,
    package: Optional[Path] = typer.Argument(None, help="Validate this installed plugin path only"),
    repo: Optional[str] = typer.Option(None, "--repo", help=REPO_FILTER_HELP),
    plugin_version: Optional[str] = typer.Option(
        None, "--plugin-version", help=PLUGIN_VERSION_HELP
    ),
    destination: Optional[Path] = typer.Option(None, "--destination", help=DESTINATION_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Check installed plugins: manifest, scenarios, entrypoints, workload definitions, resources."""
    try:
        destination = _plugin_destination(ctx, destination)
        if package is not None:
            roots = [package.resolve()]
            broken = []
        else:
            packages_, broken, destination = _discovery_scope(
                None, plugin_version, destination, _repo_filter(ctx, repo)
            )
            roots = [pkg.root for pkg in packages_]
    except (ManifestError, ProviderError) as error:
        _fail(str(error))

    results = []
    for root in roots:
        errors = plugins.validate_plugin(root)
        warnings_ = plugins.plugin_warnings(root)
        try:
            release = ScenarioPackage(root).release
            name, version = release.name, release.version
        except ManifestError:
            name, version = None, None
        results.append(
            {"name": name, "version": version, "root": str(root), "valid": not errors, "errors": errors,
             "warnings": warnings_}
        )
    for entry in broken:
        results.append(
            {"name": None, "version": None, "root": str(entry.root), "valid": False, "errors": [entry.error],
             "warnings": []}
        )

    failed = sum(1 for result in results if not result["valid"])
    if as_json:
        print(json.dumps(results, indent=2))
    elif not results:
        print(_no_plugins_message(ctx, destination))
    else:
        for result in results:
            label = f"{result['name']} {result['version']}  " if result["name"] else ""
            print(f"{'PASS' if result['valid'] else 'FAIL'}  {label}{result['root']}")
            for error in result["errors"]:
                print(f"  - {error}")
            for warning in result["warnings"]:
                print(f"  WARNING: {warning}")
        print(f"{len(results)} plugin(s) validated, {failed} failed")
    if failed:
        raise typer.Exit(code=1)


@workloads_app.command("list")
def workloads_list(
    ctx: typer.Context,
    package: Optional[Path] = typer.Argument(None, help="Report on this installed plugin path only"),
    repo: Optional[str] = typer.Option(None, "--repo", help=REPO_FILTER_HELP),
    plugin_version: Optional[str] = typer.Option(
        None, "--plugin-version", help=PLUGIN_VERSION_HELP
    ),
    destination: Optional[Path] = typer.Option(None, "--destination", help=DESTINATION_HELP),
    scenario: Optional[str] = typer.Option(
        None, "--scenario", help="Only list workloads that use this scenario id"
    ),
    copy_workload: Optional[str] = typer.Option(
        None,
        "--copy",
        help=(
            "Copy this workload definition into sas-validation.custom-workloads.location "
            "instead of listing"
        ),
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Replace an existing file when used with --copy"
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List workload definitions in installed plugins, or copy one for customization (--copy)."""
    _list_installed_content(
        ctx,
        target="workloads",
        package=package,
        plugin_version=plugin_version,
        destination=destination,
        scenario=scenario,
        copy_workload=copy_workload,
        overwrite=overwrite,
        as_json=as_json,
        repo=repo,
    )


@scenarios_app.command("list")
def scenarios_list(
    ctx: typer.Context,
    package: Optional[Path] = typer.Argument(None, help="Report on this installed plugin path only"),
    repo: Optional[str] = typer.Option(None, "--repo", help=REPO_FILTER_HELP),
    plugin_version: Optional[str] = typer.Option(
        None, "--plugin-version", help=PLUGIN_VERSION_HELP
    ),
    destination: Optional[Path] = typer.Option(None, "--destination", help=DESTINATION_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List scenarios and their test entrypoints in installed plugins."""
    _list_installed_content(
        ctx,
        target="scenarios",
        package=package,
        plugin_version=plugin_version,
        destination=destination,
        scenario=None,
        copy_workload=None,
        overwrite=False,
        as_json=as_json,
        repo=repo,
    )


def _gitlab_alias(ctx: typer.Context, repository: Optional[str]):
    alias, repo = _resolve_repository(ctx.obj.repositories_config, repository)
    if repo.provider != "gitlab-release":
        raise ProviderError(f"Repository '{alias}' is not a GitLab repository and needs no token lookup")
    return alias, repo


@auth_app.command("status")
def auth_status(
    ctx: typer.Context,
    repo_alias: Optional[str] = typer.Option(None, "--repo", help=REPO_HELP),
) -> None:
    """Show where the token for a repository would come from (never prints the token)."""
    try:
        alias, repo = _gitlab_alias(ctx, repo_alias)
    except (ManifestError, ProviderError) as error:
        _fail(str(error))
    token = resolve_gitlab_token(repo)
    if token is None:
        _fail(f"No token found for '{alias}' ({repository_host(repo)}). Log in with 'glab auth login --hostname {repository_host(repo)}' or set {RELEASE_TOKEN_ENV}")
    typer.echo(f"'{alias}' will use the token from {token.source}.")


@app.command()
def run(
    ctx: typer.Context,
    package: Optional[Path] = typer.Argument(
        None, help="Installed plugin path to use instead of searching the installed plugins"
    ),
    workload_definition: Optional[str] = typer.Option(
        None,
        "-w",
        "--workload",
        "--workload-definition",
        help="Plugin workload name, definition filename, or path to a definition file",
    ),
    custom_workload: Optional[str] = typer.Option(
        None,
        "--custom-workload",
        help="Workload definition name or file from sas-validation.custom-workloads.location",
    ),
    scenario: Optional[str] = typer.Option(
        None,
        "--scenario",
        help="Scenario id to run a single test from, without an authored workload definition",
    ),
    test: Optional[str] = typer.Option(
        None, "--test", help="Test entrypoint file to run (used with --scenario)"
    ),
    users: Optional[int] = typer.Option(
        None,
        "--users",
        help="Number of users (with --scenario/--test); worker-replicas is set to match",
    ),
    spawn_rate: Optional[int] = typer.Option(
        None, "--spawn-rate", help="Locust spawn rate (with --scenario/--test)"
    ),
    iterations: Optional[int] = typer.Option(
        None, "--iterations", help="Number of iterations (with --scenario/--test)"
    ),
    generate_only: bool = typer.Option(
        False, "--generate-only", help="Generate the workload but do not execute it"
    ),
    plugin_version: Optional[str] = typer.Option(
        None,
        "--plugin-version",
        help=(
            "Select this installed plugin version when more than one plugin provides "
            "the workload or scenario, e.g. 2026.08 (a leading 'v' is optional); "
            "ignored when a plugin path is given"
        ),
    ),
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        help=(
            "Select the installed plugin that came from this repository alias; "
            "ignored when a plugin path is given"
        ),
    ),
    framework_root: Optional[Path] = typer.Option(
        None,
        "--framework-root",
        help="Framework directory (default: sas-validation.framework-root)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Directory for generated workloads (default: sas-validation.output.destination)",
    ),
    users_file: Optional[Path] = typer.Option(
        None, "--users-file", help="Users CSV file for seeding test credentials"
    ),
    workload_overrides: Optional[Path] = typer.Option(
        None,
        "--workload-overrides",
        help="YAML file of overrides applied to the workload definition",
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level: WARN, WARNING, INFO or DEBUG"
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help=(
            "Run Locust on this machine instead of Kubernetes; needs a users file "
            "(--users-file or sas-validation.execution.users-file) and the 'local' extra "
            "of the sas-validation package"
        ),
    ),
    headed: bool = typer.Option(
        False,
        "--headed",
        help="With --local, show the Playwright browser windows (headless by default)",
    ),
    processes: Optional[int] = typer.Option(
        None,
        "--processes",
        min=1,
        help="With --local, number of Locust worker processes (default: the workload's user count)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="With --local, install missing Locust/Playwright dependencies without prompting",
    ),
) -> None:
    """Generate a workload and run it.

    Choose one of: --workload, --custom-workload, or --scenario with --test.
    Requires sas-validation.execution.hostname in the config. Use --local to run
    Locust on this machine instead of in Kubernetes.
    """
    state = ctx.obj
    try:
        ad_hoc = scenario is not None or test is not None
        if not local and (headed or processes is not None or yes):
            raise typer.BadParameter("--headed, --processes and --yes require --local")
        if custom_workload is not None and workload_definition is not None:
            raise typer.BadParameter(
                "Specify either --custom-workload or --workload-definition, not both"
            )
        if ad_hoc and (workload_definition is not None or custom_workload is not None):
            raise typer.BadParameter(
                "Specify --custom-workload/--workload-definition or --scenario/--test, not both"
            )
        if ad_hoc and (scenario is None or test is None):
            raise typer.BadParameter("--scenario and --test must be provided together")
        if not ad_hoc and workload_definition is None and custom_workload is None:
            raise typer.BadParameter("Specify --custom-workload, --workload-definition, or --scenario/--test")
        if not ad_hoc and (users is not None or spawn_rate is not None or iterations is not None):
            raise typer.BadParameter(
                "--users/--spawn-rate/--iterations require --scenario/--test; "
                "use --workload-overrides to override an authored workload definition"
            )

        package_config = _require_config(state.package_config, "--config")
        defaults = load_scenario_package_defaults(package_config)
        destination, framework_root, output = _resolve_defaults(
            defaults, None, framework_root, output
        )
        if framework_root is None:
            raise ManifestError(
                "--framework-root is required (or set 'framework-root' in --config under 'sas-validation')"
            )
        if output is None:
            raise ManifestError(
                "--output is required (or set 'output.destination' in --config under 'sas-validation')"
            )

        if local:
            if users_file is None and defaults.users_file is None:
                raise ManifestError(
                    "--local needs a users file: pass --users-file or set "
                    "'sas-validation.execution.users-file' in the config"
                )
            users_file = _existing_file(
                users_file if users_file is not None else defaults.users_file,
                "--users-file" if users_file is not None else "sas-validation.execution.users-file",
            )

        if custom_workload is not None:
            custom_workload_path = _resolve_custom_workload(
                custom_workload, defaults.custom_workloads
            )
            workload_definition = str(custom_workload_path)

        package_path = package
        if package_path is None:
            repo_filter = _repo_filter(ctx, repo)
            if ad_hoc:
                package_path = _installed_package_for_scenario(
                    scenario, plugin_version, destination, repo_filter
                )
            elif custom_workload is not None:
                package_path = _installed_package_for_workload_file(
                    Path(workload_definition), plugin_version, destination, repo_filter
                )
            else:
                package_path = _installed_package_for_workload(
                    workload_definition, plugin_version, destination, repo_filter
                )
        scenario_package = ScenarioPackage(package_path)

        if ad_hoc:
            workload_definition = str(
                scenario_package.synthesize_workload_definition(
                    scenario,
                    test,
                    output,
                    users=users,
                    spawn_rate=spawn_rate,
                    iterations=iterations,
                )
            )

        if local:
            unsupported = scenario_package.unsupported_scenarios(workload_definition, "local")
            if unsupported:
                raise ManifestError(
                    "These scenarios can only run in Kubernetes ('execution-targets' excludes local): "
                    f"{', '.join(unsupported)}"
                )
            if headed and users is not None and users > HEADED_USERS_WARNING_THRESHOLD:
                typer.echo(
                    f"WARNING: --headed opens one browser window per user ({users}); "
                    f"use headless mode for more than {HEADED_USERS_WARNING_THRESHOLD} users.",
                    err=True,
                )
            if not generate_only:
                _ensure_local_dependencies(yes)

        result = scenario_package.generate(
            workload_definition,
            output,
            framework_root,
            hostname=_require_hostname(defaults),
            trusted_certs=defaults.trusted_certs,
            namespace=defaults.namespace,
            users_file=_existing_file(users_file, "--users-file"),
            workload_overrides=_existing_file(workload_overrides, "--workload-overrides"),
            log_level=_normalized_log_level(log_level),
            execution_target="local" if local else "kubernetes",
            local_options={"headed": headed, "processes": processes} if local else None,
        )
        print(f"generated_workload_root={result.generated_workload_root}")

        if generate_only:
            return

        exit_code = scenario_package.run_workload(
            workload_definition, result.generated_workload_root, local=local
        )
        print(f"workload_exit_code={exit_code}")
        if exit_code:
            raise typer.Exit(code=exit_code)
    except (ManifestError, ProviderError, InstallError) as error:
        _fail(str(error))



@app.command("cleanup")
def cleanup_cmd(
    local: bool = typer.Option(False, "--local", help="Inspect or stop tracked local runs only."),
    list_only: bool = typer.Option(False, "--list", help="List recorded local runs without stopping them."),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Local run ID printed in the workload log."),
    stop: bool = typer.Option(False, "--stop", help="Stop the selected run after confirmation (otherwise preview only)."),
    yes: bool = typer.Option(False, "--yes", help="Confirm stopping the selected run without prompting."),
) -> None:
    """Preview or clean up processes belonging to a specific local run."""
    if not local:
        raise typer.BadParameter("Cleanup requires --local; Kubernetes cleanup is not supported")
    if os.name != "posix":
        raise typer.BadParameter("Local cleanup requires macOS or Linux")
    if list_only and (run_id is not None or stop or yes):
        raise typer.BadParameter("--list cannot be combined with --run-id, --stop, or --yes")
    if yes and not stop:
        raise typer.BadParameter("--yes requires --stop")
    if not list_only and run_id is None:
        raise typer.BadParameter("Specify --list or --run-id")
    try:
        if list_only:
            records = local_processes.list_runs()
        else:
            assert run_id is not None
            records = [local_processes.read_record(run_id)]
        if not records:
            typer.echo("No recorded local runs.")
        for record in records:
            members = local_processes.owned_members(record)
            pids = ", ".join(str(item["pid"]) for item in members) or "none (stale record)"
            typer.echo(f"run_id={record['run_id']} processes={pids}\n  directory={record['cwd']}")
        if stop:
            assert run_id is not None
            if yes or typer.confirm(f"Stop all owned processes for local run {run_id}?"):
                local_processes.cleanup_run(run_id)
                typer.echo(f"Cleaned up local run {run_id}.")
        elif run_id is not None:
            typer.echo("Preview only. Add --stop to request cleanup.")
    except (OSError, ValueError, RuntimeError, psutil.Error) as error:
        _fail(f"Local cleanup failed: {error}")


@app.command("preflight")
def preflight_cmd(
    ctx: typer.Context,
    namespace: Optional[str] = typer.Option(
        None, "--namespace", help="Kubernetes namespace (default: sas-validation.execution.namespace)"
    ),
    hostname: Optional[str] = typer.Option(
        None, "--hostname", help="Viya URL (default: sas-validation.execution.hostname)"
    ),
    framework_root: Optional[Path] = typer.Option(
        None,
        "--framework-root",
        help="Framework directory (default: sas-validation.framework-root)",
    ),
    users_file: Optional[Path] = typer.Option(
        None, "--users-file", help="users.csv used to seed or verify test credentials"
    ),
    group: List[str] = typer.Option(
        [],
        "--group",
        help=(
            "Check groups: client, cluster, or local (for run --local); repeatable "
            "(default: client and cluster)"
        ),
    ),
    fix: bool = typer.Option(False, "--fix", help="Apply the remediations that can be automated"),
    yes: bool = typer.Option(False, "--yes", help="Do not prompt before --fix"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Stream fix scripts' own output live (for troubleshooting)"
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", help="Timeout in seconds for HTTP requests and commands"
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Inspect the environment for everything a generated workload needs."""
    for name in group:
        if name not in preflight.GROUPS:
            raise typer.BadParameter(
                f"--group must be one of: {', '.join(preflight.GROUPS)}", param_hint="--group"
            )
    args = SimpleNamespace(
        namespace=namespace,
        hostname=hostname,
        framework_root=framework_root,
        users_file=users_file,
        groups=group,
        fix=fix,
        assume_yes=yes,
        verbose=verbose,
        timeout=timeout,
        as_json=as_json,
    )
    try:
        exit_code = _run_preflight(args, ctx.obj.package_config)
    except ManifestError as error:
        _fail(str(error))
    if exit_code:
        raise typer.Exit(code=exit_code)


def _load_users(
    ctx: typer.Context,
    namespace: str = typer.Option(..., "--namespace", help="Kubernetes namespace"),
    users_file: Path = typer.Option(..., "--users-file", help="Path to users.csv file"),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Load a users CSV file into a Kubernetes secret."""
    args = SimpleNamespace(
        namespace=namespace,
        users_file=users_file,
        as_json=as_json,
    )
    try:
        exit_code = _run_load_users(args)
    except ManifestError as error:
        _fail(str(error))
    if exit_code:
        raise typer.Exit(code=exit_code)


@users_app.command("load")
def users_load(
    ctx: typer.Context,
    namespace: str = typer.Option(..., "--namespace", help="Kubernetes namespace"),
    users_file: Path = typer.Option(..., "--users-file", help="Path to users.csv file"),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Load a users CSV file into the 'validation-scenarios' Kubernetes secret (uses KUBECONFIG)."""
    ctx.invoke(
        _load_users,
        ctx=ctx,
        namespace=namespace,
        users_file=users_file,
        as_json=as_json,
    )


app.add_typer(plugins_app, name="plugins")
app.add_typer(workloads_app, name="workloads")
app.add_typer(scenarios_app, name="scenarios")
app.add_typer(users_app, name="users")
app.add_typer(auth_app, name="auth")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
