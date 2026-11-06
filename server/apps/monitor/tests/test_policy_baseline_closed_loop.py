"""无数据基准闭环：长路径落库、缺数告警、新序列同步、数据恢复。

VictoriaMetrics 只替换查询结果。基准、扫描、告警和恢复走真实服务和数据库。
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.db import DataError, connection, transaction
from django.db.models import Max
from django.db.models.functions import Length

from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorInstance, MonitorObject, MonitorPolicy, PolicyInstanceBaseline
from apps.monitor.services.policy_baseline import PolicyBaselineService
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService
from apps.monitor.tasks.services.policy_scan.scanner import MonitorPolicyScan
from apps.monitor.utils.dimension import is_metric_instance_fingerprint, metric_instance_storage_key

pytestmark = [pytest.mark.django_db]

INSTANCE_COUNT = 40
SHORT_MOUNTS = ("/", "/boot", "/data")
GROUP_BY = ["instance_id", "mount", "path", "fstype"]


def _long_mount(index, suffix=""):
    return (
        "/var/lib/kubelet/pods/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        "/volumes/kubernetes.io~csi/pvc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        f"/mount/host-{index:04d}{suffix}"
    )


def _host_series(index, extra_mount=""):
    label = f"os_h{index:04d}"
    rows = [(label, mount, mount, "ext4") for mount in SHORT_MOUNTS]
    mount = _long_mount(index)
    rows.append((label, mount, mount, "overlay"))
    if extra_mount:
        rows.append((label, extra_mount, extra_mount, "xfs"))
    return str((label,)), rows


def _vm_payload(rows):
    result = []
    for instance_id, mount, path, fstype in rows:
        result.append(
            {
                "metric": {
                    "instance_id": instance_id,
                    "mount": mount,
                    "path": path,
                    "fstype": fstype,
                },
                "values": [[1_700_000_000, "1"]],
            }
        )
    return {"status": "success", "data": {"result": result}}


def test_long_disk_no_data_loop_uses_fingerprint_without_parsing_it():
    monitor_object = MonitorObject.objects.create(name="UTLoopHost", level="base", instance_id_keys=["instance_id"])
    monitor_ids = []
    instances = []
    initial_rows = []
    for index in range(INSTANCE_COUNT):
        monitor_instance_id, rows = _host_series(index)
        monitor_ids.append(monitor_instance_id)
        initial_rows.extend(rows)
        instances.append(MonitorInstance(id=monitor_instance_id, name=f"host-{index:04d}", monitor_object=monitor_object))
    MonitorInstance.objects.bulk_create(instances, batch_size=100)

    missing_monitor_id, missing_rows = _host_series(7)
    missing_tuple = missing_rows[-1]
    missing_key = metric_instance_storage_key(missing_tuple)
    assert len(str(missing_tuple)) > MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
    assert is_metric_instance_fingerprint(missing_key)

    extra_mount = _long_mount(7, "-new")
    extra_tuple = ("os_h0007", extra_mount, extra_mount, "xfs")
    extra_key = metric_instance_storage_key(extra_tuple)
    assert is_metric_instance_fingerprint(extra_key)
    assert extra_key != missing_key

    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="ut-loop-policy",
        algorithm="max",
        source={"type": "instance", "values": monitor_ids},
        group_by=GROUP_BY,
        period={"type": "min", "value": 5},
        query_condition={"type": "pmq", "query": "disk_used_percent", "instance_id_keys": ["instance_id"]},
        no_data_period={"type": "min", "value": 10},
        no_data_recovery_period={"type": "min", "value": 5},
        no_data_alert_name="$instance_name",
        no_data_level="warning",
        enable_alerts=["no_data"],
        notice=False,
        last_run_time=datetime(2026, 11, 5, tzinfo=timezone.utc),
    )

    current = {"payload": _vm_payload(initial_rows)}

    def query_range(self, *args, **kwargs):
        return current["payload"]

    with patch("apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI.query_range", query_range), patch(
        "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
    ), patch("apps.monitor.tasks.services.policy_scan.event_alert_manager.AlertLifecycleNotifier"):
        PolicyBaselineService(policy).refresh()

        stored = PolicyInstanceBaseline.objects.filter(policy_id=policy.id)
        expected = INSTANCE_COUNT * (len(SHORT_MOUNTS) + 1)
        assert stored.count() == expected
        longest = stored.aggregate(longest=Max(Length("metric_instance_id")))["longest"]
        assert longest <= MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
        assert stored.filter(metric_instance_id__startswith="mi1_").count() == INSTANCE_COUNT
        missing_baseline = stored.get(metric_instance_id=missing_key)
        assert missing_baseline.monitor_instance_id == missing_monitor_id
        assert missing_baseline.dimensions["mount"] == missing_tuple[1]
        assert missing_baseline.dimensions["path"] == missing_tuple[2]

        query_service = MetricQueryService(policy, {missing_monitor_id: "host-0007"})
        assert query_service.get_monitor_instance_id_from_metric_instance_id(missing_key) == ""
        assert query_service.get_monitor_instance_id_from_metric_instance_id(missing_monitor_id) == missing_monitor_id

        if connection.vendor == "postgresql":
            table = PolicyInstanceBaseline._meta.db_table
            with connection.cursor() as cursor:
                columns = {column.name: column for column in connection.introspection.get_table_description(cursor, table)}
            assert columns["metric_instance_id"].display_size == MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
            with pytest.raises(DataError):
                with transaction.atomic():
                    PolicyInstanceBaseline.objects.create(
                        policy_id=policy.id,
                        monitor_instance_id=missing_monitor_id,
                        metric_instance_id="x" * (MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH + 1),
                    )

        gap_rows = [row for row in initial_rows if row != missing_tuple]
        gap_rows.append(extra_tuple)
        current["payload"] = _vm_payload(gap_rows)
        MonitorPolicyScan(policy).run()

        alert = MonitorAlert.objects.get(policy_id=policy.id, alert_type="no_data", status="new")
        assert alert.metric_instance_id == missing_key
        assert len(alert.metric_instance_id) <= MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
        assert alert.monitor_instance_id == missing_monitor_id
        assert alert.dimensions["mount"] == missing_tuple[1]
        assert missing_tuple[1] in alert.content
        event = MonitorEvent.objects.get(alert_id=alert.id)
        assert event.metric_instance_id == missing_key
        assert event.dimensions["fstype"] == "overlay"
        added = stored.get(metric_instance_id=extra_key)
        assert added.monitor_instance_id == missing_monitor_id
        assert added.dimensions["mount"] == extra_mount
        assert "mi1_" not in added.monitor_instance_id

        restored_rows = list(initial_rows)
        restored_rows.append(extra_tuple)
        current["payload"] = _vm_payload(restored_rows)
        MonitorPolicyScan(policy).run()

    alert.refresh_from_db()
    assert alert.status == "recovered"
    assert stored.filter(metric_instance_id=missing_key).exists()
    assert stored.filter(metric_instance_id=extra_key).exists()
