import copy
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
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
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyInstanceBaseline,
    PolicyTemplate,
)
from apps.monitor.services.policy import PolicyService
from apps.monitor.services.policy_group import PolicyGroupService
from apps.monitor.views.policy_group import _serialize_group

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
    return CollectConfig.objects.create(
        id=f"cfg-{instance.name}-{plugin.name}",
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector="Telegraf",
        collect_type="host",
        config_type=plugin.name,
        file_type="toml",
    )


def test_member_group_names_only_current_org_members():
    monitor_object = _object()
    plugin = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, plugin, "CPU")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[template],
    )
    foreign = PolicyGroupService.create_from_templates(
        organization=2,
        monitor_object=monitor_object,
        name="其他组织",
        templates=[template],
    )
    host = _instance(monitor_object, "host-a", 1)
    left = _instance(monitor_object, "host-b", 1)
    outsider = _instance(monitor_object, "host-c", 2)
    PolicyGroupService.join(instance=host, group=group)
    PolicyGroupService.join(instance=left, group=group)
    PolicyGroupService.leave(instance=left)
    PolicyGroupService.join(instance=outsider, group=foreign)

    found = PolicyGroupService.member_group_names([host.id, left.id, outsider.id], organization=1)

    assert found == {host.id: {"id": group.id, "name": "主机默认告警"}}


@pytest.mark.django_db(transaction=True)
def test_rule_editor_keeps_group_fields_and_closes_alerts_for_recipe_changes():
    monitor_object = _object()
    plugin = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, plugin, "CPU")],
    )
    rule = group.rules.get()
    policy = rule.policy
    policy.algorithm = "avg"
    policy.alert_name = "旧告警名"
    policy.schedule = {"type": "min", "value": 5}
    policy.notice = True
    policy.save(update_fields=["algorithm", "alert_name", "schedule", "notice", "updated_at"])
    original_source = copy.deepcopy(policy.source)
    host = _instance(monitor_object, "host-editor", 1)
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new")

    closed = PolicyGroupService.apply_rule_editor(
        rule,
        {
            "name": "磁盘读速过高",
            "alert_name": "新告警名",
            "schedule": {"type": "hour", "value": 1},
            "notice": False,
            "source": {"type": "instance", "values": []},
        },
    )

    rule.refresh_from_db()
    policy.refresh_from_db()
    alert.refresh_from_db()
    assert closed is False
    assert rule.name == "磁盘读速过高"
    assert policy.name == "磁盘读速过高"
    assert policy.alert_name == "新告警名"
    assert policy.schedule == {"type": "min", "value": 5}
    assert policy.notice is True
    assert policy.source == original_source
    assert alert.status == "new"

    closed = PolicyGroupService.apply_rule_editor(rule, {"algorithm": "max"})
    policy.refresh_from_db()
    alert.refresh_from_db()
    assert closed is True
    assert policy.algorithm == "max"
    assert alert.status == "closed"


@pytest.mark.django_db(transaction=True)
def test_rule_editor_name_save_ignores_form_echo():
    monitor_object = _object()
    plugin = _plugin(monitor_object, "Telegraf")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, plugin, "IO")],
    )
    rule = group.rules.select_related("policy", "plugin").get()
    policy = rule.policy
    metric = Metric.objects.get(monitor_plugin=plugin, name="cpu_usage_total")
    policy.collect_type = "host"
    policy.metric_unit = ""
    policy.calculation_unit = ""
    policy.threshold_unit = ""
    policy.query_condition = {"type": "metric", "filter": [], "metric_id": metric.id}
    policy.schedule = {"type": "min", "value": 5}
    policy.notice = True
    policy.save()
    host = _instance(monitor_object, "io-host", 1)
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new")

    closed = PolicyGroupService.apply_rule_editor(
        rule,
        {
            "name": "只改名字",
            "collect_type": plugin.id,
            "query_condition": {
                "type": "metric",
                "metric_id": metric.id,
                "metric_name": "cpu_usage_total",
                "filter": [],
            },
            "metric_unit": "percent",
            "calculation_unit": "",
            "threshold_unit": "",
            "schedule": {"type": "hour", "value": 1},
            "notice": False,
        },
    )

    rule.refresh_from_db()
    policy.refresh_from_db()
    alert.refresh_from_db()
    assert closed is False
    assert rule.name == "只改名字"
    assert rule.plugin_id == plugin.id
    assert policy.collect_type == "host"
    assert policy.metric_unit == ""
    assert policy.query_condition == {"type": "metric", "filter": [], "metric_id": metric.id}
    assert policy.schedule == {"type": "min", "value": 5}
    assert policy.notice is True
    assert alert.status == "new"

    other = _plugin(monitor_object, "Remote")
    closed = PolicyGroupService.apply_rule_editor(rule, {"collect_type": other.id})
    rule.refresh_from_db()
    policy.refresh_from_db()
    alert.refresh_from_db()
    assert closed is True
    assert rule.plugin_id == other.id
    assert policy.collect_type == "host"
    assert alert.status == "closed"


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
    policies = [rule.policy for rule in group.rules.select_related("policy")]
    assert len(policies) == 2
    assert all(policy.notice_users == [] for policy in policies)
    assert all(policy.handlers == [] for policy in policies)
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
    dispatch = {
        rule.plugin.name: PeriodicTask.objects.get(name=f"scan_policy_task_{rule.policy_id}").enabled
        for rule in group.rules.select_related("policy", "plugin")
    }
    assert dispatch["WMI"] is True
    assert dispatch["SSH"] is False
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
    PolicyInstanceBaseline.objects.create(policy=policy, monitor_instance_id=host.id, metric_instance_id=f"cpu-{host.id}")
    other = _instance(monitor_object, "web-02", 1)
    PolicyInstanceBaseline.objects.create(policy=policy, monitor_instance_id=other.id, metric_instance_id=f"cpu-{other.id}")

    PolicyGroupService.leave(instance=host)

    host.policy_group_membership.refresh_from_db()
    assert PeriodicTask.objects.get(name=f"scan_policy_task_{policy.id}").enabled is False
    alert.refresh_from_db()
    policy.refresh_from_db()
    assert host.policy_group_membership.state == "declined"
    assert host.policy_group_membership.policy_group_id is None
    assert alert.status == "closed"
    assert policy.source["values"] == []
    assert not PolicyInstanceBaseline.objects.filter(policy=policy, monitor_instance_id=host.id).exists()
    assert PolicyInstanceBaseline.objects.filter(policy=policy, monitor_instance_id=other.id).exists()


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


