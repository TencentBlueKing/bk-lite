#!/usr/bin/env python3
"""Run one child process with a wall-clock limit and kill its process group."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


TIMEOUT_EXIT_CODE = 124


def _descendant_pids(root_pid: int) -> list[int]:
    """Return descendants deepest-first without moving them out of the hook PG."""
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid=,ppid="],
            text=True,
            timeout=0.2,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    children: dict[int, list[int]] = {}
    for line in output.splitlines():
        try:
            pid_text, parent_text = line.split()
            children.setdefault(int(parent_text), []).append(int(pid_text))
        except (ValueError, TypeError):
            continue

    descendants: list[int] = []

    def visit(parent_pid: int) -> None:
        for child_pid in children.get(parent_pid, []):
            visit(child_pid)
            descendants.append(child_pid)

    visit(root_pid)
    return descendants


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _signal_tree(pids: list[int], signum: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, signum)
        except ProcessLookupError:
            pass


def _terminate_process_tree(
    process: subprocess.Popen[bytes],
    deadline: float,
) -> None:
    pids = _descendant_pids(process.pid) + [process.pid]
    _signal_tree(pids, signal.SIGTERM)

    while time.monotonic() < deadline and any(_is_alive(pid) for pid in pids):
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    _signal_tree([pid for pid in pids if _is_alive(pid)], signal.SIGKILL)
    try:
        process.wait(timeout=0.1)
    except subprocess.TimeoutExpired:
        pass


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: run_bounded.py <seconds> <command> [args...]", file=sys.stderr)
        return 2

    try:
        timeout_seconds = float(sys.argv[1])
    except ValueError:
        print("timeout must be a positive number", file=sys.stderr)
        return 2
    if timeout_seconds <= 0:
        return TIMEOUT_EXIT_CODE

    # Keep the command in webhookd's hook process group. If webhookd reaches its
    # outer hard timeout, one group kill must still cover the wrapper and child.
    process = subprocess.Popen(sys.argv[2:])
    deadline = time.monotonic() + timeout_seconds
    termination_grace = min(0.2, max(0.02, timeout_seconds * 0.1))
    command_deadline = deadline - termination_grace

    def forward_signal(signum: int, _frame: object) -> None:
        _terminate_process_tree(process, time.monotonic() + termination_grace)
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, forward_signal)

    try:
        return process.wait(timeout=max(0.0, command_deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process, deadline)
        return TIMEOUT_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
