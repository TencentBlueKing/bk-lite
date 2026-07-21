from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from redis import Redis  # noqa: E402

from core.redis_config import REDIS_CONFIG  # noqa: E402
from core.task_queue_cleanup import (  # noqa: E402
    QUEUE_KEY,
    CleanupBackupError,
    CleanupDriftError,
    CleanupExecutionError,
    CleanupStateError,
    apply_cleanup_plan,
    build_cleanup_plan,
    create_cleanup_backup,
)


DEFAULT_BACKUP_DIR = Path("/tmp/stargazer-task-queue-backups")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely inspect or clear the Stargazer ARQ task queue.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the cleanup plan; default is read-only dry-run",
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="select every safe pending job in arq:queue",
    )
    parser.add_argument(
        "--include-in-progress",
        action="store_true",
        help="include related in-progress jobs after all workers are stopped",
    )
    parser.add_argument(
        "--worker-stopped",
        action="store_true",
        help="confirm all Stargazer workers were stopped externally",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"backup directory (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit stable JSON output",
    )
    return parser


def _decode_identifier(value: bytes) -> str:
    return value.decode(errors="backslashreplace")


def _result_payload(args, plan, *, redis_db: int, remaining_queue_jobs: int) -> dict:
    return {
        "backup_path": None,
        "deleted_jobs": 0,
        "deleted_markers": 0,
        "dry_run": not args.apply,
        "error_code": None,
        "marker_keys": [_decode_identifier(key) for key in plan.marker_keys],
        "mode": "all_pending" if args.all_pending else "blocking",
        "protected_jobs": [
            _decode_identifier(job_id) for job_id in plan.protected_job_ids
        ],
        "redis_db": redis_db,
        "remaining_queue_jobs": remaining_queue_jobs,
        "selected_jobs": [
            _decode_identifier(job_id) for job_id in plan.selected_job_ids
        ],
        "status": "dry_run" if not args.apply else "completed",
    }


def _error_payload(args, *, redis_db: int, error_code: str) -> dict:
    return {
        "backup_path": None,
        "deleted_jobs": 0,
        "deleted_markers": 0,
        "dry_run": not args.apply,
        "error_code": error_code,
        "marker_keys": [],
        "mode": "all_pending" if args.all_pending else "blocking",
        "protected_jobs": [],
        "redis_db": redis_db,
        "remaining_queue_jobs": None,
        "selected_jobs": [],
        "status": "error",
    }


def _emit(payload: dict, *, as_json: bool, error: bool = False) -> None:
    output = sys.stderr if error else sys.stdout
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=output)
        return

    if error:
        print(f"ERROR [{payload['error_code']}] operation stopped safely", file=output)
        return

    print(f"Mode: {payload['mode']}", file=output)
    print(f"Redis DB: {payload['redis_db']}", file=output)
    print(f"Selected jobs: {len(payload['selected_jobs'])}", file=output)
    for job_id in payload["selected_jobs"]:
        print(f"  - {job_id}", file=output)
    print(f"Protected jobs: {len(payload['protected_jobs'])}", file=output)
    if payload["dry_run"]:
        print("DRY-RUN: no Redis data was modified", file=output)
    elif payload["status"] == "no_targets":
        print("No matching jobs; no Redis data was modified", file=output)
    else:
        print(f"Backup: {payload['backup_path']}", file=output)
        print(f"Deleted jobs: {payload['deleted_jobs']}", file=output)
        print(f"Deleted markers: {payload['deleted_markers']}", file=output)
        print(f"Remaining queued jobs: {payload['remaining_queue_jobs']}", file=output)


def _emit_error(args, *, redis_db: int, error_code: str) -> None:
    _emit(
        _error_payload(args, redis_db=redis_db, error_code=error_code),
        as_json=args.json,
        error=True,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    redis_factory=Redis,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    redis_db = int(REDIS_CONFIG["database"])

    if args.include_in_progress and not (args.apply and args.worker_stopped):
        print(
            "ERROR [INVALID_ARGUMENTS] --include-in-progress requires "
            "--worker-stopped and --apply",
            file=sys.stderr,
        )
        return 2

    try:
        redis_client = redis_factory(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            password=REDIS_CONFIG["password"],
            db=redis_db,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        redis_client.ping()
        plan = build_cleanup_plan(
            redis_client,
            all_pending=args.all_pending,
            include_in_progress=args.include_in_progress,
        )
        remaining_queue_jobs = int(redis_client.zcard(QUEUE_KEY))
    except CleanupStateError:
        _emit_error(args, redis_db=redis_db, error_code="QUEUE_STATE_INVALID")
        return 3
    except Exception:
        _emit_error(args, redis_db=redis_db, error_code="REDIS_CONNECTION_FAILED")
        return 3

    payload = _result_payload(
        args,
        plan,
        redis_db=redis_db,
        remaining_queue_jobs=remaining_queue_jobs,
    )
    if not args.apply:
        _emit(payload, as_json=args.json)
        return 0

    if not plan.selected_job_ids:
        payload["status"] = "no_targets"
        _emit(payload, as_json=args.json)
        return 0

    try:
        backup_path = create_cleanup_backup(
            redis_client,
            plan,
            backup_dir=args.backup_dir,
            redis_db=redis_db,
        )
    except CleanupBackupError:
        _emit_error(args, redis_db=redis_db, error_code="BACKUP_FAILED")
        return 4

    try:
        result = apply_cleanup_plan(redis_client, plan)
    except CleanupDriftError:
        _emit_error(args, redis_db=redis_db, error_code="STATE_DRIFT")
        return 5
    except CleanupExecutionError:
        _emit_error(args, redis_db=redis_db, error_code="TRANSACTION_FAILED")
        return 6

    payload.update(
        {
            "backup_path": str(backup_path),
            "deleted_jobs": result.deleted_job_count,
            "deleted_markers": result.deleted_marker_count,
            "remaining_queue_jobs": result.remaining_queue_jobs,
            "status": "completed",
        }
    )
    _emit(payload, as_json=args.json)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
