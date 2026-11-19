import logging

import pytest
from django.core.management import call_command
from django_celery_beat.models import PeriodicTask

from apps.core.logger import SafeLogException
from apps.monitor.models import (
    Metric,
    MetricGroup,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPlugin,
    PolicyGroup,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyGroupRule,
    PolicyTemplate,
)
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db

SENTINEL = "policy-template-secret-sentinel"


def _object(name):
    return MonitorObject.objects.create(name=name, level="base")


def _plugin(monitor_object, name):
    plugin = MonitorPlugin.objects.create(name=name, collector="Telegraf", collect_type="host")
    plugin.monitor_object.add(monitor_object)
    return plugin


def _template(monitor_object, plugin, name, *, config=None):
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
        config=config or {"metric_name": "cpu_usage_total", "threshold": [{"level": "warning", "value": 80, "method": ">="}]},
    )


def _instance(monitor_object, name, organization):
    instance = MonitorInstance.objects.create(id=f"('{name}',)", name=name, monitor_object=monitor_object)
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=organization)
    return instance


def _default_group():
    return Group.objects.create(name="Default", parent_id=0)


def test_default_organization_gets_one_group_per_builtin_object():
    default = _default_group()
    host = _object("InitHost")
    switch = _object("InitSwitch")
    bare = _object("InitBare")
    host_plugin = _plugin(host, "InitHostPlugin")
    switch_plugin = _plugin(switch, "InitSwitchPlugin")
    _template(host, host_plugin, "CPU")
    _template(host, host_plugin, "Memory")
    _template(switch, switch_plugin, "Port")
    existing = _instance(host, "already-there", default.id)
    memberships_before = PolicyGroupMembership.objects.count()

    call_command("init_default_policy_groups")

    host_group = PolicyGroup.objects.get(organization=default.id, monitor_object=host)
    switch_group = PolicyGroup.objects.get(organization=default.id, monitor_object=switch)
    assert host_group.origin == PolicyGroup.ORIGIN_SYSTEM
    assert host_group.name == "InitHost默认告警"
    assert switch_group.name == "InitSwitch默认告警"
    assert host_group.rules.count() == 2
    assert switch_group.rules.count() == 1
    assert PolicyGroupDefault.objects.filter(organization=default.id, monitor_object=host, policy_group=host_group).exists()
    assert PolicyGroupDefault.objects.filter(organization=default.id, monitor_object=switch, policy_group=switch_group).exists()
    assert not PolicyGroup.objects.filter(monitor_object=bare).exists()
    assert not PolicyGroupDefault.objects.filter(monitor_object=bare).exists()
    policy_ids = list(PolicyGroupRule.objects.filter(group__organization=default.id).values_list("policy_id", flat=True))
    assert len(policy_ids) == 3
    tasks = list(PeriodicTask.objects.filter(name__in=[f"scan_policy_task_{policy_id}" for policy_id in policy_ids]))
    assert len(tasks) == 3
    assert all(task.enabled is False for task in tasks)
    assert PolicyGroupMembership.objects.count() == memberships_before
    assert not PolicyGroupMembership.objects.filter(monitor_instance=existing).exists()


def test_second_run_does_not_rebuild_groups(caplog):
    default = _default_group()
    host = _object("TwiceHost")
    plugin = _plugin(host, "TwicePlugin")
    _template(host, plugin, "CPU")
    call_command("init_default_policy_groups")
    group_ids = set(PolicyGroup.objects.values_list("id", flat=True))
    rule_ids = set(PolicyGroupRule.objects.values_list("id", flat=True))
    pointer_ids = set(PolicyGroupDefault.objects.values_list("id", flat=True))

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="monitor"):
        call_command("init_default_policy_groups")

    assert set(PolicyGroup.objects.values_list("id", flat=True)) == group_ids
    assert set(PolicyGroupRule.objects.values_list("id", flat=True)) == rule_ids
    assert set(PolicyGroupDefault.objects.values_list("id", flat=True)) == pointer_ids
    finished = [
        record.getMessage() for record in caplog.records if record.name == "monitor" and "policy_group_default_init_finished" in record.getMessage()
    ]
    assert finished == [f"event=policy_group_default_init_finished organization={default.id} created=0 skipped=1 failed=0"]


