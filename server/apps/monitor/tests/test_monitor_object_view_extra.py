"""MonitorObjectViewSet / MonitorObjectTypeViewSet / 组织规则视图补充测试。"""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObjectOrganizationRule
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.serializers.monitor_object import MonitorObjectSerializer
from apps.monitor.views import monitor_object as monitor_object_view
from apps.monitor.views.monitor_object import MonitorObjectViewSet

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
    @pytest.mark.parametrize(
        "value",
        [True, False, 1.0, float("inf"), 0, -1, "01", "0", "-1", "１", 2_147_483_648],
    )
    def test_candidate_team_ids_reject_noncanonical_values(self, value):
        assert monitor_object_view._normalize_candidate_team_ids([value]) == set()

    def test_candidate_team_ids_accept_canonical_positive_values(self):
        assert monitor_object_view._normalize_candidate_team_ids([1, "2", {"id": 3}, 2_147_483_647]) == {1, 2, 3, 2_147_483_647}

    def test_candidate_team_ids_reject_oversized_numeric_string(self):
        assert monitor_object_view._normalize_candidate_team_ids(["9" * 5000]) == set()

    def test_list_adds_display_and_children_count(self, api_client):
        parent = MonitorObject.objects.create(name="OVParent", display_name="父对象", level="base")
        MonitorObject.objects.create(name="OVChild", level="derivative", parent=parent)
        resp = api_client.get(f"{BASE}/api/monitor_object/")
        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()["data"]}
        assert rows["OVParent"]["children_count"] == 1
        assert rows["OVParent"]["display_name"] == "父对象"
        assert "is_builtin" in rows["OVParent"]

    def test_list_uses_custom_type_name_as_display_type(self, api_client):
        custom_type = MonitorObjectType.objects.create(
            id="7ef18d88-3f62-4e2d-946d-7da0238f98a8",
            name="测试分类",
        )
        MonitorObject.objects.create(
            name="OVCustomType",
            display_name="测试对象",
            level="base",
            type=custom_type,
        )

        resp = api_client.get(f"{BASE}/api/monitor_object/")

        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()["data"]}
        assert rows["OVCustomType"]["display_type"] == "测试分类"

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

        checked_ids = {call.args[1] for call in permission_spy.call_args_list if call.args[0] in {allowed_object.id, fallback_object.id}}
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

    def test_instance_count_keeps_all_team_permission_semantics(self, api_client, mocker):
        monitor_object = MonitorObject.objects.create(name="OVCountAllTeam", level="base")
        allowed = MonitorInstance.objects.create(
            id="ov-count-all-team",
            name="全局团队授权实例",
            monitor_object=monitor_object,
        )
        unrelated = MonitorInstance.objects.create(
            id="ov-count-all-unrelated",
            name="全局范围外实例",
            monitor_object=monitor_object,
        )
        MonitorInstanceOrganization.objects.create(monitor_instance=allowed, organization=30)
        MonitorInstanceOrganization.objects.create(monitor_instance=unrelated, organization=99)
        mocker.patch(
            "apps.monitor.views.monitor_object.get_permissions_rules",
            return_value={"data": {"all": {"team": [30]}}, "team": []},
        )
        permission_spy = mocker.spy(monitor_object_view, "check_instance_permission")

        response = api_client.get(f"{BASE}/api/monitor_object/?add_instance_count=true")

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["data"]}
        assert rows[monitor_object.name]["instance_count"] == 1
        checked_ids = {call.args[1] for call in permission_spy.call_args_list if call.args[0] == monitor_object.id}
        assert checked_ids == {allowed.id}

    def test_instance_count_ignores_invalid_team_candidate(self, api_client, mocker):
        monitor_object = MonitorObject.objects.create(name="OVCountInvalidTeam", level="base")
        instance = MonitorInstance.objects.create(
            id="ov-count-invalid-team",
            name="非法团队候选实例",
            monitor_object=monitor_object,
        )
        MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=10)
        mocker.patch(
            "apps.monitor.views.monitor_object.get_permissions_rules",
            return_value={"data": {str(monitor_object.id): {"team": ["not-a-team"]}}, "team": []},
        )
        permission_spy = mocker.spy(monitor_object_view, "check_instance_permission")

        response = api_client.get(f"{BASE}/api/monitor_object/?add_instance_count=true")

        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["data"]}
        assert rows[monitor_object.name]["instance_count"] == 0
        assert all(call.args[1] != instance.id for call in permission_spy.call_args_list)

    def test_instance_count_candidates_match_full_scan_reference(self):
        object_team = MonitorObject.objects.create(name="OVDiffObjectTeam", level="base")
        object_fallback = MonitorObject.objects.create(name="OVDiffFallback", level="base")
        object_admin = MonitorObject.objects.create(name="OVDiffAdmin", level="base")

        fixtures = (
            ("ov-diff-team", object_team, 10),
            ("ov-diff-explicit", object_team, 99),
            ("ov-diff-denied", object_team, 98),
            ("ov-diff-fallback", object_fallback, 20),
            ("ov-diff-admin", object_admin, 30),
            ("ov-diff-unrelated", object_admin, 97),
        )
        instance_ids = []
        for instance_id, monitor_object, organization in fixtures:
            instance = MonitorInstance.objects.create(
                id=instance_id,
                name=instance_id,
                monitor_object=monitor_object,
            )
            MonitorInstanceOrganization.objects.create(
                monitor_instance=instance,
                organization=organization,
            )
            instance_ids.append(instance_id)

        permissions = {
            "all": {"team": [30, None, "not-a-team", {"unexpected": 1}]},
            str(object_team.id): {
                "team": [10, None, "not-a-team"],
                "instance": [{"id": "ov-diff-explicit", "permission": ["View"]}, {"unexpected": 1}],
            },
            "malformed": ["not-a-rule"],
        }
        cur_team = [20, None, "not-a-team"]

        def count_by_object(queryset):
            counts = {}
            for instance in queryset:
                teams = {item.organization for item in instance.monitorinstanceorganization_set.all()}
                if monitor_object_view.check_instance_permission(
                    instance.monitor_object_id,
                    instance.id,
                    teams,
                    permissions,
                    cur_team,
                ):
                    counts[instance.monitor_object_id] = counts.get(instance.monitor_object_id, 0) + 1
            return counts

        full_scan = MonitorInstance.objects.filter(id__in=instance_ids).prefetch_related("monitorinstanceorganization_set")
        candidates = monitor_object_view._build_instance_count_queryset(permissions, cur_team).filter(id__in=instance_ids)

        assert (
            count_by_object(candidates)
            == count_by_object(full_scan)
            == {
                object_team.id: 2,
                object_fallback.id: 1,
                object_admin.id: 1,
            }
        )


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
        from apps.monitor.models import MonitorInstance
        from apps.monitor.views.organization_rule import _validate_rule_binding
        obj = MonitorObject.objects.create(name="VRBObj", level="base")
        other = MonitorObject.objects.create(name="VRBOther", level="base")
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        with pytest.raises(BaseAppException):
            _validate_rule_binding(other.id, "('h1',)")

    def test_validate_rule_binding_ok(self):
        from apps.monitor.models import MonitorInstance
        from apps.monitor.views.organization_rule import _validate_rule_binding
        obj = MonitorObject.objects.create(name="VRBObj2", level="base")
        MonitorInstance.objects.create(id="('h2',)", name="h2", monitor_object=obj)
        # 匹配 → 不抛错
        assert _validate_rule_binding(obj.id, "('h2',)") is None

    def test_validate_rule_binding_derivative_object_with_parent_instance(self):
        """子对象(derivative)规则引用父实例应视为合法:对应 create_default_rule 自动建规则的设计"""
        from apps.monitor.models import MonitorInstance
        from apps.monitor.views.organization_rule import _validate_rule_binding
        parent = MonitorObject.objects.create(name="VRBParent", level="base")
        child = MonitorObject.objects.create(name="VRBChild", level="derivative", parent=parent)
        MonitorInstance.objects.create(id="('p1',)", name="p1", monitor_object=parent)
        # 规则对象=child,实例=parent 的实例 → 应放行
        assert _validate_rule_binding(child.id, "('p1',)") is None

    def test_validate_rule_binding_derivative_object_with_unrelated_instance(self):
        """子对象(derivative)规则引用无关实例必须仍报错,避免绕过访问范围"""
        from apps.core.exceptions.base_app_exception import BaseAppException
        from apps.monitor.models import MonitorInstance
        from apps.monitor.views.organization_rule import _validate_rule_binding
        parent = MonitorObject.objects.create(name="VRBParentU", level="base")
        child = MonitorObject.objects.create(name="VRBChildU", level="derivative", parent=parent)
        unrelated = MonitorObject.objects.create(name="VRBUnrelated", level="base")
        MonitorInstance.objects.create(id="('u1',)", name="u1", monitor_object=unrelated)
        with pytest.raises(BaseAppException):
            _validate_rule_binding(child.id, "('u1',)")

    def test_update_derivative_rule_with_parent_instance_succeeds(self, api_client):
        """回归: vmware 父实例自动建的子规则,编辑保存时不再被 500/校验拦截"""
        from apps.monitor.models import MonitorInstance, MonitorInstanceOrganization, MonitorObjectOrganizationRule
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
        from unittest.mock import patch

        import pytest_mock  # noqa: F401
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
        from types import SimpleNamespace

        from apps.monitor.views.organization_rule import _rule_is_authorized
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
