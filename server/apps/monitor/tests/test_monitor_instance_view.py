import types

from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.views import monitor_instance as monitor_instance_view


def test_remove_monitor_instance_refreshes_flow_cloud_regions(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=monitor_object.id,
        cloud_region_id=3,
        ip="10.0.0.12",
        enabled_protocols=["netflow"],
    )
    refresh_calls = []

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(monitor_instance_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(monitor_instance_view, "cleanup_policy_sources", lambda instance_ids: None)
    monkeypatch.setattr(
        "apps.monitor.services.flow_onboarding.FlowOnboardingService._schedule_region_refresh",
        lambda *region_ids: refresh_calls.append(region_ids),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)

    instance.refresh_from_db()
    assert instance.is_deleted is True
    assert refresh_calls == [(3,)]


def test_remove_monitor_instance_registers_refresh_before_cleanup(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Edge Switch",
        monitor_object_id=monitor_object.id,
        cloud_region_id=5,
        ip="10.0.0.22",
        enabled_protocols=["sflow"],
    )
    refresh_calls = []

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(monitor_instance_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(
        "apps.monitor.services.flow_onboarding.FlowOnboardingService._schedule_region_refresh",
        lambda *region_ids: refresh_calls.append(region_ids),
    )
    monkeypatch.setattr(
        monitor_instance_view,
        "cleanup_policy_sources",
        lambda instance_ids: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    try:
        monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)
        assert False, "expected cleanup failure"
    except RuntimeError as error:
        assert str(error) == "cleanup failed"

    instance.refresh_from_db()
    assert instance.is_deleted is True
    assert refresh_calls == [(5,)]
