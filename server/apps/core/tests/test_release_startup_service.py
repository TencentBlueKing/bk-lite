import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
STARTUP_SCRIPT = REPOSITORY_ROOT / "server/support-files/release/startup.sh"
pytestmark = pytest.mark.integration


def _bash_executable() -> str | None:
    found = shutil.which("bash")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _bash_path(path: Path) -> str:
    resolved = str(path.resolve())
    if len(resolved) >= 2 and resolved[1] == ":":
        return "/" + resolved[0].lower() + resolved[2:].replace("\\", "/")
    return resolved.replace("\\", "/")


def _supervisor_conf_dir(tmp_path):
    supervisor_conf_dir = tmp_path / "supervisor"
    supervisor_conf_dir.mkdir(parents=True, exist_ok=True)
    (supervisor_conf_dir / "consumer.conf").write_text("[program:consumer]\n", encoding="utf-8")
    (supervisor_conf_dir / "opspilot_celery.conf").write_text("[program:opspilot_celery]\n", encoding="utf-8")
    (supervisor_conf_dir / "celery.conf").write_text("[program:celery]\n", encoding="utf-8")
    return supervisor_conf_dir


def _run_startup(tmp_path, migrate_returncode, install_apps="opspilot", strict_mode=False):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    command_log = tmp_path / "commands.log"
    supervisor_conf_dir = _supervisor_conf_dir(tmp_path)

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
            "COMMAND_LOG": _bash_path(command_log),
            "INSTALL_APPS": install_apps,
            "MIGRATE_RETURNCODE": str(migrate_returncode),
            "SUPERVISOR_CONF_DIR": _bash_path(supervisor_conf_dir),
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
        }
    )
    bash_executable = _bash_executable()
    if bash_executable is None:
        pytest.skip("bash is required to execute startup.sh")
    bash_command = [bash_executable]
    if strict_mode:
        bash_command.append("-e")
    result = subprocess.run(
        [*bash_command, str(STARTUP_SCRIPT)],
        cwd=REPOSITORY_ROOT / "server",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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


RELEASE_DIR = REPOSITORY_ROOT / "server/support-files/release"


def test_opspilot_celery_worker_is_packaged_without_default_worker_exclude():
    dockerfile = (RELEASE_DIR / "Dockerfile").read_text(encoding="utf-8")
    celery_conf = (RELEASE_DIR / "supervisor/celery.conf").read_text(encoding="utf-8")
    opspilot_conf = (RELEASE_DIR / "supervisor/opspilot_celery.conf").read_text(encoding="utf-8")
    startup = STARTUP_SCRIPT.read_text(encoding="utf-8")

    assert "opspilot_celery.conf" in dockerfile
    assert "-X" not in celery_conf
    assert "opspilot_channel" not in celery_conf
    assert "-Q opspilot_channel,opspilot_wiki,opspilot_maintenance" in opspilot_conf
    assert 'rm -f "$SUPERVISOR_CONF_DIR/opspilot_celery.conf"' in startup
    assert "SUPERVISOR_CONF_DIR=${SUPERVISOR_CONF_DIR:-/etc/supervisor/conf.d}" in startup


def test_release_startup_removes_opspilot_celery_conf_when_opspilot_not_installed(tmp_path):
    result, commands = _run_startup(tmp_path, migrate_returncode=0, install_apps="system_mgmt,console_mgmt")
    conf_dir = tmp_path / "supervisor"

    assert result.returncode == 0
    assert commands[-1] == "supervisord:-n"
    assert "删除 opspilot 专用 supervisor 配置" in result.stdout
    assert not (conf_dir / "opspilot_celery.conf").exists()
    assert not (conf_dir / "consumer.conf").exists()
    assert (conf_dir / "celery.conf").exists()


def test_release_startup_keeps_opspilot_celery_conf_when_opspilot_installed(tmp_path):
    result, _commands = _run_startup(tmp_path, migrate_returncode=0, install_apps="system_mgmt,console_mgmt,opspilot")
    conf_dir = tmp_path / "supervisor"

    assert result.returncode == 0
    assert (conf_dir / "opspilot_celery.conf").exists()
    assert (conf_dir / "consumer.conf").exists()
    assert (conf_dir / "celery.conf").exists()


def test_release_startup_keeps_opspilot_celery_conf_when_install_apps_empty(tmp_path):
    result, _commands = _run_startup(tmp_path, migrate_returncode=0, install_apps="")
    conf_dir = tmp_path / "supervisor"

    assert result.returncode == 0
    assert (conf_dir / "opspilot_celery.conf").exists()
