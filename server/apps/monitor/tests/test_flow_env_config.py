import json
import types

from apps.monitor.models import MonitorInstance, MonitorObject
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import CloudRegion, Collector, CollectorConfiguration, Node


def _create_telegraf_collector():
    collector, _ = Collector.objects.get_or_create(
        node_operating_system="linux",
        cpu_architecture="x86_64",
        name="Telegraf",
        defaults={
            "id": "telegraf-linux-flow-test",
            "service_type": "exec",
            "executable_path": "/opt/fusion-collectors/bin/telegraf",
            "execute_parameters": "--config %s",
            "validation_parameters": "",
            "default_template": "",
            "introduction": "Telegraf",
            "default_config": {},
            "tags": ["linux", "monitor"],
            "package_name": "telegraf",
        },
    )
    return collector


def _create_node(*, node_id, cloud_region, node_type):
    return Node.objects.create(
        id=node_id,
        name=node_id,
        ip="127.0.0.1",
        operating_system="linux",
        collector_configuration_directory="/etc/telegraf",
        cloud_region=cloud_region,
        node_type=node_type,
    )


def _create_telegraf_config(*, name, cloud_region, node, env_config=None, is_pre=True):
    config = CollectorConfiguration.objects.create(
        name=name,
        collector=_create_telegraf_collector(),
        config_template="[[outputs.nats]]",
        cloud_region=cloud_region,
        is_pre=is_pre,
        env_config=env_config or {},
    )
    config.nodes.add(node)
    return config


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
            "instance_id": "flow-device-1",
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


def test_refresh_collect_configs_updates_container_telegraf_base_config(db, monkeypatch):
    cloud_region = CloudRegion.objects.create(name="flow-region-1")
    container_node = _create_node(
        node_id="flow-container-node-1",
        cloud_region=cloud_region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    host_node = _create_node(
        node_id="flow-host-node-1",
        cloud_region=cloud_region,
        node_type=ControllerConstants.NODE_TYPE_HOST,
    )
    container_config = _create_telegraf_config(
        name="telegraf-flow-container-config-1",
        cloud_region=cloud_region,
        node=container_node,
        env_config={"EXISTING_ENV": "preserved"},
    )
    host_config = _create_telegraf_config(
        name="telegraf-flow-host-config-1",
        cloud_region=cloud_region,
        node=host_node,
        env_config={"EXISTING_ENV": "host-preserved"},
    )

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    monkeypatch.setattr(
        FlowEnvConfigService,
        "build_asset_map",
        classmethod(
            lambda cls, *, cloud_region_id: {
                f"{cloud_region_id}:10.0.0.12": {
                    "instance_id": "flow-device-1",
                    "instance_type": "switch",
                    "fallback_sampling_rate": 1000,
                    "protocols": ["netflow"],
                }
            }
        ),
    )

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=cloud_region.id)

    container_config.refresh_from_db()
    host_config.refresh_from_db()
    assert refreshed == 1
    expected_asset_map = json.dumps(
        {
            f"{cloud_region.id}:10.0.0.12": {
                "fallback_sampling_rate": 1000,
                "instance_id": "flow-device-1",
                "instance_type": "switch",
                "protocols": ["netflow"],
            }
        },
        sort_keys=True,
    )
    assert container_config.env_config == {
        "EXISTING_ENV": "preserved",
        "FLOW_ASSET_MAP_JSON": expected_asset_map,
    }
    assert host_config.env_config == {"EXISTING_ENV": "host-preserved"}


def test_refresh_collect_configs_updates_all_container_telegraf_base_configs(db, monkeypatch):
    cloud_region = CloudRegion.objects.create(name="flow-region-2")
    first_node = _create_node(
        node_id="flow-container-node-2a",
        cloud_region=cloud_region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    second_node = _create_node(
        node_id="flow-container-node-2b",
        cloud_region=cloud_region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    first_config = _create_telegraf_config(name="telegraf-flow-container-config-2a", cloud_region=cloud_region, node=first_node)
    second_config = _create_telegraf_config(name="telegraf-flow-container-config-2b", cloud_region=cloud_region, node=second_node)

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    monkeypatch.setattr(
        FlowEnvConfigService,
        "build_asset_map",
        classmethod(
            lambda cls, *, cloud_region_id: {
                f"{cloud_region_id}:10.0.0.12": {
                    "instance_id": "flow-device-1",
                    "instance_type": "switch",
                    "fallback_sampling_rate": 1000,
                    "protocols": ["netflow"],
                }
            }
        ),
    )

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=cloud_region.id)

    first_config.refresh_from_db()
    second_config.refresh_from_db()
    assert refreshed == 2
    assert "FLOW_ASSET_MAP_JSON" in first_config.env_config
    assert "FLOW_ASSET_MAP_JSON" in second_config.env_config


def test_refresh_collect_configs_logs_and_skips_when_container_telegraf_base_config_missing(db, monkeypatch):
    cloud_region = CloudRegion.objects.create(name="flow-region-3")
    logged = []

    monkeypatch.setattr("apps.monitor.services.flow_env_config.logger.info", lambda message, region_id: logged.append((message, region_id)))

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=cloud_region.id)

    assert refreshed == 0
    assert logged == [("未找到可刷新的 Flow Telegraf 基础配置: cloud_region_id=%s", cloud_region.id)]


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
    monkeypatch.setattr(
        FlowOnboardingService,
        "_schedule_region_refresh",
        staticmethod(lambda *region_ids: refresh_calls.append(region_ids)),
    )

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
    monkeypatch.setattr(
        "apps.monitor.services.flow_onboarding.logger.exception",
        lambda message, region_id: logged.append((message, region_id)),
    )

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


def test_refresh_collect_configs_continues_when_single_base_config_update_fails(db, monkeypatch):
    cloud_region = CloudRegion.objects.create(name="flow-region-4")
    broken_node = _create_node(
        node_id="flow-container-node-4a",
        cloud_region=cloud_region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    healthy_node = _create_node(
        node_id="flow-container-node-4b",
        cloud_region=cloud_region,
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    broken_config = _create_telegraf_config(name="telegraf-flow-container-config-4a", cloud_region=cloud_region, node=broken_node)
    healthy_config = _create_telegraf_config(name="telegraf-flow-container-config-4b", cloud_region=cloud_region, node=healthy_node)
    logged = []
    original_save = CollectorConfiguration.save

    def save_with_failure(self, *args, **kwargs):
        if self.id == broken_config.id:
            raise RuntimeError("boom")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(CollectorConfiguration, "save", save_with_failure)
    monkeypatch.setattr(
        "apps.monitor.services.flow_env_config.logger.exception",
        lambda message, config_id: logged.append((message, config_id)),
    )

    from apps.monitor.services.flow_env_config import FlowEnvConfigService

    monkeypatch.setattr(
        FlowEnvConfigService,
        "build_asset_map",
        classmethod(
            lambda cls, *, cloud_region_id: {
                f"{cloud_region_id}:10.0.0.12": {
                    "instance_id": "flow-device-1",
                    "instance_type": "switch",
                    "fallback_sampling_rate": 1000,
                    "protocols": ["netflow"],
                }
            }
        ),
    )

    refreshed = FlowEnvConfigService.refresh_collect_configs(cloud_region_id=cloud_region.id)

    healthy_config.refresh_from_db()
    assert refreshed == 2
    assert "FLOW_ASSET_MAP_JSON" in healthy_config.env_config
    assert logged == [("刷新 Flow Telegraf 基础配置 env_config 失败: config_id=%s", broken_config.id)]
