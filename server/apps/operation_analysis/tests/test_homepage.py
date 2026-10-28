"""登录首页偏好：权限、组织可见性、超管与删除清理。"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.homepage import HomepagePreference
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.services.directory_service import DictDirectoryService
from apps.operation_analysis.views.homepage_view import HomepageViewSet
from apps.system_mgmt.models import OperationLog


def _request(method, path, user, data=None, team="1", include_children="0"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    if team is not None:
        request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = include_children
    force_authenticate(request, user=user)
    return request


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _viewer(user, *, roles=None, superuser=False, permission=None, groups=None):
    user.is_superuser = superuser
    user.roles = roles if roles is not None else ["ops-analysis--normal"]
    user.permission = permission if permission is not None else {"ops-analysis": {"view-View"}}
    user.group_list = groups if groups is not None else [{"id": 1, "name": "Default"}]
    return user


def _dashboard(name="运维盘", groups=None, **kwargs):
    directory = kwargs.pop("directory", None)
    if directory is None:
        directory = Directory.objects.create(name=f"{name}目录", groups=groups or [1], created_by="testuser")
    return Dashboard.objects.create(
        name=name,
        groups=groups or [1],
        directory=directory,
        created_by="testuser",
        **kwargs,
    )


def _personal(user, mode, dashboard_id=None):
    return HomepagePreference.objects.create(
        scope=HomepagePreference.SCOPE_USER,
        username=user.username,
        domain=user.domain,
        mode=mode,
        dashboard_id=dashboard_id,
    )


def _global(mode, dashboard_id=None):
    return HomepagePreference.objects.create(
        scope=HomepagePreference.SCOPE_GLOBAL,
        username="",
        domain="",
        mode=mode,
        dashboard_id=dashboard_id,
    )


@pytest.mark.django_db
def test_personal_set_requires_view_permission_and_current_org(authenticated_user):
    user = _viewer(authenticated_user)
    visible = _dashboard("可见盘", groups=[1])
    hidden = _dashboard("其他组织盘", groups=[2])
    builtin = _dashboard("内置盘", groups=[1], is_build_in=True, build_in_key="home-builtin")

    user.permission = {}
    denied = HomepageViewSet.as_view({"post": "personal"})(
        _request("post", "/homepage/personal/", user, data={"action": "set", "dashboard_id": visible.id})
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    user.permission = {"ops-analysis": {"view-View"}}

    wrong_org = HomepageViewSet.as_view({"post": "personal"})(
        _request("post", "/homepage/personal/", user, data={"action": "set", "dashboard_id": hidden.id})
    )
    assert wrong_org.status_code == status.HTTP_403_FORBIDDEN
    assert not HomepagePreference.objects.filter(scope=HomepagePreference.SCOPE_USER).exists()

    ok = HomepageViewSet.as_view({"post": "personal"})(
        _request("post", "/homepage/personal/", user, data={"action": "set", "dashboard_id": builtin.id})
    )
    payload = _render(ok)
    assert ok.status_code == status.HTTP_200_OK
    assert payload["data"]["personal_mode"] == "dashboard"
    assert payload["data"]["personal_dashboard_id"] == builtin.id
    assert payload["data"]["is_platform_admin"] is False
    assert OperationLog.objects.filter(app="system-manager").count() == 0


@pytest.mark.django_db
def test_include_children_matches_directory_tree(authenticated_user):
    user = _viewer(authenticated_user)
    user.group_tree = [{"id": 1, "name": "父", "subGroups": [{"id": 2, "name": "子"}]}]
    child_dashboard = _dashboard("子组织盘", groups=[2])

    blocked = HomepageViewSet.as_view({"post": "personal"})(
        _request(
            "post",
            "/homepage/personal/",
            user,
            data={"action": "set", "dashboard_id": child_dashboard.id},
            include_children="0",
        )
    )
    assert blocked.status_code == status.HTTP_403_FORBIDDEN

    allowed = HomepageViewSet.as_view({"post": "personal"})(
        _request(
            "post",
            "/homepage/personal/",
            user,
            data={"action": "set", "dashboard_id": child_dashboard.id},
            include_children="1",
        )
    )
    assert allowed.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_clear_follows_global_and_pin_workbench_ignores_global(authenticated_user):
    user = _viewer(authenticated_user)
    dashboard = _dashboard()
    _global(HomepagePreference.MODE_DASHBOARD, dashboard.id)
    _personal(user, HomepagePreference.MODE_DASHBOARD, dashboard.id)

    cleared = HomepageViewSet.as_view({"post": "personal"})(_request("post", "/homepage/personal/", user, data={"action": "clear"}))
    cleared_data = _render(cleared)["data"]
    assert cleared_data["personal_mode"] == "follow"
    assert cleared_data["personal_dashboard_id"] is None
    assert cleared_data["global_dashboard_id"] == dashboard.id
    assert not HomepagePreference.objects.filter(scope=HomepagePreference.SCOPE_USER).exists()

    pinned = HomepageViewSet.as_view({"post": "personal"})(_request("post", "/homepage/personal/", user, data={"action": "pin_workbench"}))
    pinned_data = _render(pinned)["data"]
    assert pinned_data["personal_mode"] == "workbench"
    landing = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
    assert landing == {"dashboard_id": None, "fallback": None}


@pytest.mark.django_db
def test_global_setting_requires_platform_admin_role_and_writes_audit(authenticated_user):
    dashboard = _dashboard()
    user = _viewer(authenticated_user, roles=["ops-analysis--admin"], superuser=True)
    app_denied = HomepageViewSet.as_view({"post": "global_setting"})(
        _request("post", "/homepage/global/", user, data={"action": "set", "dashboard_id": dashboard.id})
    )
    assert app_denied.status_code == status.HTTP_403_FORBIDDEN

    _viewer(user, roles=["system-manager--admin"], superuser=True)
    system_denied = HomepageViewSet.as_view({"post": "global_setting"})(
        _request("post", "/homepage/global/", user, data={"action": "set", "dashboard_id": dashboard.id})
    )
    assert system_denied.status_code == status.HTTP_403_FORBIDDEN
    assert OperationLog.objects.count() == 0

    _viewer(user, roles=["admin"], superuser=False, permission={})
    created = HomepageViewSet.as_view({"post": "global_setting"})(
        _request("post", "/homepage/global/", user, data={"action": "set", "dashboard_id": dashboard.id})
    )
    assert created.status_code == status.HTTP_200_OK
    assert _render(created)["data"]["is_platform_admin"] is True
    log = OperationLog.objects.get()
    assert log.app == "system-manager"
    assert log.action_type == "update"
    assert log.summary == "设置全局默认登录首页"
    assert log.target_id == str(dashboard.id)
    assert log.detail == {}
    assert "view_sets" not in log.summary

    restored = HomepageViewSet.as_view({"post": "global_setting"})(_request("post", "/homepage/global/", user, data={"action": "restore"}))
    assert restored.status_code == status.HTTP_200_OK
    assert _render(restored)["data"]["global_mode"] == "workbench"
    restore_log = OperationLog.objects.exclude(pk=log.pk).get()
    assert restore_log.summary == "还原全局默认登录首页"
    assert restore_log.action_type == "update"
    assert restore_log.detail == {}


@pytest.mark.django_db
def test_landing_priority_permission_and_first_login(authenticated_user):
    user = _viewer(authenticated_user)
    personal_dashboard = _dashboard("个人盘")
    global_dashboard = _dashboard("全局盘")
    _global(HomepagePreference.MODE_DASHBOARD, global_dashboard.id)
    _personal(user, HomepagePreference.MODE_DASHBOARD, personal_dashboard.id)

    landing = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
    assert landing["dashboard_id"] == personal_dashboard.id
    assert landing["fallback"] is None

    no_view = _viewer(authenticated_user, permission={}, superuser=False)
    silent = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", no_view)))["data"]
    assert silent == {"dashboard_id": None, "fallback": None}
    assert HomepagePreference.objects.filter(dashboard_id=personal_dashboard.id).exists()

    user.permission = {"ops-analysis": {"view-View"}}
    HomepagePreference.objects.filter(scope=HomepagePreference.SCOPE_USER).delete()
    followed = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
    assert followed["dashboard_id"] == global_dashboard.id

    global_row = HomepagePreference.objects.get(scope=HomepagePreference.SCOPE_GLOBAL)
    global_row.dashboard_id = 999999
    global_row.mode = HomepagePreference.MODE_DASHBOARD
    global_row.save(update_fields=["dashboard_id", "mode"])
    missing = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
    assert missing == {"dashboard_id": None, "fallback": "missing"}
    global_row.refresh_from_db()
    assert global_row.dashboard_id == 999999

    user.group_list = [{"id": 9, "name": "OpsPilotGuest"}]
    global_row.dashboard_id = personal_dashboard.id
    global_row.save(update_fields=["dashboard_id"])
    skipped = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
    assert skipped == {"dashboard_id": None, "fallback": None}


@pytest.mark.django_db
def test_access_distinguishes_permission_missing_and_org(authenticated_user):
    user = _viewer(authenticated_user)
    dashboard = _dashboard(groups=[1])
    other = _dashboard("别处", groups=[8])

    ok = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={dashboard.id}", user)))["data"]
    assert ok["status"] == "ok"
    assert ok["name"] == dashboard.name

    org = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={other.id}", user)))["data"]
    assert org["status"] == "org"

    missing = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", "/homepage/access/?dashboard_id=999999", user)))["data"]
    assert missing["status"] == "missing"

    no_view = _viewer(authenticated_user, permission={}, superuser=False)
    silent = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={dashboard.id}", no_view)))["data"]
    assert silent["status"] == "permission"
    assert HomepagePreference.objects.count() == 0


@pytest.mark.django_db
def test_superuser_still_follows_directory_org_rule(authenticated_user):
    admin = _viewer(authenticated_user, roles=["admin"], superuser=True)
    hidden = _dashboard("超管当前组织看不到", groups=[3])
    access = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={hidden.id}", admin)))["data"]
    assert access["status"] == "org"

    denied = HomepageViewSet.as_view({"post": "global_setting"})(
        _request("post", "/homepage/global/", admin, data={"action": "set", "dashboard_id": hidden.id})
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_dashboard_delete_and_directory_cascade_clear_pointers(authenticated_user):
    user = _viewer(authenticated_user)
    directory = Directory.objects.create(name="将被删除", groups=[1], created_by="testuser")
    removed = _dashboard("要删", groups=[1], directory=directory)
    kept = _dashboard("保留")
    _global(HomepagePreference.MODE_DASHBOARD, removed.id)
    _personal(user, HomepagePreference.MODE_DASHBOARD, removed.id)
    other_user_pref = HomepagePreference.objects.create(
        scope=HomepagePreference.SCOPE_USER,
        username="other",
        domain="domain.com",
        mode=HomepagePreference.MODE_DASHBOARD,
        dashboard_id=kept.id,
    )

    removed.delete()
    global_row = HomepagePreference.objects.get(scope=HomepagePreference.SCOPE_GLOBAL)
    assert global_row.mode == HomepagePreference.MODE_WORKBENCH
    assert global_row.dashboard_id is None
    assert not HomepagePreference.objects.filter(username=user.username, dashboard_id=removed.id).exists()
    assert HomepagePreference.objects.filter(pk=other_user_pref.pk, dashboard_id=kept.id).exists()

    cascaded = _dashboard("级联", groups=[1], directory=directory)
    global_row = HomepagePreference.objects.get(scope=HomepagePreference.SCOPE_GLOBAL)
    global_row.mode = HomepagePreference.MODE_DASHBOARD
    global_row.dashboard_id = cascaded.id
    global_row.save(update_fields=["mode", "dashboard_id"])
    _personal(user, HomepagePreference.MODE_DASHBOARD, cascaded.id)
    directory.delete()
    assert not Dashboard.objects.filter(pk=cascaded.id).exists()
    assert not HomepagePreference.objects.filter(dashboard_id=cascaded.id).exists()
    global_after = HomepagePreference.objects.get(scope=HomepagePreference.SCOPE_GLOBAL)
    assert global_after.mode == HomepagePreference.MODE_WORKBENCH
    assert global_after.dashboard_id is None


@pytest.mark.django_db
def test_shortcut_follows_landing_and_hides_when_inaccessible(authenticated_user):
    user = _viewer(authenticated_user)
    personal = _dashboard("个人盘", groups=[1])
    global_dashboard = _dashboard("全局盘", groups=[1])
    hidden = _dashboard("其他组织盘", groups=[3])
    _global(HomepagePreference.MODE_DASHBOARD, global_dashboard.id)
    _personal(user, HomepagePreference.MODE_DASHBOARD, personal.id)

    visible = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
    assert visible == {"dashboard_id": personal.id}

    HomepagePreference.objects.filter(scope=HomepagePreference.SCOPE_USER).delete()
    followed = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
    assert followed == {"dashboard_id": global_dashboard.id}

    _personal(user, HomepagePreference.MODE_WORKBENCH)
    pinned = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
    assert pinned == {"dashboard_id": None}

    HomepagePreference.objects.filter(scope=HomepagePreference.SCOPE_USER).delete()
    global_row = HomepagePreference.objects.get(scope=HomepagePreference.SCOPE_GLOBAL)
    global_row.dashboard_id = hidden.id
    global_row.save(update_fields=["dashboard_id"])
    org_hidden = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
    assert org_hidden == {"dashboard_id": None}
    global_row.refresh_from_db()
    assert global_row.dashboard_id == hidden.id

    global_row.dashboard_id = global_dashboard.id
    global_row.save(update_fields=["dashboard_id"])
    user.permission = {}
    user.is_superuser = False
    silent = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
    assert silent == {"dashboard_id": None}

    user.permission = {"ops-analysis": {"view-View"}}
    user.group_list = [{"id": 9, "name": "OpsPilotGuest"}]
    first_login = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
    assert first_login == {"dashboard_id": None}


def _tree_dashboard_ids(user):
    found = []

    def walk(nodes):
        for node in nodes:
            if node.get("type") == "dashboard":
                found.append(node.get("data_id"))
            walk(node.get("children") or [])

    walk(DictDirectoryService.get_dict_trees(_request("get", "/directory/trees/", user)))
    return found


def _point_global(dashboard_id):
    HomepagePreference.objects.update_or_create(
        scope=HomepagePreference.SCOPE_GLOBAL,
        username="",
        domain="",
        defaults={"mode": HomepagePreference.MODE_DASHBOARD, "dashboard_id": dashboard_id},
    )


@pytest.mark.django_db
def test_homepage_follows_directory_tree_not_dashboard_groups(authenticated_user):
    user = _viewer(authenticated_user, roles=["admin"])
    inactive = _dashboard("停用目录盘", groups=[1])
    inactive.directory.is_active = False
    inactive.directory.save(update_fields=["is_active"])

    other_org_directory = _dashboard("目录在别的组织", groups=[1])
    other_org_directory.directory.groups = [2]
    other_org_directory.directory.save(update_fields=["groups"])

    visible = _dashboard("树上可见", groups=[1])
    tree_ids = _tree_dashboard_ids(user)
    assert inactive.id not in tree_ids
    assert other_org_directory.id not in tree_ids
    assert visible.id in tree_ids

    for hidden in (inactive, other_org_directory):
        access = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={hidden.id}", user)))["data"]
        assert access["status"] == "org"

        personal = HomepageViewSet.as_view({"post": "personal"})(
            _request("post", "/homepage/personal/", user, data={"action": "set", "dashboard_id": hidden.id})
        )
        assert personal.status_code == status.HTTP_403_FORBIDDEN

        global_denied = HomepageViewSet.as_view({"post": "global_setting"})(
            _request("post", "/homepage/global/", user, data={"action": "set", "dashboard_id": hidden.id})
        )
        assert global_denied.status_code == status.HTTP_403_FORBIDDEN

        _point_global(hidden.id)
        landing = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
        assert landing == {"dashboard_id": None, "fallback": "org"}
        shortcut = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user)))["data"]
        assert shortcut == {"dashboard_id": None}
        assert HomepagePreference.objects.filter(
            scope=HomepagePreference.SCOPE_GLOBAL,
            dashboard_id=hidden.id,
        ).exists()

    _point_global(visible.id)
    opened = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={visible.id}", user)))["data"]
    assert opened["status"] == "ok"
    assert opened["name"] == "树上可见"
    landing = _render(HomepageViewSet.as_view({"get": "landing"})(_request("get", "/homepage/landing/", user)))["data"]
    assert landing["dashboard_id"] == visible.id
    personal_ok = HomepageViewSet.as_view({"post": "personal"})(
        _request("post", "/homepage/personal/", user, data={"action": "set", "dashboard_id": visible.id})
    )
    assert personal_ok.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_access_localizes_builtin_dashboard_name_and_desc(authenticated_user):
    user = _viewer(authenticated_user)
    user.locale = "en"
    dashboard = _dashboard(
        "CMDB仪表盘_内置",
        groups=[1],
        desc="原始描述",
        is_build_in=True,
        build_in_key="dashboard::CMDB仪表盘_内置",
    )

    english = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={dashboard.id}", user)))["data"]
    assert english["status"] == "ok"
    assert english["is_build_in"] is True
    assert english["name"] == "CMDB Dashboard"
    assert english["desc"].startswith("Shows CMDB models")

    user.locale = "zh-Hans"
    chinese = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={dashboard.id}", user)))["data"]
    assert chinese["name"] == "CMDB仪表盘"
    assert chinese["desc"].startswith("集中展示 CMDB")


@pytest.mark.django_db
def test_landing_defers_when_team_cookie_belongs_to_another_account(authenticated_user):
    user = _viewer(authenticated_user, groups=[{"id": 1, "name": "Default"}, {"id": 2, "name": "Other"}])
    user.group_tree = [{"id": 1, "subGroups": []}, {"id": 2, "subGroups": []}]
    dashboard = _dashboard("本账号可见盘", groups=[1])
    _point_global(dashboard.id)
    landing_view = HomepageViewSet.as_view({"get": "landing"})

    stale = _render(landing_view(_request("get", "/homepage/landing/", user, team="99")))["data"]
    assert stale == {"dashboard_id": dashboard.id, "fallback": None}

    own_but_hidden = _render(landing_view(_request("get", "/homepage/landing/", user, team="2")))["data"]
    assert own_but_hidden == {"dashboard_id": None, "fallback": "org"}


@pytest.mark.django_db
def test_forged_team_cookie_cannot_bind_or_read_foreign_dashboard(authenticated_user):
    """伪造 current_team 不能读取别的组织仪表盘元信息，也不能绑成个人首页。"""

    user = _viewer(authenticated_user, groups=[{"id": 1, "name": "Default"}])
    user.group_tree = [{"id": 1, "subGroups": []}]
    foreign = _dashboard("外组织盘", groups=[99])

    access = _render(HomepageViewSet.as_view({"get": "access"})(_request("get", f"/homepage/access/?dashboard_id={foreign.id}", user, team="99")))[
        "data"
    ]
    assert access == {"status": "org", "name": "", "desc": "", "is_build_in": False}

    bind = HomepageViewSet.as_view({"post": "personal"})(
        _request(
            "post",
            "/homepage/personal/",
            user,
            data={"action": "set", "dashboard_id": foreign.id},
            team="99",
        )
    )
    assert bind.status_code == status.HTTP_403_FORBIDDEN
    assert not HomepagePreference.objects.filter(scope=HomepagePreference.SCOPE_USER).exists()

    shortcut = _render(HomepageViewSet.as_view({"get": "shortcut"})(_request("get", "/homepage/shortcut/", user, team="99")))["data"]
    assert shortcut == {"dashboard_id": None}
