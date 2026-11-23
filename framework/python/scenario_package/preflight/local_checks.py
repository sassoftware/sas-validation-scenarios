# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Checks for running workloads with Locust on this machine (sas-validation run --local)."""

import importlib
import platform
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from . import k8s
from .core import Check, CheckResult, PreflightContext, fail, ok, skipped, warn
from .http import HttpError

# Import name -> pip requirement, matching the 'local' extra in pyproject.toml.
LOCAL_MODULES = (
    ("locust", "locust"),
    ("locust_plugins", "locust-plugins[playwright]"),
    ("playwright", "playwright"),
    ("dotenv", "python-dotenv"),
)
BROWSER = "chromium"
INSTALL_EXTRA_HINT = (
    "pip install --prefer-binary -e '.[local]' (from the sas-validation-scenarios directory)"
)
# Below this, Locust's gevent dependency often has no prebuilt package and pip compiles it.
RECOMMENDED_PYTHON = (3, 10)
_WHEEL_BUILD_FAILURE = re.compile(r"Failed building wheel for ([A-Za-z0-9_.\-]+)")

# Prints the path of the Playwright browser executable; it exists only after 'playwright install'.
_BROWSER_PROBE = (
    "from playwright.sync_api import sync_playwright\n"
    "with sync_playwright() as p:\n"
    f"    print(p.{BROWSER}.executable_path)\n"
)


def _python_version_text(version: Tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version[:2])


def _python_too_old(version: Tuple[int, ...]) -> bool:
    return tuple(version[:2]) < RECOMMENDED_PYTHON


def _python_version(context: PreflightContext) -> CheckResult:
    version = tuple(sys.version_info[:3])
    current = _python_version_text(version)
    if _python_too_old(version):
        return warn(
            f"Python {current} is older than {_python_version_text(RECOMMENDED_PYTHON)}; "
            "Locust's dependencies (gevent) may have no prebuilt packages for it and need compiling",
            remedy=f"Use Python {_python_version_text(RECOMMENDED_PYTHON)} or newer for local runs",
        )
    return ok(f"Python {current} ({sys.executable})")


def _pip_failure(output: str, returncode: int) -> str:
    """One-line explanation of a failed pip install; the full output is saved to a log file."""
    match = None
    for match in _WHEEL_BUILD_FAILURE.finditer(output):
        pass
    if match is not None:
        package = match.group(1)
        version = tuple(sys.version_info[:2])
        message = (
            f"pip could not build {package} from source (no prebuilt package for "
            f"Python {_python_version_text(version)} on {platform.machine() or 'this machine'})"
        )
        if _python_too_old(version):
            message += f"; use Python {_python_version_text(RECOMMENDED_PYTHON)} or newer"
        else:
            message += "; a C compiler and the Python development headers are needed to build it"
    else:
        errors = [line.strip() for line in output.splitlines() if line.strip().startswith("ERROR:")]
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        detail = errors[-1] if errors else (lines[-1] if lines else "no output")
        message = f"pip install exited {returncode}: {detail}"
    try:
        with tempfile.NamedTemporaryFile(
            "w", prefix="sas-validation-pip-", suffix=".log", delete=False, encoding="utf-8"
        ) as log:
            log.write(output)
        message += f" (full pip output: {log.name})"
    except OSError:
        pass
    return message


def _missing_modules(context: PreflightContext) -> List[str]:
    return [name for name, _ in LOCAL_MODULES if not context.module_available(name)]


def _python_modules(context: PreflightContext) -> CheckResult:
    missing = _missing_modules(context)
    if missing:
        return fail(
            f"missing python modules: {', '.join(missing)}",
            remedy=INSTALL_EXTRA_HINT,
            fixable=True,
        )
    return ok(f"{', '.join(name for name, _ in LOCAL_MODULES)} installed")


def _install_modules(context: PreflightContext) -> str:
    missing = set(_missing_modules(context))
    requirements = [requirement for name, requirement in LOCAL_MODULES if name in missing]
    if not requirements:
        return "nothing to install"
    completed = context.run_command(
        [sys.executable, "-m", "pip", "install", "--prefer-binary", *requirements],
        max(context.timeout, 600.0),
    )
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise RuntimeError(_pip_failure(output, completed.returncode))
    # Let the re-check in this process see the packages pip just installed.
    importlib.invalidate_caches()
    return f"installed {', '.join(requirements)}"


_SHARED_LIBRARY_ERROR = re.compile(r"error while loading shared libraries: ([^:\s]+)")


def _missing_shared_library(output: str) -> Optional[str]:
    match = _SHARED_LIBRARY_ERROR.search(output or "")
    return match.group(1) if match else None


def _driver_library_remedy(library: str) -> str:
    return (
        f"Install the system package that provides {library}, then run: "
        f"{sys.executable} -m playwright install {BROWSER}"
    )


def _driver_missing_library(context: PreflightContext) -> Optional[str]:
    """The shared library that stops Playwright's bundled Node.js driver from starting, if any."""
    completed = context.run_command(
        [sys.executable, "-m", "playwright", "--version"], context.timeout
    )
    if completed.returncode == 0:
        return None
    return _missing_shared_library(f"{completed.stdout or ''}\n{completed.stderr or ''}")


