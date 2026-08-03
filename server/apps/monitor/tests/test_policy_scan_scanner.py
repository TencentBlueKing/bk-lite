"""MonitorPolicyScan 编排器规格测试。

聚焦实例映射/基准映射构建、来源解析、步骤错误处理、快照触发条件、前置检查。
子服务方法通过 mocker.patch.object 隔离，断言编排契约。
"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.monitor.models import (
    MonitorAlert,
    MonitorEvent,
    MonitorInstance,
    MonitorInstanceOrganization,
    PolicyInstanceBaseline,
)
from apps.monitor.serializers.monitor_alert import MonitorAlertSerializer
from apps.monitor.tasks.services.policy_scan import metric_query as metric_query_module
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.tasks.services.policy_scan.scanner import MonitorPolicyScan

pytestmark = pytest.mark.django_db


def _make_policy(obj, source=None, **kwargs):
    base = dict(
        monitor_object=obj,
        name="p1",
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source=source if source is not None else {"type": "instance", "values": []},
        group_by=["instance_id"],
        enable_alerts=["threshold"],
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return MonitorPolicy.objects.create(**base)


def _make_obj():
    return MonitorObject.objects.create(name="ScanObj", level="base", instance_id_keys=["instance_id"])


class TestBuildInstancesMap:
    def test_no_source_empty(self):
        obj = _make_obj()
        policy = _make_policy(obj, source={})
        scan = MonitorPolicyScan(policy)
        assert scan.instances_map == {}

    def test_instance_source(self):
        obj = _make_obj()
        MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=obj)
        policy = _make_policy(obj, source={"type": "instance", "values": ["('h1',)"]})
        scan = MonitorPolicyScan(policy)
        assert scan.instances_map == {"('h1',)": "主机1"}

    def test_organization_source(self):
        obj = _make_obj()
        inst = MonitorInstance.objects.create(id="('h2',)", name="主机2", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=5)
        policy = _make_policy(obj, source={"type": "organization", "values": [5]})
        scan = MonitorPolicyScan(policy)
        assert scan.instances_map == {"('h2',)": "主机2"}

    def test_deleted_instance_excluded(self):
        obj = _make_obj()
        MonitorInstance.objects.create(id="('h3',)", name="主机3", monitor_object=obj, is_deleted=True)
        policy = _make_policy(obj, source={"type": "instance", "values": ["('h3',)"]})
        scan = MonitorPolicyScan(policy)
        assert scan.instances_map == {}

    def test_derivative_object_builds_parent_name_map(self):
        parent = MonitorObject.objects.create(
            name="ClusterObj", level="base", instance_id_keys=["instance_id"]
        )
        child = MonitorObject.objects.create(
            name="PodObj",
            level="derivative",
            parent=parent,
            instance_id_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id="('cluster-a',)", name="生产集群", monitor_object=parent
        )
        child_id = "('cluster-a', 'orders-7f9')"
        MonitorInstance.objects.create(
            id=child_id, name="orders-7f9", monitor_object=child
        )
        policy = _make_policy(
            child, source={"type": "instance", "values": [child_id]}
        )

        scan = MonitorPolicyScan(policy)

        assert scan.parent_instances_map == {"('cluster-a',)": "生产集群"}


class TestGetInstanceListBySource:
    def test_unknown_type_returns_empty(self):
        obj = _make_obj()
        policy = _make_policy(obj, source={})
        scan = MonitorPolicyScan(policy)
        assert scan._get_instance_list_by_source("bogus", ["x"]) == []


class TestBuildBaselinesMap:
    def test_maps_metric_to_monitor_instance(self):
        obj = _make_obj()
        MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=obj)
        policy = _make_policy(obj, source={"type": "instance", "values": ["('h1',)"]})
        PolicyInstanceBaseline.objects.create(
            policy=policy, monitor_instance_id="('h1',)", metric_instance_id="('h1','eth0')",
        )
        scan = MonitorPolicyScan(policy)
        assert scan.baselines_map == {"('h1','eth0')": "('h1',)"}


class TestExecuteStep:
    def test_success_returns_result(self):
        obj = _make_obj()
        scan = MonitorPolicyScan(_make_policy(obj, source={}))
        ok, result = scan._execute_step("step", lambda: 42)
        assert ok is True and result == 42

    def test_failure_swallowed_non_critical(self):
        obj = _make_obj()
        scan = MonitorPolicyScan(_make_policy(obj, source={}))

        def boom():
            raise RuntimeError("x")

        ok, result = scan._execute_step("step", boom)
        assert ok is False and result is None

    def test_failure_reraised_when_critical(self):
        obj = _make_obj()
        scan = MonitorPolicyScan(_make_policy(obj, source={}))

        def boom():
            raise RuntimeError("x")

        with pytest.raises(RuntimeError):
            scan._execute_step("step", boom, critical=True)


class TestPreCheck:
    def test_source_but_no_instances_returns_false(self):
        obj = _make_obj()
        policy = _make_policy(obj, source={"type": "instance", "values": ["('missing',)"]})
        scan = MonitorPolicyScan(policy)
        assert scan._pre_check() is False

    def test_passes_and_sets_instance_key(self, mocker):
        obj = _make_obj()
        policy = _make_policy(obj, source={})
        scan = MonitorPolicyScan(policy)
        spy = mocker.patch.object(scan.metric_query_service, "set_monitor_obj_instance_key")
        assert scan._pre_check() is True
        spy.assert_called_once()


class TestRecordSnapshots:
    def test_skips_when_no_active_alerts(self, mocker):
        obj = _make_obj()
        scan = MonitorPolicyScan(_make_policy(obj, source={}))
        spy = mocker.patch.object(scan.snapshot_recorder, "record_snapshots_for_active_alerts")
        scan._record_snapshots(info_events=[], event_objs=[], new_alerts=[])
        spy.assert_not_called()

    def test_records_when_active_and_data(self, mocker):
        obj = _make_obj()
        scan = MonitorPolicyScan(_make_policy(obj, source={}))
        spy = mocker.patch.object(scan.snapshot_recorder, "record_snapshots_for_active_alerts")
        scan._record_snapshots(info_events=[], event_objs=[], new_alerts=["a"])
        spy.assert_called_once()


class TestRun:
    def test_run_orchestrates_collect_and_create(self, mocker):
        obj = _make_obj()
        MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=obj)
        policy = _make_policy(obj, source={"type": "instance", "values": ["('h1',)"]})
        scan = MonitorPolicyScan(policy)
        mocker.patch.object(scan.metric_query_service, "set_monitor_obj_instance_key")
        mocker.patch.object(
            scan.alert_detector, "detect_threshold_alerts",
            return_value=([], []),
        )
        mocker.patch.object(scan.alert_detector, "count_events")
        mocker.patch.object(scan.alert_detector, "recover_threshold_alerts")
        create = mocker.patch.object(
            scan.event_alert_manager, "create_events_and_alerts",
            return_value=([], []),
        )
        scan.run()
        # 无事件 → create_events_and_alerts 不应被调用（events 为空走 early return）
        create.assert_not_called()


class TestPodAlertEndToEnd:
    """用隔离测试库和 VictoriaMetrics mock 验证 Pod 告警完整生命周期。"""

    def test_child_names_and_no_data_aggregation_lifecycle(self, mocker):
        parent = MonitorObject.objects.create(
            name="K3SCluster",
            level="base",
            instance_id_keys=["instance_id"],
        )
        pod_object = MonitorObject.objects.create(
            name="K3SPod",
            level="derivative",
            parent=parent,
            instance_id_keys=["instance_id", "pod"],
        )
        MonitorInstance.objects.create(
            id="('cluster-a',)",
            name="生产集群",
            monitor_object=parent,
        )
        pod_id = "('cluster-a', 'orders-7f9')"
        MonitorInstance.objects.create(
            id=pod_id,
            name="orders-7f9",
            monitor_object=pod_object,
        )

        phase = {"result": []}

        def mock_victoriametrics(*args, **kwargs):
            return {"data": {"result": phase["result"]}}

        mocker.patch.dict(metric_query_module.METHOD, {"max": mock_victoriametrics})
        mocker.patch(
            "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
            return_value="2026/01/01/mock.json.gz",
        )
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.snapshot_recorder."
            "SnapshotRecorder.record_snapshots_for_active_alerts"
        )
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.alert_detector."
            "AlertLifecycleNotifier.notify_alerts"
        )

        query_condition = {
            "type": "pmq",
            "query": "kube_pod_container_status_ready",
            "instance_id_keys": ["instance_id", "pod"],
        }
        common = {
            "monitor_object": pod_object,
            "algorithm": "max",
            "query_condition": query_condition,
            "source": {"type": "instance", "values": [pod_id]},
            "group_by": ["instance_id", "pod", "container"],
            "period": {"type": "min", "value": 5},
            "notice": False,
            "last_run_time": datetime(2026, 8, 1, 9, 55, tzinfo=timezone.utc),
        }

        threshold_policy = MonitorPolicy.objects.create(
            **common,
            name="Pod Ready 阈值",
            alert_name="$parent_resource_name/$resource_name Pod Ready 超阈值",
            threshold=[{"method": ">", "value": 0.5, "level": "critical"}],
            enable_alerts=["threshold"],
        )
        phase["result"] = [
            {
                "metric": {
                    "instance_id": "cluster-a",
                    "pod": "orders-7f9",
                    "container": "api",
                },
                "values": [[1785558900, "1"]],
            }
        ]

        MonitorPolicyScan(threshold_policy).run()

        threshold_alert = MonitorAlert.objects.get(policy_id=threshold_policy.id)
        threshold_payload = MonitorAlertSerializer(threshold_alert).data
        assert threshold_payload["monitor_instance_id"] == pod_id
        assert threshold_payload["monitor_instance_name"] == "orders-7f9"
        assert threshold_payload["content"] == "生产集群/orders-7f9 Pod Ready 超阈值"

        no_data_policy = MonitorPolicy.objects.create(
            **common,
            name="Pod Ready 无数据",
            no_data_period={"type": "min", "value": 10},
            no_data_recovery_period={"type": "min", "value": 10},
            no_data_level="critical",
            no_data_alert_name="$parent_resource_name/$resource_name Pod Ready 无数据",
            enable_alerts=["no_data"],
        )
        baselines = [
            "('cluster-a', 'orders-7f9', 'api')",
            "('cluster-a', 'orders-7f9', 'worker')",
        ]
        PolicyInstanceBaseline.objects.bulk_create(
            [
                PolicyInstanceBaseline(
                    policy=no_data_policy,
                    monitor_instance_id=pod_id,
                    metric_instance_id=metric_instance_id,
                )
                for metric_instance_id in baselines
            ]
        )

        # 两个容器同时无数据：生成两个事件，但按 Pod 聚合为一个 alert。
        phase["result"] = []
        MonitorPolicyScan(no_data_policy).run()

        no_data_alert = MonitorAlert.objects.get(policy_id=no_data_policy.id)
        first_events = MonitorEvent.objects.filter(policy_id=no_data_policy.id)
        assert no_data_alert.monitor_instance_id == pod_id
        assert no_data_alert.monitor_instance_name == "orders-7f9"
        assert no_data_alert.content == "生产集群/orders-7f9 Pod Ready 无数据"
        assert first_events.count() == 2
        assert set(first_events.values_list("alert_id", flat=True)) == {no_data_alert.id}

        # api 恢复但 worker 仍无数据：复用原 alert，不应提前恢复。
        no_data_policy.last_run_time += timedelta(minutes=10)
        no_data_policy.save(update_fields=["last_run_time"])
        phase["result"] = [
            {
                "metric": {
                    "instance_id": "cluster-a",
                    "pod": "orders-7f9",
                    "container": "api",
                },
                "values": [[1785559500, "1"]],
            }
        ]
        MonitorPolicyScan(no_data_policy).run()

        no_data_alert.refresh_from_db()
        assert no_data_alert.status == "new"
        assert MonitorAlert.objects.filter(policy_id=no_data_policy.id).count() == 1
        assert MonitorEvent.objects.filter(policy_id=no_data_policy.id).count() == 3

        # 两个容器都恢复数据：同一个聚合 alert 自动恢复。
        no_data_policy.last_run_time += timedelta(minutes=10)
        no_data_policy.save(update_fields=["last_run_time"])
        phase["result"] = [
            {
                "metric": {
                    "instance_id": "cluster-a",
                    "pod": "orders-7f9",
                    "container": container,
                },
                "values": [[1785560100, "1"]],
            }
            for container in ("api", "worker")
        ]
        MonitorPolicyScan(no_data_policy).run()

        no_data_alert.refresh_from_db()
        assert no_data_alert.status == "recovered"
        assert no_data_alert.end_event_time == no_data_policy.last_run_time
