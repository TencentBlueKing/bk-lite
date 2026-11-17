"""附件清理调度器必须在休眠、退出和异常前清理本线程连接。"""

import importlib.util
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from django.apps.registry import Apps
from django.db import connections, models


class Catalog(models.Model):
    oid = models.IntegerField(primary_key=True)

    class Meta:
        apps = Apps()
        app_label = "artifact_scheduler_tests"
        managed = False
        db_table = "pg_class"


@pytest.fixture
def scheduler(monkeypatch):
    # 只替换清理服务依赖，验证真实命令循环；实际删除语义由 test_artifacts 覆盖。
    with monkeypatch.context() as imports:
        service = ModuleType("apps.workflow.services.artifacts")
        service.cleanup_expired_artifacts = Mock(return_value={"selected": 0, "deleted": 0, "failed": 0})
        imports.setitem(sys.modules, service.__name__, service)
        path = Path(__file__).parents[1] / "management" / "commands" / "run_workflow_artifact_cleanup_scheduler.py"
        spec = importlib.util.spec_from_file_location("artifact_scheduler_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module.time = SimpleNamespace(sleep=Mock(side_effect=KeyboardInterrupt))
    return module


@pytest.mark.parametrize("outcome", [None, ValueError("failed"), KeyboardInterrupt()])
def test_iteration_cleans_connections_without_changing_outcome(scheduler, monkeypatch, outcome):
    events = []
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: events.append("cleanup"), raising=False)

    def cleanup(*, batch_size):
        assert batch_size == 25
        events.append("run")
        if outcome is not None:
            raise outcome
        return {"selected": 1, "deleted": 1, "failed": 0}

    scheduler.cleanup_expired_artifacts.side_effect = cleanup
    output = StringIO()
    command = scheduler.Command(stdout=output)
    if outcome is None:
        command.handle(once=True, interval=3600, batch_size=25)
        assert output.getvalue() == "artifact cleanup: selected=1 deleted=1 failed=0\n"
    else:
        with pytest.raises(type(outcome)) as raised:
            command.handle(once=False, interval=3600, batch_size=25)
        assert raised.value is outcome
    assert events == ["cleanup", "run", "cleanup"]
    scheduler.time.sleep.assert_not_called()


@pytest.mark.integration
@pytest.mark.parametrize("once", [True, False])
def test_pg_connection_closed_before_sleep_or_once_exit(scheduler, monkeypatch, django_db_blocker, once):
    if connections["default"].vendor != "postgresql":
        pytest.skip("需要 PostgreSQL 验证连接生命周期")
    alias = "artifact_scheduler_test"
    db = connections["default"].copy(alias=alias)
    db.settings_dict["CONN_MAX_AGE"] = 0
    monkeypatch.setitem(connections.settings, alias, db.settings_dict)
    connections[alias] = db
    drivers = []
    sleeps = []

    def cleanup(*, batch_size):
        assert batch_size == 25
        assert Catalog.objects.using(alias).exists()
        drivers.append(db.connection)
        return {"selected": 0, "deleted": 0, "failed": 0}

    def sleep(interval):
        assert interval == 3600
        # 线程仍存活时检查，不能靠进程退出或 GC 掩盖未关闭连接。
        assert db.connection is None
        assert drivers[-1].closed
        sleeps.append(interval)
        if len(sleeps) == 3:
            raise KeyboardInterrupt

    scheduler.cleanup_expired_artifacts.side_effect = cleanup
    scheduler.time.sleep.side_effect = sleep
    with django_db_blocker.unblock():
        try:
            if once:
                scheduler.Command().handle(once=True, interval=3600, batch_size=25)
            else:
                with pytest.raises(KeyboardInterrupt):
                    scheduler.Command().handle(once=False, interval=3600, batch_size=25)
            assert db.connection is None
            assert len(drivers) == (1 if once else 3)
            assert all(driver.closed for driver in drivers)
        finally:
            db.close()
            del connections[alias]
