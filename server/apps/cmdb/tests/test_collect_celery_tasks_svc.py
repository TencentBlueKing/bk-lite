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
from datetime import timedelta

import pydantic.root_model  # noqa: F401
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
    text = "\n".join(["Traceback (most recent call last):", '  File "a.py", line 1, in <module>', '  File "b.py", line 2, in run', "KeyError: 0",])
    excerpt = ct._build_traceback_excerpt(text, max_lines=2)
    assert excerpt == '  File "b.py", line 2, in run\nKeyError: 0'


def test_build_traceback_location_returns_last_file_frame():
    text = "\n".join(["Traceback (most recent call last):", '  File "a.py", line 1, in <module>', '  File "b.py", line 2, in run', "KeyError: 0",])
    assert ct._build_traceback_location(text) == 'File "b.py", line 2, in run'


# --------------------------------------------------------------------------
# sync_periodic_update_task_status
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_periodic_update使用任务deadline写入超时终态():
    started_at = now() - timedelta(seconds=31)
    task = CollectModels.objects.create(
        name="deadline-30",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=started_at,
        task_id="execution-30",
        params={"task_job_timeout": 30},
        team=[1],
    )

    ct.sync_periodic_update_task_status()

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.TIME_OUT
    assert task.execution_claim_token is None
    assert task.collect_digest["execution_id"] == "execution-30"
    assert task.collect_digest["deadline_seconds"] == 30
    assert task.collect_digest["started_at"] == started_at.isoformat()


@pytest.mark.django_db
def test_sync_periodic_update默认600秒而非固定5分钟(monkeypatch):
    monkeypatch.setenv("TASK_JOB_TIMEOUT", "600")
    five_minutes = CollectModels.objects.create(
        name="five-minutes",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=now() - timedelta(minutes=5),
        task_id="execution-fresh",
        team=[1],
    )
    expired = CollectModels.objects.create(
        name="expired-601",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=now() - timedelta(seconds=601),
        task_id="execution-expired",
        team=[1],
    )

    ct.sync_periodic_update_task_status()

    five_minutes.refresh_from_db()
    expired.refresh_from_db()
    assert five_minutes.exec_status == CollectRunStatusType.RUNNING
    assert expired.exec_status == CollectRunStatusType.TIME_OUT


@pytest.mark.django_db
def test_timeout条件写回不能覆盖新execution():
    task = CollectModels.objects.create(
        name="timeout-stale",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=now() - timedelta(seconds=31),
        task_id="execution-A",
        params={"task_job_timeout": 30},
        team=[1],
    )
    stale_snapshot = CollectModels.objects.get(id=task.id)
    CollectModels.objects.filter(id=task.id).update(task_id="execution-B")

    updated = ct._timeout_collect_task_if_current(stale_snapshot, now())

    task.refresh_from_db()
    assert updated is False
    assert task.task_id == "execution-B"
    assert task.exec_status == CollectRunStatusType.RUNNING


@pytest.mark.django_db
def test_timeout条件写回校验owner并清理claim_token():
    task = CollectModels.objects.create(
        name="timeout-owner-fence",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=now() - timedelta(seconds=31),
        task_id="execution-A",
        execution_claim_token="owner-A",
        params={"task_job_timeout": 30},
        team=[1],
    )
    stale_owner = CollectModels.objects.get(id=task.id)
    CollectModels.objects.filter(id=task.id).update(execution_claim_token="owner-B")

    assert ct._timeout_collect_task_if_current(stale_owner, now()) is False

    current_owner = CollectModels.objects.get(id=task.id)
    assert ct._timeout_collect_task_if_current(current_owner, now()) is True
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.TIME_OUT
    assert task.execution_claim_token is None


@pytest.mark.django_db
def test_periodic_recovery_clears_force_stopped_execution_claim():
    task = CollectModels.objects.create(
        name="force-stop-claim-cleanup",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        exec_status=CollectRunStatusType.FORCE_STOP,
        task_id="execution-stopped",
        execution_claim_token="execution-stopped:owner",
        team=[1],
    )

    ct.sync_periodic_update_task_status()

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.FORCE_STOP
    assert task.execution_claim_token is None


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
        "apps.cmdb.display_field.DisplayFieldSynchronizer.sync_all", staticmethod(lambda data: {"organizations": 3, "users": 1}),
    )
    out = ct.sync_cmdb_display_fields_task({"organizations": [{"id": 1, "name": "x"}], "users": []})
    assert out["result"] is True
    assert out["data"] == {"organizations": 3, "users": 1}


