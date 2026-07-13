"""cmdb Celery 任务单元测试。

对照 apps/cmdb/tasks/celery_tasks.py：
  - _build_safe_error_message：多来源错误信息回退
  - sync_periodic_update_task_status：超时任务置失败（含 config_file 分流）
  - sync_collect_credential_results_task：NATS 化后的跳过返回
  - sync_cmdb_display_fields_task：成功/异常返回
  - execute_collect_tool_debug_task：成功/异常落库
  - reconcile / full_sync 任务委派服务层
  - sync_node_mgmt_hosts / collect_node_mgmt_hosts / daily_data_cleanup_task 委派
  - sync_collect_task 的「未发现有效数据 → ERROR」与异常分支

服务层 / 委派对象在真实边界打桩；任务对 DB 的真实读写副作用被断言。
"""
import pydantic.root_model  # noqa: F401

from datetime import timedelta

import pytest
from django.utils.timezone import now

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tasks import celery_tasks as ct


# --------------------------------------------------------------------------
# _build_safe_error_message
# --------------------------------------------------------------------------
def test_build_safe_error_message_prefers_str():
    assert ct._build_safe_error_message(ValueError("boom")) == "boom"


def test_build_safe_error_message_ignores_numeric_placeholder():
    assert ct._build_safe_error_message(Exception(0)) == "Exception(0)"


def test_build_safe_error_message_falls_back_to_message_attr():
    class E(Exception):
        message = "attr-msg"

        def __str__(self):
            return ""

    assert ct._build_safe_error_message(E()) == "attr-msg"


def test_build_safe_error_message_falls_back_to_detail():
    class E(Exception):
        detail = "detail-msg"

        def __str__(self):
            return ""

    assert ct._build_safe_error_message(E()) == "detail-msg"


def test_build_safe_error_message_falls_back_to_classname():
    class WeirdError(Exception):
        def __str__(self):
            return ""

    assert ct._build_safe_error_message(WeirdError()) == "WeirdError"


def test_build_traceback_excerpt_keeps_tail():
    text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "a.py", line 1, in <module>',
            '  File "b.py", line 2, in run',
            "KeyError: 0",
        ]
    )
    excerpt = ct._build_traceback_excerpt(text, max_lines=2)
    assert excerpt == '  File "b.py", line 2, in run\nKeyError: 0'


def test_build_traceback_location_returns_last_file_frame():
    text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "a.py", line 1, in <module>',
            '  File "b.py", line 2, in run',
            "KeyError: 0",
        ]
    )
    assert ct._build_traceback_location(text) == 'File "b.py", line 2, in run'


# --------------------------------------------------------------------------
# sync_periodic_update_task_status
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_periodic_update_marks_stale_running_failed():
    old_time = now() - timedelta(minutes=10)
    stale = CollectModels.objects.create(
        name="stale", task_type=CollectPluginTypes.HOST, model_id="host", cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING, exec_time=old_time, team=[1],
    )
    cfg = CollectModels.objects.create(
        name="stale-cfg", task_type=CollectPluginTypes.CONFIG_FILE, model_id="host", driver_type="job", cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING, exec_time=old_time, team=[1],
    )
    fresh = CollectModels.objects.create(
        name="fresh", task_type=CollectPluginTypes.HOST, model_id="host", driver_type="snmp", cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING, exec_time=now(), team=[1],
    )
    ct.sync_periodic_update_task_status()
    stale.refresh_from_db()
    cfg.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.exec_status == CollectRunStatusType.ERROR
    assert cfg.exec_status == CollectRunStatusType.ERROR
    assert "5 分钟" in cfg.collect_digest["message"]
    # 未超时的保持 RUNNING
    assert fresh.exec_status == CollectRunStatusType.RUNNING


# --------------------------------------------------------------------------
# sync_collect_credential_results_task
# --------------------------------------------------------------------------
def test_sync_collect_credential_results_task_skips():
    out = ct.sync_collect_credential_results_task()
    assert out["skipped"] is True
    assert out["result"] is True


