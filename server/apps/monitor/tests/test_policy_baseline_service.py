"""PolicyBaselineService 测试 — 基准表增量/全量/清理的真实 DB 副作用,VM 查询走 mock 边界。"""
from unittest.mock import MagicMock, patch

import pytest

from apps.monitor.models import (
    MonitorObject,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorPolicy,
    PolicyInstanceBaseline,
)
from apps.monitor.services.policy_baseline import PolicyBaselineService

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def obj():
    return MonitorObject.objects.create(name="UTBaseObj", level="base")


@pytest.fixture
def policy(obj):
    return MonitorPolicy.objects.create(
        monitor_object=obj,
        name="ut-policy",
        algorithm="max",
        source={"type": "instance", "values": ["i1", "i2"]},
        group_by=["instance_id"],
        period={"type": "min", "value": 5},
    )


def _baselines(policy):
    return set(
        PolicyInstanceBaseline.objects.filter(policy_id=policy.id).values_list("metric_instance_id", flat=True)
    )


def test_sync_adds_only_new_baselines(policy):
    svc = PolicyBaselineService(policy)
    svc.sync({"m1": "i1", "m2": "i2"})
    assert _baselines(policy) == {"m1", "m2"}
    # 二次同步含已存在 + 新增,只新增 m3
    svc.sync({"m1": "i1", "m3": "i3"})
    assert _baselines(policy) == {"m1", "m2", "m3"}


def test_sync_noop_when_no_source(policy):
    policy.source = {}
    policy.save()
    PolicyBaselineService(policy).sync({"m1": "i1"})
    assert _baselines(policy) == set()


def test_sync_noop_when_empty_input(policy):
    PolicyBaselineService(policy).sync({})
    assert _baselines(policy) == set()


def test_clear_deletes_all_for_policy(policy):
    PolicyInstanceBaseline.objects.create(policy_id=policy.id, monitor_instance_id="i1", metric_instance_id="m1")
    PolicyInstanceBaseline.objects.create(policy_id=policy.id, monitor_instance_id="i2", metric_instance_id="m2")
    PolicyBaselineService(policy).clear()
    assert _baselines(policy) == set()


def test_get_instance_list_by_source_instance_type(policy):
    svc = PolicyBaselineService(policy)
    assert svc._get_instance_list_by_source("instance", ["a", "b"]) == ["a", "b"]


def test_get_instance_list_by_source_unknown_returns_empty(policy):
    assert PolicyBaselineService(policy)._get_instance_list_by_source("weird", ["x"]) == []


def test_get_instance_list_by_source_organization(obj, policy):
    inst = MonitorInstance.objects.create(id="org-inst-1", name="oi1", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=77)
    out = PolicyBaselineService(policy)._get_instance_list_by_source("organization", [77])
    assert out == ["org-inst-1"]


def test_build_instances_map_filters_deleted_and_object(obj, policy):
    live = MonitorInstance.objects.create(id="i1", name="live", monitor_object=obj)
    MonitorInstance.objects.create(id="i2", name="dead", monitor_object=obj, is_deleted=True)
    result = PolicyBaselineService(policy)._build_instances_map()
    assert result == {"i1": "live"}
    assert live.id in result


def test_refresh_skips_when_no_source(policy):
    policy.source = {}
    policy.save()
    PolicyBaselineService(policy).refresh()  # 不抛异常即可
    assert _baselines(policy) == set()


def test_refresh_clears_when_no_instances(obj, policy):
    PolicyInstanceBaseline.objects.create(policy_id=policy.id, monitor_instance_id="x", metric_instance_id="mx")
    # source 指向不存在的实例 → instances_map 为空 → clear
    PolicyBaselineService(policy).refresh()
    assert _baselines(policy) == set()


def test_refresh_replaces_baselines_on_successful_query(obj, policy):
    # 生产中实例 id 以 tuple 串形式存储(如 "('i1',)"),source.values 也需用该格式才能命中。
    real_id = "('i1',)"
    policy.source = {"type": "instance", "values": [real_id]}
    policy.save()
    MonitorInstance.objects.create(id=real_id, name="host1", monitor_object=obj)
    # 旧基准应被替换
    PolicyInstanceBaseline.objects.create(policy_id=policy.id, monitor_instance_id="old", metric_instance_id="old-m")

    fake_metrics = {"data": {"result": [{"metric": {"instance_id": "i1"}}]}}
    fake_query_svc = MagicMock()
    fake_query_svc.query_aggregation_metrics.return_value = fake_metrics

    with patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.MetricQueryService",
        return_value=fake_query_svc,
    ):
        PolicyBaselineService(policy).refresh()

    # group_by=["instance_id"] → metric_instance_id = "('i1',)",monitor_instance_id 同值且命中映射
    assert _baselines(policy) == {real_id}


def test_refresh_keeps_existing_when_query_fails(obj, policy):
    real_id = "('i1',)"
    policy.source = {"type": "instance", "values": [real_id]}
    policy.save()
    MonitorInstance.objects.create(id=real_id, name="host1", monitor_object=obj)
    PolicyInstanceBaseline.objects.create(policy_id=policy.id, monitor_instance_id=real_id, metric_instance_id="keep")

    with patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.MetricQueryService",
        side_effect=RuntimeError("vm down"),
    ):
        PolicyBaselineService(policy).refresh()

    # 查询失败返回 None,保留既有基准
    assert _baselines(policy) == {"keep"}
