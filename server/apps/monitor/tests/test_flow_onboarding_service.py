import pytest

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorObjectOrganizationRule,
)
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.manual_collect import ManualCollectService


def _create_child_default_metric(parent_object: MonitorObject, child_name: str = "SwitchPort") -> MonitorObject:
    child_object = MonitorObject.objects.create(name=child_name, display_name=child_name, parent=parent_object)
    metric_group = MetricGroup.objects.create(monitor_object=child_object, name=f"{child_name} Metrics")
    Metric.objects.create(
        monitor_object=child_object,
        metric_group=metric_group,
        name="traffic_in",
        query="traffic_in_total",
    )
    return child_object


def test_flow_instance_fields_and_protocols_are_persisted(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Flow Device 1",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    instance.refresh_from_db()

    assert instance.cloud_region_id == 1
    assert instance.ip == "10.0.0.12"
    assert instance.fallback_sampling_rate == 1000
    assert instance.enabled_protocols == ["netflow"]

    defaulted_instance = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Flow Device 2",
        monitor_object_id=switch_object.id,
    )

    defaulted_instance.refresh_from_db()

    assert defaulted_instance.fallback_sampling_rate == 1000


def test_create_or_bind_flow_asset_reuses_existing_instance(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    existing = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1],
    )

    existing.refresh_from_db()
    assert result["instance_id"] == existing.id
    assert set(existing.enabled_protocols) == {"netflow", "sflow"}
    assert MonitorInstance.objects.filter(monitor_object_id=switch_object.id, cloud_region_id=1, ip="10.0.0.12").count() == 1


def test_create_or_bind_flow_asset_creates_monitor_side_asset(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1, 2],
        fallback_sampling_rate=2000,
    )

    instance = MonitorInstance.objects.get(id=result["instance_id"])
    assert instance.monitor_object_id == switch_object.id
    assert instance.name == "Core Switch"
    assert instance.cloud_region_id == 1
    assert instance.ip == "10.0.0.12"
    assert instance.fallback_sampling_rate == 2000
    assert instance.enabled_protocols == ["netflow"]
    assert instance.auto is False
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {1, 2}


def test_create_or_bind_flow_asset_restores_soft_deleted_asset(db, monkeypatch):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    restored_rule_calls = []

    monkeypatch.setattr(
        ManualCollectService,
        "create_organization_rule_by_child_object",
        lambda monitor_object_id, instance_id, organization_ids: restored_rule_calls.append(
            (monitor_object_id, instance_id, list(organization_ids))
        ),
    )

    created = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1],
    )
    restored_rule_calls.clear()

    deleted = MonitorInstance.objects.get(id=created["instance_id"])
    deleted.is_deleted = True
    deleted.save(update_fields=["is_deleted"])

    recreated = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[2],
        fallback_sampling_rate=2000,
    )

    restored = MonitorInstance.objects.get(id=created["instance_id"])

    assert recreated["instance_id"] == created["instance_id"]
    assert restored.is_deleted is False
    assert restored.monitor_object_id == switch_object.id
    assert restored.cloud_region_id == 1
    assert restored.ip == "10.0.0.12"
    assert restored.fallback_sampling_rate == 2000
    assert set(restored.enabled_protocols) == {"netflow", "sflow"}
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=restored.id).values_list("organization", flat=True)
    ) == {2}
    assert restored_rule_calls == [(switch_object.id, restored.id, [2])]
    assert MonitorInstance.objects.filter(
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
    ).count() == 1


def test_create_or_bind_flow_asset_rejects_restoring_deleted_asset_with_duplicate_name(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    created = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1],
    )
    deleted = MonitorInstance.objects.get(id=created["instance_id"])
    deleted.is_deleted = True
    deleted.save(update_fields=["is_deleted"])

    MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=1000,
        enabled_protocols=["sflow"],
    )

    with pytest.raises(ValidationAppException, match="实例名称已存在"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=switch_object.id,
            protocol="sflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Core Switch",
            organizations=[2],
        )

    deleted.refresh_from_db()
    assert deleted.is_deleted is True


def test_create_or_bind_flow_asset_rejects_duplicate_tuple_across_supported_monitor_objects(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    router_object = MonitorObject.objects.create(name="Router", display_name="Router")

    switch_result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Asset",
        organizations=[1],
    )
    with pytest.raises(ValidationAppException, match="Flow asset already exists"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=router_object.id,
            protocol="sflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Core Asset",
            organizations=[2],
        )

    switch_instance = MonitorInstance.objects.get(id=switch_result["instance_id"])

    assert switch_instance.monitor_object_id == switch_object.id
    assert switch_instance.ip == "10.0.0.12"
    assert switch_instance.cloud_region_id == 1
    assert not MonitorInstance.objects.filter(monitor_object_id=router_object.id, cloud_region_id=1, ip="10.0.0.12").exists()



