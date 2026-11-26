from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.core.utils.current_team_scope import _get_actor_context, actor_context_to_wire
from apps.core.utils.module_scope import ModuleRoleGrantError, client_id_from_request, sanitize_submitted_roles
from apps.core.utils.viewset_utils import GenericViewSetFun
from apps.system_mgmt.models import Group, Role, User
from apps.system_mgmt.nats.permissions import _prepare_user_rules_query
from apps.system_mgmt.nats.users import get_assignable_groups, get_authorized_groups_scoped

pytestmark = pytest.mark.django_db


@pytest.fixture
def module_actor():
    own = Group.objects.create(name="module-scope-own", parent_id=0)
    other = Group.objects.create(name="module-scope-other", parent_id=0)
    child = Group.objects.create(name="module-scope-child", parent_id=other.id)
    role = Role.objects.create(app="cmdb", name="module_admin")
    user = User.objects.create(username="module-scope-user", domain="domain.com", password="x", group_list=[own.id], role_list=[role.id])
    return user, own, other, child, role


@pytest.mark.parametrize("role_name", ["module_admin", "module_auditor"])
def test_module_roles_open_only_matching_application(module_actor, role_name):
    user, own, other, child, role = module_actor
    role.name = role_name
    role.save()
    context = {"username": user.username, "domain": user.domain, "current_team": other.id}
    assert get_authorized_groups_scoped(context)["data"] == []
    assert get_authorized_groups_scoped({**context, "app": "monitor"})["data"] == []
    assert get_authorized_groups_scoped({**context, "app": "system-manager"})["data"] == []
    actual = get_authorized_groups_scoped({**context, "app": "cmdb"}, include_children=True)
    assert set(actual["data"]) == {other.id, child.id}
    assert actual["is_superuser"] is False
    assert set(get_authorized_groups_scoped({**context, "client_id": "cmdb"})["data"]) == {other.id}
    assert set(get_assignable_groups({**context, "app": "cmdb"})["data"]) >= {own.id, other.id, child.id}
    assert other.id not in get_assignable_groups(context)["data"]
    assert other.id not in get_assignable_groups({**context, "app": "monitor"})["data"]


def test_rules_query_expands_module_subtree_only_in_current_app(module_actor):
    user, own, other, child, role = module_actor
    _, ids, _, _, is_admin = _prepare_user_rules_query(other.id, user.username, user.domain, "cmdb", True)
    assert is_admin is True
    assert set(ids) == {other.id, child.id}
    _, ids, _, _, is_admin = _prepare_user_rules_query(other.id, user.username, user.domain, "monitor", True)
    assert is_admin is False
    assert child.id not in ids


def test_module_auditor_expands_org_scope_without_admin_permission_blob(module_actor):
    from apps.system_mgmt.nats.permissions import get_user_rules_by_module

    user, own, other, child, role = module_actor
    role.name = "module_auditor"
    role.save()
    _, ids, _, _, is_admin = _prepare_user_rules_query(other.id, user.username, user.domain, "cmdb", True)
    assert is_admin is False
    assert set(ids) == {other.id, child.id}
    result = get_user_rules_by_module(other.id, user.username, user.domain, "cmdb", "instance", True)
    assert result["result"] is True
    assert "all" not in result["data"]
    assert set(result["team"]) == {other.id, child.id}
    role.name = "module_admin"
    role.save()
    admin_result = get_user_rules_by_module(other.id, user.username, user.domain, "cmdb", "instance", True)
    assert set(admin_result["data"]["all"]["team"]) == {other.id, child.id}


def test_viewset_expands_real_descendants_for_module_role(module_actor):
    user, own, other, child, role = module_actor
    from apps.opspilot.models.wiki_mgmt import WikiKnowledgeBase

    class CmdbView(GenericViewSetFun):
        __module__ = "apps.cmdb.views.test"
        ORGANIZATION_FIELD = "team"
        permission_key = "wiki"

    visible = WikiKnowledgeBase.objects.create(name="child-visible", team=[child.id])
    hidden = WikiKnowledgeBase.objects.create(name="home-hidden", team=[own.id])
    actor = SimpleNamespace(roles=["cmdb--module_admin"], group_list=[own.id], group_tree=[])
    request = SimpleNamespace(COOKIES={"current_team": str(other.id), "include_children": "1"}, user=actor)
    queryset = WikiKnowledgeBase.objects.all()
    _, _, _, query = CmdbView.filter_by_group(queryset, request, actor)
    assert set(queryset.filter(query).values_list("id", flat=True)) == {visible.id}
    assert hidden.id != visible.id
    with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [other.id, child.id], "instance": []}):
        assert CmdbView().get_has_permission(actor, visible, other.id, include_children=True) is True
        assert CmdbView().get_has_permission(actor, hidden, other.id, include_children=True) is False


def test_http_and_wire_context_keep_server_route_app():
    req = SimpleNamespace(path="/api/v1/node_mgmt/node/", user=SimpleNamespace(username="u", group_list=[], is_superuser=False))
    assert client_id_from_request(req) == "node"
    ctx = _get_actor_context(req)
    assert ctx["app"] == "node"
    ctx.update(current_team=1, data_team_ids=[1])
    assert actor_context_to_wire(ctx)["app"] == "node"
    req.path = "/api/v1/system_mgmt/user/"
    assert _get_actor_context(req)["app"] == "system-manager"


