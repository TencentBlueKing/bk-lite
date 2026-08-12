import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
STARTUP_SCRIPT = REPOSITORY_ROOT / "server/support-files/release/startup.sh"


def _run_startup(tmp_path, migrate_returncode):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"

    python_stub = fake_bin / "python3"
    python_stub.write_text(
        """#!/bin/bash
printf 'python3:%s\\n' "$*" >> "$COMMAND_LOG"
if [ "$*" = "manage.py migrate" ]; then
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
            "INSTALL_APPS": "opspilot",
            "MIGRATE_RETURNCODE": str(migrate_returncode),
            "PATH": f"{fake_bin}:{env['PATH']}",
        }
    )
    result = subprocess.run(
        ["bash", str(STARTUP_SCRIPT)],
        cwd=REPOSITORY_ROOT / "server",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    commands = command_log.read_text().splitlines()
    return result, commands


def test_release_startup_stops_when_migration_fails(tmp_path):
    result, commands = _run_startup(tmp_path, migrate_returncode=42)

    assert result.returncode != 0
    assert "数据库迁移失败，停止启动" in result.stdout
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
