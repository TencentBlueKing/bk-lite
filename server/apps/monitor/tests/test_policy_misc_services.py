"""policy_source_cleanup / policy / organization_rule 服务规格测试。"""

from datetime import datetime, timezone

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObjectOrganizationRule,
)
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyTemplate
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.policy_source_cleanup import (
    PolicySourceCleanupService,
    cleanup_policy_sources,
)
from apps.monitor.services.policy import PolicyService
from apps.monitor.services.organization_rule import OrganizationRule

pytestmark = pytest.mark.django_db


def _make_obj(name="MiscObj"):
    return MonitorObject.objects.create(name=name, level="base", instance_id_keys=["instance_id"])


def _make_policy(obj, source, enable=True):
    return MonitorPolicy.objects.create(
        monitor_object=obj, name="p", algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source=source, group_by=["instance_id"], enable=enable,
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestPolicySourceCleanup:
    def test_empty_ids_returns_zero(self):
        result = cleanup_policy_sources([])
        assert result["cleaned_count"] == 0
        assert result["policy_ids"] == []

    def test_removes_deleted_instance_from_source(self):
        obj = _make_obj()
        policy = _make_policy(obj, {"type": "instance", "values": ["('h1',)", "('h2',)"]})
        result = PolicySourceCleanupService.cleanup_by_instance_ids(["('h1',)"])
        policy.refresh_from_db()
        assert policy.source["values"] == ["('h2',)"]
        assert policy.enable is True
        assert result["cleaned_count"] == 1
        assert result["disabled_count"] == 0

    def test_disables_policy_when_all_instances_removed(self):
        obj = _make_obj()
        policy = _make_policy(obj, {"type": "instance", "values": ["('h1',)"]})
        result = PolicySourceCleanupService.cleanup_by_instance_ids(["('h1',)"])
        policy.refresh_from_db()
        assert policy.source["values"] == []
        assert policy.enable is False
        assert result["disabled_count"] == 1
        assert policy.id in result["disabled_policy_ids"]

    def test_untouched_policy_not_updated(self):
        obj = _make_obj()
        policy = _make_policy(obj, {"type": "instance", "values": ["('keep',)"]})
        result = PolicySourceCleanupService.cleanup_by_instance_ids(["('other',)"])
        policy.refresh_from_db()
        assert policy.source["values"] == ["('keep',)"]
        assert result["cleaned_count"] == 0


class TestPolicyService:
    def test_import_and_get_templates(self):
        obj = MonitorObject.objects.create(name="ImpObj", display_name="导入对象", level="base")
        MonitorPlugin.objects.create(name="ImpPlugin", display_name="导入插件", collector="Telegraf")
        PolicyService.import_monitor_policy({
            "plugin": "ImpPlugin", "object": "ImpObj",
            "templates": [{"name": "t1", "metric_id": 1}],
        })
        templates = PolicyService.get_policy_templates("ImpObj")
        assert len(templates) == 1
        assert templates[0]["name"] == "t1"
        assert templates[0]["plugin_name"] == "ImpPlugin"
        assert templates[0]["monitor_object_name"] == "ImpObj"
        assert "导入对象" in templates[0]["template_group"]

    def test_import_updates_existing(self):
        MonitorObject.objects.create(name="ImpObj2", level="base")
        MonitorPlugin.objects.create(name="ImpPlugin2", collector="Telegraf")
        data = {"plugin": "ImpPlugin2", "object": "ImpObj2", "templates": [{"name": "a"}]}
        PolicyService.import_monitor_policy(data)
        data["templates"] = [{"name": "b"}, {"name": "c"}]
        PolicyService.import_monitor_policy(data)
        assert PolicyTemplate.objects.filter(monitor_object__name="ImpObj2").count() == 1
        templates = PolicyService.get_policy_templates("ImpObj2")
        assert {t["name"] for t in templates} == {"b", "c"}

    def test_get_template_monitor_objects(self):
        obj = MonitorObject.objects.create(name="ImpObj3", level="base")
        plugin = MonitorPlugin.objects.create(name="ImpPlugin3", collector="Telegraf")
        PolicyTemplate.objects.create(monitor_object=obj, plugin=plugin, templates=[])
        assert obj.id in PolicyService.get_policy_templates_monitor_object()


class TestOrganizationRule:
    def test_missing_rule_raises(self):
        with pytest.raises(BaseAppException):
            OrganizationRule.del_organization_rule(999999, del_instance_org=False)

    def test_deletes_rule_only(self):
        obj = _make_obj("OrgRuleObj")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj, name="r", organizations=[1], rule={},
        )
        OrganizationRule.del_organization_rule(rule.id, del_instance_org=False)
        assert not MonitorObjectOrganizationRule.objects.filter(id=rule.id).exists()

    def test_deletes_rule_and_instance_org(self, mocker):
        obj = _make_obj("OrgRuleObj2")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=7)
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj, name="r2", organizations=[7], rule={},
        )
        mocker.patch(
            "apps.monitor.services.organization_rule.RuleGrouping.get_asso_by_condition_rule",
            return_value=[("('h1',)", 7)],
        )
        OrganizationRule.del_organization_rule(rule.id, del_instance_org=True)
        assert not MonitorObjectOrganizationRule.objects.filter(id=rule.id).exists()
        assert not MonitorInstanceOrganization.objects.filter(
            monitor_instance_id="('h1',)", organization=7
        ).exists()