def test_sync_cmdb_display_fields_failure(monkeypatch):
    def _boom(data):
        raise RuntimeError("sync failed")

    monkeypatch.setattr("apps.cmdb.display_field.DisplayFieldSynchronizer.sync_all", staticmethod(_boom))
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
        "apps.cmdb.services.collect_tool_service.CollectToolService.build_error_result", staticmethod(lambda **kw: {"error": kw["summary"]}),
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
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.recover_stale_runs",
        staticmethod(lambda: calls.append("recover")),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.trigger_sync",
        staticmethod(lambda: calls.append("sync") or {"synced": 5}),
    )
    assert ct.sync_node_mgmt_hosts() == {"synced": 5}
    assert calls == ["recover", "sync"]


def test_sync_node_mgmt_hosts_propagates_error(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.recover_stale_runs",
        staticmethod(lambda: calls.append("recover")),
    )

    def raise_sync_error():
        calls.append("sync")
        raise RuntimeError("sync err")

    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.trigger_sync",
        staticmethod(raise_sync_error),
    )
    with pytest.raises(RuntimeError, match="sync err"):
        ct.sync_node_mgmt_hosts()
    assert calls == ["recover", "sync"]


def test_collect_node_mgmt_hosts_delegates(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.recover_stale_runs",
        staticmethod(lambda: calls.append("recover")),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.refresh_submitted_collect_runs",
        staticmethod(lambda: calls.append("refresh")),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.node_mgmt_sync_service.NodeMgmtSyncService.trigger_collect",
        staticmethod(lambda: calls.append("collect")),
    )
    ct.collect_node_mgmt_hosts()
    assert calls == ["recover", "refresh", "collect"]


# --------------------------------------------------------------------------
# daily_data_cleanup_task
# --------------------------------------------------------------------------
def test_daily_data_cleanup_task_delegates(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.data_cleanup_service.DataCleanupService.run_daily_cleanup", staticmethod(lambda: {"deleted": 12}),
    )
    assert ct.daily_data_cleanup_task() == {"deleted": 12}


# --------------------------------------------------------------------------
# sync_collect_task：未发现有效数据 → ERROR
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_collect_task_no_data_marks_error(monkeypatch):
    task = CollectModels.objects.create(
        name="empty-collect",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch", staticmethod(lambda inst: False),
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
        name="running-collect",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.RUNNING,
        collect_digest={"message": "keep-running"},
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot", lambda instance: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch",
        staticmethod(lambda inst: (_ for _ in ()).throw(AssertionError("dispatch decision should not run"))),
    )
    monkeypatch.setattr(
        ct, "ProtocolCollect", lambda task: (_ for _ in ()).throw(AssertionError("protocol collect should not run")),
    )
    monkeypatch.setattr(
        ct, "JobCollect", lambda task: (_ for _ in ()).throw(AssertionError("job collect should not run")),
    )

    ct.sync_collect_task(task.id)

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_digest == {"message": "keep-running"}


@pytest.mark.django_db
def test_claim_collect_task_execution_only_one_runner_can_acquire(monkeypatch):
    task = CollectModels.objects.create(
        name="claim-once",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.NOT_START,
    )
    start_time = now()

    first = ct._claim_collect_task_execution(task.id, start_time)
    second = ct._claim_collect_task_execution(task.id, start_time)

    assert first is not None
    assert first.exec_status == CollectRunStatusType.RUNNING
    assert first.task_id
    assert second is None

    preclaimed = CollectModels.objects.create(
        name="claim-token",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.NOT_START,
    )
    assert ct._claim_collect_task_execution(preclaimed.id, start_time, execution_id="owner-token") is not None
    assert ct._claim_collect_task_execution(preclaimed.id, start_time, execution_id="other-token") is None
    assert ct._claim_collect_task_execution(preclaimed.id, start_time, execution_id="owner-token") is None


@pytest.mark.django_db
def test_same_execution_id_duplicate_delivery_cannot_acquire_or_execute(monkeypatch):
    task = CollectModels.objects.create(
        name="same-execution-delivery-once",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.RUNNING,
        task_id="execution-A",
        collect_digest={},
    )
    first = ct._claim_collect_task_execution(task.id, now(), execution_id="execution-A")
    second = ct._claim_collect_task_execution(task.id, now(), execution_id="execution-A")

    assert first is not None
    assert first.claim_token
    assert first.claim_token.startswith("execution-A:")
    assert first.collect_digest == {}
    assert second is None

    monkeypatch.setattr(
        ct, "ProtocolCollect", lambda task: (_ for _ in ()).throw(AssertionError("duplicate delivery must not execute")),
    )
    ct.sync_collect_task(task.id, execution_id="execution-A")


