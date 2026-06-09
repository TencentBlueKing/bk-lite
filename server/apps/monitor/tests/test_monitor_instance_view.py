import types

from apps.monitor.models.collect_config import CollectConfig
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


def test_remove_monitor_instance_always_cleans_configs(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Host", display_name="Host")
    instance = MonitorInstance.objects.create(
        id="('host-1',)",
        name="Host-1",
        monitor_object_id=monitor_object.id,
    )
    child_config = CollectConfig.objects.create(
        id="child-cfg",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )
    base_config = CollectConfig.objects.create(
        id="base-cfg",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host-base",
        config_type="agent",
        file_type="toml",
        is_child=False,
    )
    cleanup_calls = {"child": None, "base": None}

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(monitor_instance_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(monitor_instance_view, "cleanup_policy_sources", lambda instance_ids: None)
    monkeypatch.setattr(
        monitor_instance_view,
        "NodeMgmt",
        lambda: types.SimpleNamespace(
            delete_child_configs=lambda ids: cleanup_calls.__setitem__("child", ids),
            delete_configs=lambda ids: cleanup_calls.__setitem__("base", ids),
        ),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)

    instance.refresh_from_db()
    assert instance.is_deleted is True
    assert cleanup_calls == {"child": [child_config.id], "base": [base_config.id]}
    assert CollectConfig.objects.filter(monitor_instance_id=instance.id).count() == 0