def test_only_platform_superuser_can_change_module_roles(module_actor):
    *_, role = module_actor
    ordinary = SimpleNamespace(is_superuser=False, is_auditor=False)
    auditor = SimpleNamespace(is_superuser=False, is_auditor=True)
    admin = SimpleNamespace(is_superuser=True)
    for actor in (ordinary, auditor):
        with pytest.raises(ModuleRoleGrantError):
            sanitize_submitted_roles(actor, [role.id], [])
        with pytest.raises(ModuleRoleGrantError):
            sanitize_submitted_roles(actor, [], [role.id])
        assert sanitize_submitted_roles(actor, [role.id], [role.id]) == [role.id]
    assert sanitize_submitted_roles(admin, [role.id], []) == [role.id]
    assert sanitize_submitted_roles(admin, [], [role.id]) == []


@pytest.mark.parametrize("action", ["add_user", "delete_user"])
@pytest.mark.parametrize("is_auditor", [True, False])
def test_role_membership_endpoints_block_non_superuser(module_actor, action, is_auditor):
    from apps.system_mgmt.viewset.role_viewset import RoleViewSet

    user, *_, role = module_actor
    req = SimpleNamespace(
        data={"role_id": role.id, "user_ids": [user.id]}, user=SimpleNamespace(is_superuser=False, is_auditor=is_auditor, locale="en")
    )
    response = getattr(RoleViewSet, action).__wrapped__(RoleViewSet(), req)
    assert response.status_code == 403
    user.refresh_from_db()
    assert user.role_list == [role.id]


@pytest.mark.parametrize("action", ["create_user", "update_user"])
@pytest.mark.parametrize("is_auditor", [True, False])
def test_user_endpoints_block_module_role_grants(module_actor, action, is_auditor):
    from apps.system_mgmt.services.platform_roles import ensure_platform_auditor_role
    from apps.system_mgmt.viewset.user_viewset import UserViewSet

    user, own, other, child, role = module_actor
    Role.objects.get_or_create(name="admin", app="")
    ensure_platform_auditor_role()
    actor = SimpleNamespace(
        username="operator", domain="domain.com", locale="en", is_superuser=False, is_auditor=is_auditor, group_list=[{"id": own.id}]
    )
    user.role_list = []
    user.save()
    data = {
        "username": user.username,
        "groups": [own.id],
        "roles": [str(role.id)],
        "phone": "",
        "email": "module-scope@example.com",
        "lastName": "Scope",
        "locale": "en",
        "timezone": "Asia/Shanghai",
    }
    if action == "update_user":
        data["user_id"] = user.id
    req = SimpleNamespace(data=data, user=actor)
    view = UserViewSet()
    # This test exercises the endpoint's grant guard after the independent organization checks.
    with patch.object(view, "_validate_target_user_permission", return_value=(True, None)), patch.object(
        view, "_validate_group_scope_for_request", return_value=None
    ):
        # create_user's existing role validation accepts integer IDs.
        if action == "create_user":
            data["roles"] = [role.id]
        response = getattr(UserViewSet, action).__wrapped__(view, req)
    assert response.status_code == 403
    user.refresh_from_db()
    assert user.role_list == []


@pytest.mark.parametrize(("package", "client"), [("monitor", "monitor"), ("log", "log"), ("node_mgmt", "node"), ("cmdb", "cmdb")])
def test_http_scope_resolves_foreign_org_for_current_module(module_actor, monkeypatch, package, client):
    from apps.core.utils.current_team_scope import resolve_assignable_organization_ids, resolve_current_team_data_scope

    user, own, other, child, role = module_actor
    role.app = client
    role.save()
    actor = SimpleNamespace(
        username=user.username, domain=user.domain, is_superuser=False, group_list=[{"id": own.id}], roles=[f"{client}--module_admin"]
    )
    req = SimpleNamespace(user=actor, path=f"/api/v1/{package}/instance/", COOKIES={"current_team": str(other.id), "include_children": "1"})
    rpc = SimpleNamespace(get_authorized_groups_scoped=get_authorized_groups_scoped, get_assignable_groups=get_assignable_groups)
    monkeypatch.setattr("apps.core.utils.current_team_scope.SystemMgmt", lambda: rpc)
    assert resolve_current_team_data_scope(req).data_team_ids == frozenset({other.id, child.id})
    assert other.id in resolve_assignable_organization_ids(req)
    if client == "cmdb":
        from apps.cmdb.views.instance import InstanceViewSet

        assert other.id in InstanceViewSet()._get_allowed_org_ids(req)


@pytest.mark.parametrize("superuser", [True, False])
def test_group_edit_cannot_assign_module_roles(module_actor, superuser):
    from apps.system_mgmt.viewset.group_viewset import GroupViewSet

    user, own, other, child, role = module_actor
    view = GroupViewSet()
    req = SimpleNamespace(
        data={"group_id": own.id, "group_name": own.name, "role_ids": [str(role.id)]}, user=SimpleNamespace(is_superuser=superuser, locale="en")
    )
    with patch.object(view, "_get_active_group_or_error", return_value=(own, None)):
        response = GroupViewSet.update_group.__wrapped__(view, req)
    assert response.status_code == 400
    assert not own.roles.exists()