# --------------------------------------------------------------------------
# sync_cmdb_display_fields_task
# --------------------------------------------------------------------------
def test_sync_cmdb_display_fields_success(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.display_field.DisplayFieldSynchronizer.sync_all",
        staticmethod(lambda data: {"organizations": 3, "users": 1}),
    )
    out = ct.sync_cmdb_display_fields_task({"organizations": [{"id": 1, "name": "x"}], "users": []})
    assert out["result"] is True
    assert out["data"] == {"organizations": 3, "users": 1}


def test_sync_cmdb_display_fields_failure(monkeypatch):
    def _boom(data):
        raise RuntimeError("sync failed")

    monkeypatch.setattr(
        "apps.cmdb.display_field.DisplayFieldSynchronizer.sync_all", staticmethod(_boom)
    )
    out = ct.sync_cmdb_display_fields_task({})
    assert out["result"] is False
    assert "sync failed" in out["message"]


# --------------------------------------------------------------------------
# execute_collect_tool_debug_task
# --------------------------------------------------------------------------
def test_execute_collect_tool_debug_task_success(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.collect_tool_service.CollectToolService.run_debug_task",
        staticmethod(lambda debug_id, payload, service_name, timeout: {"ok": True, "debug_id": debug_id}),
    )
    out = ct.execute_collect_tool_debug_task("d1", {"action": "run"}, "svc", 30)
    assert out["ok"] is True
    assert out["debug_id"] == "d1"


def test_execute_collect_tool_debug_task_failure_saves_error(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.collect_tool_service.CollectToolService.run_debug_task",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("debug boom"))),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_tool_service.CollectToolService.build_error_result",
        staticmethod(lambda **kw: {"error": kw["summary"]}),
    )
    saved = []
    monkeypatch.setattr(
        "apps.cmdb.services.collect_tool_service.CollectToolService.save_debug_state",
        staticmethod(lambda debug_id, state, result: saved.append((debug_id, state))),
    )
    out = ct.execute_collect_tool_debug_task("d2", {"action": "run"}, "svc", 30)
    assert "debug boom" in out["error"]
    assert saved == [("d2", "error")]


# --------------------------------------------------------------------------
# reconcile / full_sync delegation
# --------------------------------------------------------------------------
def test_reconcile_instance_task_delegates(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.AutoRelationRuleReconcileService.reconcile_for_instance",
        classmethod(lambda cls, iid: {"instance_id": iid, "ok": True}),
    )
    assert ct.reconcile_instance_auto_association_task(9) == {"instance_id": 9, "ok": True}


def test_full_sync_rule_task_delegates(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.AutoRelationRuleReconcileService.full_sync_rule",
        classmethod(lambda cls, mid: {"model_asst_id": mid, "ok": True}),
    )
    assert ct.full_sync_auto_association_rule_task("m1") == {"model_asst_id": "m1", "ok": True}


# --------------------------------------------------------------------------
# node mgmt sync delegation
# --------------------------------------------------------------------------
def test_sync_node_mgmt_hosts_delegates(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.trigger_sync",
        staticmethod(lambda: {"synced": 5}),
    )
    assert ct.sync_node_mgmt_hosts() == {"synced": 5}


def test_sync_node_mgmt_hosts_propagates_error(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.trigger_sync",
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("sync err"))),
    )
    with pytest.raises(RuntimeError, match="sync err"):
        ct.sync_node_mgmt_hosts()


def test_collect_node_mgmt_hosts_delegates(monkeypatch):
    called = []
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.trigger_collect",
        staticmethod(lambda: called.append(True)),
    )
    ct.collect_node_mgmt_hosts()
    assert called == [True]


# --------------------------------------------------------------------------
# daily_data_cleanup_task
# --------------------------------------------------------------------------
def test_daily_data_cleanup_task_delegates(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.data_cleanup_service.DataCleanupService.run_daily_cleanup",
        staticmethod(lambda: {"deleted": 12}),
    )
    assert ct.daily_data_cleanup_task() == {"deleted": 12}


