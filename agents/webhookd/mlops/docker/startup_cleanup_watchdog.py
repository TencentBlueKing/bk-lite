#!/usr/bin/env python3
"""Rollback uncommitted serving containers if the launcher is killed."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


POLL_INTERVAL_SECONDS = 0.05


def _parent_exists(parent_pid: int) -> bool:
    try:
        os.kill(parent_pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_container_id(cid_file: Path) -> str:
    try:
        return cid_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _labelled_container_ids(instance_id: str, timeout: float) -> list[str]:
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=bk-lite.startup-id={instance_id}",
                "--no-trunc",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [value for value in result.stdout.splitlines() if value]


def _rollback(cid_file: Path, instance_id: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    container_ids: set[str] = set()

    # docker run may be killed while dockerd is still committing the container.
    # Retry the label lookup briefly so that the parent-death path does not race
    # the daemon-side create operation.
    while time.monotonic() < deadline:
        container_id = _read_container_id(cid_file)
        if container_id:
            container_ids.add(container_id)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        container_ids.update(
            _labelled_container_ids(instance_id, min(0.5, remaining))
        )
        if container_ids:
            break
        time.sleep(min(POLL_INTERVAL_SECONDS, max(0.0, remaining)))

    remaining = deadline - time.monotonic()
    if not container_ids or remaining <= 0:
        return
    try:
        subprocess.run(
            ["docker", "rm", "-f", *sorted(container_ids)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=remaining,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def main() -> int:
    if len(sys.argv) != 8:
        return 2

    parent_pid = int(sys.argv[1])
    cid_file = Path(sys.argv[2])
    instance_id = sys.argv[3]
    commit_file = Path(sys.argv[4])
    handled_file = Path(sys.argv[5])
    ready_file = Path(sys.argv[6])
    timeout_seconds = float(sys.argv[7])

    # Detach before telling the launcher we are ready. webhookd terminates the
    # launcher process group with SIGKILL at its hard timeout; this watcher must
    # survive that signal long enough to perform the bounded rollback.
    os.setsid()
    ready_file.touch()
    try:
        while _parent_exists(parent_pid):
            if commit_file.exists() or handled_file.exists():
                return 0
            time.sleep(POLL_INTERVAL_SECONDS)

        if not commit_file.exists() and not handled_file.exists():
            _rollback(cid_file, instance_id, timeout_seconds)
        return 0
    finally:
        for path in (cid_file, commit_file, handled_file, ready_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
