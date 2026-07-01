"""AlertLifecycleNotifier 补充规格测试（通知决策 / 组织解析）。"""

from types import SimpleNamespace

import pytest

from apps.monitor.services.alert_lifecycle_notify import (
    NOTIFY_SCOPE_ALERT_CENTER_ONLY,
    NOTIFY_SCOPE_ALL_CONFIGURED,
    AlertLifecycleNotifier,
)


def _alert(**kwargs):
    base = dict(
        id="a1", notice_type_ids=[], notice_users=[], notice_logs=[],
        monitor_instance_id="('h1',)",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _policy(**kwargs):
    base = dict(notice=True, notice_type_ids=[], notice_users=[], organizations=[])
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestResolveNoticeTypeIds:
    def test_alert_overrides_policy(self):
        n = AlertLifecycleNotifier(_policy(notice_type_ids=[9]))
        assert n._resolve_notice_type_ids(_alert(notice_type_ids=[1])) == [1]

    def test_falls_back_to_policy(self):
        n = AlertLifecycleNotifier(_policy(notice=True, notice_type_ids=[9]))
        assert n._resolve_notice_type_ids(_alert()) == [9]

    def test_empty_when_none(self):
        n = AlertLifecycleNotifier(None)
        assert n._resolve_notice_type_ids(_alert()) == []


class TestResolveNoticeUsers:
    def test_alert_overrides(self):
        n = AlertLifecycleNotifier(_policy(notice_users=["b"]))
        assert n._resolve_notice_users(_alert(notice_users=["a"])) == ["a"]

    def test_policy_fallback(self):
        n = AlertLifecycleNotifier(_policy(notice_users=["b"]))
        assert n._resolve_notice_users(_alert()) == ["b"]


class TestHasSuccessfulCreatedNotice:
    def test_found(self):
        n = AlertLifecycleNotifier(None)
        alert = _alert(notice_logs=[
            {"action": "created", "channel_id": "c1", "success": True},
        ])
        assert n._has_successful_created_notice(alert, "c1") is True

    def test_not_found_wrong_channel(self):
        n = AlertLifecycleNotifier(None)
        alert = _alert(notice_logs=[
            {"action": "created", "channel_id": "c2", "success": True},
        ])
        assert n._has_successful_created_notice(alert, "c1") is False

    def test_ignores_failed_and_non_created(self):
        n = AlertLifecycleNotifier(None)
        alert = _alert(notice_logs=[
            {"action": "created", "channel_id": "c1", "success": False},
            {"action": "closed", "channel_id": "c1", "success": True},
            "bad-entry",
        ])
        assert n._has_successful_created_notice(alert, "c1") is False


class TestShouldNotifyChannel:
    def _channel(self, is_ac=False):
        if is_ac:
            return SimpleNamespace(channel_type="nats", config={"method_name": "receive_alert_events"})
        return SimpleNamespace(channel_type="email", config={})

    def test_alert_center_only_skips_non_ac(self):
        n = AlertLifecycleNotifier(_policy())
        assert n._should_notify_channel(
            _alert(), self._channel(is_ac=False), "c1", "recovered",
            NOTIFY_SCOPE_ALERT_CENTER_ONLY,
        ) is False

    def test_notice_disabled_created_skipped(self):
        n = AlertLifecycleNotifier(_policy(notice=False))
        assert n._should_notify_channel(
            _alert(), self._channel(), "c1", "created", NOTIFY_SCOPE_ALL_CONFIGURED,
        ) is False

    def test_notice_enabled_always_true(self):
        n = AlertLifecycleNotifier(_policy(notice=True))
        assert n._should_notify_channel(
            _alert(), self._channel(), "c1", "created", NOTIFY_SCOPE_ALL_CONFIGURED,
        ) is True

    def test_recovered_requires_prior_created(self):
        n = AlertLifecycleNotifier(_policy(notice=False))
        alert = _alert(notice_logs=[
            {"action": "created", "channel_id": "c1", "success": True},
        ])
        assert n._should_notify_channel(
            alert, self._channel(), "c1", "recovered", NOTIFY_SCOPE_ALL_CONFIGURED,
        ) is True


class TestIsAlertCenterChannel:
    def test_true(self):
        n = AlertLifecycleNotifier(None)
        ch = SimpleNamespace(channel_type="nats", config={"method_name": "receive_alert_events"})
        assert n._is_alert_center_channel(ch) is True

    def test_false(self):
        n = AlertLifecycleNotifier(None)
        ch = SimpleNamespace(channel_type="email", config={})
        assert n._is_alert_center_channel(ch) is False


class TestResolveAlertOrganizations:
    def test_instance_org_priority(self):
        n = AlertLifecycleNotifier(_policy(organizations=[99]))
        assert n._resolve_alert_organizations(_alert(), {"('h1',)": [1, 2]}) == [1, 2]

    def test_policy_fallback(self):
        n = AlertLifecycleNotifier(_policy(organizations=[99]))
        assert n._resolve_alert_organizations(_alert(), {}) == [99]

    def test_empty(self):
        n = AlertLifecycleNotifier(_policy(organizations=[]))
        assert n._resolve_alert_organizations(_alert(), {}) == []


@pytest.mark.django_db
class TestBuildInstanceOrgMap:
    def test_maps_instances_to_orgs(self):
        from apps.monitor.models import MonitorInstanceOrganization
        from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance

        obj = MonitorObject.objects.create(name="ALNObj", level="base")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=5)
        n = AlertLifecycleNotifier(None)
        org_map = n._build_instance_org_map([_alert(monitor_instance_id="('h1',)")])
        assert org_map["('h1',)"] == [5]

    def test_empty_alerts(self):
        n = AlertLifecycleNotifier(None)
        assert n._build_instance_org_map([_alert(monitor_instance_id="")]) == {}


class TestBuildAlertCenterPayload:
    def test_payload_shape(self):
        from datetime import datetime, timezone
        n = AlertLifecycleNotifier(_policy(name="策略A", organizations=[3]))
        alert = _alert(
            id="al-1", policy_id=7, content="CPU高", level="critical", value=90.0,
            status="new", start_event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_event_time=None, dimensions={"k": "v"}, monitor_instance_name="主机1",
            metric_instance_id="m1",
        )
        payload = n._build_alert_center_payload(alert, "created", "sys", "auto", {"('h1',)": [3]})
        assert payload["external_id"] == "al-1"
        assert payload["rule_id"] == "7"
        assert payload["value"] == 90.0
        assert payload["organizations"] == [3]
        assert payload["labels"]["policy_name"] == "策略A"
