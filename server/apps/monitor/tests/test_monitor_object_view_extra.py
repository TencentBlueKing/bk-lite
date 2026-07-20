"""MonitorObjectViewSet / MonitorObjectTypeViewSet / 组织规则视图补充测试。"""

import pytest

from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.models import MonitorObjectOrganizationRule
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


def _superuser_actor_context():
    scope = CurrentTeamDataScope(1, frozenset({1}), False, "u", "domain.com", True)
    return {
        "is_superuser": True,
        "current_team": 1,
        "username": "u",
        "domain": "domain.com",
        "include_children": False,
        "group_list": [],
        "data_scope": scope,
    }


class TestMonitorObjectList:
    def test_list_adds_display_and_children_count(self, api_client):
        parent = MonitorObject.objects.create(name="OVParent", display_name="父对象", level="base")
        MonitorObject.objects.create(name="OVChild", level="derivative", parent=parent)
        resp = api_client.get(f"{BASE}/api/monitor_object/")
        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()["data"]}
        assert rows["OVParent"]["children_count"] == 1
        assert rows["OVParent"]["display_name"] == "父对象"
        assert "is_builtin" in rows["OVParent"]

    def test_parent_only_filter(self, api_client):
        parent = MonitorObject.objects.create(name="OVP2", level="base")
        MonitorObject.objects.create(name="OVC2", level="derivative", parent=parent)
        resp = api_client.get(f"{BASE}/api/monitor_object/?parent_only=true")
        names = {r["name"] for r in resp.json()["data"]}
        assert "OVP2" in names and "OVC2" not in names


class TestMonitorObjectCreate:
    def test_create_with_children_autofills(self, api_client):
        mtype = MonitorObjectType.objects.create(id="custom", name="自定义")
        resp = api_client.post(
            f"{BASE}/api/monitor_object/",
            {"name": "NewParent", "type": "custom",
             "children": [{"id": "ChildA", "name": "子A"}]},
            format="json",
        )
        assert resp.status_code == 200
        parent = MonitorObject.objects.get(name="NewParent")
        # default_metric 自动填充
        assert "instance_type='NewParent'" in parent.default_metric
        assert parent.instance_id_keys == ["instance_id"]
        child = MonitorObject.objects.get(name="ChildA")
        assert child.level == "derivative"
        assert child.parent_id == parent.id
        assert child.display_name == "子A"


class TestMonitorObjectUpdate:
    def test_update_adds_new_child(self, api_client):
        parent = MonitorObject.objects.create(name="UpdParent", level="base", instance_id_keys=["instance_id"])
        resp = api_client.put(
            f"{BASE}/api/monitor_object/{parent.id}/",
            {"name": "UpdParent", "level": "base",
             "children": [{"id": "UpdChild", "name": "新子"}]},
            format="json",
        )
        assert resp.status_code == 200
        child = MonitorObject.objects.get(name="UpdChild")
        assert child.parent_id == parent.id


class TestMonitorObjectActions:
    def test_order(self, api_client, mocker):
        spy = mocker.patch(
            "apps.monitor.views.monitor_object.MonitorObjectService.set_object_order"
        )
        resp = api_client.post(
            f"{BASE}/api/monitor_object/order/",
            [{"id": 1, "order": 2}],
            format="json",
        )
        assert resp.status_code == 200
        spy.assert_called_once()

    def test_visibility_toggle(self, api_client):
        obj = MonitorObject.objects.create(name="VisObj", level="base", is_visible=True)
        resp = api_client.post(
            f"{BASE}/api/monitor_object/{obj.id}/visibility/",
            {"is_visible": False}, format="json",
        )
        assert resp.status_code == 200
        obj.refresh_from_db()
        assert obj.is_visible is False

    def test_visibility_requires_field(self, api_client):
        obj = MonitorObject.objects.create(name="VisObj2", level="base")
        resp = api_client.post(
            f"{BASE}/api/monitor_object/{obj.id}/visibility/", {}, format="json",
        )
        body = resp.json()
        assert body.get("result") is False or resp.status_code != 200


class TestMonitorObjectTypeList:
    def test_list_excludes_all_and_counts(self, api_client):
        MonitorObjectType.objects.create(id="all", name="全部")
        t = MonitorObjectType.objects.create(id="net", name="网络")
        MonitorObject.objects.create(name="NetObj", level="base", type=t)
        resp = api_client.get(f"{BASE}/api/monitor_object_type/")
        assert resp.status_code == 200
        rows = {r["id"]: r for r in resp.json()["data"]}
        assert "all" not in rows
        assert rows["net"]["object_count"] == 1
        assert rows["net"]["display_name"] == "网络"


