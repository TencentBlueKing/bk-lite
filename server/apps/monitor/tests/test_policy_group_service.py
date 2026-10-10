import pytest

from apps.monitor.filters.monitor_policy import exclude_policy_group_rules
from django_celery_beat.models import PeriodicTask

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
    return CollectConfig.objects.create(
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

    PolicyGroupService.leave(instance=host)

    host.policy_group_membership.refresh_from_db()
    assert PeriodicTask.objects.get(name=f"scan_policy_task_{policy.id}").enabled is False
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
    other_alert = MonitorAlert.objects.create(
        policy_id=other_policy.id, monitor_instance_id=host.id, status="new", alert_type="alert"
    )

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