def test_standalone_rule_stays_on_strategy_list_and_group_rules_do_not():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, wmi, "WMI CPU")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[template],
    )
    host = _instance(monitor_object, "web-01", 1)
    standalone = PolicyGroupService.create_standalone(instance=host, template=template)
    visible = set(exclude_policy_group_rules(MonitorPolicy.objects.all()).values_list("id", flat=True))
    assert standalone.id in visible
    assert group.rules.get().policy_id not in visible


def test_update_copy_and_delete_default_do_not_touch_other_groups():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="默认",
        templates=[_template(monitor_object, wmi, "WMI CPU", threshold=80)],
    )
    other = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="另一组",
        templates=[_template(monitor_object, wmi, "另一条", threshold=70)],
    )
    PolicyGroupService.set_default(group)
    rule = group.rules.get()
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    alert = MonitorAlert.objects.create(policy_id=rule.policy_id, monitor_instance_id=host.id, status="new")
    PolicyGroupService.update_rule(rule, threshold=[{"level": "warning", "value": 95, "method": ">="}])
    saved = PolicyGroupService.save_rule_as_template(rule)
    copied = PolicyGroupService.copy_group(group, name="副本")

    rule.policy.refresh_from_db()
    other.rules.get().policy.refresh_from_db()
    alert.refresh_from_db()
    assert rule.policy.threshold[0]["value"] == 95
    assert other.rules.get().policy.threshold[0]["value"] == 70
    assert alert.status == "closed"
    assert saved.template_type == "custom"
    assert copied.memberships.count() == 0
    assert copied.rules.get().policy.threshold[0]["value"] == 95
    PolicyGroupService.delete_group(group)
    assert PolicyGroupService.ensure_default(organization=1, monitor_object=monitor_object) is None
    host.policy_group_membership.refresh_from_db()
    assert host.policy_group_membership.state == "declined"


def test_changing_collect_plugin_keeps_membership_and_closes_old_alerts():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU"), _template(monitor_object, ssh, "SSH CPU")],
    )
    host = _instance(monitor_object, "web-01", 1)
    config = _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    wmi_policy = group.rules.get(plugin=wmi).policy
    alert = MonitorAlert.objects.create(policy_id=wmi_policy.id, monitor_instance_id=host.id, status="new", alert_type="alert")
    PolicyInstanceBaseline.objects.create(policy=wmi_policy, monitor_instance_id=host.id, metric_instance_id="wmi-cpu")
    ssh_policy = group.rules.get(plugin=ssh).policy
    PolicyInstanceBaseline.objects.create(policy=ssh_policy, monitor_instance_id=host.id, metric_instance_id="ssh-cpu")

    config.monitor_plugin = ssh
    config.save(update_fields=["monitor_plugin"])
    PolicyGroupService.refresh_collect_coverage(host)

    host.policy_group_membership.refresh_from_db()
    wmi_policy.refresh_from_db()
    ssh_policy = group.rules.get(plugin=ssh).policy
    ssh_policy.refresh_from_db()
    alert.refresh_from_db()
    assert host.policy_group_membership.policy_group_id == group.id
    assert wmi_policy.source["values"] == []
    assert ssh_policy.source["values"] == [host.id]
    assert alert.status == "closed"
    assert not PolicyInstanceBaseline.objects.filter(policy=wmi_policy, monitor_instance_id=host.id).exists()
    assert PolicyInstanceBaseline.objects.filter(policy=ssh_policy, monitor_instance_id=host.id).exists()


def test_access_choice_applies_only_to_instances_without_a_decision():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    default_group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="默认",
        templates=[_template(monitor_object, wmi, "默认 CPU")],
    )
    other = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="核心",
        templates=[_template(monitor_object, wmi, "核心 CPU")],
    )
    existing = _instance(monitor_object, "old", 1)
    PolicyGroupService.join(instance=existing, group=default_group)
    fresh = _instance(monitor_object, "new", 1)
    declined = _instance(monitor_object, "off", 1)

    PolicyGroupService.apply_access_choice(existing, join=True, group_id=other.id)
    PolicyGroupService.apply_access_choice(fresh, join=True, group_id=other.id)
    PolicyGroupService.apply_access_choice(declined, join=False)

    existing.policy_group_membership.refresh_from_db()
    fresh.policy_group_membership.refresh_from_db()
    declined.policy_group_membership.refresh_from_db()
    assert existing.policy_group_membership.policy_group_id == default_group.id
    assert fresh.policy_group_membership.policy_group_id == other.id
    assert declined.policy_group_membership.state == "declined"


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


def test_delete_group_removes_rule_policies_scan_tasks_and_keeps_declined_members():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    PolicyGroupService.set_default(group)
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    policy = group.rules.get().policy
    assert PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").exists()
    PolicyInstanceBaseline.objects.create(policy=policy, monitor_instance_id=host.id, metric_instance_id="cpu")
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new", alert_type="alert", content="open")

    PolicyGroupService.delete_group(group, operator="editor")

    assert not MonitorPolicy.objects.filter(id=policy.id).exists()
    assert not PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").exists()
    assert not PolicyInstanceBaseline.objects.filter(policy_id=policy.id).exists()
    alert.refresh_from_db()
    assert alert.status == "closed"
    host.policy_group_membership.refresh_from_db()
    assert host.policy_group_membership.state == "declined"
    assert host.policy_group_membership.policy_group_id is None
    pointer = PolicyGroupDefault.objects.get(organization=1, monitor_object=monitor_object)
    assert pointer.policy_group_id is None
    assert PolicyGroupService.ensure_default(organization=1, monitor_object=monitor_object) is None


def test_group_rule_and_standalone_rule_get_a_scan_task():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, wmi, "WMI CPU")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[template],
    )
    policy = group.rules.get().policy
    policy.refresh_from_db()
    assert policy.schedule == {"type": "min", "value": 5}
    assert policy.period == {"type": "min", "value": 5}
    assert policy.enable_alerts == ["threshold"]
    assert PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}", enabled=False).exists()

    PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").delete()
    PolicyGroupService.ensure_scan_task(policy)
    assert PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").exists()

    host = _instance(monitor_object, "web-01", 1)
    standalone = PolicyGroupService.create_standalone(instance=host, template=template, organization=1)
    assert standalone.period == {"type": "min", "value": 5}
    assert standalone.enable_alerts == ["threshold"]
    assert PeriodicTask.objects.filter(name=f"scan_policy_task_{standalone.id}", enabled=True).exists()
    assert list(standalone.policyorganization_set.values_list("organization", flat=True)) == [1]