class TestOrganizationRuleView:
    def test_create_with_empty_organizations_has_no_rule_side_effect(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        obj = MonitorObject.objects.create(name="ORVEmptyCreateObj", level="base")
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
            return_value={"result": True, "data": [1]},
        )
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
            return_value={"result": True, "data": [1]},
        )

        resp = api_client.post(
            f"{BASE}/api/organization_rule/",
            {
                "monitor_object": obj.id,
                "name": "empty-org-rule",
                "organizations": [],
                "rule": {},
            },
            format="json",
        )

        assert resp.status_code == 500
        assert not MonitorObjectOrganizationRule.objects.filter(name="empty-org-rule").exists()

    def test_partial_update_shared_rule_without_organizations_keeps_existing_assignment(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        obj = MonitorObject.objects.create(name="ORVSharedPatchObj", level="base")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            name="shared-rule",
            organizations=[1, 2],
            rule={},
        )
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
            return_value={"result": True, "data": [1]},
        )
        assignable = mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
            return_value={"result": True, "data": [1]},
        )

        resp = api_client.patch(
            f"{BASE}/api/organization_rule/{rule.id}/",
            {"name": "renamed-shared-rule"},
            format="json",
        )

        assert resp.status_code == 200, resp.content
        rule.refresh_from_db()
        assert rule.name == "renamed-shared-rule"
        assert rule.organizations == [1, 2]
        assignable.assert_not_called()

    def test_partial_update_shared_rule_allows_assignable_sibling(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        obj = MonitorObject.objects.create(name="ORVSharedAssignObj", level="base")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            name="shared-rule",
            organizations=[1, 2],
            rule={},
        )
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
            return_value={"result": True, "data": [1]},
        )
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
            return_value={"result": True, "data": [1, 2]},
        )

        resp = api_client.patch(
            f"{BASE}/api/organization_rule/{rule.id}/",
            {"organizations": [2]},
            format="json",
        )

        assert resp.status_code == 200, resp.content
        rule.refresh_from_db()
        assert rule.organizations == [2]

    def test_partial_update_shared_rule_rejects_explicit_empty_organizations(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        obj = MonitorObject.objects.create(name="ORVSharedEmptyPatchObj", level="base")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            name="shared-rule",
            organizations=[1, 2],
            rule={},
        )
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
            return_value={"result": True, "data": [1]},
        )
        mocker.patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
            return_value={"result": True, "data": [1, 2]},
        )

        resp = api_client.patch(
            f"{BASE}/api/organization_rule/{rule.id}/",
            {"organizations": []},
            format="json",
        )

        assert resp.status_code == 500
        rule.refresh_from_db()
        assert rule.organizations == [1, 2]

    def test_destroy_calls_service(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        obj = MonitorObject.objects.create(name="ORVObj", level="base")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj, name="r", organizations=[1], rule={},
        )
        mocker.patch(
            "apps.monitor.views.organization_rule._build_actor_context",
            return_value=_superuser_actor_context(),
        )
        spy = mocker.patch(
            "apps.monitor.views.organization_rule.OrganizationRule.del_organization_rule"
        )
        resp = api_client.delete(f"{BASE}/api/organization_rule/{rule.id}/?del_instance_org=true")
        assert resp.status_code == 200
        spy.assert_called_once()
        assert spy.call_args.kwargs["del_instance_org"] is True

    def test_normalize_rule_organizations(self):
        from apps.monitor.views.organization_rule import _normalize_rule_organizations

        assert _normalize_rule_organizations([1, "2"]) == {1, 2}

    @pytest.mark.parametrize(
        "organizations",
        [
            [True],
            [1.5],
            ["01"],
            [1, "2", True],
            [1, None],
            [],
        ],
    )
    def test_normalize_rule_organizations_rejects_noncanonical_or_empty_snapshot(self, organizations):
        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.views.organization_rule import _normalize_rule_organizations

        with pytest.raises(BaseAppException):
            _normalize_rule_organizations(organizations)

    def test_validate_rule_binding_mismatch(self):
        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.views.organization_rule import _validate_rule_binding
        from apps.monitor.models import MonitorInstance
        obj = MonitorObject.objects.create(name="VRBObj", level="base")
        other = MonitorObject.objects.create(name="VRBOther", level="base")
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        with pytest.raises(BaseAppException):
            _validate_rule_binding(other.id, "('h1',)")

    def test_validate_rule_binding_ok(self):
        from apps.monitor.views.organization_rule import _validate_rule_binding
        from apps.monitor.models import MonitorInstance
        obj = MonitorObject.objects.create(name="VRBObj2", level="base")
        MonitorInstance.objects.create(id="('h2',)", name="h2", monitor_object=obj)
        # 匹配 → 不抛错
        assert _validate_rule_binding(obj.id, "('h2',)") is None

    def test_validate_rule_binding_derivative_object_with_parent_instance(self):
        """子对象(derivative)规则引用父实例应视为合法:对应 create_default_rule 自动建规则的设计"""
        from apps.monitor.views.organization_rule import _validate_rule_binding
        from apps.monitor.models import MonitorInstance
        parent = MonitorObject.objects.create(name="VRBParent", level="base")
        child = MonitorObject.objects.create(name="VRBChild", level="derivative", parent=parent)
        MonitorInstance.objects.create(id="('p1',)", name="p1", monitor_object=parent)
        # 规则对象=child,实例=parent 的实例 → 应放行
        assert _validate_rule_binding(child.id, "('p1',)") is None

    def test_validate_rule_binding_derivative_object_with_unrelated_instance(self):
        """子对象(derivative)规则引用无关实例必须仍报错,避免绕过访问范围"""
        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.views.organization_rule import _validate_rule_binding
        from apps.monitor.models import MonitorInstance
        parent = MonitorObject.objects.create(name="VRBParentU", level="base")
        child = MonitorObject.objects.create(name="VRBChildU", level="derivative", parent=parent)
        unrelated = MonitorObject.objects.create(name="VRBUnrelated", level="base")
        MonitorInstance.objects.create(id="('u1',)", name="u1", monitor_object=unrelated)
        with pytest.raises(BaseAppException):
            _validate_rule_binding(child.id, "('u1',)")

    def test_update_derivative_rule_with_parent_instance_succeeds(self, api_client):
        """回归: vmware 父实例自动建的子规则,编辑保存时不再被 500/校验拦截"""
        from apps.monitor.models import MonitorObjectOrganizationRule
        from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization
        parent = MonitorObject.objects.create(name="UpdDeriveParent", level="base")
        child = MonitorObject.objects.create(name="UpdDeriveChild", level="derivative", parent=parent)
        instance = MonitorInstance.objects.create(id="('vp1',)", name="vp1", monitor_object=parent)
        MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=1)
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=child,
            name="UpdDeriveChild-vp1",
            organizations=[1],
            rule={
                "type": "metric",
                "metric_id": 1,
                "filter": [{"name": "instance_id", "method": "=", "value": "vp1"}],
            },
            monitor_instance_id="('vp1',)",
        )
        mocker_module = pytest.importorskip("pytest_mock")
        import pytest_mock  # noqa: F401
        from unittest.mock import patch
        with patch(
            "apps.monitor.views.organization_rule._build_actor_context",
            return_value=_superuser_actor_context(),
        ), patch(
            "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
            return_value={"result": True, "data": [1]},
        ):
            resp = api_client.put(
                f"{BASE}/api/organization_rule/{rule.id}/",
                {
                    "name": "UpdDeriveChild-vp1",
                    "monitor_object": child.id,
                    "rule": rule.rule,
                    "organizations": [1],
                },
                format="json",
            )
        assert resp.status_code == 200, resp.content

    def test_rule_is_authorized_superuser(self):
        from apps.monitor.views.organization_rule import _rule_is_authorized
        from types import SimpleNamespace
        rule = SimpleNamespace(organizations=[1], monitor_instance_id="", monitor_object_id=1)
        assert _rule_is_authorized(rule, _superuser_actor_context()) is True

    def test_rule_serializer_hides_sibling_organizations(self):
        from apps.monitor.serializers.monitor_object import MonitorObjectOrganizationRuleSerializer

        obj = MonitorObject.objects.create(name="ORVProjectionObj", level="base")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj,
            name="shared-rule",
            organizations=[1, 2],
            rule={},
        )

        data = MonitorObjectOrganizationRuleSerializer(
            rule,
            context={"data_team_ids": frozenset({1})},
        ).data

        assert data["organizations"] == [1]