def test_update_flow_asset_updates_editable_fields(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow", "sflow"],
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=1)

    result = FlowOnboardingService.update_asset(
        instance_id=instance.id,
        name="Core Switch Updated",
        organizations=[2],
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=3000,
    )

    instance.refresh_from_db()
    assert result["instance_id"] == instance.id
    assert instance.name == "Core Switch Updated"
    assert instance.cloud_region_id == 2
    assert instance.ip == "10.0.0.13"
    assert instance.fallback_sampling_rate == 3000
    assert set(instance.enabled_protocols) == {"netflow", "sflow"}
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {2}



def test_update_flow_asset_rejects_unsupported_monitor_object(db):
    host_object = MonitorObject.objects.create(name="Host", display_name="Host")
    instance = MonitorInstance.objects.create(
        id="('host-device-1',)",
        name="Existing Host",
        monitor_object_id=host_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    with pytest.raises(BaseAppException, match="Unsupported flow monitor object"):
        FlowOnboardingService.update_asset(
            instance_id=instance.id,
            name="Existing Host Updated",
            fallback_sampling_rate=2000,
        )

    instance.refresh_from_db()
    assert instance.name == "Existing Host"
    assert instance.fallback_sampling_rate == 1000
    assert instance.enabled_protocols == ["netflow"]


def test_update_flow_asset_refreshes_child_object_organization_rules_when_organizations_change(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    child_object = _create_child_default_metric(switch_object)
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=1)
    MonitorObjectOrganizationRule.objects.create(
        name=f"{child_object.name}-flow-device-1",
        monitor_object_id=child_object.id,
        rule={
            "type": "metric",
            "metric_id": Metric.objects.get(monitor_object_id=child_object.id).id,
            "filter": [{"name": "instance_id", "method": "=", "value": "flow-device-1"}],
        },
        organizations=[1],
        monitor_instance_id=instance.id,
    )

    FlowOnboardingService.update_asset(
        instance_id=instance.id,
        organizations=[2, 3],
    )

    rules = list(MonitorObjectOrganizationRule.objects.filter(monitor_instance_id=instance.id))
    assert len(rules) == 1
    assert rules[0].monitor_object_id == child_object.id
    assert rules[0].organizations == [2, 3]
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {2, 3}


def test_update_flow_asset_name_only_change_does_not_refresh_flow_env_config(db, monkeypatch):
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

    monkeypatch.setattr(
        FlowOnboardingService,
        "_schedule_region_refresh",
        staticmethod(lambda *region_ids: refresh_calls.append(region_ids)),
    )

    FlowOnboardingService.update_asset(
        instance_id=instance.id,
        name="Core Switch Updated",
    )

    instance.refresh_from_db()
    assert instance.name == "Core Switch Updated"
    assert refresh_calls == []


def test_create_or_bind_flow_asset_refreshes_child_object_organization_rules_when_rebinding_live_asset(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    child_object = _create_child_default_metric(switch_object)
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=1)
    MonitorObjectOrganizationRule.objects.create(
        name=f"{child_object.name}-flow-device-1",
        monitor_object_id=child_object.id,
        rule={
            "type": "metric",
            "metric_id": Metric.objects.get(monitor_object_id=child_object.id).id,
            "filter": [{"name": "instance_id", "method": "=", "value": "flow-device-1"}],
        },
        organizations=[1],
        monitor_instance_id=instance.id,
    )

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[2, 3],
    )

    instance.refresh_from_db()
    rules = list(MonitorObjectOrganizationRule.objects.filter(monitor_instance_id=instance.id))

    assert result["instance_id"] == instance.id
    assert set(instance.enabled_protocols) == {"netflow", "sflow"}
    assert len(rules) == 1
    assert rules[0].monitor_object_id == child_object.id
    assert rules[0].organizations == [2, 3]
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {2, 3}


def test_create_or_bind_flow_asset_preserves_zero_fallback_sampling_rate(db):
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

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        fallback_sampling_rate=0,
    )

    instance.refresh_from_db()

    assert result["instance_id"] == instance.id
    assert instance.fallback_sampling_rate == 0


def test_create_or_bind_flow_asset_with_explicit_empty_organizations_clears_bindings(db):
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
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=1)
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=2)

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[],
        instance_id=instance.id,
    )

    instance.refresh_from_db()
    assert result["instance_id"] == instance.id
    assert set(instance.enabled_protocols) == {"netflow", "sflow"}
    assert not MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).exists()


def test_create_or_bind_flow_asset_without_organizations_keeps_existing_bindings(db):
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
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=1)

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        instance_id=instance.id,
    )

    instance.refresh_from_db()
    assert result["instance_id"] == instance.id
    assert set(instance.enabled_protocols) == {"netflow", "sflow"}
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {1}