def test_copy_keeps_the_current_rule_after_the_template_is_gone():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, wmi, "WMI CPU", threshold=80)
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[template],
    )
    PolicyGroupService.set_default(group)
    policy = group.rules.get().policy
    metric_id = PolicyGroupService.metric_id_for_policy(policy)
    assert PolicyGroupService.metric_names_for_policies([policy])[metric_id] == "cpu_usage_total"

    policy.algorithm = "max"
    policy.schedule = {"type": "min", "value": 15}
    policy.notice_users = ["alice"]
    policy.handlers = [7]
    policy.threshold = [{"level": "warning", "value": 95, "method": ">="}]
    policy.save()
    template.config = {**template.config, "metric_name": "mem_used", "threshold": [{"level": "warning", "value": 1, "method": ">="}]}
    template.save(update_fields=["config"])
    template.delete()

    copied = PolicyGroupService.copy_group(group, name="副本")
    cloned = copied.rules.get().policy
    pointer = PolicyGroupDefault.objects.get(organization=1, monitor_object=monitor_object)

    assert copied.memberships.count() == 0
    assert pointer.policy_group_id == group.id
    assert cloned.threshold[0]["value"] == 95
    assert cloned.algorithm == "max"
    assert cloned.schedule == {"type": "min", "value": 15}
    assert cloned.notice_users == ["alice"]
    assert cloned.handlers == [7]
    assert cloned.query_condition["metric_id"] == metric_id
    assert cloned.source == {"type": "instance", "values": []}
    assert cloned.source_template_id is None
    assert PolicyGroupService.metric_names_for_policies([cloned])[metric_id] == "cpu_usage_total"
    assert PeriodicTask.objects.filter(name=f"scan_policy_task_{cloned.id}").exists()


def test_closing_group_alerts_is_queued_for_the_alert_center(mocker, django_capture_on_commit_callbacks):
    notifier = mocker.Mock()
    mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier", return_value=notifier)
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
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new", alert_type="alert", content="open")

    with django_capture_on_commit_callbacks(execute=True):
        PolicyGroupService.leave(instance=host)

    alert.refresh_from_db()
    assert alert.status == "closed"
    notifier.enqueue_alert_center_deliveries.assert_called_once()
    assert notifier.enqueue_alert_center_deliveries.call_args.args[1] == "closed"
    assert notifier.enqueue_alert_center_deliveries.call_args.kwargs["reason"] == "policy_group_member_left"
    notifier.notify_alerts.assert_called_once()
    assert notifier.notify_alerts.call_args.kwargs["reason"] == "policy_group_member_left"


def test_template_period_and_alert_switches_are_kept_on_the_rule():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, wmi, "WMI CPU")
    template.config = {
        **template.config,
        "period": {"type": "hour", "value": 1},
        "enable_alerts": ["threshold", "no_data"],
    }
    template.save(update_fields=["config"])

    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[template],
    )

    policy = group.rules.get().policy
    assert policy.period == {"type": "hour", "value": 1}
    assert policy.enable_alerts == ["threshold", "no_data"]


def test_template_sync_keeps_standalone_period_and_alert_switches():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    template = _template(monitor_object, wmi, "WMI CPU", threshold=80)
    standalone = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="旧策略",
        source_template=template,
        period={"type": "min", "value": 1},
        enable_alerts=["no_data"],
        threshold=[{"level": "warning", "value": 80, "method": ">="}],
        source={"type": "instance", "values": []},
    )
    template.config = {
        **template.config,
        "period": {"type": "hour", "value": 2},
        "enable_alerts": ["threshold"],
        "threshold": [{"level": "warning", "value": 99, "method": ">="}],
    }
    template.save(update_fields=["config"])

    PolicyService.sync_issued_policies_from_template(template, type("User", (), {"username": "tester"})())

    standalone.refresh_from_db()
    assert standalone.period == {"type": "min", "value": 1}
    assert standalone.enable_alerts == ["no_data"]
    assert standalone.threshold == [{"level": "warning", "value": 99, "method": ">="}]


def test_repair_fills_only_empty_group_rule_scan_settings():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU"), _template(monitor_object, ssh, "SSH CPU")],
    )
    empty_rule, custom_rule = list(group.rules.select_related("policy").order_by("id"))
    empty_rule.policy.period = {}
    empty_rule.policy.enable_alerts = []
    empty_rule.policy.save(update_fields=["period", "enable_alerts", "updated_at"])
    custom_rule.policy.period = {"type": "hour", "value": 2}
    custom_rule.policy.enable_alerts = ["no_data"]
    custom_rule.policy.save(update_fields=["period", "enable_alerts", "updated_at"])
    host = _instance(monitor_object, "web-01", 1)
    standalone = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="旧策略",
        period={},
        enable_alerts=[],
        source={"type": "instance", "values": [host.id]},
    )

    assert PolicyGroupService.repair_empty_scan_settings() == 1
    empty_rule.policy.refresh_from_db()
    custom_rule.policy.refresh_from_db()
    standalone.refresh_from_db()
    assert empty_rule.policy.period == {"type": "min", "value": 5}
    assert empty_rule.policy.enable_alerts == ["threshold"]
    assert custom_rule.policy.period == {"type": "hour", "value": 2}
    assert custom_rule.policy.enable_alerts == ["no_data"]
    assert standalone.period == {}
    assert standalone.enable_alerts == []

    repaired_at = empty_rule.policy.updated_at
    assert PolicyGroupService.repair_empty_scan_settings() == 0
    empty_rule.policy.refresh_from_db()
    assert empty_rule.policy.updated_at == repaired_at


def test_matching_instance_resumes_scan_from_now_and_disabled_policy_stays_off():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    policy = group.rules.get().policy
    task_name = f"scan_policy_task_{policy.id}"
    assert PeriodicTask.objects.get(name=task_name).enabled is False

    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    policy.refresh_from_db()
    assert PeriodicTask.objects.get(name=task_name).enabled is True
    started = policy.last_run_time
    assert started is not None

    PolicyGroupService.sync_coverage(group)
    policy.refresh_from_db()
    assert policy.last_run_time == started

    policy.enable = False
    policy.save(update_fields=["enable"])
    PolicyGroupService.sync_coverage(group)
    assert PeriodicTask.objects.get(name=task_name).enabled is False


