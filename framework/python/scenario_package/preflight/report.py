# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rendering for preflight findings."""

from typing import Dict, List, Sequence

from .core import Finding, PreflightContext, Status

GROUP_TITLES = {
    "client": "Client workstation",
    "cluster": "Load generation cluster",
    "local": "Local Locust execution",
    "viya": "SAS Viya environment",
}
MARKERS = {
    Status.OK: "  OK  ",
    Status.WARN: " WARN ",
    Status.FAIL: " FAIL ",
    Status.SKIPPED: " SKIP ",
}


def as_json(findings: Sequence[Finding]) -> List[Dict]:
    return [
        {
            "id": finding.identifier,
            "group": finding.check.group,
            "title": finding.check.title,
            "status": finding.result.status.value,
            "detail": finding.result.detail,
            "remedy": finding.result.remedy,
            "fixable": finding.fixable,
            "fix-applied": finding.fix_applied,
            "fix-error": finding.fix_error,
        }
        for finding in findings
    ]


def render(findings: Sequence[Finding], fixed: bool) -> List[str]:
    lines: List[str] = []
    for group in GROUP_TITLES:
        rows = [finding for finding in findings if finding.check.group == group]
        if not rows:
            continue
        lines.append("")
        lines.append(GROUP_TITLES[group])
        for finding in rows:
            lines.append(
                f"[{MARKERS[finding.result.status]}] {finding.check.title}: {finding.result.detail}"
            )
            if finding.fix_applied:
                if finding.result.status is Status.OK:
                    lines.append(f"           fixed: {finding.fix_applied}")
                else:
                    lines.append(
                        f"           fix ran but the check still reports "
                        f"{finding.result.status.value.upper()}: {finding.fix_applied}"
                    )
            if finding.fix_error:
                lines.append(f"           fix failed: {finding.fix_error}")

    counts = {status: 0 for status in Status}
    for finding in findings:
        counts[finding.result.status] += 1
    lines.append("")
    lines.append(
        f"{counts[Status.OK]} ok, {counts[Status.WARN]} warning, "
        f"{counts[Status.FAIL]} failed, {counts[Status.SKIPPED]} skipped"
    )

    fixable = [finding for finding in findings if finding.fixable and not finding.fix_error]
    if fixable:
        lines.append("")
        lines.append(f"Fixable automatically ({len(fixable)}) - re-run with --fix:")
        for finding in fixable:
            lines.append(f"  {finding.identifier}: {finding.result.remedy}")

    manual = [
        finding
        for finding in findings
        if finding.result.status in (Status.FAIL, Status.WARN)
        and finding.result.remedy
        and (not finding.fixable or finding.fix_error)
    ]
    if manual:
        lines.append("")
        lines.append(f"Complete these manually ({len(manual)}):")
        for finding in manual:
            lines.append(f"  {finding.identifier}: {finding.result.remedy}")

    if fixed and not any(finding.result.status is Status.FAIL for finding in findings):
        lines.append("")
        lines.append("Environment is ready to run generated workloads.")
    return lines


def render_plan(findings: Sequence[Finding], context: PreflightContext) -> List[str]:
    lines = ["The following changes will be applied:"]

    round0: Dict[str, List[Finding]] = {}
    for finding in findings:
        if finding.fixable:
            round0.setdefault(finding.check.remediation_key, []).append(finding)

    for group in round0.values():
        lines.append(f"  {group[0].check.fix_description}")
        if len(group) > 1:
            lines.append(f"    (affects: {', '.join(f.check.title for f in group)})")
        else:
            lines.append(f"    ({group[0].identifier}: {group[0].result.remedy})")

    # Static cascade preview: which currently-skipped checks become reachable once
    # the changes above are applied? Mirrors apply_fixes()'s rounds without running
    # anything, so it can only promise these will be *re-checked*, not fixed for sure.
    satisfied = {finding.identifier for finding in findings if finding.result.status is Status.OK}
    for group in round0.values():
        satisfied.update(finding.identifier for finding in group)

    cascade: Dict[str, List[Finding]] = {}
    remaining = [
        finding
        for finding in findings
        if finding.check.fix is not None
        and (finding.check.fix_available is None or finding.check.fix_available(context))
        and finding.identifier not in satisfied
        and finding.check.remediation_key not in round0
    ]
    changed = True
    while changed:
        changed = False
        for finding in list(remaining):
            if all(req in satisfied for req in finding.check.requires):
                cascade.setdefault(finding.check.remediation_key, []).append(finding)
                satisfied.add(finding.identifier)
                remaining.remove(finding)
                changed = True

    if cascade:
        lines.append("")
        lines.append(
            "Fixing the above also unblocks these checks; they will be re-checked "
            "and fixed automatically if still failing:"
        )
        for group in cascade.values():
            lines.append(f"  {group[0].check.fix_description}")
            lines.append(f"    (affects: {', '.join(f.check.title for f in group)})")

    return lines
