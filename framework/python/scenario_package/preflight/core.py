# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check framework for environment readiness inspection."""

import importlib.util
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    status: Status
    detail: str
    remedy: Optional[str] = None
    fixable: bool = False


def ok(detail: str) -> CheckResult:
    return CheckResult(Status.OK, detail)


def warn(detail: str, remedy: Optional[str] = None, fixable: bool = False) -> CheckResult:
    return CheckResult(Status.WARN, detail, remedy, fixable)


def fail(detail: str, remedy: Optional[str] = None, fixable: bool = False) -> CheckResult:
    return CheckResult(Status.FAIL, detail, remedy, fixable)


def skipped(detail: str) -> CheckResult:
    return CheckResult(Status.SKIPPED, detail)


@dataclass
class Check:
    identifier: str
    group: str
    title: str
    run: Callable[["PreflightContext"], CheckResult]
    fix: Optional[Callable[["PreflightContext"], str]] = None
    requires: Tuple[str, ...] = ()
    fix_key: Optional[str] = None
    fix_summary: Optional[str] = None
    # Static preview hook: is the fix usable given current args, without running the check yet?
    fix_available: Optional[Callable[["PreflightContext"], bool]] = None

    @property
    def remediation_key(self) -> str:
        """Checks sharing a key are repaired by a single fix invocation."""
        return self.fix_key or self.identifier

    @property
    def fix_description(self) -> str:
        """Human-readable summary of what the fix does, shown before it runs."""
        return self.fix_summary or self.title


@dataclass
class Finding:
    check: Check
    result: CheckResult
    fix_applied: Optional[str] = None
    fix_error: Optional[str] = None

    @property
    def identifier(self) -> str:
        return self.check.identifier

    @property
    def fixable(self) -> bool:
        return self.result.fixable and self.check.fix is not None


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _run_command(command: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def stream_command(
    command: Sequence[str], timeout: float, on_line: Callable[[str], None]
) -> subprocess.CompletedProcess:
    """Like _run_command, but calls on_line(text) for each line as it is produced."""
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_lines: List[str] = []
    deadline = time.monotonic() + timeout
    try:
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            on_line(line.rstrip("\n"))
            if time.monotonic() > deadline:
                process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(list(command), timeout, output="".join(output_lines))
        returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    output = "".join(output_lines)
    return subprocess.CompletedProcess(list(command), returncode, stdout=output, stderr="")


@dataclass
class PreflightContext:
    """Inputs and injectable collaborators shared by every check."""

    namespace: Optional[str] = None
    hostname: Optional[str] = None
    trusted_certs: Optional[Path] = None
    users_file: Optional[Path] = None
    # sas-validation.execution.users-file; used by the local checks when --users-file is not given.
    configured_users_file: Optional[Path] = None
    framework_root: Optional[Path] = None
    config_path: Optional[Path] = None
    config_error: Optional[str] = None
    timeout: float = 30.0
    environ: Mapping[str, str] = field(default_factory=dict)
    which: Callable[[str], Optional[str]] = shutil.which
    module_available: Callable[[str], bool] = _module_available
    run_command: Callable[[Sequence[str], float], subprocess.CompletedProcess] = _run_command
    kube_factory: Optional[Callable[["PreflightContext"], object]] = None
    http: Optional[object] = None
    # Populated by checks for downstream consumers.
    state: Dict[str, object] = field(default_factory=dict)
    _kube: Optional[object] = field(default=None, repr=False)

    def kube(self):
        """Kubernetes clients, created once per run."""
        if self._kube is None:
            if self.kube_factory is None:
                from .k8s import KubeClients

                self._kube = KubeClients.load(self.environ.get("KUBECONFIG"))
            else:
                self._kube = self.kube_factory(self)
        return self._kube


def run_checks(checks: Sequence[Check], context: PreflightContext) -> List[Finding]:
    findings: List[Finding] = []
    statuses: Dict[str, Status] = {}
    for check in checks:
        blockers = [
            required
            for required in check.requires
            if statuses.get(required) in (Status.FAIL, Status.SKIPPED, None)
        ]
        if blockers:
            result = skipped(f"skipped, depends on: {', '.join(blockers)}")
        else:
            try:
                result = check.run(context)
            except Exception as error:  # a broken probe must not abort the whole report
                result = fail(f"check raised {type(error).__name__}: {error}")
        statuses[check.identifier] = result.status
        findings.append(Finding(check, result))
    return findings


def apply_fixes(
    checks: Sequence[Check],
    findings: Sequence[Finding],
    context: PreflightContext,
    max_rounds: int = 4,
    on_fix_start: Optional[Callable[[str, List[Check]], None]] = None,
    on_fix_complete: Optional[
        Callable[[str, List[Check], Optional[str], Optional[str], float], None]
    ] = None,
) -> List[Finding]:
    """Apply auto-fixes and re-check, repeating because a fix can unblock skipped checks.

    on_fix_start/on_fix_complete fire once per remediation_key actually invoked, so
    callers can report progress without affecting the dedup/round logic below.
    """
    outcomes: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    current = list(findings)
    for _ in range(max_rounds):
        pending = [
            finding
            for finding in current
            if finding.fixable and finding.identifier not in outcomes
        ]
        if not pending:
            break
        by_key: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for finding in pending:
            key = finding.check.remediation_key
            if key not in by_key:
                group = [f.check for f in pending if f.check.remediation_key == key]
                if on_fix_start is not None:
                    on_fix_start(key, group)
                started = time.monotonic()
                try:
                    by_key[key] = (finding.check.fix(context), None)
                except Exception as error:
                    by_key[key] = (None, f"{type(error).__name__}: {error}")
                if on_fix_complete is not None:
                    applied, error = by_key[key]
                    on_fix_complete(key, group, applied, error, time.monotonic() - started)
            outcomes[finding.identifier] = by_key[key]
        context._kube = None
        current = run_checks(checks, context)

    for finding in current:
        applied, error = outcomes.get(finding.identifier, (None, None))
        finding.fix_applied = applied
        finding.fix_error = error
    return current


def fixable_findings(findings: Sequence[Finding]) -> List[Finding]:
    return [finding for finding in findings if finding.fixable]


def exit_code(findings: Sequence[Finding]) -> int:
    return 1 if any(finding.result.status is Status.FAIL for finding in findings) else 0