def test_update_notice_writes_every_policy_and_keeps_open_alerts():
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
    policy = group.rules.filter(plugin=wmi).get().policy
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new", alert_type="alert")

    PolicyGroupService.update_notice(
        group,
        notice=True,
        notice_type="email",
        notice_type_ids=[9],
        notice_users=["12"],
    )

    for rule in group.rules.select_related("policy"):
        rule.policy.refresh_from_db()
        assert rule.policy.notice is True
        assert rule.policy.notice_type == "email"
        assert rule.policy.notice_type_ids == [9]
        assert rule.policy.notice_users == ["12"]
    alert.refresh_from_db()
    assert alert.status == "new"
    other_policy = other.rules.get().policy
    other_policy.refresh_from_db()
    assert other_policy.notice_users == []
    assert other_policy.notice_type_ids == []

    with pytest.raises(BaseAppException):
        PolicyGroupService.update_notice(group, notice=True, notice_type_ids=[], notice_users=["12"])


def test_update_notice_writes_handlers_and_leaves_existing_alerts():
    from apps.monitor.views.policy_group import _group_notice
    from apps.system_mgmt.models import User

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
    assignee = User.objects.create(
        username="group-handler",
        display_name="组处理人",
        email="group-handler@example.com",
        password="x",
        group_list=[1],
    )
    outsider = User.objects.create(
        username="group-outsider",
        display_name="组外",
        email="group-outsider@example.com",
        password="x",
        group_list=[99],
    )
    host = _instance(monitor_object, "web-01", 1)
    policy = group.rules.filter(plugin=wmi).get().policy
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=host.id,
        status="new",
        alert_type="alert",
        handlers=[999],
    )

    PolicyGroupService.update_notice(group, notice=False, handlers=[assignee.id, str(assignee.id)])

    for rule in group.rules.select_related("policy"):
        rule.policy.refresh_from_db()
        assert rule.policy.notice is False
        assert rule.policy.notice_users == []
        assert rule.policy.handlers == [assignee.id]
    alert.refresh_from_db()
    assert alert.status == "new"
    assert alert.handlers == [999]
    other.rules.get().policy.refresh_from_db()
    assert other.rules.get().policy.handlers == []

    listed = _group_notice(list(group.rules.select_related("policy")))
    assert listed["handlers"] == [assignee.id]
    assert listed["handlers_uniform"] is True

    PolicyGroupService.update_notice(
        group,
        notice=True,
        notice_type="email",
        notice_type_ids=[9],
        notice_users=["12"],
    )
    policy.refresh_from_db()
    assert policy.handlers == [assignee.id]
    assert policy.notice_users == ["12"]

    with pytest.raises(ValidationAppException, match="不属于策略所属组织"):
        PolicyGroupService.update_notice(group, notice=False, handlers=[outsider.id])
    policy.refresh_from_db()
    assert policy.handlers == [assignee.id]
    assert policy.notice_users == ["12"]

    PolicyGroupService.update_notice(group, notice=False, handlers=[])
    for rule in group.rules.select_related("policy"):
        rule.policy.refresh_from_db()
        assert rule.policy.handlers == []
        assert rule.policy.notice is False


def test_group_notice_keeps_handler_uniformity_separate_from_notice():
    from apps.monitor.views.policy_group import _group_notice

    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU"), _template(monitor_object, ssh, "SSH CPU")],
    )
    policies = [rule.policy for rule in group.rules.select_related("policy")]
    policies[0].handlers = [3]
    policies[0].save(update_fields=["handlers"])
    policies[1].handlers = [4]
    policies[1].notice = True
    policies[1].notice_type_ids = [9]
    policies[1].notice_users = ["4"]
    policies[1].save(update_fields=["handlers", "notice", "notice_type_ids", "notice_users"])

    mixed = _group_notice(list(group.rules.select_related("policy")))
    assert mixed["handlers_uniform"] is False
    assert mixed["handlers"] == []
    assert mixed["notice_uniform"] is False

    policies[0].notice = False
    policies[0].notice_type = ""
    policies[0].notice_type_ids = []
    policies[0].notice_users = []
    policies[0].save(update_fields=["notice", "notice_type", "notice_type_ids", "notice_users"])
    policies[1].handlers = [3]
    policies[1].notice = False
    policies[1].notice_type = ""
    policies[1].notice_type_ids = []
    policies[1].notice_users = []
    policies[1].save(update_fields=["handlers", "notice", "notice_type", "notice_type_ids", "notice_users"])
    aligned = _group_notice(list(group.rules.select_related("policy")))
    assert aligned["handlers"] == [3]
    assert aligned["handlers_uniform"] is True
    assert aligned["notice_uniform"] is True


def test_update_enable_stops_the_group_and_resumes_from_now():
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
    _collect(host, ssh)
    PolicyGroupService.join(instance=host, group=group)
    wmi_policy = group.rules.filter(plugin=wmi, name="WMI CPU").get().policy
    ssh_policy = group.rules.filter(plugin=ssh).get().policy
    alert = MonitorAlert.objects.create(policy_id=wmi_policy.id, monitor_instance_id=host.id, status="new", alert_type="alert")
    other_policy = other.rules.get().policy
    other_alert = MonitorAlert.objects.create(policy_id=other_policy.id, monitor_instance_id=host.id, status="new", alert_type="alert")

    PolicyGroupService.update_enable(group, enable=False, operator="tester")

    wmi_policy.refresh_from_db()
    ssh_policy.refresh_from_db()
    alert.refresh_from_db()
    other_policy.refresh_from_db()
    other_alert.refresh_from_db()
    membership = PolicyGroupMembership.objects.get(monitor_instance=host)
    assert wmi_policy.enable is False
    assert ssh_policy.enable is False
    assert PeriodicTask.objects.get(name=f"scan_policy_task_{wmi_policy.id}").enabled is False
    assert PeriodicTask.objects.get(name=f"scan_policy_task_{ssh_policy.id}").enabled is False
    assert alert.status == "closed"
    assert alert.operation_logs[-1]["reason"] == "policy_disabled"
    assert membership.state == PolicyGroupMembership.STATE_MEMBER
    assert membership.policy_group_id == group.id
    assert other_policy.enable is True
    assert other_alert.status == "new"

    extra = _instance(monitor_object, "web-02", 1)
    _collect(extra, wmi)
    PolicyGroupService.join(instance=extra, group=group)
    assert PeriodicTask.objects.get(name=f"scan_policy_task_{wmi_policy.id}").enabled is False
    assert PolicyGroupMembership.objects.get(monitor_instance=host).policy_group_id == group.id

    PolicyGroupService.update_enable(group, enable=True, operator="tester")

    wmi_policy.refresh_from_db()
    ssh_policy.refresh_from_db()
    assert wmi_policy.enable is True
    assert ssh_policy.enable is True
    assert wmi_policy.last_run_time is not None
    assert PeriodicTask.objects.get(name=f"scan_policy_task_{wmi_policy.id}").enabled is True
    assert MonitorAlert.objects.filter(policy_id=wmi_policy.id, status="new").count() == 0
    assert PolicyGroupMembership.objects.filter(policy_group=group, state=PolicyGroupMembership.STATE_MEMBER).count() == 2

    started = wmi_policy.last_run_time
    PolicyGroupService.update_enable(group, enable=True)
    wmi_policy.refresh_from_db()
    assert wmi_policy.last_run_time == started