def test_create_or_bind_flow_asset_rejects_duplicate_tuple_when_rebinding_specific_instance(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    reused = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Flow Asset A",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    other = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Flow Asset B",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=1000,
        enabled_protocols=["sflow"],
    )

    with pytest.raises(ValidationAppException, match="Flow asset already exists"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=switch_object.id,
            protocol="sflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Flow Asset B",
            organizations=[1],
            instance_id=other.id,
        )

    reused.refresh_from_db()
    other.refresh_from_db()
    assert reused.cloud_region_id == 1
    assert reused.ip == "10.0.0.12"
    assert reused.enabled_protocols == ["netflow"]
    assert other.cloud_region_id == 2
    assert other.ip == "10.0.0.13"
    assert other.enabled_protocols == ["sflow"]
    assert MonitorInstance.objects.filter(monitor_object_id=switch_object.id, cloud_region_id=1, ip="10.0.0.12").count() == 1


def test_update_flow_asset_rejects_duplicate_tuple_when_moving_asset(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    existing = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Flow Asset A",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    moving = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Flow Asset B",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=2000,
        enabled_protocols=["sflow"],
    )

    with pytest.raises(ValidationAppException, match="Flow asset already exists"):
        FlowOnboardingService.update_asset(
            instance_id=moving.id,
            cloud_region_id=1,
            ip="10.0.0.12",
        )

    existing.refresh_from_db()
    moving.refresh_from_db()
    assert existing.cloud_region_id == 1
    assert existing.ip == "10.0.0.12"
    assert moving.cloud_region_id == 2
    assert moving.ip == "10.0.0.13"
    assert MonitorInstance.objects.filter(monitor_object_id=switch_object.id, cloud_region_id=1, ip="10.0.0.12").count() == 1


def test_update_flow_asset_rejects_duplicate_name_with_validation_error(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Flow Asset A",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )
    target = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Flow Asset B",
        monitor_object_id=switch_object.id,
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=2000,
        enabled_protocols=["sflow"],
    )

    with pytest.raises(ValidationAppException, match="实例名称已存在"):
        FlowOnboardingService.update_asset(
            instance_id=target.id,
            name="Flow Asset A",
        )

    target.refresh_from_db()
    assert target.name == "Flow Asset B"
    assert target.cloud_region_id == 2
    assert target.ip == "10.0.0.13"


def test_create_manual_collect_instance_rejects_flow_only_fields_with_validation_error(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    with pytest.raises(ValidationAppException, match="Use flow_asset for flow asset fields"):
        ManualCollectService.create_manual_collect_instance(
            {
                "id": "flow-bypass",
                "name": "Core Switch",
                "monitor_object_id": switch_object.id,
                "cloud_region_id": 1,
                "ip": "10.0.0.12",
                "fallback_sampling_rate": 2000,
                "enabled_protocols": ["netflow"],
                "organizations": [1],
            }
        )

    assert not MonitorInstance.objects.filter(
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
    ).exists()


def test_create_or_bind_flow_asset_rejects_unknown_protocol(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    with pytest.raises(ValidationAppException, match="Unsupported flow protocol"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=switch_object.id,
            protocol="ipfix",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Core Switch",
            organizations=[1],
        )


def test_create_or_bind_flow_asset_rejects_unsupported_monitor_object(db):
    unsupported_object = MonitorObject.objects.create(name="Host", display_name="Host")

    with pytest.raises(ValidationAppException, match="Unsupported flow monitor object"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=unsupported_object.id,
            protocol="netflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Core Host",
            organizations=[1],
        )


def test_create_or_bind_flow_asset_rejects_explicit_binding_for_unsupported_monitor_object(db):
    unsupported_object = MonitorObject.objects.create(name="Host", display_name="Host")
    existing = MonitorInstance.objects.create(
        id="('host-device-1',)",
        name="Existing Host",
        monitor_object_id=unsupported_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    with pytest.raises(ValidationAppException, match="Unsupported flow monitor object"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=unsupported_object.id,
            protocol="sflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Existing Host",
            instance_id=existing.id,
        )

    existing.refresh_from_db()
    assert existing.enabled_protocols == ["netflow"]


def test_create_or_bind_flow_asset_rejects_nonexistent_monitor_object(db):
    with pytest.raises(ValidationAppException, match="Monitor object does not exist"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=999999,
            protocol="netflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Missing Object",
            organizations=[1],
        )


def test_create_or_bind_flow_asset_rejects_nonexistent_instance(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    with pytest.raises(ValidationAppException, match="Monitor instance does not exist"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=switch_object.id,
            protocol="netflow",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Missing Instance",
            instance_id="missing-instance",
        )
