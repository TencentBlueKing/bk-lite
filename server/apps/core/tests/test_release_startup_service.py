import os
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
STARTUP_SCRIPT = REPOSITORY_ROOT / "server/support-files/release/startup.sh"
pytestmark = pytest.mark.integration


def _run_startup(tmp_path, migrate_returncode, install_apps="opspilot", strict_mode=False):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    command_log = tmp_path / "commands.log"

    python_stub = fake_bin / "python3"
    python_stub.write_text(
        """#!/bin/bash
printf 'python3:%s\\n' "$*" >> "$COMMAND_LOG"
if [ "$*" = "manage.py migrate" ]; then
    if [ "$MIGRATE_RETURNCODE" -ne 0 ]; then
        echo "migration failed: schema conflict" >&2
    fi
    exit "$MIGRATE_RETURNCODE"
fi
exit 0
"""
    )
    python_stub.chmod(0o755)

    supervisor_stub = fake_bin / "supervisord"
    supervisor_stub.write_text(
        """#!/bin/bash
printf 'supervisord:%s\\n' "$*" >> "$COMMAND_LOG"
exit 0
"""
    )
    supervisor_stub.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "COMMAND_LOG": str(command_log),
            "INSTALL_APPS": install_apps,
            "MIGRATE_RETURNCODE": str(migrate_returncode),
            "PATH": f"{fake_bin}:{env['PATH']}",
        }
    )
    bash_command = ["bash"]
    if strict_mode:
        bash_command.append("-e")
    result = subprocess.run(
        [*bash_command, str(STARTUP_SCRIPT)],
        cwd=REPOSITORY_ROOT / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    commands = command_log.read_text().splitlines()
    return result, commands


def test_release_startup_stops_when_migration_fails(tmp_path):
    result, commands = _run_startup(tmp_path, migrate_returncode=42, strict_mode=True)

    assert result.returncode == 42
    assert "migration failed: schema conflict" in result.stderr
    assert "数据库迁移失败，停止启动" in result.stderr
    assert commands == ["python3:manage.py migrate"]


def test_release_startup_keeps_existing_success_path(tmp_path):
    result, commands = _run_startup(tmp_path, migrate_returncode=0)

    assert result.returncode == 0
    assert commands == [
        "python3:manage.py migrate",
        "python3:manage.py createcachetable django_cache",
        "python3:manage.py collectstatic --noinput",
        "python3:manage.py batch_init --apps=opspilot",
        "supervisord:-n",
    ]


def test_release_startup_supports_empty_install_apps_on_first_start(tmp_path):
    result, commands = _run_startup(tmp_path, migrate_returncode=0, install_apps="")

    assert result.returncode == 0
    assert "python3:manage.py batch_init --apps=" in commands
    assert commands[-1] == "supervisord:-n"


def test_release_startup_recovers_after_migration_is_fixed(tmp_path):
    failed, commands = _run_startup(tmp_path, migrate_returncode=42)
    recovered, commands_after_recovery = _run_startup(tmp_path, migrate_returncode=0)

    assert failed.returncode == 42
    assert recovered.returncode == 0
    assert commands_after_recovery[: len(commands)] == commands
    assert commands_after_recovery[-1] == "supervisord:-n"


def test_release_startup_is_repeatable_with_existing_state(tmp_path):
    first, first_commands = _run_startup(tmp_path, migrate_returncode=0)
    second, all_commands = _run_startup(tmp_path, migrate_returncode=0)

    assert first.returncode == 0
    assert second.returncode == 0
    assert all_commands == first_commands * 2


def test_release_startup_does_not_continue_after_existing_state_migration_conflict(tmp_path):
    succeeded, existing_commands = _run_startup(tmp_path, migrate_returncode=0)
    failed, all_commands = _run_startup(tmp_path, migrate_returncode=42)

    assert succeeded.returncode == 0
    assert failed.returncode == 42
    assert all_commands == [*existing_commands, "python3:manage.py migrate"]
