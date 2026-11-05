"""几千实例的无数据基准：身份列保持 varchar(255)，长路径写入 dimensions。

VictoriaMetrics 查询被 mock。落库走真实数据库，用来确认批量替换、列宽和扫描差集。
"""
import time
from unittest.mock import MagicMock, patch

import pytest
from django.db import DataError, connection, transaction
from django.db.models import Max
from django.db.models.functions import Length

from apps.monitor.constants.monitor_object import MonitorObjConstants
from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPolicy, PolicyInstanceBaseline
from apps.monitor.services.policy_baseline import PolicyBaselineService
from apps.monitor.tasks.services.policy_scan.scanner import MonitorPolicyScan
from apps.monitor.utils.dimension import is_metric_instance_fingerprint, metric_instance_storage_key

pytestmark = [pytest.mark.slow, pytest.mark.django_db]

INSTANCE_COUNT = 3000
SHORT_MOUNTS = ("/", "/boot", "/data")
GROUP_BY = ["instance_id", "mount", "path", "fstype"]


def _long_mount(index):
    return (
        "/var/lib/kubelet/pods/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        "/volumes/kubernetes.io~csi/pvc-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        f"/mount/host-{index:04d}"
    )


def _series_for_host(index):
    label = f"os_h{index:04d}"
    monitor_instance_id = str((label,))
    series = []
    for mount in SHORT_MOUNTS:
        series.append((label, mount, mount, "ext4"))
    mount = _long_mount(index)
    series.append((label, mount, mount, "overlay"))
    return monitor_instance_id, series


def _metrics_payload(series_rows):
    result = []
    for instance_id, mount, path, fstype in series_rows:
        result.append(
            {
                "metric": {
                    "instance_id": instance_id,
                    "mount": mount,
                    "path": path,
                    "fstype": fstype,
                }
            }
        )
    return {"data": {"result": result}}


def _refresh(policy, payload):
    fake_query_svc = MagicMock()
    fake_query_svc.query_existence_metrics.return_value = payload
    started = time.perf_counter()
    with patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.MetricQueryService",
        return_value=fake_query_svc,
    ):
        with transaction.atomic():
            PolicyBaselineService(policy).refresh()
    return time.perf_counter() - started


def test_thousands_of_instances_fit_the_existing_baseline_column():
    monitor_object = MonitorObject.objects.create(
        name="UTScaleHost",
        level="base",
        instance_id_keys=["instance_id"],
    )
    monitor_ids = []
    series_rows = []
    instances = []
    long_raw_over_limit = 0
    for index in range(INSTANCE_COUNT):
        monitor_instance_id, host_series = _series_for_host(index)
        monitor_ids.append(monitor_instance_id)
        series_rows.extend(host_series)
        instances.append(
            MonitorInstance(
                id=monitor_instance_id,
                name=f"host-{index:04d}",
                monitor_object=monitor_object,
            )
        )
        long_tuple = host_series[-1]
        if len(str(long_tuple)) > MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH:
            long_raw_over_limit += 1
    assert long_raw_over_limit == INSTANCE_COUNT
    assert len(str(series_rows[0])) <= MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH

    MonitorInstance.objects.bulk_create(instances, batch_size=500)
    policy = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="ut-scale-policy",
        algorithm="max",
        source={"type": "instance", "values": monitor_ids},
        group_by=GROUP_BY,
        period={"type": "min", "value": 5},
        query_condition={"type": "metric", "metric_id": "disk_used_percent"},
        no_data_period={"type": "min", "value": 10},
        no_data_alert_name="$instance_name",
        enable_alerts=["no_data"],
    )

    expected = INSTANCE_COUNT * (len(SHORT_MOUNTS) + 1)
    refresh_seconds = _refresh(policy, _metrics_payload(series_rows))

    stored = PolicyInstanceBaseline.objects.filter(policy_id=policy.id)
    assert stored.count() == expected
    longest = stored.aggregate(longest=Max(Length("metric_instance_id")))["longest"]
    assert longest <= MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
    assert stored.filter(metric_instance_id__startswith="mi1_").count() == INSTANCE_COUNT

    sample_mount = _long_mount(42)
    sample_key = metric_instance_storage_key(("os_h0042", sample_mount, sample_mount, "overlay"))
    sample = stored.get(metric_instance_id=sample_key)
    assert is_metric_instance_fingerprint(sample.metric_instance_id)
    assert sample.dimensions["mount"] == sample_mount
    assert sample.dimensions["path"] == sample_mount
    assert sample.monitor_instance_id == "('os_h0042',)"

    short = stored.get(metric_instance_id=str(("os_h0042", "/", "/", "ext4")))
    assert short.dimensions["mount"] == "/"

    if connection.vendor == "postgresql":
        table = PolicyInstanceBaseline._meta.db_table
        with connection.cursor() as cursor:
            columns = {column.name: column for column in connection.introspection.get_table_description(cursor, table)}
        assert columns["metric_instance_id"].display_size == MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
        with pytest.raises(DataError):
            with transaction.atomic():
                PolicyInstanceBaseline.objects.create(
                    policy_id=policy.id,
                    monitor_instance_id=monitor_ids[0],
                    metric_instance_id="x" * (MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH + 1),
                )

    started = time.perf_counter()
    scan = MonitorPolicyScan(policy)
    scan_seconds = time.perf_counter() - started
    assert len(scan.baselines_map) == expected
    assert scan.baseline_dimensions[sample_key]["mount"] == sample_mount

    present = {key: {} for key in scan.baselines_map if key != sample_key}
    events = scan.alert_detector._build_no_data_events(present)
    assert len(events) == 1
    assert events[0]["metric_instance_id"] == sample_key
    assert len(events[0]["metric_instance_id"]) <= MonitorObjConstants.METRIC_INSTANCE_ID_MAX_LENGTH
    assert sample_mount in events[0]["content"]
    assert events[0]["dimensions"]["fstype"] == "overlay"

    PolicyBaselineService(policy).sync(
        {metric_instance_storage_key(("os_h0042", "/new", "/new", "xfs")): "('os_h0042',)"},
        dimensions_by_id={
            metric_instance_storage_key(("os_h0042", "/new", "/new", "xfs")): {
                "instance_id": "os_h0042",
                "mount": "/new",
                "path": "/new",
                "fstype": "xfs",
            }
        },
    )
    assert stored.count() == expected + 1

    replaced = _refresh(policy, _metrics_payload([series_rows[0]]))
    assert stored.count() == 1

    print(
        f"scale baselines={expected} refresh_s={refresh_seconds:.2f} "
        f"scan_load_s={scan_seconds:.2f} replace_s={replaced:.2f} longest_key={longest}"
    )
