import pytest

from apps.monitor.filters.monitor_policy import exclude_policy_group_rules
from apps.monitor.models import (
    CollectConfig,
    Metric,
    MetricGroup,
    MonitorAlert,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPlugin,
    MonitorPolicy,
    PolicyInstanceBaseline,
    PolicyTemplate,
)
from apps.monitor.services.policy import PolicyService
from apps.monitor.services.policy_group import PolicyGroupService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db


def _object():
    return MonitorObject.objects.create(name="HostGroupObj", level="base")


def _plugin(monitor_object, name):
    plugin = MonitorPlugin.objects.create(name=name, collector="Telegraf", collect_type="host")
    plugin.monitor_object.add(monitor_object)
    return plugin


def _template(monitor_object, plugin, name, threshold=80):
    metric_group, _ = MetricGroup.objects.get_or_create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="os",
    )
    Metric.objects.get_or_create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name="cpu_usage_total",
        defaults={"metric_group": metric_group},
    )
    return PolicyTemplate.objects.create(
        key=f"builtin-{plugin.name}-{name}",
        scope_key="builtin",
        template_type=PolicyTemplate.TYPE_BUILTIN,
        organization=None,
        monitor_object=monitor_object,
        plugin=plugin,
        name=name,
        config={"metric_name": "cpu_usage_total", "threshold": [{"level": "warning", "value": threshold, "method": ">="}]},
    )


def _instance(monitor_object, name, organization):
    instance = MonitorInstance.objects.create(id=f"('{name}',)", name=name, monitor_object=monitor_object)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=organization)
    return instance


def _collect(instance, plugin):
    CollectConfig.objects.create(
        id=f"cfg-{instance.name}-{plugin.name}",
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector="Telegraf",
        collect_type="host",
        config_type=plugin.name,
        file_type="toml",
    )


def test_create_group_keeps_one_policy_per_rule_and_skips_notice_users():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    templates = [
        _template(monitor_object, wmi, "CPU 过高"),
        _template(monitor_object, ssh, "CPU 过高"),
    ]
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=templates,
    )

    assert group.memberships.count() == 0
    assert group.rules.count() == 2
    assert set(group.rules.values_list("plugin__name", flat=True)) == {"WMI", "SSH"}
    assert list(group.rules.values_list("push_alert_center", flat=True)) == [True, True]
    policies = [rule.policy for rule in group.rules.select_related("policy")]
    assert len(policies) == 2
    assert all(policy.notice_users == [] for policy in policies)
    assert all(policy.source_template_id is None for policy in policies)
    assert all(policy.source == {"type": "instance", "values": []} for policy in policies)


def test_join_covers_only_the_matching_plugin_and_one_group():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU"), _template(monitor_object, ssh, "SSH CPU")],
    )
    other = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="另一组",
        templates=[_template(monitor_object, wmi, "WMI 内存")],
    )
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)

    PolicyGroupService.join(instance=host, group=other)
    PolicyGroupService.join(instance=host, group=group)

    host.policy_group_membership.refresh_from_db()
    assert host.policy_group_membership.state == "member"
    assert host.policy_group_membership.policy_group_id == group.id
    assert other.memberships.filter(state="member").count() == 0
    by_plugin = {rule.plugin.name: rule.policy.source["values"] for rule in group.rules.select_related("policy", "plugin")}
    assert by_plugin["WMI"] == [host.id]
    assert by_plugin["SSH"] == []
    assert MonitorPolicy.objects.filter(group_rule__group=group).count() == 2


def test_leave_closes_open_alerts_and_blocks_auto_rejoin_state():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    policy = group.rules.get().policy
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new", alert_type="alert")

    PolicyGroupService.leave(instance=host)

    host.policy_group_membership.refresh_from_db()
    alert.refresh_from_db()
    policy.refresh_from_db()
    assert host.policy_group_membership.state == "declined"
    assert host.policy_group_membership.policy_group_id is None
    assert alert.status == "closed"
    assert policy.source["values"] == []


def test_join_does_not_create_no_data_baseline_for_a_silent_instance():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    policy = group.rules.get().policy

    assert PolicyGroupService.has_reported_baseline(policy, host.id) is False
    assert PolicyInstanceBaseline.objects.filter(policy_id=policy.id).count() == 0


def test_template_sync_does_not_change_group_rules_and_list_hides_them():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, wmi, "WMI CPU", threshold=80)
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[template],
    )
    policy = group.rules.get().policy
    original_threshold = policy.threshold
    template.config = {**template.config, "threshold": [{"level": "warning", "value": 99, "method": ">="}]}
    template.save(update_fields=["config"])

    PolicyService.sync_issued_policies_from_template(template, type("User", (), {"username": "tester"})())

    policy.refresh_from_db()
    assert policy.threshold == original_threshold
    legacy = MonitorPolicy.objects.create(monitor_object=monitor_object, name="旧策略", algorithm="avg", source={"type": "instance", "values": []})
    visible = list(exclude_policy_group_rules(MonitorPolicy.objects.all()).values_list("name", flat=True))
    assert visible == ["旧策略"]
    assert legacy.name == "旧策略"


def test_auto_join_uses_builtin_templates_once_and_skips_repeat():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    _template(monitor_object, wmi, "WMI CPU")
    host = _instance(monitor_object, "node-01", 1)
    _collect(host, wmi)

    membership = PolicyGroupService.consider_auto_join(host, [1])
    again = PolicyGroupService.consider_auto_join(host, [1])

    assert membership.state == "member"
    assert again.policy_group_id == membership.policy_group_id
    assert membership.policy_group.origin == "system"
    assert membership.policy_group.rules.count() == 1
    PolicyGroupService.ensure_default(organization=1, monitor_object=monitor_object)
    assert membership.policy_group.rules.count() == 1


def test_auto_join_skips_when_no_template_multiple_orgs_or_legacy_policy():
    monitor_object = _object()
    bare = _instance(monitor_object, "bare", 1)
    skipped = PolicyGroupService.consider_auto_join(bare, [1])
    assert skipped.state == "skipped"
    assert skipped.policy_group_id is None
    PolicyGroupService.ensure_default(organization=1, monitor_object=monitor_object)
    bare.policy_group_membership.refresh_from_db()
    assert bare.policy_group_membership.state == "skipped"

    multi = _instance(monitor_object, "multi", 1)
    MonitorInstanceOrganization.objects.create(monitor_instance=multi, organization=2)
    assert PolicyGroupService.consider_auto_join(multi, [1, 2]).state == "skipped"

    wmi = _plugin(monitor_object, "WMI")
    _template(monitor_object, wmi, "WMI CPU")
    legacy_host = _instance(monitor_object, "legacy", 1)
    MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="旧策略",
        algorithm="avg",
        source={"type": "instance", "values": [legacy_host.id]},
    )
    assert PolicyGroupService.consider_auto_join(legacy_host, [1]).state == "skipped"


def test_join_rejects_instance_outside_group_organization():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    host = _instance(monitor_object, "web-01", 2)

    with pytest.raises(BaseAppException, match="不属于该策略组的组织"):
        PolicyGroupService.join(instance=host, group=group)