def test_missing_templates_do_not_burn_the_default_pointer():
    monitor_object = _object()
    early = _instance(monitor_object, "early", 1)
    skipped = PolicyGroupService.consider_auto_join(early, [1])

    assert skipped.state == "skipped"
    assert not PolicyGroupDefault.objects.filter(organization=1, monitor_object=monitor_object).exists()

    wmi = _plugin(monitor_object, "WMI")
    _template(monitor_object, wmi, "WMI CPU")
    group = PolicyGroupService.ensure_default(organization=1, monitor_object=monitor_object)
    early.policy_group_membership.refresh_from_db()
    later = _instance(monitor_object, "later", 1)
    _collect(later, wmi)
    joined = PolicyGroupService.consider_auto_join(later, [1])

    assert group is not None
    assert early.policy_group_membership.state == "skipped"
    assert joined.state == "member"
    assert joined.policy_group_id == group.id


def test_legacy_policy_matches_storage_key_and_logical_id():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    _template(monitor_object, wmi, "WMI CPU")
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="旧策略",
        algorithm="avg",
        source={"type": "instance", "values": ["web-01"]},
    )

    assert PolicyGroupService.consider_auto_join(host, [1]).state == "skipped"


def test_auto_join_failure_leaves_no_membership(monkeypatch, caplog):
    monitor_object = _object()
    host = _instance(monitor_object, "web-01", 1)

    def boom(*args, **kwargs):
        raise RuntimeError("pointer down")

    monkeypatch.setattr(PolicyGroupService, "consider_auto_join", boom)
    with caplog.at_level("ERROR", logger="monitor"):
        result = PolicyGroupService.apply_best_effort_auto_join(host, [1])

    assert result is not None
    assert result.state == "failed"
    host.policy_group_membership.refresh_from_db()
    assert host.policy_group_membership.state == "failed"
    assert host.policy_group_membership.policy_group_id is None
    records = [record for record in caplog.records if record.name == "monitor" and record.levelname == "ERROR"]
    assert len(records) == 1
    assert records[0].getMessage() == "event=policy_group_auto_join_failed instance_id=('web-01',) failed_stage=auto_join error_type=RuntimeError"
    assert records[0].exc_info is not None
    assert "pointer down" not in records[0].getMessage()


def test_onboarding_membership_failure_does_not_raise(monkeypatch, caplog):
    monitor_object = _object()
    host = _instance(monitor_object, "web-01", 1)

    def boom(*args, **kwargs):
        raise RuntimeError("join down")

    monkeypatch.setattr(PolicyGroupService, "apply_access_choice", boom)
    with caplog.at_level("ERROR", logger="monitor"):
        results = PolicyGroupService.apply_onboarding_memberships(
            new_instances=[{"instance_id": host.id}],
            existing_instances=[],
            created_ids={host.id},
            choice={"join": True, "group_id": 1},
        )

    assert results == [{"instance_id": host.id, "outcome": "failed", "reason": "策略组加入失败，可在实例页重新加入"}]
    host.policy_group_membership.refresh_from_db()
    assert host.policy_group_membership.state == "failed"
    records = [record for record in caplog.records if record.name == "monitor" and record.levelname == "ERROR"]
    assert len(records) == 1
    assert "failed_stage=onboarding_join" in records[0].getMessage()
    assert records[0].exc_info is not None


def test_group_rule_without_baseline_does_not_use_instance_ids_as_no_data_keys():
    from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector

    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    host = _instance(monitor_object, "web-01", 1)
    policy = group.rules.get().policy
    grouped = AlertDetector(policy, {host.id: host.name}, {}, [], None)
    assert grouped._get_baseline_keys() == set()

    lone = MonitorPolicy.objects.create(
        monitor_object=monitor_object,
        name="单策略",
        algorithm="avg",
        source={"type": "instance", "values": [host.id]},
    )
    standalone = AlertDetector(lone, {host.id: host.name}, {}, [], None)
    assert standalone._get_baseline_keys() == {host.id}


def test_retiring_plugin_closes_group_policy_alerts_and_scan():
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
    alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id=host.id, status="new")

    PolicyGroupService.retire_policies_for_plugins([wmi.id], operator="tester")

    alert.refresh_from_db()
    assert alert.status == "closed"
    assert not MonitorPolicy.objects.filter(id=policy.id).exists()
    assert not PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").exists()
    assert group.rules.count() == 0
    host.policy_group_membership.refresh_from_db()
    assert host.policy_group_membership.state == "member"


def _mixed_group():
    """每个插件一条实例级规则、一条磁盘规则。磁盘规则先创建，id 更小。"""
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[
            _template(monitor_object, wmi, "WMI 磁盘"),
            _template(monitor_object, wmi, "WMI CPU"),
            _template(monitor_object, ssh, "SSH 磁盘"),
            _template(monitor_object, ssh, "SSH CPU"),
        ],
    )
    for rule in group.rules.select_related("policy"):
        if "磁盘" in rule.name:
            rule.policy.group_by = ["instance_id", "device"]
            rule.policy.save(update_fields=["group_by", "updated_at"])
    return group, wmi, ssh


def _no_data_payload(**overrides):
    payload = {
        "enabled": True,
        "period": {"type": "min", "value": 10},
        "level": "error",
        "alert_name": "{{host}} 无数据",
        "recovery_period": {"type": "min", "value": 5},
    }
    payload.update(overrides)
    return payload


def _existence_query(instance_name):
    fake = MagicMock()
    fake.query_existence_metrics.return_value = {"data": {"result": [{"metric": {"instance_id": instance_name}}]}}
    return patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.MetricQueryService",
        return_value=fake,
    )


def _policies_by_name(group):
    return {rule.name: rule.policy for rule in group.rules.select_related("policy")}


