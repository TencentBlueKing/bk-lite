"""实例绑定策略列表过滤不得在分页前物化全部 source JSON。"""

import pytest
from django.db.models.query import QuerySet

from apps.monitor.filters.monitor_policy import filter_policy_queryset_by_instance
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy

pytestmark = pytest.mark.django_db


def _create_policy(monitor_object, name, source):
    return MonitorPolicy.objects.create(
        name=name,
        monitor_object=monitor_object,
        algorithm="avg",
        source=source,
    )


def test_instance_filter_does_not_materialize_all_sources(monkeypatch):
    monitor_object = MonitorObject.objects.create(name="PolFilterObj", level="base")
    target = "inst-target"
    for index in range(5):
        values = [target] if index < 3 else [f"other-{index}"]
        _create_policy(
            monitor_object,
            f"policy-{index}",
            {"type": "instance", "values": values},
        )
    _create_policy(
        monitor_object,
        "org-policy",
        {"type": "organization", "values": [target]},
    )

    original_values_list = QuerySet.values_list
    materialized = {"count": 0}

    def wrapped_values_list(self, *args, **kwargs):
        if args[:2] == ("id", "source"):
            materialized["count"] += 1
        return original_values_list(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "values_list", wrapped_values_list)

    filtered = filter_policy_queryset_by_instance(MonitorPolicy.objects.all(), target)
    page = list(filtered[:2])

    assert materialized["count"] == 0
    assert filtered.count() == 3
    assert len(page) == 2
    assert {item.name for item in page} <= {f"policy-{index}" for index in range(3)}


def test_instance_filter_matches_tuple_storage_key():
    monitor_object = MonitorObject.objects.create(name="PolTupleObj", level="base")
    storage_key = "('host-1',)"
    _create_policy(
        monitor_object,
        "tuple-bound",
        {"type": "instance", "values": [storage_key]},
    )
    _create_policy(
        monitor_object,
        "other",
        {"type": "instance", "values": ["('host-2',)"]},
    )

    filtered = filter_policy_queryset_by_instance(MonitorPolicy.objects.all(), storage_key)
    assert list(filtered.values_list("name", flat=True)) == ["tuple-bound"]
