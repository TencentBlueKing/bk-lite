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


def _labelled_container_ids(
    instance_id: str,
    timeout: float,
) -> tuple[list[str], str]:
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
    except OSError as exc:
        return [], f"docker ps failed: {exc}"
    except subprocess.TimeoutExpired:
        return [], "docker ps timed out"
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        return [], f"docker ps failed: {detail}"
    return [value for value in result.stdout.splitlines() if value], ""


def _rollback(
    cid_file: Path,
    instance_id: str,
    timeout_seconds: float,
) -> tuple[bool, str, list[str]]:
    deadline = time.monotonic() + timeout_seconds
    container_ids: set[str] = set()
    last_error = ""
    successful_label_query = False

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
        labelled_ids, query_error = _labelled_container_ids(
            instance_id,
            min(0.5, remaining),
        )
        if query_error:
            last_error = query_error
        else:
            successful_label_query = True
            last_error = ""
            container_ids.update(labelled_ids)

        if container_ids:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                result = subprocess.run(
                    ["docker", "rm", "-f", *sorted(container_ids)],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=min(0.5, remaining),
                )
                if result.returncode == 0:
                    return True, "", sorted(container_ids)
                detail = result.stderr.strip() or f"exit code {result.returncode}"
                last_error = f"docker rm failed: {detail}"
            except OSError as exc:
                last_error = f"docker rm failed: {exc}"
            except subprocess.TimeoutExpired:
                last_error = "docker rm timed out"

        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(POLL_INTERVAL_SECONDS, remaining))

    if not container_ids and successful_label_query and not last_error:
        return True, "", []
    return (
        False,
        last_error or "startup container cleanup deadline exhausted",
        sorted(container_ids),
    )


def main() -> int:
    if len(sys.argv) != 9:
        return 2

    parent_pid = int(sys.argv[1])
    cid_file = Path(sys.argv[2])
    instance_id = sys.argv[3]
    commit_file = Path(sys.argv[4])
    handled_file = Path(sys.argv[5])
    failure_file = Path(sys.argv[6])
    ready_file = Path(sys.argv[7])
    timeout_seconds = float(sys.argv[8])

    # Detach before telling the launcher we are ready. webhookd terminates the
    # launcher process group with SIGKILL at its hard timeout; this watcher must
    # survive that signal long enough to perform the bounded rollback.
    os.setsid()
    ready_file.touch()
    cleanup_succeeded = True
    try:
        while _parent_exists(parent_pid):
            if commit_file.exists() or handled_file.exists():
                return 0
            time.sleep(POLL_INTERVAL_SECONDS)

        if not commit_file.exists() and not handled_file.exists():
            cleanup_succeeded, error, container_ids = _rollback(
                cid_file,
                instance_id,
                timeout_seconds,
            )
            if not cleanup_succeeded:
                if container_ids:
                    cid_file.write_text(
                        "\n".join(container_ids) + "\n",
                        encoding="utf-8",
                    )
                container_detail = ",".join(container_ids) or "unknown"
                message = (
                    "startup cleanup failed for "
                    f"instance {instance_id}; containers={container_detail}: {error}\n"
                )
                failure_file.write_text(message, encoding="utf-8")
                print(message, file=sys.stderr, end="")
                return 1
        return 0
    finally:
        cleanup_paths = [commit_file, handled_file, ready_file]
        if cleanup_succeeded:
            cleanup_paths.extend([cid_file, failure_file])
        for path in cleanup_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
