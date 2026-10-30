"""验证 CLI 边界、只读报告与部署预检的实际返回行为。"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from celery import Celery
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.celery_runtime import launcher
from apps.core.celery_runtime.config import POOL_IMPLEMENTATION
from apps.core.celery_runtime.routing import configure_routes
from apps.core.management.commands import celery_prefork_check, celery_routes, celery_runtime_report
from apps.core.tests.test_celery_runtime_pure import runtime_env


def configure_env(monkeypatch):
    monkeypatch.delenv("CELERY_CONCURRENCY", raising=False)
    for key, value in runtime_env().items():
        monkeypatch.setenv(key, value)


def test_launcher_atomically_generates_configuration_and_checks(monkeypatch, tmp_path, capsys):
    configure_env(monkeypatch)
    target = tmp_path / "celery.conf"
    target.write_text("old")
    monkeypatch.setattr("sys.argv", ["launcher", "--supervisor", str(target)])
    launcher.main()
    assert target.read_text().count("[program:") == 5
    assert list(tmp_path.iterdir()) == [target]
    monkeypatch.setattr("sys.argv", ["launcher", "--check"])
    launcher.main()
    assert "最大并发=7" in capsys.readouterr().out


def test_launcher_rejects_bad_config_without_replacing_file(monkeypatch, tmp_path):
    configure_env(monkeypatch)
    monkeypatch.setenv("CELERY_STATE_MAX", "0")
    target = tmp_path / "celery.conf"
    target.write_text("old")
    monkeypatch.setattr("sys.argv", ["launcher", "--supervisor", str(target)])
    with pytest.raises(SystemExit):
        launcher.main()
    assert target.read_text() == "old"


def test_launcher_reads_dotenv_like_django_without_overriding_exported_values(tmp_path):
    root = Path(__file__).resolve().parents[3]
    values = runtime_env(CELERY_CRITICAL_MAX="3", CELERY_TOTAL_CONCURRENCY_LIMIT="8")
    (tmp_path / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()))
    env = {key: value for key, value in os.environ.items() if not key.startswith(("CELERY_", "ENABLE_CELERY", "AUTOSCALE_"))}
    env.update(PYTHONPATH=str(root), CELERY_CRITICAL_MAX="2")
    result = subprocess.run(
        [sys.executable, "-m", "apps.core.celery_runtime.launcher", "--check"], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "执行池数=4" in result.stdout
    assert "最大并发=7" in result.stdout


def test_worker_launcher_preflights_before_exec(monkeypatch):
    configure_env(monkeypatch)
    monkeypatch.setattr("sys.argv", ["launcher", "--worker", "critical"])
    preflight = Mock()
    execute = Mock()
    monkeypatch.setattr(launcher, "check_prefork", preflight)
    monkeypatch.setattr(launcher.os, "execv", execute)
    launcher.main()
    preflight.assert_called_once()
    assert "--autoscale=2,1" in execute.call_args.args[1]


def test_prefork_command_blocks_wrong_pool_and_handles_disabled(settings, monkeypatch):
    settings.IS_USE_CELERY = False
    app = SimpleNamespace(loader=Mock(), tasks={}, conf=SimpleNamespace(worker_pool=POOL_IMPLEMENTATION))
    monkeypatch.setattr(celery_prefork_check, "current_app", app)
    call_command(celery_prefork_check.Command(), stdout=io.StringIO())
    app.loader.import_default_modules.assert_not_called()
    settings.IS_USE_CELERY = True
    monkeypatch.setattr(celery_prefork_check, "prefork_issues", lambda _: [{"setting": "worker_pool", "required": POOL_IMPLEMENTATION}])
    with pytest.raises(CommandError):
        call_command(celery_prefork_check.Command(), stdout=io.StringIO())


@pytest.mark.django_db
def test_readonly_report_has_effective_routes_and_strict_failure(monkeypatch):
    configure_env(monkeypatch)
    app = Celery("report_test", broker="memory://", set_as_current=False, fixups=[])
    configure_routes(app)
    monkeypatch.setattr(app.loader, "import_default_modules", lambda: None)
    monkeypatch.setattr(celery_runtime_report, "current_app", app)
    output = io.StringIO()
    call_command(celery_runtime_report.Command(), stdout=output)
    report = json.loads(output.getvalue())
    assert report["config"]["total_limit"] == 7
    assert "broker_url" not in report
    monkeypatch.setattr(celery_runtime_report, "worker_report", lambda _: {"workers": {}, "queue_consumers": {}, "unavailable": ["stats"]})
    with pytest.raises(CommandError, match="未通过"):
        call_command(celery_runtime_report.Command(), workers=True, strict=True, stdout=io.StringIO())

    def scan_probe():
        return None

    app.task(name="apps.monitor.tasks.monitor_policy.scan_policy_task", shared=False)(scan_probe)
    workers = {}
    for pool in ("critical", "notification", "state", "background"):
        workers[f"{pool}@test"] = {
            "capacity": {"min": 1, "max": 1 if pool == "background" else 2},
            "queues": ["background", "celery"] if pool == "background" else [pool],
            "registered": [],
            "pool_implementation": POOL_IMPLEMENTATION,
        }
    monkeypatch.setattr(
        celery_runtime_report,
        "worker_report",
        lambda _: {
            "workers": workers,
            "queue_consumers": dict.fromkeys(["critical", "notification", "state", "background", "celery"], 1),
            "unavailable": [],
        },
    )
    output = io.StringIO()
    with pytest.raises(CommandError):
        call_command(celery_runtime_report.Command(), workers=True, strict=True, stdout=output)
    assert "worker 注册集缺少该池目标任务" in output.getvalue()
    with pytest.raises(CommandError, match="timeout"):
        call_command(celery_runtime_report.Command(), timeout=0, stdout=io.StringIO())
    app.close()


def test_route_command_preserves_safe_error_output(monkeypatch):
    monkeypatch.setattr(celery_routes, "restore_routes", Mock(side_effect=ValueError("secret detail")))
    with pytest.raises(CommandError) as error:
        call_command(celery_routes.Command(), restore="snapshot.json", stdout=io.StringIO())
    assert "secret" not in str(error.value)
    monkeypatch.setattr(celery_routes, "restore_routes", lambda *args, **kwargs: [])
    output = io.StringIO()
    call_command(celery_routes.Command(), restore="snapshot.json", stdout=output)
    assert json.loads(output.getvalue())["applied"] is False