@pytest.mark.django_db
def test_beat_request_id_deduplicates_redelivery_and_allows_next_period(monkeypatch):
    task = CollectModels.objects.create(
        name="beat-periodic-execution",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
    )
    executions = []
    monkeypatch.setattr(ct.CollectDispatchService, "should_dispatch", staticmethod(lambda instance: False))
    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot", lambda instance: None,
    )

    class FakeCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            executions.append(self.task.task_id)
            return {"execution_id": self.task.task_id}, {
                "add": [],
                "update": [],
                "delete": [],
                "association": [],
                "__raw_data__": [{"__time__": "2026-07-17T00:00:00Z"}],
            }

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)

    ct.sync_collect_task.apply(args=[task.id], task_id="beat-delivery-1", throw=True)
    ct.sync_collect_task.apply(args=[task.id], task_id="beat-delivery-1", throw=True)

    task.refresh_from_db()
    assert executions == ["beat-delivery-1"]
    assert task.task_id == "beat-delivery-1"
    assert task.exec_status == CollectRunStatusType.SUCCESS
    assert task.execution_claim_token is None

    ct.sync_collect_task.apply(args=[task.id], task_id="beat-delivery-2", throw=True)

    task.refresh_from_db()
    assert executions == ["beat-delivery-1", "beat-delivery-2"]
    assert task.task_id == "beat-delivery-2"
    assert task.exec_status == CollectRunStatusType.SUCCESS
    assert task.execution_claim_token is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal_status",
    [CollectRunStatusType.SUCCESS, CollectRunStatusType.ERROR, CollectRunStatusType.FORCE_STOP],
)
def test_delayed_duplicate_delivery_cannot_reopen_terminal_execution(monkeypatch, terminal_status):
    task = CollectModels.objects.create(
        name=f"terminal-delivery-{terminal_status}",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=terminal_status,
        task_id="execution-terminal",
        collect_digest={"message": "terminal"},
    )
    monkeypatch.setattr(
        ct, "ProtocolCollect", lambda task: (_ for _ in ()).throw(AssertionError("terminal delivery must not execute")),
    )

    ct.sync_collect_task(task.id, execution_id="execution-terminal")

    task.refresh_from_db()
    assert task.exec_status == terminal_status
    assert task.task_id == "execution-terminal"
    assert task.collect_digest == {"message": "terminal"}


@pytest.mark.django_db
def test_new_execution_id_can_acquire_not_started_task():
    task = CollectModels.objects.create(
        name="new-execution-can-start",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.NOT_START,
    )

    claimed = ct._claim_collect_task_execution(task.id, now(), execution_id="execution-new")

    assert claimed is not None
    assert claimed.task_id == "execution-new"
    assert claimed.claim_token


@pytest.mark.django_db
def test_newly_queued_execution_can_replace_stale_claim_from_previous_execution():
    task = CollectModels.objects.create(
        name="replace-stale-claim",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.RUNNING,
        task_id="execution-new",
        execution_claim_token="execution-old:stale-owner",
        collect_digest={},
    )

    claimed = ct._claim_collect_task_execution(task.id, now(), execution_id="execution-new")

    assert claimed is not None
    assert claimed.claim_token.startswith("execution-new:")


@pytest.mark.django_db
def test_collect_result_requires_current_execution_owner():
    task = CollectModels.objects.create(
        name="execution-owner-fence",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        exec_status=CollectRunStatusType.NOT_START,
    )
    owner_a = ct._claim_collect_task_execution(task.id, now(), execution_id="execution-A")
    CollectModels.objects.filter(id=task.id).update(
        exec_status=CollectRunStatusType.NOT_START,
        task_id="",
        execution_claim_token=None,
    )
    owner_b = ct._claim_collect_task_execution(task.id, now(), execution_id="execution-B")

    assert not ct._save_collect_result_if_current(
        task.id,
        "execution-A",
        owner_a.claim_token,
        {"exec_status": CollectRunStatusType.SUCCESS, "collect_digest": {"owner": "A"}},
    )
    assert ct._save_collect_result_if_current(
        task.id,
        "execution-B",
        owner_b.claim_token,
        {"exec_status": CollectRunStatusType.SUCCESS, "collect_digest": {"owner": "B"}},
    )

    task.refresh_from_db()
    assert task.task_id == "execution-B"
    assert task.exec_status == CollectRunStatusType.SUCCESS
    assert task.collect_digest == {"owner": "B"}
    assert task.execution_claim_token is None


