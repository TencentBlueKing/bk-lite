#!/usr/bin/env python3
"""Run one child process with a wall-clock limit and kill its process group."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


TIMEOUT_EXIT_CODE = 124


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _signal_process_group(process_group_id: int, signum: int) -> None:
    try:
        os.killpg(process_group_id, signum)
    except ProcessLookupError:
        pass


def _terminate_process_group(
    process: subprocess.Popen[bytes],
    deadline: float,
) -> None:
    _signal_process_group(process.pid, signal.SIGTERM)

    while time.monotonic() < deadline and _process_group_exists(process.pid):
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    _signal_process_group(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=0.1)
    except subprocess.TimeoutExpired:
        pass


def _start_parent_death_watchdog(process_group_id: int) -> tuple[int, int]:
    """Kill the detached command group even if webhookd SIGKILLs this runner."""
    read_fd, write_fd = os.pipe()
    watchdog_pid = os.fork()
    if watchdog_pid == 0:
        try:
            os.close(write_fd)
            os.setsid()
            while os.read(read_fd, 1):
                pass
            _signal_process_group(process_group_id, signal.SIGKILL)
        finally:
            os._exit(0)

    os.close(read_fd)
    return watchdog_pid, write_fd


def _stop_parent_death_watchdog(watchdog_pid: int, write_fd: int) -> None:
    try:
        os.close(write_fd)
    except OSError:
        pass
    try:
        os.waitpid(watchdog_pid, 0)
    except ChildProcessError:
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

    # A dedicated command group lets the runner terminate all descendants. A
    # detached watchdog observes runner death and kills that group even when
    # webhookd uses SIGKILL, which cannot be handled by an EXIT/signal trap.
    process = subprocess.Popen(sys.argv[2:], start_new_session=True)
    watchdog_pid, watchdog_write_fd = _start_parent_death_watchdog(process.pid)
    deadline = time.monotonic() + timeout_seconds
    termination_grace = min(0.2, max(0.02, timeout_seconds * 0.1))
    command_deadline = deadline - termination_grace

    def forward_signal(signum: int, _frame: object) -> None:
        _terminate_process_group(process, time.monotonic() + termination_grace)
        _stop_parent_death_watchdog(watchdog_pid, watchdog_write_fd)
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, forward_signal)

    try:
        result = process.wait(timeout=max(0.0, command_deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        _terminate_process_group(process, deadline)
        result = TIMEOUT_EXIT_CODE

    _stop_parent_death_watchdog(watchdog_pid, watchdog_write_fd)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