def test_empty_default_pointer_is_not_rebuilt():
    default = _default_group()
    host = _object("DeletedDefaultHost")
    plugin = _plugin(host, "DeletedDefaultPlugin")
    _template(host, plugin, "CPU")
    pointer = PolicyGroupDefault.objects.create(organization=default.id, monitor_object=host, policy_group=None)

    call_command("init_default_policy_groups")

    pointer.refresh_from_db()
    assert pointer.policy_group_id is None
    assert not PolicyGroup.objects.filter(organization=default.id, monitor_object=host).exists()


def test_guest_and_other_organizations_are_not_initialized():
    default = _default_group()
    guest = Group.objects.create(name="Guest", parent_id=0)
    business = Group.objects.create(name="业务", parent_id=0)
    host = _object("SharedHost")
    plugin = _plugin(host, "SharedPlugin")
    _template(host, plugin, "CPU")

    call_command("init_default_policy_groups")

    assert PolicyGroup.objects.filter(organization=default.id).count() == 1
    assert PolicyGroup.objects.filter(organization=guest.id).count() == 0
    assert PolicyGroup.objects.filter(organization=business.id).count() == 0
    assert not PolicyGroupDefault.objects.exclude(organization=default.id).exists()


def test_one_object_failure_continues_and_hides_sentinel(monkeypatch, caplog):
    default = _default_group()
    failing = _object("FailingHost")
    healthy = _object("HealthyHost")
    failing_plugin = _plugin(failing, "FailingPlugin")
    healthy_plugin = _plugin(healthy, "HealthyPlugin")
    _template(failing, failing_plugin, "CPU", config={"secret": SENTINEL, "metric_name": "cpu_usage_total"})
    _template(healthy, healthy_plugin, "CPU")
    from apps.monitor.services.policy_group import PolicyGroupService

    real_ensure_default = PolicyGroupService.ensure_default
    raised = {}

    def wrapped(*, organization, monitor_object, operator="system"):
        if monitor_object.id == failing.id:
            error = RuntimeError(f"ensure failed {SENTINEL}")
            raised["error"] = error
            raise error
        return real_ensure_default(organization=organization, monitor_object=monitor_object, operator=operator)

    monkeypatch.setattr(PolicyGroupService, "ensure_default", staticmethod(wrapped))
    memberships_before = PolicyGroupMembership.objects.count()

    with caplog.at_level(logging.DEBUG, logger="monitor"):
        call_command("init_default_policy_groups")

    assert PolicyGroup.objects.filter(organization=default.id, monitor_object=healthy).count() == 1
    assert not PolicyGroup.objects.filter(monitor_object=failing).exists()
    assert not PolicyGroupDefault.objects.filter(monitor_object=failing).exists()
    assert PolicyGroupMembership.objects.count() == memberships_before
    traceback_records = [record for record in caplog.records if record.exc_info]
    assert len(traceback_records) == 1
    record = traceback_records[0]
    assert record.levelname == "ERROR"
    assert record.msg == "event=policy_group_default_init_failed organization=%s monitor_object_id=%s failed_stage=ensure_default error_type=%s"
    assert record.args == (default.id, failing.id, "RuntimeError")
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is raised["error"].__traceback__
    rendered = record.getMessage()
    formatted = logging.Formatter().format(record)
    assert "failed_stage=ensure_default" in rendered
    assert "error_type=RuntimeError" in rendered
    assert formatted.count("Traceback (most recent call last)") == 1
    assert SENTINEL not in rendered
    assert SENTINEL not in formatted
    assert SENTINEL not in caplog.text
    finished = [item.getMessage() for item in caplog.records if "policy_group_default_init_finished" in item.getMessage()]
    assert finished == [f"event=policy_group_default_init_finished organization={default.id} created=1 skipped=0 failed=1"]


def test_missing_default_organization_warns_and_creates_nothing(caplog):
    Group.objects.create(name="Guest", parent_id=0)
    host = _object("NoDefaultHost")
    plugin = _plugin(host, "NoDefaultPlugin")
    _template(host, plugin, "CPU")

    with caplog.at_level(logging.WARNING, logger="monitor"):
        call_command("init_default_policy_groups")

    assert PolicyGroup.objects.count() == 0
    assert PolicyGroupDefault.objects.count() == 0
    warnings = [record for record in caplog.records if record.levelname == "WARNING" and record.name == "monitor"]
    assert len(warnings) == 1
    assert warnings[0].msg == "event=policy_group_default_init_skipped reason=default_organization_missing failed_stage=resolve_organization"
    assert warnings[0].getMessage() == warnings[0].msg
    assert not any("policy_group_default_init_finished" in record.getMessage() for record in caplog.records)
