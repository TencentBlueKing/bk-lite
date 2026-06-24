"""MonitorPolicyScan 编排器规格测试。

聚焦实例映射/基准映射构建、来源解析、步骤错误处理、快照触发条件、前置检查。
子服务方法通过 mocker.patch.object 隔离，断言编排契约。
"""

from datetime import datetime, timezone

import pytest

from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    PolicyInstanceBaseline,
)
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
