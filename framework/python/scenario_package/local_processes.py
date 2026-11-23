"""Supervise local workloads and recover only processes owned by a recorded run."""

import argparse
import json
import os
from pathlib import Path
from types import FrameType
import signal
import subprocess
import sys
import time
from typing import Optional, TypedDict
from uuid import UUID, uuid4

from platformdirs import user_state_path
import psutil


GRACE_SECONDS = 15
POLL_SECONDS = 0.1


class ProcessIdentity(TypedDict):
    pid: int
    created: float
    group: int


class RunRecord(TypedDict):
    run_id: str
    uid: int
    group: int
    cwd: str
    members: list[ProcessIdentity]


def registry_directory() -> Path:
    directory = user_state_path("sas-validation") / "local-runs"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def record_path(run_id: str) -> Path:
    if str(UUID(run_id)) != run_id:
        raise ValueError("Invalid local run ID")
    return registry_directory() / f"{run_id}.json"


def identity(process: psutil.Process) -> ProcessIdentity:
    return {"pid": process.pid, "created": process.create_time(), "group": os.getpgid(process.pid)}


def group_members(group: int) -> list[ProcessIdentity]:
    members: list[ProcessIdentity] = []
    for process in psutil.process_iter(["uids"]):
        try:
            uids = process.info["uids"]
            if uids is not None and uids.real == os.getuid() and os.getpgid(process.pid) == group:
                if process.status() != psutil.STATUS_ZOMBIE:
                    members.append(identity(process))
        except (psutil.NoSuchProcess, ProcessLookupError):
            continue
    return members


def matching_process(item: ProcessIdentity) -> Optional[psutil.Process]:
    try:
        process = psutil.Process(item["pid"])
        if (process.create_time() == item["created"]
                and process.uids().real == os.getuid()
                and os.getpgid(process.pid) == item["group"]
                and process.status() != psutil.STATUS_ZOMBIE):
            return process
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass
    return None


def read_record(run_id: str) -> RunRecord:
    record = json.loads(record_path(run_id).read_text(encoding="utf-8"))
    if (not isinstance(record, dict)
            or record.get("run_id") != run_id or record.get("uid") != os.getuid()
            or type(record.get("group")) is not int or record["group"] <= 1
            or not isinstance(record.get("members"), list)
            or not isinstance(record.get("cwd"), str)):
        raise ValueError(f"Invalid ownership record for {run_id}")
    for item in record["members"]:
        if (not isinstance(item, dict) or type(item.get("pid")) is not int
                or item["pid"] <= 1 or type(item.get("created")) not in (int, float)
                or type(item.get("group")) is not int or item["group"] <= 1):
            raise ValueError(f"Invalid process identity for {run_id}")
    return RunRecord(
        run_id=record["run_id"], uid=record["uid"], group=record["group"],
        cwd=record["cwd"], members=record["members"],
    )


def owned_members(record: RunRecord) -> list[ProcessIdentity]:
    group = record["group"]
    # A recorded identity must still anchor the group. Never trust a bare PID/PGID.
    known = [item for item in record["members"] if matching_process(item) is not None]
    members = {item["pid"]: item for item in known}
    if any(item["group"] == group for item in known):
        members.update((item["pid"], item) for item in group_members(group))
    for item in list(members.values()):
        process = matching_process(item)
        if process is not None:
            try:
                for child in process.children(recursive=True):
                    if child.uids().real == os.getuid() and child.status() != psutil.STATUS_ZOMBIE:
                        members[child.pid] = identity(child)
            except (psutil.NoSuchProcess, ProcessLookupError):
                continue
    return list(members.values())


def list_runs() -> list[RunRecord]:
    return [read_record(path.stem) for path in sorted(registry_directory().glob("*.json"))]


def signal_members(members: list[ProcessIdentity], sig: int) -> None:
    for item in members:
        process = matching_process(item)
        if process is not None:
            try:
                process.send_signal(sig)
            except psutil.NoSuchProcess:
                pass