def test_enabling_group_no_data_writes_one_instance_carrier_per_plugin():
    group, wmi, ssh = _mixed_group()
    host = _instance(monitor_object=group.monitor_object, name="web-01", organization=1)
    _collect(host, wmi)
    _collect(host, ssh)
    PolicyGroupService.join(instance=host, group=group)
    policies = _policies_by_name(group)
    disk = policies["WMI 磁盘"]
    disk.enable_alerts = ["threshold", "no_data"]
    disk.no_data_period = {"type": "min", "value": 30}
    disk.save(update_fields=["enable_alerts", "no_data_period", "updated_at"])
    stray_alert = MonitorAlert.objects.create(policy_id=disk.id, monitor_instance_id=host.id, status="new", alert_type="no_data")
    PolicyInstanceBaseline.objects.create(policy=disk, monitor_instance_id=host.id, metric_instance_id="disk-old")
    threshold_alert = MonitorAlert.objects.create(policy_id=policies["WMI CPU"].id, monitor_instance_id=host.id, status="new", alert_type="alert")

    with _existence_query("web-01"):
        PolicyGroupService.update_detection(group, no_data=_no_data_payload())

    policies = _policies_by_name(group)
    carriers = []
    for name, policy in policies.items():
        policy.refresh_from_db()
        enabled = "no_data" in (policy.enable_alerts or [])
        if "CPU" in name:
            carriers.append(policy)
            assert enabled is True
            assert policy.group_by == ["instance_id"]
            assert policy.no_data_period == {"type": "min", "value": 10}
            assert policy.no_data_level == "error"
            assert policy.no_data_alert_name == "{{host}} 无数据"
            assert policy.no_data_recovery_period == {"type": "min", "value": 5}
            assert set(policy.enable_alerts) == {"threshold", "no_data"}
            assert list(PolicyInstanceBaseline.objects.filter(policy=policy).values_list("metric_instance_id", flat=True)) == ["('web-01',)"]
        else:
            assert enabled is False
            assert "threshold" in (policy.enable_alerts or [])
            assert not PolicyInstanceBaseline.objects.filter(policy=policy).exists()
    assert len(carriers) == 2
    assert {policy.id for policy in carriers} == {policies["WMI CPU"].id, policies["SSH CPU"].id}
    wmi_rules = list(group.rules.filter(plugin=wmi).order_by("id"))
    assert wmi_rules[0].name == "WMI 磁盘"
    assert wmi_rules[0].id < policies["WMI CPU"].group_rule.id
    stray_alert.refresh_from_db()
    threshold_alert.refresh_from_db()
    assert stray_alert.status == "closed"
    assert threshold_alert.status == "new"


def test_disabling_group_no_data_closes_only_no_data_alerts_and_clears_baselines():
    group, wmi, ssh = _mixed_group()
    host = _instance(group.monitor_object, "web-01", 1)
    _collect(host, wmi)
    _collect(host, ssh)
    PolicyGroupService.join(instance=host, group=group)
    with _existence_query("web-01"):
        PolicyGroupService.update_detection(group, no_data=_no_data_payload())
    carrier = _policies_by_name(group)["WMI CPU"]
    no_data_alert = MonitorAlert.objects.create(policy_id=carrier.id, monitor_instance_id=host.id, status="new", alert_type="no_data")
    threshold_alert = MonitorAlert.objects.create(policy_id=carrier.id, monitor_instance_id=host.id, status="new", alert_type="alert")
    assert PolicyInstanceBaseline.objects.filter(policy=carrier).exists()

    PolicyGroupService.update_detection(group, no_data={"enabled": False})

    carrier.refresh_from_db()
    no_data_alert.refresh_from_db()
    threshold_alert.refresh_from_db()
    assert "no_data" not in (carrier.enable_alerts or [])
    assert no_data_alert.status == "closed"
    assert threshold_alert.status == "new"
    assert not PolicyInstanceBaseline.objects.filter(policy_id__in=[rule.policy_id for rule in group.rules.all()]).exists()


def test_disabling_group_no_data_makes_carriers_with_different_windows_uniform():
    group, _wmi, _ssh = _mixed_group()
    policies = _policies_by_name(group)
    wmi_cpu = policies["WMI CPU"]
    ssh_cpu = policies["SSH CPU"]
    wmi_cpu.enable_alerts = ["threshold", "no_data"]
    wmi_cpu.no_data_period = {"type": "min", "value": 10}
    wmi_cpu.no_data_level = "warning"
    wmi_cpu.no_data_alert_name = "甲"
    wmi_cpu.no_data_recovery_period = {"type": "min", "value": 5}
    wmi_cpu.save()
    ssh_cpu.enable_alerts = ["threshold", "no_data"]
    ssh_cpu.no_data_period = {"type": "min", "value": 30}
    ssh_cpu.no_data_level = "error"
    ssh_cpu.no_data_alert_name = "乙"
    ssh_cpu.no_data_recovery_period = {"type": "min", "value": 10}
    ssh_cpu.save()
    no_data_alert = MonitorAlert.objects.create(policy_id=wmi_cpu.id, monitor_instance_id="('web-01',)", status="new", alert_type="no_data")
    threshold_alert = MonitorAlert.objects.create(policy_id=wmi_cpu.id, monitor_instance_id="('web-01',)", status="new", alert_type="alert")

    PolicyGroupService.update_detection(group, no_data={"enabled": False})

    serialized = _serialize_group(group, None, metric_names={})
    assert serialized["no_data_uniform"] is True
    assert serialized["no_data"]["enabled"] is False
    for policy in (wmi_cpu, ssh_cpu):
        policy.refresh_from_db()
        assert "no_data" not in (policy.enable_alerts or [])
        assert policy.no_data_period == {}
        assert policy.no_data_level == ""
        assert policy.no_data_alert_name == ""
        assert policy.no_data_recovery_period == {}
    no_data_alert.refresh_from_db()
    threshold_alert.refresh_from_db()
    assert no_data_alert.status == "closed"
    assert threshold_alert.status == "new"


def test_changing_no_data_window_keeps_open_alerts_and_baselines():
    group, wmi, ssh = _mixed_group()
    host = _instance(group.monitor_object, "web-01", 1)
    _collect(host, wmi)
    _collect(host, ssh)
    PolicyGroupService.join(instance=host, group=group)
    with _existence_query("web-01"):
        PolicyGroupService.update_detection(group, no_data=_no_data_payload())
    carrier = _policies_by_name(group)["SSH CPU"]
    alert = MonitorAlert.objects.create(policy_id=carrier.id, monitor_instance_id=host.id, status="new", alert_type="no_data")
    before = set(PolicyInstanceBaseline.objects.filter(policy=carrier).values_list("id", "metric_instance_id"))

    with _existence_query("replaced"):
        PolicyGroupService.update_detection(
            group,
            no_data=_no_data_payload(period={"type": "min", "value": 15}, level="warning", alert_name="{{host}} 中断"),
        )

    carrier.refresh_from_db()
    alert.refresh_from_db()
    assert carrier.no_data_period == {"type": "min", "value": 15}
    assert carrier.no_data_level == "warning"
    assert carrier.no_data_alert_name == "{{host}} 中断"
    assert alert.status == "new"
    assert set(PolicyInstanceBaseline.objects.filter(policy=carrier).values_list("id", "metric_instance_id")) == before


