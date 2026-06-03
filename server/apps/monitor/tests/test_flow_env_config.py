import types

from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.flow_onboarding import FlowOnboardingService


def test_build_flow_asset_map_uses_cloud_region_ip_composite_key(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow", "sflow"],
    )

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    payload = FlowEnvConfigService.build_asset_map(cloud_region_id=1)

    assert payload == {
        "1:10.0.0.12": {
            "instance_id": "('flow-device-1',)",
            "instance_type": "switch",
            "fallback_sampling_rate": 1000,
            "protocols": ["netflow", "sflow"],
        }
    }


def test_refresh_collect_configs_uses_controller_rendering_and_env_patch(monkeypatch):
    config_items = [
        types.SimpleNamespace(
            id="base-config-id",
            collector="Telegraf",
            collect_type="netflow",
            config_type="flow",
            monitor_plugin_id=None,
            monitor_instance_id="('flow-device-1',)",
            is_child=False,
            monitor_instance=types.SimpleNamespace(monitor_object=types.SimpleNamespace(name="Switch")),
        ),
        types.SimpleNamespace(
            id="child-config-id",
            collector="Telegraf",
            collect_type="netflow",
            config_type="flow",
            monitor_plugin_id=None,
            monitor_instance_id="('flow-device-1',)",
            is_child=True,
            monitor_instance=types.SimpleNamespace(monitor_object=types.SimpleNamespace(name="Switch")),
        ),
    ]

    class StubCollectConfigManager:
        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return self

        def select_related(self, *args):
            return self

        def order_by(self, *args):
            return config_items

    updated = []
    render_calls = []

    class StubInstanceConfigService:
        @staticmethod
        def get_config_content(ids):
            config_id = ids[0]
            if config_id == "base-config-id":
                return {
                    "base": {
                        "id": config_id,
                        "content": {"config": {"service_address": ":2055"}},
                        "env_config": {"EXISTING_ENV": "preserved"},
                    }
                }
            return {
                "child": {
                    "id": config_id,
                    "content": {"config": {"service_address": ":2055"}},
                    "env_config": {"OTHER_ENV__CHILD-CONFIG-ID": "preserved"},
                }
            }

        @staticmethod
        def update_instance_config(child_info, base_info):
            updated.append((child_info, base_info))

    class StubController:
        def __init__(self, data):
            self.data = data

        def get_templates_by_collector(self, collector, collect_type):
            assert collector == "Telegraf"
            assert collect_type == "netflow"
            return {
                "flow": [
                    {"config_type": "main", "file_type": "yaml", "content": "ignored"},
                    {"config_type": "child", "file_type": "yaml", "content": "ignored"},
                ]
            }

        def render_template(self, template_content, context):
            render_calls.append({"data": self.data, "context": dict(context)})
            return "rendered-config"

    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.CollectConfig",
        types.SimpleNamespace(objects=StubCollectConfigManager()),
    )
    monkeypatch.setattr("apps.monitor.services.flow_env_config.InstanceConfigService", StubInstanceConfigService)
    monkeypatch.setattr("apps.monitor.services.flow_env_config.Controller", StubController)

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    monkeypatch.setattr(
        FlowEnvConfigService,
        "build_asset_map",
        classmethod(
            lambda cls, *, cloud_region_id: {
                f"{cloud_region_id}:10.0.0.12": {
                    "instance_id": "('flow-device-1',)",
                    "instance_type": "switch",
                    "fallback_sampling_rate": 1000,
                    "protocols": ["netflow"],
                }
            }
        ),
    )
    monkeypatch.setattr(
        FlowEnvConfigService,
        "_parse_rendered_content",
        staticmethod(
            lambda rendered_content, file_type: {
                "config": {
                    "service_address": ":2055",
                    "asset_map": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                }
            }
        ),
    )

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=1)

    assert refreshed == 2
    assert [call["data"] for call in render_calls] == [
        {"collector": "Telegraf", "collect_type": "netflow", "monitor_plugin_id": None},
        {"collector": "Telegraf", "collect_type": "netflow", "monitor_plugin_id": None},
    ]
    assert all(call["context"]["logical_instance_value"] == "flow-device-1" for call in render_calls)
    assert all(call["context"]["instance_type"] == "switch" for call in render_calls)
    assert all(call["context"]["ENV_FLOW_ASSET_MAP_JSON"] for call in render_calls)
    assert updated == [
        (
            None,
            {
                "id": "base-config-id",
                "content": {
                    "config": {
                        "service_address": ":2055",
                        "asset_map": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                    }
                },
                "env_config": {
                    "EXISTING_ENV": "preserved",
                    "FLOW_ASSET_MAP_JSON": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                },
            },
        ),
        (
            {
                "id": "child-config-id",
                "content": {
                    "config": {
                        "service_address": ":2055",
                        "asset_map": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                    }
                },
                "env_config": {
                    "OTHER_ENV__CHILD-CONFIG-ID": "preserved",
                    "FLOW_ASSET_MAP_JSON__CHILD-CONFIG-ID": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                },
            },
            None,
        ),
    ]


