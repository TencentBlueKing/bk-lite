from datetime import timedelta

import pytest
from django.utils import timezone

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

pytestmark = pytest.mark.django_db


def _config(*, auto_collect_enabled=True):
    return NodeMgmtSyncConfig.objects.create(
        auto_sync_enabled=True, auto_collect_enabled=auto_collect_enabled, schedule_status="healthy", node_config_status="healthy",
    )


def _collect_task(region_id, **overrides):
    payload = {
        "name": f"区域采集-{region_id}",
        "task_type": "host",
        "driver_type": "job",
        "model_id": "host",
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "scan_cycle": "*/30 * * * *",
        "instances": [],
        "access_point": [{"id": f"ap-{region_id}"}],
        "credential": [],
        "params": {},
        "team": [],
        "is_interval": True,
        "is_system": True,
        "is_visible": False,
        "system_code": f"{NodeMgmtSyncService.SYSTEM_TASK_PREFIX}{region_id}",
    }
    payload.update(overrides)
    return CollectModels.objects.create(**payload)


def test_collect_display_aggregates_region_results_into_one_stable_payload():
    config = _config()
    earlier = timezone.now() - timedelta(minutes=5)
    first = _collect_task(
        7,
        format_data={"add": [{"model_id": "host", "inst_name": "host-7", "ip_addr": "10.0.0.7"}]},
        collect_digest={"all": 1, "add": 1, "add_success": 1, "last_time": "2026-07-27T01:00:00+00:00"},
        exec_status=CollectRunStatusType.SUCCESS,
        exec_time=earlier,
    )
    latest = _collect_task(
        8,
        format_data={"update": [{"model_id": "host", "inst_name": "host-8", "ip_addr": "10.0.0.8"}]},
        collect_digest={"all": 1, "update": 1, "update_success": 1, "last_time": "2026-07-27T02:00:00+00:00"},
        exec_status=CollectRunStatusType.PARTIAL_SUCCESS,
        exec_time=timezone.now(),
    )
    CollectModels.objects.filter(pk=first.pk).update(updated_at=earlier)

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == NodeMgmtSyncService.DISPLAY_SOURCE_COLLECT
    assert payload["display_schema"] == "host_collect"
    assert payload["task"]["id"] == config.pk
    assert payload["message"] == payload["summary"]
    assert payload["message"]["all"] == 2
    assert payload["message"]["add_success"] == 1
    assert payload["message"]["update_success"] == 1
    assert payload["message"]["last_time"] == "2026-07-27 02:00:00+0000"
    assert payload["detail"]["add"]["count"] == 1
    assert payload["detail"]["update"]["count"] == 1
    assert payload["detail"]["raw_data"]["count"] == 2
    assert payload["run"]["id"] == latest.pk
    assert payload["run"]["status"] == "partial_success"


def test_collect_display_preserves_process_identity_and_failure_reason():
    _config()
    _collect_task(
        7,
        format_data={
            "__raw_data__": [
                {
                    "__name__": "host_proc_usage_info_gauge",
                    "name": "next-server",
                    "pid": "2171",
                    "ip": "10.10.24.11",
                    "collect_status": "failed",
                    "cmdb_collect_error": "permission denied",
                }
            ]
        },
        exec_status=CollectRunStatusType.ERROR,
    )

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["detail"]["raw_data"]["count"] == 1
    row = payload["detail"]["raw_data"]["data"][0]
    assert row["model_id"] == "host_proc_usage"
    assert row["pid"] == "2171"
    assert row["_status"] == "failed"
    assert row["_error"] == "permission denied"