@pytest.mark.parametrize(
    "payload",
    [
        {
            "enabled": True,
            "period": {"type": "min", "value": 5},
            "recovery_period": {"type": "min", "value": 10},
            "level": "warning",
            "alert_name": "无数据",
        },
        {
            "enabled": True,
            "period": {"type": "min", "value": 10},
            "recovery_period": {"type": "min", "value": 5},
            "level": "info",
            "alert_name": "无数据",
        },
        {
            "enabled": True,
            "period": {"type": "min", "value": 10},
            "recovery_period": {"type": "min", "value": 5},
            "level": "warning",
            "alert_name": "  ",
        },
        {"enabled": "yes"},
    ],
)
def test_group_no_data_rejects_illegal_payloads(payload):
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    with pytest.raises(ValidationAppException):
        PolicyGroupService.update_detection(group, no_data=payload)
    policy = group.rules.get().policy
    policy.refresh_from_db()
    assert "no_data" not in (policy.enable_alerts or [])


def test_group_schedule_rewrites_crontab_without_closing_alerts_or_waking_idle_tasks():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    ssh = _plugin(monitor_object, "SSH")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU"), _template(monitor_object, ssh, "SSH CPU")],
    )
    host = _instance(monitor_object, "web-01", 1)
    _collect(host, wmi)
    PolicyGroupService.join(instance=host, group=group)
    covered = group.rules.get(plugin=wmi).policy
    idle = group.rules.get(plugin=ssh).policy
    started = timezone.now()
    MonitorPolicy.objects.filter(id=covered.id).update(last_run_time=started)
    alert = MonitorAlert.objects.create(policy_id=covered.id, monitor_instance_id=host.id, status="new", alert_type="alert")

    PolicyGroupService.update_detection(group, schedule={"type": "min", "value": 1})

    covered.refresh_from_db()
    idle.refresh_from_db()
    alert.refresh_from_db()
    covered_task = PeriodicTask.objects.select_related("crontab").get(name=f"scan_policy_task_{covered.id}")
    idle_task = PeriodicTask.objects.select_related("crontab").get(name=f"scan_policy_task_{idle.id}")
    assert covered.schedule == {"type": "min", "value": 1}
    assert idle.schedule == {"type": "min", "value": 1}
    assert covered.last_run_time == started
    assert idle.last_run_time is None
    assert alert.status == "new"
    assert covered_task.enabled is True
    assert covered_task.crontab.minute == "*/1"
    assert covered_task.crontab.hour == "*"
    assert idle_task.enabled is False

    PolicyGroupService.update_enable(group, enable=False)
    PolicyGroupService.update_detection(group, schedule={"type": "hour", "value": 2})

    covered.refresh_from_db()
    covered_task = PeriodicTask.objects.select_related("crontab").get(name=f"scan_policy_task_{covered.id}")
    idle_task = PeriodicTask.objects.select_related("crontab").get(name=f"scan_policy_task_{idle.id}")
    assert covered.schedule == {"type": "hour", "value": 2}
    assert covered.last_run_time == started
    assert covered_task.enabled is False
    assert covered_task.crontab.hour == "*/2"
    assert covered_task.crontab.minute == "0"
    assert idle_task.enabled is False


@pytest.mark.parametrize(
    "schedule",
    [
        {"type": "week", "value": 1},
        {"type": "min", "value": 60},
        {"type": "min", "value": 0},
        {"type": "hour", "value": 24},
        {"type": "day", "value": 2},
        {"type": "min", "value": True},
        {"type": "day", "value": "1"},
    ],
)
def test_group_schedule_rejects_illegal_values(schedule):
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    with pytest.raises(ValidationAppException):
        PolicyGroupService.update_detection(group, schedule=schedule)
    policy = group.rules.get().policy
    policy.refresh_from_db()
    assert policy.schedule == {"type": "min", "value": 5}


def test_group_detection_requires_schedule_or_no_data():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    with pytest.raises(ValidationAppException, match="至少"):
        PolicyGroupService.update_detection(group)


@pytest.mark.django_db(transaction=True)
def test_trigger_count_change_closes_open_alerts_outside_a_request_transaction():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    rule = group.rules.get()
    rule.policy.alert_name = "保持原名"
    rule.policy.save(update_fields=["alert_name", "updated_at"])
    host = _instance(monitor_object, "web-01", 1)
    alert = MonitorAlert.objects.create(policy_id=rule.policy_id, monitor_instance_id=host.id, status="new")

    PolicyGroupService.update_rule(rule, threshold=rule.policy.threshold, trigger_count=4)

    rule.policy.refresh_from_db()
    alert.refresh_from_db()
    assert rule.policy.trigger_count == 4
    assert rule.policy.alert_name == "保持原名"
    assert alert.status == "closed"


def test_alert_name_change_keeps_open_alerts():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    rule = group.rules.get()
    host = _instance(monitor_object, "web-01", 1)
    alert = MonitorAlert.objects.create(policy_id=rule.policy_id, monitor_instance_id=host.id, status="new")

    PolicyGroupService.update_rule(rule, threshold=rule.policy.threshold, alert_name="{{host}} 过高")

    rule.policy.refresh_from_db()
    alert.refresh_from_db()
    assert rule.policy.alert_name == "{{host}} 过高"
    assert rule.policy.trigger_count == 1
    assert alert.status == "new"


def test_recovery_fields_close_open_alerts():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    rule = group.rules.get()
    host = _instance(monitor_object, "web-01", 1)
    by_condition = MonitorAlert.objects.create(policy_id=rule.policy_id, monitor_instance_id=host.id, status="new")
    PolicyGroupService.update_rule(rule, recovery_condition=3)
    by_condition.refresh_from_db()
    rule.policy.refresh_from_db()
    assert rule.policy.recovery_condition == 3
    assert by_condition.status == "closed"

    by_threshold = MonitorAlert.objects.create(policy_id=rule.policy_id, monitor_instance_id=host.id, status="new")
    PolicyGroupService.update_rule(rule, recovery_threshold={"method": "<", "value": 10})
    by_threshold.refresh_from_db()
    rule.policy.refresh_from_db()
    assert rule.policy.recovery_threshold == {"method": "<", "value": 10}
    assert by_threshold.status == "closed"


