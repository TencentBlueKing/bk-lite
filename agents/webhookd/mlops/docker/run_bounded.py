#!/usr/bin/env python3
"""Run one child process with a wall-clock limit and kill its process group."""

from __future__ import annotations

import os
import signal
import subprocess
import sys


TIMEOUT_EXIT_CODE = 124


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


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

    process = subprocess.Popen(sys.argv[2:], start_new_session=True)

    def forward_signal(signum: int, _frame: object) -> None:
        _terminate_process_group(process)
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, forward_signal)

    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return TIMEOUT_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
