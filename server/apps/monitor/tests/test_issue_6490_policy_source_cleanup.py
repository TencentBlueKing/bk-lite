"""Issue 6490：清理已删实例时必须按锁内当前 source 写回，不能覆盖并发保存的来源。"""

from datetime import datetime, timezone

import pytest
from django.db.models.query import QuerySet

import apps.cmdb.models  # noqa: F401  INSTALL_APPS 需含 cmdb（monitor.nats.monitor 导入 cmdb.services）
import apps.node_mgmt.models  # noqa: F401  INSTALL_APPS 需含 node_mgmt（monitor.apps.ready → nats.monitor）
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.services.policy_source_cleanup import PolicySourceCleanupService

pytestmark = pytest.mark.django_db

A = "A"
B = "B"
C = "C"


def _make_policy(name, source, enable=True):
    monitor_object = MonitorObject.objects.create(
        name=name,
        level="base",
        instance_id_keys=["instance_id"],
    )
    return MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name=name,
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source=source,
        group_by=["instance_id"],
        enable=enable,
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _commit_current_source_after_scan(monkeypatch, policy, source, enable=True):
    """扫描 iterator 读出旧行之后、调用方处理这些对象之前，提交并发保存的 source。"""
    original_iterator = QuerySet.iterator
    committed = False

    def racing_iterator(self, *args, **kwargs):
        nonlocal committed
        rows = list(original_iterator(self, *args, **kwargs))
        if not committed and any(getattr(row, "pk", None) == policy.pk for row in rows):
            committed = True
            MonitorPolicy.objects.filter(pk=policy.pk).update(source=source, enable=enable)
        yield from rows

    monkeypatch.setattr(QuerySet, "iterator", racing_iterator)


class TestIssue6490PolicySourceCleanup:
    def test_stale_snapshot_does_not_overwrite_concurrent_source(self, monkeypatch):
        policy = _make_policy(
            "issue6490-stale",
            {"type": "instance", "values": [A, B]},
            enable=True,
        )
        _commit_current_source_after_scan(
            monkeypatch,
            policy,
            {"type": "instance", "values": [B, C]},
            enable=True,
        )

        result = PolicySourceCleanupService.cleanup_by_instance_ids([A])

        policy.refresh_from_db()
        assert policy.source == {"type": "instance", "values": [B, C]}
        assert policy.enable is True
        assert result["cleaned_count"] == 0
        assert result["disabled_count"] == 0
        assert result["policy_ids"] == []
        assert result["disabled_policy_ids"] == []

    def test_removes_deleted_id_and_keeps_remaining_order(self):
        policy = _make_policy(
            "issue6490-order",
            {"type": "instance", "values": [A, B]},
            enable=True,
        )

        result = PolicySourceCleanupService.cleanup_by_instance_ids([A])

        policy.refresh_from_db()
        assert policy.source["values"] == [B]
        assert policy.enable is True
        assert result["cleaned_count"] == 1
        assert result["disabled_count"] == 0

    def test_disables_only_when_current_values_become_empty(self):
        policy = _make_policy(
            "issue6490-empty",
            {"type": "instance", "values": [A]},
            enable=True,
        )

        result = PolicySourceCleanupService.cleanup_by_instance_ids([A])

        policy.refresh_from_db()
        assert policy.source["values"] == []
        assert policy.enable is False
        assert result["disabled_count"] == 1
        assert policy.id in result["disabled_policy_ids"]

    def test_untouched_when_deleted_id_is_absent(self):
        policy = _make_policy(
            "issue6490-absent",
            {"type": "instance", "values": [B]},
            enable=True,
        )

        result = PolicySourceCleanupService.cleanup_by_instance_ids([A])

        policy.refresh_from_db()
        assert policy.source["values"] == [B]
        assert policy.enable is True
        assert result["cleaned_count"] == 0
        assert result["disabled_count"] == 0