def cleanup_run(run_id: str, grace: float = GRACE_SECONDS) -> None:
    record = read_record(run_id)
    deadline = time.monotonic() + grace
    signaled = set()
    while True:
        members = owned_members(record)
        if not members:
            record_path(run_id).unlink(missing_ok=True)
            return
        forced = time.monotonic() >= deadline
        targets = members if forced else [item for item in members if item["pid"] not in signaled]
        record["members"] = members
        signal_members(targets, signal.SIGKILL if forced else signal.SIGTERM)
        signaled.update(item["pid"] for item in targets)
        if time.monotonic() > deadline + 3:
            raise RuntimeError(f"Processes remain for run {run_id}; ownership record retained")
        time.sleep(POLL_SECONDS)


def _write_record(path: Path, record: RunRecord) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(record, stream)
    temporary.replace(path)


def supervise(command: list[str], grace: float = GRACE_SECONDS) -> int:
    if os.name != "posix":
        raise RuntimeError("Local process supervision requires macOS or Linux")
    parent = os.getppid()
    parent_owner = psutil.Process(parent).ppid()
    os.setsid()
    group = os.getpid()
    run_id = str(uuid4())
    path = record_path(run_id)
    record = RunRecord(run_id=run_id, uid=os.getuid(), group=group,
                       cwd=os.getcwd(), members=[identity(psutil.Process())])
    requested_signal = 0

    def request_stop(signum: int, _frame: Optional[FrameType]) -> None:
        nonlocal requested_signal
        requested_signal = signum

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, request_stop)
    _write_record(path, record)
    print(f"local_run_id={run_id}", flush=True)
    child = None
    try:
        if not requested_signal:
            child = subprocess.Popen(command)
        while child is not None and child.poll() is None and not requested_signal:
            record["members"] = owned_members(record)
            _write_record(path, record)
            try:
                parent_lost = os.getppid() != parent or psutil.Process(parent).ppid() != parent_owner
            except psutil.NoSuchProcess:
                parent_lost = True
            if parent_lost:
                requested_signal = signal.SIGTERM
                break
            time.sleep(POLL_SECONDS)
        result = child.poll() if child is not None else None
    finally:
        deadline = time.monotonic() + grace
        signaled = set()
        registry_error = None
        while True:
            record["members"] = owned_members(record)
            try:
                _write_record(path, record)
            except OSError as error:
                registry_error = error
            remaining = [item for item in record["members"] if item["pid"] != group]
            if not remaining:
                break
            forced = time.monotonic() >= deadline
            targets = remaining if forced else [item for item in remaining if item["pid"] not in signaled]
            signal_members(targets, signal.SIGKILL if forced else signal.SIGTERM)
            signaled.update(item["pid"] for item in targets)
            if time.monotonic() > deadline + 3:
                raise RuntimeError(f"Processes remain for run {run_id}; ownership record retained")
            if child is not None:
                child.poll()
            time.sleep(POLL_SECONDS)
        if child is not None:
            child.wait()
        path.unlink(missing_ok=True)
        if registry_error is not None:
            raise registry_error
    if requested_signal:
        return 130 if requested_signal == signal.SIGINT else 128 + requested_signal
    return result if result is not None and result >= 0 else 128 - (result or 0)


def follow_log(path: Path) -> None:
    parent = os.getppid()
    stopping = False

    def request_stop(_signum: int, _frame: Optional[FrameType]) -> None:
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, request_stop)
    with path.open(encoding="utf-8", errors="replace") as stream:
        while True:
            line = stream.readline()
            if line:
                if not line.startswith("SAS_VALIDATION_RESULT "):
                    print(line, end="", flush=True)
            else:
                if stopping or os.getppid() != parent:
                    return
                time.sleep(POLL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "tail"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.arguments or (args.mode == "tail" and len(args.arguments) != 1):
        parser.error("run requires a command; tail requires one log path")
    try:
        if args.mode == "tail":
            follow_log(Path(args.arguments[0]))
            return 0
        return supervise(args.arguments)
    except (OSError, ValueError, RuntimeError, psutil.Error) as error:
        print(f"Local process supervision failed: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
