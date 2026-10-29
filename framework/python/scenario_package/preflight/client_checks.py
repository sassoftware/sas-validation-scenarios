# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Checks for the workstation that drives workload generation and execution."""

import sys
from pathlib import Path
from typing import List

from .core import Check, CheckResult, PreflightContext, fail, ok, warn

MINIMUM_PYTHON = (3, 9)
REQUIRED_MODULES = ("kubernetes", "yaml", "deepmerge", "platformdirs")


def _python_version(context: PreflightContext) -> CheckResult:
    current = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info[:2] < MINIMUM_PYTHON:
        return fail(
            f"python {current} is older than the required 3.9",
            remedy="Install python 3.9 or newer and recreate the virtual environment",
        )
    return ok(f"python {current}")


def _virtualenv(context: PreflightContext) -> CheckResult:
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return ok(f"running inside {sys.prefix}")
    return warn(
        "not running inside a virtual environment",
        remedy="python3 -m venv .venv && source .venv/bin/activate && pip install -e .",
    )


def _binary(name: str, required: bool, purpose: str, install_hint: str):
    def check(context: PreflightContext) -> CheckResult:
        location = context.which(name)
        if location:
            return ok(location)
        detail = f"'{name}' is not on PATH ({purpose})"
        if required:
            return fail(detail, remedy=install_hint)
        return warn(detail, remedy=install_hint)

    return check


def _python_modules(context: PreflightContext) -> CheckResult:
    missing = [name for name in REQUIRED_MODULES if not context.module_available(name)]
    if missing:
        return fail(
            f"missing python modules: {', '.join(missing)}",
            remedy="pip install -e . (from the sas-validation-scenarios directory)",
        )
    return ok(f"all required modules present ({len(REQUIRED_MODULES)} checked)")


def _kubeconfig(context: PreflightContext) -> CheckResult:
    value = context.environ.get("KUBECONFIG")
    if not value:
        return fail(
            "KUBECONFIG is not set",
            remedy="export KUBECONFIG=<path to your kubeconfig file>",
        )
    paths = [Path(part).expanduser() for part in value.split(":") if part]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        return fail(
            f"KUBECONFIG references files that do not exist: {', '.join(missing)}",
            remedy="Point KUBECONFIG at a readable kubeconfig file",
        )
    return ok(value)


def _configuration(context: PreflightContext) -> CheckResult:
    if context.config_error is not None:
        return fail(
            context.config_error,
            remedy=(
                "Create sas-validation.yaml from its template in the current directory "
                "or a parent directory, or pass --config"
            ),
        )
    missing = []
    if not context.namespace:
        missing.append("execution.namespace (or --namespace)")
    if not context.hostname:
        missing.append("execution.hostname (or --hostname)")
    if missing:
        return fail(
            f"{context.config_path}: missing {', '.join(missing)}",
            remedy=(
                "Set 'sas-validation.execution.namespace' and "
                "'sas-validation.execution.hostname' in sas-validation.yaml"
            ),
        )
    return ok(f"namespace={context.namespace} hostname={context.hostname}")


def checks() -> List[Check]:
    return [
        Check("client.python-version", "client", "Python version", _python_version),
        Check("client.venv", "client", "Virtual environment", _virtualenv),
        Check(
            "client.kubectl",
            "client",
            "kubectl available",
            _binary(
                "kubectl",
                True,
                "used by the generated workload scripts",
                "Install kubectl: https://kubernetes.io/docs/tasks/tools/",
            ),
        ),
        Check(
            "client.jq",
            "client",
            "jq available",
            _binary(
                "jq",
                True,
                "used by the generated workload scripts",
                "Install jq: https://jqlang.github.io/jq/download/",
            ),
        ),
        Check(
            "client.yq",
            "client",
            "yq available",
            _binary(
                "yq",
                False,
                "used only by the legacy generateWorkloads.sh",
                "Install yq: https://github.com/mikefarah/yq#install",
            ),
        ),
        Check("client.python-modules", "client", "Python modules", _python_modules),
        Check("client.kubeconfig", "client", "KUBECONFIG", _kubeconfig),
        Check("client.config", "client", "sas-validation.yaml", _configuration),
    ]
