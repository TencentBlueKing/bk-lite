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
        collect_digest={"all": 1, "add": 1, "add_success": 1, "last_time": "first"},
        exec_status=CollectRunStatusType.SUCCESS,
        exec_time=earlier,
    )
    latest = _collect_task(
        8,
        format_data={"update": [{"model_id": "host", "inst_name": "host-8", "ip_addr": "10.0.0.8"}]},
        collect_digest={"all": 1, "update": 1, "update_success": 1, "last_time": "latest"},
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
    assert payload["message"]["last_time"] == "latest"
    assert payload["detail"]["add"]["count"] == 1
    assert payload["detail"]["update"]["count"] == 1
    assert payload["detail"]["raw_data"]["count"] == 2
    assert payload["run"]["id"] == latest.pk
    assert payload["run"]["status"] == "partial_success"


def test_legacy_collect_instances_are_whitelisted_and_clear_stale_empty_message():
    _config()
    task = _collect_task(
        7,
        instances=[
            {"id": "node-7", "name": "legacy-host", "ip": "10.0.0.7", "password": "never-return-this", "token": "never-return-this-either"},
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
    assert "password" not in row
    assert "token" not in row
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
