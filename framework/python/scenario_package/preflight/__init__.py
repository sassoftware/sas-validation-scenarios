# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Environment readiness inspection for validation scenario execution."""

from typing import Dict, List, Sequence

from . import client_checks, cluster_checks, report
from .core import (
    Check,
    CheckResult,
    Finding,
    PreflightContext,
    Status,
    apply_fixes,
    exit_code,
    fixable_findings,
    run_checks,
)

# The 'viya' group in viya_checks.py is disabled until it is rewritten on the sas-viya admin CLI.
GROUPS = ("client", "cluster")

__all__ = [
    "Check",
    "CheckResult",
    "Finding",
    "GROUPS",
    "PreflightContext",
    "Status",
    "all_checks",
    "apply_fixes",
    "exit_code",
    "fixable_findings",
    "report",
    "run_checks",
    "select_checks",
]


def all_checks() -> List[Check]:
    return client_checks.checks() + cluster_checks.checks()


def select_checks(groups: Sequence[str]) -> List[Check]:
    """Checks for the requested groups plus the prerequisites they depend on."""
    checks = all_checks()
    if not groups:
        return checks
    by_id: Dict[str, Check] = {check.identifier: check for check in checks}
    wanted = set()

    def include(check: Check) -> None:
        if check.identifier in wanted:
            return
        wanted.add(check.identifier)
        for required in check.requires:
            if required in by_id:
                include(by_id[required])

    for check in checks:
        if check.group in groups:
            include(check)
    return [check for check in checks if check.identifier in wanted]