def _browser_remedy() -> str:
    remedy = f"{sys.executable} -m playwright install {BROWSER}"
    if sys.platform.startswith("linux"):
        remedy += f"; then sudo {sys.executable} -m playwright install-deps {BROWSER}"
    return remedy


def _browsers(context: PreflightContext) -> CheckResult:
    completed = context.run_command([sys.executable, "-c", _BROWSER_PROBE], context.timeout)
    location = (completed.stdout or "").strip().splitlines()
    executable = Path(location[-1]) if completed.returncode == 0 and location else None
    if executable is None or not executable.exists():
        if completed.returncode != 0:
            library = _missing_shared_library(completed.stderr) or _driver_missing_library(context)
            if library:
                # 'playwright install' and 'install-deps' run through the same driver, so --fix cannot help.
                return fail(
                    f"the Playwright driver cannot start: the system library {library} is missing",
                    remedy=_driver_library_remedy(library),
                )
        detail = f"the Playwright {BROWSER} browser is not installed"
        if completed.returncode != 0:
            errors = (completed.stderr or "").strip().splitlines()
            detail += f" ({errors[-1] if errors else 'probe failed'})"
        return fail(detail, remedy=_browser_remedy(), fixable=True)
    return ok(str(executable))


def _install_browser(context: PreflightContext) -> str:
    completed = context.run_command(
        [sys.executable, "-m", "playwright", "install", BROWSER], max(context.timeout, 600.0)
    )
    if completed.returncode != 0:
        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        library = _missing_shared_library(output)
        if library:
            raise RuntimeError(
                f"the Playwright driver cannot start: the system library {library} is missing. "
                f"{_driver_library_remedy(library)}"
            )
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        raise RuntimeError(
            f"playwright install exited {completed.returncode}: {lines[-1] if lines else 'no output'}"
        )
    message = f"installed the Playwright {BROWSER} browser"
    if sys.platform.startswith("linux"):
        message += f"; if it fails to start, run: sudo {sys.executable} -m playwright install-deps {BROWSER}"
    return message


def _users_file(context: PreflightContext) -> Optional[Path]:
    return context.users_file or context.configured_users_file


def _users(context: PreflightContext) -> CheckResult:
    path = _users_file(context)
    if path is None:
        return fail(
            "no users file is configured for local runs",
            remedy="Pass --users-file or set 'sas-validation.execution.users-file' in sas-validation.yaml",
        )
    if not path.is_file():
        return fail(
            f"users file does not exist: {path}",
            remedy="Create a CSV file with one 'user,password' row per (non-admin) test user",
        )
    try:
        users = k8s.users_from_csv(path)
    except Exception as error:
        return fail(str(error), remedy="Use one 'user,password' row per test user")
    return ok(f"{len(users)} user(s) in {path}")


def _configuration(context: PreflightContext) -> CheckResult:
    if context.config_error is not None:
        return fail(
            context.config_error,
            remedy=(
                "Create sas-validation.yaml from its template in the current directory "
                "or a parent directory, or pass --config"
            ),
        )
    if not context.hostname:
        return fail(
            f"{context.config_path}: missing execution.hostname (or --hostname)",
            remedy="Set 'sas-validation.execution.hostname' in sas-validation.yaml",
        )
    return ok(f"hostname={context.hostname}")


def _viya_reachable(context: PreflightContext) -> CheckResult:
    if context.http is None:
        return skipped("no HTTP client available")
    url = f"{context.hostname.rstrip('/')}/SASLogon/login"
    try:
        response = context.http.request(url)
    except HttpError as error:
        return fail(
            f"{url} is not reachable from this machine: {error}",
            remedy="Check the hostname, DNS, VPN and the trusted-certs setting",
        )
    if response.status >= 400:
        return fail(
            f"{url} returned HTTP {response.status}",
            remedy="Confirm SASLogon is running on this Viya deployment",
        )
    return ok(f"{url} returned HTTP {response.status}")


def checks() -> List[Check]:
    return [
        Check("local.python-version", "local", "Python version", _python_version),
        Check("local.config", "local", "sas-validation.yaml", _configuration),
        Check(
            "local.python-modules",
            "local",
            "Locust and Playwright modules",
            _python_modules,
            fix=_install_modules,
            fix_summary="Install locust, locust-plugins, playwright and python-dotenv with pip",
        ),
        Check(
            "local.browser",
            "local",
            "Playwright browser",
            _browsers,
            fix=_install_browser,
            requires=("local.python-modules",),
            fix_summary=f"Install the Playwright {BROWSER} browser (playwright install {BROWSER})",
        ),
        Check("local.users-file", "local", "Users file", _users),
        Check(
            "local.viya-reachable",
            "local",
            "Viya reachable",
            _viya_reachable,
            requires=("local.config",),
        ),
    ]


DEPENDENCY_CHECKS = ("local.python-modules", "local.browser")


def dependency_checks() -> List[Check]:
    """The Python packages and Playwright browser that 'run --local' needs; both fixable."""
    return [check for check in checks() if check.identifier in DEPENDENCY_CHECKS]


def python_version_check() -> Check:
    return next(check for check in checks() if check.identifier == "local.python-version")