# --------------------------------------------------------------------------
# sync_collect_task：未发现有效数据 → ERROR
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_collect_task_no_data_marks_error(monkeypatch):
    task = CollectModels.objects.create(
        name="empty-collect", task_type=CollectPluginTypes.PROTOCOL, model_id="mysql", driver_type="protocol",
        cycle_value_type="cycle", team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch",
        staticmethod(lambda inst: False),
    )

    class FakeCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            return {}, {"add": [], "update": [], "delete": [], "association": [], "__raw_data__": []}

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)
    ct.sync_collect_task(task.id)
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert "未发现任何有效数据" in task.collect_digest["message"]


@pytest.mark.django_db
def test_sync_collect_task_skips_when_task_is_already_running(monkeypatch):
    task = CollectModels.objects.create(
        name="running-collect", task_type=CollectPluginTypes.PROTOCOL, model_id="mysql", driver_type="protocol",
        cycle_value_type="cycle", team=[1],
        exec_status=CollectRunStatusType.RUNNING,
        collect_digest={"message": "keep-running"},
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot",
        lambda instance: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch",
        staticmethod(lambda inst: (_ for _ in ()).throw(AssertionError("dispatch decision should not run"))),
    )
    monkeypatch.setattr(
        ct,
        "ProtocolCollect",
        lambda task: (_ for _ in ()).throw(AssertionError("protocol collect should not run")),
    )
    monkeypatch.setattr(
        ct,
        "JobCollect",
        lambda task: (_ for _ in ()).throw(AssertionError("job collect should not run")),
    )

    ct.sync_collect_task(task.id)

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_digest == {"message": "keep-running"}


@pytest.mark.django_db
def test_claim_collect_task_execution_only_one_runner_can_acquire(monkeypatch):
    task = CollectModels.objects.create(
        name="claim-once", task_type=CollectPluginTypes.PROTOCOL, model_id="mysql", driver_type="protocol",
        cycle_value_type="cycle", team=[1],
        exec_status=CollectRunStatusType.NOT_START,
    )
    start_time = now()

    first = ct._claim_collect_task_execution(task.id, start_time)
    second = ct._claim_collect_task_execution(task.id, start_time)

    assert first is not None
    assert first.exec_status == CollectRunStatusType.RUNNING
    assert second is None

    preclaimed = CollectModels.objects.create(
        name="claim-token", task_type=CollectPluginTypes.PROTOCOL, model_id="mysql", driver_type="protocol",
        cycle_value_type="cycle", team=[1],
        exec_status=CollectRunStatusType.RUNNING,
        task_id="owner-token",
    )
    assert ct._claim_collect_task_execution(preclaimed.id, start_time, execution_id="other-token") is None
    token_owner = ct._claim_collect_task_execution(preclaimed.id, start_time, execution_id="owner-token")
    assert token_owner is not None
    assert token_owner.task_id == "owner-token"


@pytest.mark.django_db
def test_sync_collect_task_handles_collect_exception(monkeypatch):
    task = CollectModels.objects.create(
        name="boom-collect", task_type=CollectPluginTypes.PROTOCOL, model_id="mysql", driver_type="protocol",
        cycle_value_type="cycle", team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch",
        staticmethod(lambda inst: False),
    )

    class FakeCollect:
        def __init__(self, task):
            pass

        def main(self):
            raise RuntimeError("collect exploded")

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)
    ct.sync_collect_task(task.id)
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert "collect exploded" in task.collect_digest["message"]
    assert "RuntimeError: collect exploded" in task.collect_digest["traceback"]


@pytest.mark.django_db
def test_sync_collect_task_handles_numeric_exception_with_traceback(monkeypatch):
    task = CollectModels.objects.create(
        name="numeric-collect", task_type=CollectPluginTypes.PROTOCOL, model_id="mysql", driver_type="protocol",
        cycle_value_type="cycle", team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch",
        staticmethod(lambda inst: False),
    )

    class FakeCollect:
        def __init__(self, task):
            pass

        def main(self):
            raise Exception(0)

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)
    ct.sync_collect_task(task.id)
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert "Exception(0)" in task.collect_digest["message"]
    assert '@ File "' in task.collect_digest["message"]
    assert "Exception: 0" in task.collect_digest["traceback"]


@pytest.mark.django_db
def test_sync_collect_task_missing_instance_noop(monkeypatch):
    # 不存在的任务 id：早返回，不抛错
    ct.sync_collect_task(999999)