def test_collect_display_redacts_credentials_from_process_text_fields():
    _config()
    _collect_task(
        7,
        format_data={
            "__raw_data__": [
                {
                    "__name__": "host_proc_usage_info_gauge",
                    "name": "next-server",
                    "pid": "2171",
                    "ip": "10.10.24.11",
                    "arg": "next-server --password hunter2 --token=raw-token",
                    "cmdb_collect_error": "Authorization: Bearer raw-bearer",
                }
            ]
        },
        exec_status=CollectRunStatusType.ERROR,
    )

    row = NodeMgmtSyncService.get_display_payload()["detail"]["raw_data"]["data"][0]

    serialized = str(row)
    assert "hunter2" not in serialized
    assert "raw-token" not in serialized
    assert "raw-bearer" not in serialized
    assert "[REDACTED]" in serialized


def test_collect_display_reports_partial_success_when_any_region_failed():
    _config()
    _collect_task(
        7,
        format_data={"__raw_data__": [{"__name__": "host_info_gauge", "ip": "10.0.0.7"}]},
        collect_digest={"all": 1, "message": "region 7 failed"},
        exec_status=CollectRunStatusType.ERROR,
        exec_time=timezone.now() - timedelta(minutes=5),
    )
    latest = _collect_task(
        8,
        format_data={"__raw_data__": [{"__name__": "host_info_gauge", "ip": "10.0.0.8"}]},
        collect_digest={"all": 1},
        exec_status=CollectRunStatusType.SUCCESS,
        exec_time=timezone.now(),
    )

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["run"]["id"] == latest.pk
    assert payload["run"]["status"] == NodeMgmtSyncRun.STATUS_PARTIAL_SUCCESS
    assert "region 7 failed" in payload["run"]["error_message"]


def test_collect_display_uses_latest_aware_metric_time_across_regions():
    _config()
    _collect_task(
        7,
        format_data={"__raw_data__": [{"__name__": "host_info_gauge", "ip": "10.0.0.7"}]},
        collect_digest={"all": 1, "last_time": "2026-07-27T10:00:00+08:00"},
        exec_status=CollectRunStatusType.SUCCESS,
    )
    _collect_task(
        8,
        format_data={"__raw_data__": [{"__name__": "host_info_gauge", "ip": "10.0.0.8"}]},
        collect_digest={"all": 1, "last_time": "2026-07-27T09:00:00+08:00"},
        exec_status=CollectRunStatusType.SUCCESS,
    )

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["message"]["last_time"] == "2026-07-27 02:00:00+0000"


def test_collect_display_keeps_previous_complete_batch_while_new_run_is_active():
    config = _config()
    completed = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        snapshot_schema_version=2,
        snapshot_status="complete",
        expected_region_count=1,
        finished_at=timezone.now() - timedelta(minutes=5),
        summary_json={"all": 1, "raw_total": 1, "raw_host": 1},
        detail_json={
            "raw_data": {
                "data": [{"_row_key": "previous-host", "model_id": "host", "ip": "10.0.0.7"}],
                "count": 1,
            }
        },
    )
    NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
        status=NodeMgmtSyncRun.STATUS_SUBMITTED,
        active_scope=NodeMgmtSyncService.ACTIVE_SCOPE,
        deadline_at=timezone.now() + timedelta(minutes=10),
    )
    _collect_task(
        7,
        format_data={"__raw_data__": [{"__name__": "host_info_gauge", "ip": "10.0.0.99"}]},
        collect_digest={"all": 1},
        exec_status=CollectRunStatusType.RUNNING,
    )

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_schema"] == "host_collect_v2"
    assert payload["run"]["id"] == completed.pk
    assert payload["detail"]["raw_data"]["data"][0]["ip"] == "10.0.0.7"