@pytest.mark.django_db
def test_sync_collect_task_handles_collect_exception(monkeypatch):
    task = CollectModels.objects.create(
        name="boom-collect",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch", staticmethod(lambda inst: False),
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
def test_repair_snapshot_exception_closes_owned_execution_and_same_delivery_does_not_rerun(monkeypatch):
    task = CollectModels.objects.create(
        name="repair-snapshot-error",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="job",
        cycle_value_type="cycle",
        team=[1],
    )
    repair_calls = []

    def broken_repair(instance):
        repair_calls.append(instance.task_id)
        raise RuntimeError("repair snapshot exploded")

    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot",
        broken_repair,
    )
    monkeypatch.setattr(
        ct.CollectDispatchService,
        "should_dispatch",
        staticmethod(lambda instance: (_ for _ in ()).throw(AssertionError("collection must not start"))),
    )

    ct.sync_collect_task(task.id, execution_id="execution-repair")
    ct.sync_collect_task(task.id, execution_id="execution-repair")

    task.refresh_from_db()
    assert repair_calls == ["execution-repair"]
    assert task.task_id == "execution-repair"
    assert task.exec_status == CollectRunStatusType.ERROR
    assert task.execution_claim_token is None
    assert "repair snapshot exploded" in task.collect_digest["message"]
    assert "RuntimeError: repair snapshot exploded" in task.collect_digest["traceback"]


@pytest.mark.django_db
def test_sync_collect_task_handles_numeric_exception_with_traceback(monkeypatch):
    task = CollectModels.objects.create(
        name="numeric-collect",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch", staticmethod(lambda inst: False),
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


@pytest.mark.django_db
def test_sync_collect_task旧worker成功不能覆盖新execution(monkeypatch):
    task = CollectModels.objects.create(
        name="stale-success",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(ct.CollectDispatchService, "should_dispatch", staticmethod(lambda inst: False))
    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot", lambda instance: None,
    )

    class FakeCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            CollectModels.objects.filter(id=self.task.id).update(
                task_id="execution-B",
                exec_status=CollectRunStatusType.RUNNING,
                collect_data={"owner": "B"},
                format_data={"owner": "B"},
                collect_digest={"owner": "B"},
            )
            return {"owner": "A"}, {"add": [], "update": [], "delete": [], "association": [], "__raw_data__": [{"__time__": "2026-07-13T00:00:00Z"}],}

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)

    ct.sync_collect_task(task.id, execution_id="execution-A")

    task.refresh_from_db()
    assert task.task_id == "execution-B"
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_data == {"owner": "B"}
    assert task.format_data == {"owner": "B"}
    assert task.collect_digest == {"owner": "B"}


@pytest.mark.django_db
def test_sync_collect_task旧worker异常不能覆盖新execution(monkeypatch):
    task = CollectModels.objects.create(
        name="stale-error",
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    )
    monkeypatch.setattr(ct.CollectDispatchService, "should_dispatch", staticmethod(lambda inst: False))
    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot", lambda instance: None,
    )

    class FakeCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            CollectModels.objects.filter(id=self.task.id).update(
                task_id="execution-B", exec_status=CollectRunStatusType.RUNNING, collect_digest={"owner": "B"},
            )
            raise RuntimeError("late A failed")

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)

    ct.sync_collect_task(task.id, execution_id="execution-A")

    task.refresh_from_db()
    assert task.task_id == "execution-B"
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_digest == {"owner": "B"}


@pytest.mark.django_db
def test_config_file_pending不能覆盖同execution回调终态(monkeypatch):
    task = CollectModels.objects.create(
        name="config-callback-wins",
        task_type=CollectPluginTypes.CONFIG_FILE,
        model_id="host",
        driver_type="job",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "i1", "model_id": "host", "inst_name": "host1"}],
    )
    monkeypatch.setattr(ct.CollectDispatchService, "should_dispatch", staticmethod(lambda inst: False))
    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot", lambda instance: None,
    )

    class FakeCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            CollectModels.objects.filter(id=self.task.id).update(
                exec_status=CollectRunStatusType.SUCCESS, collect_data={"owner": "callback"}, collect_digest={"owner": "callback"},
            )
            return {"config_file": {"status": "pending"}}, {"add": [], "update": [], "delete": [], "association": [], "__raw_data__": [],}

    monkeypatch.setattr(ct, "JobCollect", FakeCollect)

    ct.sync_collect_task(task.id, execution_id="execution-A")

    task.refresh_from_db()
    assert task.task_id == "execution-A"
    assert task.exec_status == CollectRunStatusType.SUCCESS
    assert task.collect_data == {"owner": "callback"}
    assert task.collect_digest == {"owner": "callback"}
    assert task.execution_claim_token is None