def test_create_or_bind_flow_asset_refreshes_current_cloud_region(db, monkeypatch):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    refresh_calls = []

    monkeypatch.setattr("apps.monitor.services.flow_onboarding.transaction.on_commit", lambda callback: callback())
    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.FlowEnvConfigService.refresh_collect_configs",
        lambda *, cloud_region_id: refresh_calls.append(cloud_region_id),
    )

    FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1],
    )

    assert refresh_calls == [1]


def test_update_flow_asset_refreshes_old_and_new_cloud_regions_when_moved(db, monkeypatch):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    refresh_calls = []

    monkeypatch.setattr("apps.monitor.services.flow_onboarding.transaction.on_commit", lambda callback: callback())
    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.FlowEnvConfigService.refresh_collect_configs",
        lambda *, cloud_region_id: refresh_calls.append(cloud_region_id),
    )

    FlowOnboardingService.update_asset(
        instance_id=instance.id,
        cloud_region_id=2,
        ip="10.0.0.13",
    )

    assert refresh_calls == [1, 2]


def test_update_flow_asset_refresh_uses_locked_previous_region_state(db, monkeypatch):
    refresh_calls = []
    unlocked_instance = types.SimpleNamespace(id="flow-asset", monitor_object_id=1, cloud_region_id=1, ip="10.0.0.12")
    locked_instance = types.SimpleNamespace(id="flow-asset", monitor_object_id=1, cloud_region_id=3, ip="10.0.0.12")

    monkeypatch.setattr(
        FlowOnboardingService,
        "_get_instance",
        classmethod(lambda cls, *, instance_id, for_update=False, **kwargs: locked_instance if for_update else unlocked_instance),
    )
    monkeypatch.setattr(FlowOnboardingService, "lock_monitor_object", classmethod(lambda cls, **kwargs: None))
    monkeypatch.setattr(FlowOnboardingService, "_ensure_tuple_available", classmethod(lambda cls, **kwargs: None))
    monkeypatch.setattr(FlowOnboardingService, "_normalize_duplicate_name_conflict", classmethod(lambda cls, func, **kwargs: None))
    monkeypatch.setattr(FlowOnboardingService, "_restore_organization_rules", staticmethod(lambda **kwargs: None))
    monkeypatch.setattr(FlowOnboardingService, "_schedule_region_refresh", staticmethod(lambda *region_ids: refresh_calls.append(region_ids)))

    FlowOnboardingService.update_asset(
        instance_id="flow-asset",
        cloud_region_id=5,
    )

    assert refresh_calls == [(3, 5)]


def test_refresh_callback_logs_and_swallows_errors(db, monkeypatch):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    logged = []

    monkeypatch.setattr("apps.monitor.services.flow_onboarding.transaction.on_commit", lambda callback: callback())
    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.FlowEnvConfigService.refresh_collect_configs",
        lambda *, cloud_region_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr("apps.monitor.services.flow_onboarding.logger.exception", lambda message, region_id: logged.append((message, region_id)))

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1],
    )

    assert result["instance_id"]
    assert logged == [("刷新 Flow env_config 失败: cloud_region_id=%s", 1)]
