import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from core.task_queue_cleanup import (
    CleanupBackupError,
    CleanupDriftError,
    CleanupExecutionError,
)
from scripts import clear_task_queue as cli

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_JSON_KEYS = {
    "backup_path",
    "deleted_jobs",
    "deleted_markers",
    "dry_run",
    "error_code",
    "marker_keys",
    "mode",
    "protected_jobs",
    "redis_db",
    "remaining_queue_jobs",
    "selected_jobs",
    "status",
}


class FakeRedisClient:
    def __init__(self, *, queue_size=2, ping_error=None):
        self.queue_size = queue_size
        self.ping_error = ping_error

    def ping(self):
        if self.ping_error:
            raise self.ping_error
        return True

    def zcard(self, key):
        assert key in {"arq:queue", b"arq:queue"}
        return self.queue_size


def _plan(*, selected=(b"job-1",), protected=(b"job-2",)):
    return SimpleNamespace(
        all_pending=False,
        include_in_progress=False,
        selected_job_ids=selected,
        protected_job_ids=protected,
        marker_items=((b"task:running:task-1", b"job-1"),) if selected else (),
        marker_keys=(b"task:running:task-1",) if selected else (),
    )


@pytest.fixture
def cli_dependencies(monkeypatch):
    redis_client = FakeRedisClient()
    redis_factory = Mock(return_value=redis_client)
    build_plan = Mock(return_value=_plan())
    create_backup = Mock(return_value=Path("/tmp/backup.json"))
    apply_plan = Mock(
        return_value=SimpleNamespace(
            deleted_job_count=1,
            deleted_marker_count=1,
            remaining_queue_jobs=1,
        )
    )
    monkeypatch.setattr(cli, "build_cleanup_plan", build_plan)
    monkeypatch.setattr(cli, "create_cleanup_backup", create_backup)
    monkeypatch.setattr(cli, "apply_cleanup_plan", apply_plan)
    monkeypatch.setattr(
        cli,
        "REDIS_CONFIG",
        {
            "host": "redis.internal",
            "port": 6379,
            "password": "secret",
            "database": 7,
        },
    )
    return SimpleNamespace(
        redis_client=redis_client,
        redis_factory=redis_factory,
        build_plan=build_plan,
        create_backup=create_backup,
        apply_plan=apply_plan,
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--include-in-progress", "--apply"],
        ["--include-in-progress", "--worker-stopped"],
        ["--include-in-progress"],
    ],
)
def test_include_in_progress_requires_apply_and_worker_confirmation(
    argv, capsys,
):
    redis_factory = Mock(
        side_effect=AssertionError("must validate before Redis")
    )

    assert cli.run(argv, redis_factory=redis_factory) == 2

    assert "include-in-progress" in capsys.readouterr().err
    redis_factory.assert_not_called()


def test_default_cli_is_dry_run_and_does_not_create_backup(
    cli_dependencies, capsys,
):
    dependencies = cli_dependencies

    assert cli.run([], redis_factory=dependencies.redis_factory) == 0

    output = capsys.readouterr().out
    assert "DRY-RUN" in output
    assert "job-1" in output
    dependencies.create_backup.assert_not_called()
    dependencies.apply_plan.assert_not_called()


def test_apply_creates_backup_before_cleanup(cli_dependencies, capsys):
    dependencies = cli_dependencies
    call_order = []
    dependencies.create_backup.side_effect = lambda *args, **kwargs: (
        call_order.append("backup") or Path("/tmp/backup.json")
    )
    dependencies.apply_plan.side_effect = lambda *args, **kwargs: (
        call_order.append("apply")
        or SimpleNamespace(
            deleted_job_count=1,
            deleted_marker_count=1,
            remaining_queue_jobs=1,
        )
    )

    assert cli.run(["--apply"], redis_factory=dependencies.redis_factory) == 0

    assert call_order == ["backup", "apply"]
    assert "/tmp/backup.json" in capsys.readouterr().out


def test_apply_with_no_targets_skips_backup_and_writes(cli_dependencies):
    dependencies = cli_dependencies
    dependencies.build_plan.return_value = _plan(selected=(), protected=())

    assert cli.run(["--apply"], redis_factory=dependencies.redis_factory) == 0

    dependencies.create_backup.assert_not_called()
    dependencies.apply_plan.assert_not_called()


def test_json_output_has_stable_safe_schema(cli_dependencies, capsys):
    dependencies = cli_dependencies

    assert cli.run(["--json"], redis_factory=dependencies.redis_factory) == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == EXPECTED_JSON_KEYS
    assert payload["dry_run"] is True
    assert payload["selected_jobs"] == ["job-1"]
    serialized = json.dumps(payload).lower()
    assert "password" not in serialized
    assert "secret" not in serialized


def test_redis_connection_failure_returns_three_without_secret(
    monkeypatch, capsys,
):
    redis_factory = Mock(
        return_value=FakeRedisClient(
            ping_error=RuntimeError("redis://:secret-value@redis.internal")
        )
    )
    monkeypatch.setattr(
        cli,
        "REDIS_CONFIG",
        {
            "host": "redis.internal",
            "port": 6379,
            "password": "secret-value",
            "database": 7,
        },
    )

    assert cli.run([], redis_factory=redis_factory) == 3

    output = capsys.readouterr().err
    assert "secret-value" not in output
    assert "REDIS_CONNECTION_FAILED" in output


def test_backup_failure_returns_four(cli_dependencies, monkeypatch, capsys):
    dependencies = cli_dependencies
    monkeypatch.setattr(
        cli,
        "create_cleanup_backup",
        Mock(side_effect=CleanupBackupError("disk contains secret")),
    )

    assert cli.run(["--apply"], redis_factory=dependencies.redis_factory) == 4

    assert "BACKUP_FAILED" in capsys.readouterr().err


def test_drift_returns_five(cli_dependencies, monkeypatch, capsys):
    dependencies = cli_dependencies
    monkeypatch.setattr(
        cli,
        "apply_cleanup_plan",
        Mock(side_effect=CleanupDriftError("changed")),
    )

    assert cli.run(["--apply"], redis_factory=dependencies.redis_factory) == 5

    assert "STATE_DRIFT" in capsys.readouterr().err


def test_transaction_failure_returns_six(
    cli_dependencies, monkeypatch, capsys
):
    dependencies = cli_dependencies
    monkeypatch.setattr(
        cli,
        "apply_cleanup_plan",
        Mock(side_effect=CleanupExecutionError("secret payload")),
    )

    assert cli.run(["--apply"], redis_factory=dependencies.redis_factory) == 6

    output = capsys.readouterr().err
    assert "TRANSACTION_FAILED" in output
    assert "secret payload" not in output


def test_absolute_script_path_can_import_core():
    result = subprocess.run(
        [
            sys.executable,
            str(STARGAZER_ROOT / "scripts" / "clear_task_queue.py"),
            "--help",
        ],
        cwd="/",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Stargazer" in result.stdout
