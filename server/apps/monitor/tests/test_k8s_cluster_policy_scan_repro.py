"""复合对象策略扫描：一级对象与二级对象都要能出事件。

一级对象是采集入口（Cluster / Docker），库中单维主键是 "('id',)"，
页面经常给出逻辑 ID。二级对象随一级一起被发现（Pod / Node / Docker Container），
身份是「父键 + 子键」的 tuple，不能靠父逻辑 ID 或同名子对象猜测归属。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models import (
    MonitorEvent,
    MonitorInstance,
    MonitorObject,
    MonitorPolicy,
)
from apps.monitor.tasks.services.policy_scan import metric_query as metric_query_module
from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector
from apps.monitor.tasks.services.policy_scan.scanner import MonitorPolicyScan


CLUSTER_STORAGE_ID = "('prod-cluster',)"
CLUSTER_LOGICAL_ID = "prod-cluster"
POD_STORAGE_ID = "('prod-cluster', 'nginx')"
NODE_STORAGE_ID = "('prod-cluster', 'node-1')"
DOCKER_STORAGE_ID = "('host1',)"
DOCKER_LOGICAL_ID = "host1"
CONTAINER_STORAGE_ID = "('host1', 'c1')"


def _cluster_object():
    return SimpleNamespace(
        name="Cluster",
        level="base",
        instance_id_keys=["instance_id"],
        parent=None,
        parent_id=None,
    )


def _policy(**kwargs):
    base = dict(
        id=101,
        period={"type": "min", "value": 1},
        group_by=["instance_id"],
        alert_name="$instance_name 超阈值 $value",
        threshold=[{"method": ">", "value": 10, "level": "critical"}],
        source={"type": "instance", "values": [CLUSTER_STORAGE_ID]},
        monitor_object=_cluster_object(),
        query_condition={"type": "metric", "metric_id": 1},
        no_data_period={},
        recovery_condition=5,
        last_run_time=datetime(2026, 8, 19, 3, 0, 0, tzinfo=timezone.utc),
        trigger_count=1,
        metric_unit="percent",
        calculation_unit="percent",
        threshold_unit="percent",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mq(agg, instance_id_keys=None):
    return SimpleNamespace(
        metric=SimpleNamespace(
            display_name="使用率",
            name="utilization",
            instance_id_keys=instance_id_keys or ["instance_id"],
            dimensions=[],
        ),
        query_aggregation_metrics=lambda period, points=1: agg,
        convert_metric_values=lambda data: data,
        format_aggregation_metrics=lambda data: {},
        get_display_unit=lambda: "%",
        get_enum_value_map=lambda: {},
        convert_thresholds=lambda thresholds: thresholds,
    )


def _agg(metric, value="80"):
    return {"data": {"result": [{"metric": metric, "values": [[1, value]]}]}}


def _cluster_agg(include_instance_id=True, value="80"):
    metric = {"instance_id": CLUSTER_LOGICAL_ID} if include_instance_id else {}
    return _agg(metric, value)


def _patch_scan(mocker, agg):
    mocker.patch.dict(
        metric_query_module.METHOD,
        {"avg": lambda *args, **kwargs: agg},
    )
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="2026/08/19/mock.json.gz",
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.snapshot_recorder."
        "SnapshotRecorder.record_snapshots_for_active_alerts"
    )
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.alert_detector."
        "AlertLifecycleNotifier.notify_alerts"
    )


def _create_policy(obj, *, name, source_values, group_by, alert_name):
    return MonitorPolicy.objects.create(
        monitor_object=obj,
        name=name,
        algorithm="avg",
        query_condition={"type": "pmq", "query": "utilization"},
        source={"type": "instance", "values": source_values},
        group_by=group_by,
        period={"type": "min", "value": 1},
        threshold=[{"method": ">", "value": 10, "level": "critical"}],
        enable_alerts=["threshold"],
        notice=False,
        last_run_time=datetime(2026, 8, 19, 3, 0, 0, tzinfo=timezone.utc),
        alert_name=alert_name,
    )


def _create_compound_tree(prefix, *, child_name, child_keys):
    parent = MonitorObject.objects.create(
        name=f"{prefix}Base",
        level="base",
        instance_id_keys=["instance_id"],
    )
    child = MonitorObject.objects.create(
        name=f"{prefix}{child_name}",
        level="derivative",
        parent=parent,
        instance_id_keys=child_keys,
    )
    return parent, child


def test_k8s_cluster_threshold_triggers_when_storage_id_matches():
    instances = {CLUSTER_STORAGE_ID: "生产集群"}
    detector = AlertDetector(
        _policy(),
        instances,
        {},
        [],
        _mq(_cluster_agg()),
    )

    alerts, infos = detector.detect_threshold_alerts()

    assert len(alerts) == 1, f"K8s Cluster 超阈值应产生告警，实际={alerts}"
    assert alerts[0]["monitor_instance_id"] == CLUSTER_STORAGE_ID
    assert alerts[0]["value"] == 80.0
    assert infos == []


@pytest.mark.django_db
class TestBaseObjectPolicyScan:
    """一级对象：采集数据的对象本身，单维 instance_id。"""

    def test_k8s_cluster_logical_source_id_still_scans_and_creates_events(self, mocker):
        obj = MonitorObject.objects.create(
            name="ClusterRepro",
            level="base",
            instance_id_keys=["instance_id"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=obj,
        )
        policy = _create_policy(
            obj,
            name="集群内存超阈值",
            source_values=[CLUSTER_LOGICAL_ID],
            group_by=["instance_id"],
            alert_name="$instance_name 超阈值 $value",
        )
        _patch_scan(mocker, _cluster_agg())

        MonitorPolicyScan(policy).run()

        events = list(MonitorEvent.objects.filter(policy_id=policy.id))
        assert len(events) == 1, (
            f"一级 Cluster 逻辑 instance_id 应能扫出事件，实际 {len(events)} 条"
        )
        assert events[0].monitor_instance_id == CLUSTER_STORAGE_ID
        assert events[0].level == "critical"

    def test_k8s_cluster_tuple_source_id_creates_events(self, mocker):
        obj = MonitorObject.objects.create(
            name="ClusterReproTuple",
            level="base",
            instance_id_keys=["instance_id"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=obj,
        )
        policy = _create_policy(
            obj,
            name="集群内存超阈值-tuple",
            source_values=[CLUSTER_STORAGE_ID],
            group_by=["instance_id"],
            alert_name="$instance_name 超阈值 $value",
        )
        _patch_scan(mocker, _cluster_agg())

        MonitorPolicyScan(policy).run()

        assert MonitorEvent.objects.filter(policy_id=policy.id).count() == 1

    def test_docker_host_logical_source_id_creates_events(self, mocker):
        obj = MonitorObject.objects.create(
            name="DockerHostRepro",
            level="base",
            instance_id_keys=["instance_id"],
        )
        MonitorInstance.objects.create(
            id=DOCKER_STORAGE_ID,
            name="docker-host-1",
            monitor_object=obj,
        )
        policy = _create_policy(
            obj,
            name="宿主机内存超阈值",
            source_values=[DOCKER_LOGICAL_ID],
            group_by=["instance_id"],
            alert_name="$instance_name 超阈值 $value",
        )
        _patch_scan(mocker, _agg({"instance_id": DOCKER_LOGICAL_ID}))

        MonitorPolicyScan(policy).run()

        events = list(MonitorEvent.objects.filter(policy_id=policy.id))
        assert len(events) == 1
        assert events[0].monitor_instance_id == DOCKER_STORAGE_ID

    def test_base_policy_does_not_select_derivative_instances(self):
        parent, child = _create_compound_tree(
            "BaseIsolation",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID,
            name="nginx",
            monitor_object=child,
        )
        policy = _create_policy(
            parent,
            name="一级不扫二级",
            source_values=[CLUSTER_LOGICAL_ID],
            group_by=["instance_id"],
            alert_name="$instance_name 超阈值 $value",
        )

        scan = MonitorPolicyScan(policy)

        assert scan.instances_map == {CLUSTER_STORAGE_ID: "生产集群"}
        assert POD_STORAGE_ID not in scan.instances_map


@pytest.mark.django_db
class TestDerivativeObjectPolicyScan:
    """二级对象：跟随一级一起被采集上来，身份是父键+子键。"""

    def test_k8s_pod_full_identity_creates_events_with_parent_name(self, mocker):
        parent, child = _create_compound_tree(
            "PodScan",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID,
            name="nginx",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="Pod CPU 超阈值",
            source_values=[POD_STORAGE_ID],
            group_by=["instance_id", "pod"],
            alert_name="$parent_resource_name/$resource_name 超阈值",
        )
        _patch_scan(
            mocker,
            _agg({"instance_id": CLUSTER_LOGICAL_ID, "pod": "nginx"}),
        )

        MonitorPolicyScan(policy).run()

        events = list(MonitorEvent.objects.filter(policy_id=policy.id))
        assert len(events) == 1
        assert events[0].monitor_instance_id == POD_STORAGE_ID
        assert events[0].content == "生产集群/nginx 超阈值"

    def test_k8s_node_full_identity_creates_events_with_parent_name(self, mocker):
        parent, child = _create_compound_tree(
            "NodeScan",
            child_name="Node",
            child_keys=["instance_id", "node"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=NODE_STORAGE_ID,
            name="node-1",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="Node 磁盘超阈值",
            source_values=[NODE_STORAGE_ID],
            group_by=["instance_id", "node"],
            alert_name="$parent_resource_name/$resource_name 超阈值",
        )
        _patch_scan(
            mocker,
            _agg({"instance_id": CLUSTER_LOGICAL_ID, "node": "node-1"}),
        )

        MonitorPolicyScan(policy).run()

        events = list(MonitorEvent.objects.filter(policy_id=policy.id))
        assert len(events) == 1
        assert events[0].monitor_instance_id == NODE_STORAGE_ID
        assert events[0].content == "生产集群/node-1 超阈值"

    def test_docker_container_full_identity_creates_events_with_parent_name(self, mocker):
        parent, child = _create_compound_tree(
            "ContainerScan",
            child_name="Container",
            child_keys=["instance_id", "container_name"],
        )
        MonitorInstance.objects.create(
            id=DOCKER_STORAGE_ID,
            name="docker-host-1",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=CONTAINER_STORAGE_ID,
            name="c1",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="容器内存超阈值",
            source_values=[CONTAINER_STORAGE_ID],
            group_by=["instance_id", "container_name"],
            alert_name="$parent_resource_name/$resource_name 超阈值",
        )
        _patch_scan(
            mocker,
            _agg({"instance_id": DOCKER_LOGICAL_ID, "container_name": "c1"}),
        )

        MonitorPolicyScan(policy).run()

        events = list(MonitorEvent.objects.filter(policy_id=policy.id))
        assert len(events) == 1
        assert events[0].monitor_instance_id == CONTAINER_STORAGE_ID
        assert events[0].content == "docker-host-1/c1 超阈值"

    def test_derivative_policy_does_not_select_base_instances(self):
        parent, child = _create_compound_tree(
            "ChildIsolation",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID,
            name="nginx",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="二级不扫一级",
            source_values=[POD_STORAGE_ID],
            group_by=["instance_id", "pod"],
            alert_name="$resource_name 超阈值",
        )

        scan = MonitorPolicyScan(policy)

        assert scan.instances_map == {POD_STORAGE_ID: "nginx"}
        assert CLUSTER_STORAGE_ID not in scan.instances_map
        assert scan.parent_instances_map == {CLUSTER_STORAGE_ID: "生产集群"}

    def test_parent_logical_id_does_not_select_derivative_instances(self):
        """扩键只兼容一级单维写法，不能把父逻辑 ID 当成二级实例。"""
        parent, child = _create_compound_tree(
            "ParentLogical",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID,
            name="nginx",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="父逻辑ID不能选子实例",
            source_values=[CLUSTER_LOGICAL_ID],
            group_by=["instance_id", "pod"],
            alert_name="$resource_name 超阈值",
        )

        scan = MonitorPolicyScan(policy)

        assert scan.instances_map == {}

    def test_child_name_alone_does_not_select_derivative_instances(self):
        parent, child = _create_compound_tree(
            "ChildNameOnly",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID,
            name="生产集群",
            monitor_object=parent,
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID,
            name="nginx",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="子名不能当实例ID",
            source_values=["nginx"],
            group_by=["instance_id", "pod"],
            alert_name="$resource_name 超阈值",
        )

        scan = MonitorPolicyScan(policy)

        assert scan.instances_map == {}

    def test_same_child_name_on_two_parents_does_not_guess(self, mocker):
        parent, child = _create_compound_tree(
            "AmbiguousPod",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        other_cluster = "('other-cluster',)"
        other_pod = "('other-cluster', 'nginx')"
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID, name="生产集群", monitor_object=parent
        )
        MonitorInstance.objects.create(
            id=other_cluster, name="备集群", monitor_object=parent
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID, name="nginx", monitor_object=child
        )
        MonitorInstance.objects.create(
            id=other_pod, name="nginx", monitor_object=child
        )
        policy = _create_policy(
            child,
            name="同名 Pod 不得猜测",
            source_values=[POD_STORAGE_ID, other_pod],
            group_by=["pod"],
            alert_name="$resource_name 超阈值",
        )
        _patch_scan(mocker, _agg({"pod": "nginx"}))

        MonitorPolicyScan(policy).run()

        assert MonitorEvent.objects.filter(policy_id=policy.id).count() == 0

    def test_unique_child_in_scope_matches_partial_labels(self, mocker):
        parent, child = _create_compound_tree(
            "UniquePod",
            child_name="Pod",
            child_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id=CLUSTER_STORAGE_ID, name="生产集群", monitor_object=parent
        )
        MonitorInstance.objects.create(
            id=POD_STORAGE_ID, name="nginx", monitor_object=child
        )
        MonitorInstance.objects.create(
            id="('prod-cluster', 'redis')",
            name="redis",
            monitor_object=child,
        )
        policy = _create_policy(
            child,
            name="范围内唯一 Pod 可归属",
            source_values=[POD_STORAGE_ID],
            group_by=["pod"],
            alert_name="$parent_resource_name/$resource_name 超阈值",
        )
        _patch_scan(mocker, _agg({"pod": "nginx"}))

        MonitorPolicyScan(policy).run()

        events = list(MonitorEvent.objects.filter(policy_id=policy.id))
        assert len(events) == 1
        assert events[0].monitor_instance_id == POD_STORAGE_ID
        assert events[0].content == "生产集群/nginx 超阈值"
