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


def test_build_flow_asset_map_excludes_unsupported_monitor_objects(db):
    unsupported_object = MonitorObject.objects.create(name="Host", display_name="Host")
    MonitorInstance.objects.create(
        id="('host-device-1',)",
        name="Host Device",
        monitor_object_id=unsupported_object.id,
        cloud_region_id=1,
        ip="10.0.0.30",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    assert FlowEnvConfigService.build_asset_map(cloud_region_id=1) == {}


def test_refresh_collect_configs_only_updates_env_config(monkeypatch):
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

    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.CollectConfig",
        types.SimpleNamespace(objects=StubCollectConfigManager()),
    )
    monkeypatch.setattr("apps.monitor.services.flow_env_config.InstanceConfigService", StubInstanceConfigService)

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
    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=1)

    assert refreshed == 2
    assert updated == [
        (
            None,
            {
                "id": "base-config-id",
                "content": {"config": {"service_address": ":2055"}},
                "env_config": {
                    "EXISTING_ENV": "preserved",
                    "FLOW_ASSET_MAP_JSON": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                },
            },
        ),
        (
            {
                "id": "child-config-id",
                "content": {"config": {"service_address": ":2055"}},
                "env_config": {
                    "OTHER_ENV__CHILD-CONFIG-ID": "preserved",
                    "FLOW_ASSET_MAP_JSON__CHILD-CONFIG-ID": "{\"1:10.0.0.12\": {\"fallback_sampling_rate\": 1000, \"instance_id\": \"('flow-device-1',)\", \"instance_type\": \"switch\", \"protocols\": [\"netflow\"]}}",
                },
            },
            None,
        ),
    ]


def test_refresh_collect_configs_only_updates_target_cloud_region(monkeypatch):
    target_config = types.SimpleNamespace(
        id="target-config-id",
        collector="Telegraf",
        collect_type="netflow",
        config_type="flow",
        monitor_plugin_id=None,
        monitor_instance_id="('flow-device-1',)",
        is_child=False,
        monitor_instance=types.SimpleNamespace(
            cloud_region_id=1,
            monitor_object=types.SimpleNamespace(name="Switch"),
        ),
    )
    off_target_config = types.SimpleNamespace(
        id="off-target-config-id",
        collector="Telegraf",
        collect_type="sflow",
        config_type="flow",
        monitor_plugin_id=None,
        monitor_instance_id="('flow-device-2',)",
        is_child=False,
        monitor_instance=types.SimpleNamespace(
            cloud_region_id=2,
            monitor_object=types.SimpleNamespace(name="Router"),
        ),
    )

    class StubCollectConfigQuerySet:
        def __init__(self, items):
            self.items = items

        def select_related(self, *args):
            return self

        def order_by(self, *args):
            return self.items

    class StubCollectConfigManager:
        def __init__(self, items):
            self.items = items
            self.filter_kwargs = None

        def filter(self, **kwargs):
            self.filter_kwargs = kwargs
            return StubCollectConfigQuerySet(
                [
                    item
                    for item in self.items
                    if item.collect_type in kwargs["collect_type__in"]
                    and item.monitor_instance.cloud_region_id == kwargs["monitor_instance__cloud_region_id"]
                ]
            )

    config_manager = StubCollectConfigManager([target_config, off_target_config])
    updated_ids = []

    class StubInstanceConfigService:
        @staticmethod
        def get_config_content(ids):
            return {
                "base": {
                    "id": ids[0],
                    "content": {"config": {"service_address": ":2055"}},
                    "env_config": {},
                }
            }

        @staticmethod
        def update_instance_config(child_info, base_info):
            updated_ids.append((child_info or base_info)["id"])

    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.CollectConfig",
        types.SimpleNamespace(objects=config_manager),
    )
    monkeypatch.setattr("apps.monitor.services.flow_env_config.InstanceConfigService", StubInstanceConfigService)

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

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=1)

    assert refreshed == 1
    assert config_manager.filter_kwargs == {
        "collect_type__in": ("netflow", "sflow"),
        "monitor_instance__cloud_region_id": 1,
    }
    assert updated_ids == ["target-config-id"]


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


def test_create_or_bind_flow_asset_refreshes_old_and_new_cloud_regions_when_rebinding_instance(db, monkeypatch):
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
        "apps.monitor.services.flow_onboarding.FlowOnboardingService._schedule_region_refresh",
        lambda *region_ids: refresh_calls.extend(region_ids),
    )

    FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=2,
        ip="10.0.0.13",
        name="Core Switch",
        organizations=[1],
        instance_id=instance.id,
    )

    assert refresh_calls == [1, 2]


def test_update_flow_asset_refresh_uses_locked_previous_region_state(db, monkeypatch):
    refresh_calls = []
    unlocked_instance = types.SimpleNamespace(
        id="flow-asset",
        monitor_object_id=1,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
    )
    locked_instance = types.SimpleNamespace(
        id="flow-asset",
        monitor_object_id=1,
        cloud_region_id=3,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
    )

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


def test_refresh_collect_configs_continues_when_single_config_update_fails(monkeypatch):
    config_items = [
        types.SimpleNamespace(
            id="broken-config-id",
            collect_type="netflow",
            is_child=False,
        ),
        types.SimpleNamespace(
            id="healthy-config-id",
            collect_type="sflow",
            is_child=False,
        ),
    ]

    class StubCollectConfigManager:
        def filter(self, **kwargs):
            return self

        def select_related(self, *args):
            return self

        def order_by(self, *args):
            return config_items

    updated = []
    logged = []

    class StubInstanceConfigService:
        @staticmethod
        def get_config_content(ids):
            return {
                "base": {
                    "id": ids[0],
                    "content": {"config": {"service_address": ":2055"}},
                    "env_config": {},
                }
            }

        @staticmethod
        def update_instance_config(child_info, base_info):
            config_id = (child_info or base_info)["id"]
            if config_id == "broken-config-id":
                raise RuntimeError("boom")
            updated.append(config_id)

    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.CollectConfig",
        types.SimpleNamespace(objects=StubCollectConfigManager()),
    )
    monkeypatch.setattr("apps.monitor.services.flow_env_config.InstanceConfigService", StubInstanceConfigService)
    monkeypatch.setattr("apps.monitor.services.flow_env_config.logger.exception", lambda message, config_id: logged.append((message, config_id)))

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    monkeypatch.setattr(
        FlowEnvConfigService,
        "build_asset_map",
        classmethod(lambda cls, *, cloud_region_id: {f"{cloud_region_id}:10.0.0.12": {"instance_id": "x", "instance_type": "switch", "fallback_sampling_rate": 1000, "protocols": ["netflow"]}}),
    )

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=1)

    assert refreshed == 2
    assert updated == ["healthy-config-id"]
    assert logged == [("刷新 Flow env_config 失败: config_id=%s", "broken-config-id")]