def test_multi_rule_rejects_recovery_threshold():
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    rule = group.rules.get()
    rule.policy.query_condition = {"type": "multi", "queries": []}
    rule.policy.save(update_fields=["query_condition", "updated_at"])
    host = _instance(monitor_object, "web-01", 1)
    alert = MonitorAlert.objects.create(policy_id=rule.policy_id, monitor_instance_id=host.id, status="new")

    with pytest.raises(ValidationAppException, match="恢复阈值"):
        PolicyGroupService.update_rule(rule, recovery_threshold={"method": ">", "value": 1})

    rule.policy.refresh_from_db()
    alert.refresh_from_db()
    assert rule.policy.recovery_threshold == {}
    assert alert.status == "new"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trigger_count": 0},
        {"trigger_count": True},
        {"trigger_count": "3"},
        {"recovery_condition": 0},
        {"recovery_condition": -1},
        {"recovery_threshold": {"method": "??", "value": 1}},
        {"recovery_threshold": {"method": ">", "value": "x"}},
        {"alert_name": ""},
        {"alert_name": " "},
        {"alert_name": "名" * 201},
    ],
)
def test_rule_level_fields_reject_illegal_values(kwargs):
    monitor_object = _object()
    wmi = _plugin(monitor_object, "WMI")
    group = PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name="主机默认告警",
        templates=[_template(monitor_object, wmi, "WMI CPU")],
    )
    rule = group.rules.get()
    before = (
        rule.policy.trigger_count,
        rule.policy.recovery_condition,
        rule.policy.recovery_threshold,
        rule.policy.alert_name,
    )
    with pytest.raises(ValidationAppException):
        PolicyGroupService.update_rule(rule, **kwargs)
    rule.policy.refresh_from_db()
    assert (
        rule.policy.trigger_count,
        rule.policy.recovery_condition,
        rule.policy.recovery_threshold,
        rule.policy.alert_name,
    ) == before


def test_copy_keeps_schedule_no_data_and_rule_fields_on_the_same_plugin_carrier():
    group, wmi, ssh = _mixed_group()
    for rule in group.rules.select_related("policy"):
        policy = rule.policy
        policy.schedule = {"type": "min", "value": 1}
        policy.trigger_count = 3
        policy.recovery_condition = 4
        policy.alert_name = "{{host}} 过高"
        policy.recovery_threshold = {} if "磁盘" in rule.name else {"method": "<", "value": 20}
        if policy.group_by == ["instance_id"]:
            policy.enable_alerts = ["threshold", "no_data"]
            policy.no_data_period = {"type": "min", "value": 10}
            policy.no_data_level = "critical"
            policy.no_data_alert_name = "{{host}} 无数据"
            policy.no_data_recovery_period = {"type": "min", "value": 5}
        policy.save()

    copied = PolicyGroupService.copy_group(group, name="副本")

    def snapshot(target):
        rows = {}
        for rule in target.rules.select_related("policy", "plugin"):
            policy = rule.policy
            rows[(rule.plugin_id, tuple(policy.group_by or []))] = {
                "schedule": policy.schedule,
                "trigger_count": policy.trigger_count,
                "recovery_condition": policy.recovery_condition,
                "alert_name": policy.alert_name,
                "recovery_threshold": policy.recovery_threshold,
                "enable_alerts": policy.enable_alerts,
                "no_data_period": policy.no_data_period,
                "no_data_level": policy.no_data_level,
                "no_data_alert_name": policy.no_data_alert_name,
                "no_data_recovery_period": policy.no_data_recovery_period,
            }
        return rows

    assert snapshot(copied) == snapshot(group)
    copied_payload = _serialize_group(copied, None, metric_names={})
    flags = {rule["name"]: rule["no_data_carrier"] for rule in copied_payload["rules"]}
    assert flags["WMI CPU"] is True
    assert flags["SSH CPU"] is True
    assert flags["WMI 磁盘"] is False
    assert flags["SSH 磁盘"] is False
    copied_cpu = copied.rules.get(name="WMI CPU").policy
    copied_cpu.schedule = {"type": "hour", "value": 3}
    copied_cpu.save(update_fields=["schedule", "updated_at"])
    original_cpu = group.rules.get(name="WMI CPU").policy
    original_cpu.refresh_from_db()
    assert original_cpu.schedule == {"type": "min", "value": 1}


def test_group_serialization_reports_uniform_and_mixed_detection():
    group, wmi, ssh = _mixed_group()
    for rule in group.rules.select_related("policy"):
        rule.policy.schedule = {"type": "min", "value": 5}
        rule.policy.alert_name = rule.name
        rule.policy.trigger_count = 2
        rule.policy.recovery_condition = 3
        rule.policy.recovery_threshold = {"method": "<", "value": 1}
        if rule.policy.group_by == ["instance_id"]:
            rule.policy.enable_alerts = ["threshold", "no_data"]
            rule.policy.no_data_period = {"type": "min", "value": 10}
            rule.policy.no_data_level = "warning"
            rule.policy.no_data_alert_name = "无数据"
            rule.policy.no_data_recovery_period = {"type": "min", "value": 10}
        rule.policy.save()

    uniform = _serialize_group(group, None, metric_names={})
    assert uniform["schedule"] == {"type": "min", "value": 5}
    assert uniform["schedule_uniform"] is True
    assert uniform["no_data"] == {
        "enabled": True,
        "period": {"type": "min", "value": 10},
        "level": "warning",
        "alert_name": "无数据",
        "recovery_period": {"type": "min", "value": 10},
    }
    assert uniform["no_data_uniform"] is True
    cpu = next(item for item in uniform["rules"] if item["name"] == "WMI CPU")
    assert cpu["alert_name"] == "WMI CPU"
    assert cpu["trigger_count"] == 2
    assert cpu["recovery_condition"] == 3
    assert cpu["recovery_threshold"] == {"method": "<", "value": 1}
    assert cpu["no_data_carrier"] is True

    disk = group.rules.get(name="WMI 磁盘")
    disk.policy.schedule = {"type": "hour", "value": 1}
    disk.policy.enable_alerts = ["threshold", "no_data"]
    disk.policy.save(update_fields=["schedule", "enable_alerts", "updated_at"])
    mixed = _serialize_group(group, None, metric_names={})
    assert mixed["schedule"] == {}
    assert mixed["schedule_uniform"] is False
    assert mixed["no_data_uniform"] is False
    assert mixed["no_data"]["enabled"] is False
    disk_row = next(item for item in mixed["rules"] if item["name"] == "WMI 磁盘")
    assert disk_row["no_data_carrier"] is False
