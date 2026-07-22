"""InstanceConfigService 规格测试。

聚焦节点选择校验、默认分组指标、实例属性同步、采集配置内容读取、授权助手。
NodeMgmt RPC / 权限规则为外部边界，mock。
"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.constants.permission import PermissionConstants  # noqa: F401
from apps.monitor.models import CollectConfig, Metric
from apps.monitor.models.monitor_metrics import MetricGroup
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.node_mgmt import InstanceConfigService

pytestmark = pytest.mark.django_db
SVC = InstanceConfigService


def _actor_context(*, teams=(1,), is_superuser=True):
    scope = CurrentTeamDataScope(
        current_team=1,
        data_team_ids=frozenset(teams),
        include_children=False,
        username="admin",
        domain="domain.com",
        is_superuser=is_superuser,
    )
    return {
        "username": scope.username,
        "domain": scope.domain,
        "current_team": scope.current_team,
        "include_children": scope.include_children,
        "is_superuser": scope.is_superuser,
        "data_scope": scope,
    }


class TestPermissionDataHelpers:
    def test_build_permission_data(self):
        ctx = {"username": "u", "domain": "d", "current_team": 1, "include_children": True}
        out = SVC._build_permission_data(ctx)
        assert out == {"username": "u", "domain": "d", "current_team": 1, "include_children": True}

    def test_build_actor_user(self):
        user = SVC._build_actor_user({"username": "u", "domain": "d"})
        assert user.username == "u" and user.domain == "d"


class TestGetPluginNodeSelector:
    def test_empty_id_returns_empty(self):
        assert SVC._get_plugin_node_selector(None) == {}

    def test_missing_plugin_raises(self):
        with pytest.raises(BaseAppException):
            SVC._get_plugin_node_selector(999999)

    def test_normalizes_selector(self):
        plugin = MonitorPlugin.objects.create(name="NSPlugin", node_selector={"is_container": True})
        assert SVC._get_plugin_node_selector(plugin.id) == {"is_container": True}


class TestValidateNodesAgainstSelector:
    def test_no_selector_noop(self):
        assert SVC._validate_nodes_against_selector([{"id": 1}], {}) is None

    def test_container_required_rejects_non_container(self):
        nodes = [{"id": "n1", "node_type": "host"}]
        with pytest.raises(BaseAppException):
            SVC._validate_nodes_against_selector(nodes, {"is_container": True})

    def test_container_required_accepts_container(self):
        from apps.node_mgmt.constants.controller import ControllerConstants
        nodes = [{"id": "n1", "node_type": ControllerConstants.NODE_TYPE_CONTAINER}]
        assert SVC._validate_nodes_against_selector(nodes, {"is_container": True}) is None


class TestGetDefaultGroupMetric:
    def test_prefers_configured_metric(self):
        obj = MonitorObject.objects.create(name="Pod", level="derivative")
        plugin = MonitorPlugin.objects.create(name="PodPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        Metric.objects.create(monitor_object=obj, monitor_plugin=plugin, metric_group=group, name="other")
        preferred = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group, name="pod_status_phase",
        )
        out = SVC._get_default_group_metric(obj)
        assert out.id == preferred.id

    def test_falls_back_to_first_metric(self):
        obj = MonitorObject.objects.create(name="CustomObj", level="derivative")
        plugin = MonitorPlugin.objects.create(name="CustomPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        first = Metric.objects.create(monitor_object=obj, monitor_plugin=plugin, metric_group=group, name="m1")
        out = SVC._get_default_group_metric(obj)
        assert out.id == first.id


class TestSyncExistingInstanceAttrs:
    def test_empty_returns_zero(self):
        assert SVC._sync_existing_instance_attrs([], deleted_ids=None) == 0

    def test_updates_to_manual_and_active(self):
        obj = MonitorObject.objects.create(name="SyncAttrObj", level="base")
        MonitorInstance.objects.create(
            id="('h1',)", name="old", monitor_object=obj, auto=True, is_deleted=True, is_active=False,
        )
        count = SVC._sync_existing_instance_attrs(
            [{"instance_id": "('h1',)", "instance_name": "new"}],
            deleted_ids={"('h1',)"},
        )
        assert count == 1
        inst = MonitorInstance.objects.get(id="('h1',)")
        assert inst.name == "new"
        assert inst.auto is False
        assert inst.is_active is True
        assert inst.is_deleted is False


class TestGetConfigContent:
    def _mk_config(self, is_child, file_type):
        obj = MonitorObject.objects.create(name=f"CCObj-{is_child}-{file_type}", level="base")
        plugin = MonitorPlugin.objects.create(name=f"CCPlugin-{is_child}-{file_type}")
        inst = MonitorInstance.objects.create(id=f"('cc-{is_child}-{file_type}',)", name="i", monitor_object=obj)
        return CollectConfig.objects.create(
            id=f"cfg-{is_child}-{file_type}", monitor_instance=inst, monitor_plugin=plugin,
            collector="Telegraf", collect_type="snmp", config_type="child" if is_child else "base",
            file_type=file_type, is_child=is_child,
        )

    def test_empty_ids(self):
        assert SVC.get_config_content([]) == {}

    def test_child_toml_config(self, mocker):
        cfg = self._mk_config(is_child=True, file_type="toml")
        node = mocker.patch("apps.monitor.services.node_mgmt.NodeMgmt")
        node.return_value.get_child_configs_by_ids.return_value = [
            {"id": cfg.id, "content": '[[inputs.snmp]]\nagents=["x"]'}
        ]
        out = SVC.get_config_content([cfg.id])
        assert "child" in out
        assert isinstance(out["child"]["content"], dict)

    def test_base_yaml_config(self, mocker):
        cfg = self._mk_config(is_child=False, file_type="yaml")
        node = mocker.patch("apps.monitor.services.node_mgmt.NodeMgmt")
        node.return_value.get_configs_by_ids.return_value = [
            {"id": cfg.id, "config_template": "key: value"}
        ]
        out = SVC.get_config_content([cfg.id])
        assert "base" in out
        assert out["base"]["content"] == {"key": "value"}

    def test_invalid_file_type_raises(self, mocker):
        cfg = self._mk_config(is_child=True, file_type="ini")
        node = mocker.patch("apps.monitor.services.node_mgmt.NodeMgmt")
        node.return_value.get_child_configs_by_ids.return_value = [{"id": cfg.id, "content": "x"}]
        with pytest.raises(BaseAppException):
            SVC.get_config_content([cfg.id])


class TestEnsureInstanceAccess:
    def test_missing_instance_raises(self):
        with pytest.raises(BaseAppException):
            SVC._ensure_instance_access("('missing',)")

    def test_superuser_returns_instance(self):
        obj = MonitorObject.objects.create(name="EIAObj", level="base")
        instance = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=1)
        inst = SVC._ensure_instance_access("('h1',)", actor_context=_actor_context())
        assert inst.id == "('h1',)"

    def test_no_actor_context_returns_instance(self):
        obj = MonitorObject.objects.create(name="EIAObj2", level="base")
        MonitorInstance.objects.create(id="('h2',)", name="h2", monitor_object=obj)
        inst = SVC._ensure_instance_access("('h2',)", actor_context=None)
        assert inst.id == "('h2',)"


class TestGetInstanceConfigs:
    def test_groups_configs_by_plugin_and_type(self, mocker):
        obj = MonitorObject.objects.create(name="GICObj", level="base")
        plugin = MonitorPlugin.objects.create(name="GICPlugin")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        CollectConfig.objects.create(
            id="gic-base", monitor_instance=inst, monitor_plugin=plugin,
            collector="Telegraf", collect_type="snmp", config_type="base",
            file_type="toml", is_child=False,
        )
        # get_config_content 已单测，这里 stub 掉避免触达 NodeMgmt
        mocker.patch(
            "apps.monitor.services.node_mgmt.InstanceConfigService.get_config_content",
            return_value={"base": {"content": {}}},
        )
        items = SVC.get_instance_configs("('h1',)")
        assert len(items) == 1
        assert items[0]["instance_id"] == "('h1',)"
        assert items[0]["config_ids"] == ["gic-base"]
        assert "config_content" in items[0]


class TestCreateDefaultRule:
    def test_no_children_returns_empty(self):
        obj = MonitorObject.objects.create(name="CDRObj", level="base")
        assert SVC.create_default_rule(obj.id, "('h1',)", [1]) == []

    def test_creates_rule_for_child(self):
        from apps.monitor.models import MonitorObjectOrganizationRule
        parent = MonitorObject.objects.create(name="CDRParent", level="base")
        child = MonitorObject.objects.create(name="CDRChild", level="derivative", parent=parent)
        plugin = MonitorPlugin.objects.create(name="CDRPlugin")
        group = MetricGroup.objects.create(monitor_object=child, monitor_plugin=plugin, name="g")
        Metric.objects.create(monitor_object=child, monitor_plugin=plugin, metric_group=group, name="m")
        rule_ids = SVC.create_default_rule(parent.id, "('h1',)", [5])
        assert len(rule_ids) == 1
        rule = MonitorObjectOrganizationRule.objects.get(id=rule_ids[0])
        assert rule.monitor_object_id == child.id
        assert rule.organizations == [5]
        assert rule.rule["filter"][0]["value"] == "h1"


class TestGetAuthorizedMonitorInstancesSuperuser:
    def test_superuser_stays_in_current_team(self, mocker):
        obj = MonitorObject.objects.create(name="AuthObj", level="base")
        current = MonitorInstance.objects.create(id="('a1',)", name="a1", monitor_object=obj)
        sibling = MonitorInstance.objects.create(id="('a2',)", name="a2", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=current, organization=1)
        MonitorInstanceOrganization.objects.create(monitor_instance=sibling, organization=2)
        mocker.patch(
            "apps.monitor.services.node_mgmt.get_permission_rules",
            return_value={"team": [1, 2], "instance": []},
        )

        qs = SVC._get_authorized_monitor_instances(_actor_context(), obj.id)

        assert set(qs.values_list("id", flat=True)) == {current.id}