def test_legacy_collect_instances_are_whitelisted_and_clear_stale_empty_message():
    _config()
    task = _collect_task(
        7,
        instances=[
            {
                "id": "node-7",
                "name": "legacy-host",
                "ip": "10.0.0.7",
                "password": "never-return-this",
                "token": "never-return-this-either",
                "credential": {"username": "root"},
                "private_key": "never-return-this-key",
                "unknown_extra": "never-return-this-extra",
            },
            "invalid-row",
        ],
        collect_digest={"message": "未发现数据"},
        exec_status=CollectRunStatusType.SUCCESS,
    )

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["message"]["all"] == 1
    assert payload["message"]["message"] == ""
    assert payload["detail"]["raw_data"]["count"] == 1
    row = payload["detail"]["raw_data"]["data"][0]
    assert row["model_id"] == "host"
    assert row["inst_name"] == "legacy-host"
    assert row["ip_addr"] == "10.0.0.7"
    assert row["_status"] == "success"
    assert set(row) == {
        "id",
        "model_id",
        "inst_name",
        "name",
        "ip_addr",
        "ip",
        "cloud_name",
        "_status",
        "_error",
    }
    assert payload["run"]["id"] == task.pk


def test_collect_display_falls_back_to_latest_persisted_run_then_empty_state():
    config = _config()
    run = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
        status=NodeMgmtSyncRun.STATUS_BLOCKED,
        reason_code="NO_ACCESS_POINT",
        summary_json={"message": "没有接入点"},
        detail_json={"todo": [{"reason_code": "NO_ACCESS_POINT"}]},
    )

    persisted = NodeMgmtSyncService.get_display_payload()

    assert persisted["display_source"] == NodeMgmtSyncService.DISPLAY_SOURCE_COLLECT
    assert persisted["run"]["id"] == run.pk
    assert persisted["run"]["reason_code"] == "NO_ACCESS_POINT"
    assert persisted["detail"]["todo"] == [{"reason_code": "NO_ACCESS_POINT"}]

    run.delete()
    empty = NodeMgmtSyncService.get_display_payload()

    assert empty["display_source"] == NodeMgmtSyncService.DISPLAY_SOURCE_COLLECT
    assert empty["run"]["id"] is None
    assert empty["message"]["all"] == 0
    assert empty["detail"]["raw_data"]["count"] == 0


def test_unexecuted_collect_task_falls_back_to_latest_successful_sync():
    config = _config()
    sync_run = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        summary_json={"all": 1, "update": 1, "update_success": 1},
        detail_json={
            "update": {
                "data": [{"id": "host-1", "inst_name": "host-1", "ip_addr": "10.0.0.1"}],
                "count": 1,
            },
            "raw_data": {
                "data": [{"id": "host-1", "inst_name": "host-1", "ip_addr": "10.0.0.1"}],
                "count": 1,
            },
        },
    )
    _collect_task(
        1,
        instances=[{"id": "host-1", "name": "host-1", "ip": "10.0.0.1"}],
        exec_status=CollectRunStatusType.NOT_START,
    )

    payload = NodeMgmtSyncService.get_display_payload()

    assert payload["display_source"] == NodeMgmtSyncService.DISPLAY_SOURCE_SYNC_FALLBACK
    assert payload["run"]["id"] == sync_run.pk
    assert payload["run"]["status"] == NodeMgmtSyncRun.STATUS_SUCCESS
    assert payload["message"]["update"] == 1
    assert payload["detail"]["update"]["count"] == 1


def test_disabled_collect_uses_latest_sync_result_without_reenabling_switch():
    config = _config(auto_collect_enabled=False)
    sync_run = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_SYNC,
        status=NodeMgmtSyncRun.STATUS_SUCCESS,
        summary_json={"all": 1, "add_count": 1},
        detail_json={"add": [{"id": "host-1", "ip_addr": "10.0.0.1"}]},
    )

    payload = NodeMgmtSyncService.get_display_payload()

    config.refresh_from_db()
    assert config.auto_collect_enabled is False
    assert payload["task"]["auto_collect_enabled"] is False
    assert payload["display_source"] == NodeMgmtSyncService.DISPLAY_SOURCE_SYNC
    assert payload["run"]["id"] == sync_run.pk
    assert payload["message"]["add"] == 1
    assert payload["detail"]["raw_data"]["count"] == 1
