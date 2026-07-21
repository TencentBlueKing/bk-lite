"""MonitorObjectViewSet / MonitorObjectTypeViewSet / 组织规则视图补充测试。"""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObjectOrganizationRule
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer
from apps.monitor.views import monitor_object as monitor_object_view
from apps.monitor.views.monitor_object import MonitorObjectViewSet

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


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

    def test_type_serialization_query_count_is_constant(self):
        single_type = MonitorObjectType.objects.create(id="query-single", name="单对象类型")
        multiple_type = MonitorObjectType.objects.create(id="query-multiple", name="多对象类型")
        MonitorObject.objects.create(name="OVQuerySingle0", level="base", type=single_type)
        for index in range(4):
            MonitorObject.objects.create(name=f"OVQueryMultiple{index}", level="base", type=multiple_type)

        view = MonitorObjectViewSet()
        view.request = SimpleNamespace(query_params={})

        def serialize(prefix):
            queryset = view.get_queryset().filter(name__startswith=prefix)
            with CaptureQueriesContext(connection) as queries:
                MonitorObjectSerializer(queryset, many=True).data
            return len(queries)

        assert serialize("OVQuerySingle") == serialize("OVQueryMultiple") == 1

    def test_instance_count_only_checks_permission_candidates(self, api_client, mocker):
        allowed_object = MonitorObject.objects.create(name="OVCountAllowed", level="base")
        fallback_object = MonitorObject.objects.create(name="OVCountFallback", level="base")

        allowed_by_team = MonitorInstance.objects.create(
            id="ov-count-team",
            name="团队授权实例",
            monitor_object=allowed_object,
        )
        allowed_explicitly = MonitorInstance.objects.create(
            id="ov-count-explicit",
            name="显式授权实例",
            monitor_object=allowed_object,
        )
        denied = MonitorInstance.objects.create(
            id="ov-count-denied",
            name="无关实例",
            monitor_object=allowed_object,
        )
        allowed_by_current_team = MonitorInstance.objects.create(
            id="ov-count-current-team",
            name="当前团队实例",
            monitor_object=fallback_object,
        )
        unrelated = MonitorInstance.objects.create(
            id="ov-count-unrelated",
            name="范围外实例",
            monitor_object=fallback_object,
        )

        for instance, organization in (
            (allowed_by_team, 10),
            (allowed_explicitly, 99),
            (denied, 99),
            (allowed_by_current_team, 20),
            (unrelated, 99),
        ):
            MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=organization)

        permissions = {
            str(allowed_object.id): {
                "team": [10],
                "instance": [{"id": allowed_explicitly.id, "permission": ["View"]}],
            }
        }
        mocker.patch(
            "apps.monitor.views.monitor_object.get_permissions_rules",
            return_value={"data": permissions, "team": [20]},
        )
        permission_spy = mocker.spy(monitor_object_view, "check_instance_permission")

        response = api_client.get(f"{BASE}/api/monitor_object/?add_instance_count=true")

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["data"]}
        assert rows[allowed_object.name]["instance_count"] == 2
        assert rows[fallback_object.name]["instance_count"] == 1

        checked_ids = {
            call.args[1]
            for call in permission_spy.call_args_list
            if call.args[0] in {allowed_object.id, fallback_object.id}
        }
        assert checked_ids == {
            allowed_by_team.id,
            allowed_explicitly.id,
            allowed_by_current_team.id,
        }

    def test_instance_count_skips_query_candidates_when_permissions_are_empty(self, api_client, mocker):
        monitor_object = MonitorObject.objects.create(name="OVCountEmpty", level="base")
        instance = MonitorInstance.objects.create(
            id="ov-count-empty",
            name="无授权实例",
            monitor_object=monitor_object,
        )
        MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=99)
        mocker.patch(
            "apps.monitor.views.monitor_object.get_permissions_rules",
            return_value={"data": {}, "team": []},
        )
        permission_spy = mocker.spy(monitor_object_view, "check_instance_permission")

        response = api_client.get(f"{BASE}/api/monitor_object/?add_instance_count=true")

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["data"]}
        assert rows[monitor_object.name]["instance_count"] == 0
        assert all(call.args[1] != instance.id for call in permission_spy.call_args_list)


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
    def test_destroy_calls_service(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        obj = MonitorObject.objects.create(name="ORVObj", level="base")
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj, name="r", organizations=[1], rule={},
        )
        # 超级用户路径绕过授权过滤
        mocker.patch(
            "apps.monitor.views.organization_rule._build_actor_context",
            return_value={"is_superuser": True, "current_team": 1,
                          "username": "u", "domain": "domain.com",
                          "include_children": False, "group_list": []},
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
        assert _normalize_rule_organizations([1, "2", None, ""]) == {1, 2}

    def test_normalize_rule_organizations_invalid(self):
        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.views.organization_rule import _normalize_rule_organizations
        with pytest.raises(BaseAppException):
            _normalize_rule_organizations(["abc"])

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
        from apps.monitor.models import MonitorInstance
        parent = MonitorObject.objects.create(name="UpdDeriveParent", level="base")
        child = MonitorObject.objects.create(name="UpdDeriveChild", level="derivative", parent=parent)
        MonitorInstance.objects.create(id="('vp1',)", name="vp1", monitor_object=parent)
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
        # 超级用户路径绕过授权过滤
        mocker_module = pytest.importorskip("pytest_mock")
        import pytest_mock  # noqa: F401
        from unittest.mock import patch
        with patch(
            "apps.monitor.views.organization_rule._build_actor_context",
            return_value={"is_superuser": True, "current_team": 1,
                          "username": "u", "domain": "domain.com",
                          "include_children": False, "group_list": []},
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
        assert _rule_is_authorized(rule, {"is_superuser": True}) is True
