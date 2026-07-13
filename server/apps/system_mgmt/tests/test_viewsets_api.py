"""多个 system_mgmt ViewSet 的 API 行为测试（经 DRF 路由，superuser 绕过权限）。

覆盖：group_data_rule / custom_menu_group / login_module / operation_log / error_log。
只 mock 真实外部边界（log_operation、celery delay、clear_users_permission_cache）。
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.models import (
    CustomMenuGroup,
    ErrorLog,
    GroupDataRule,
    LoginModule,
    OperationLog,
)

pytestmark = pytest.mark.django_db

V = "/api/v1/system_mgmt"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="vsadmin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    # current_team cookie 供 GroupFilterMixin 使用
    client.cookies["current_team"] = "1"
    return client


# ---------------------------------------------------------------------------
# group_data_rule
# ---------------------------------------------------------------------------
def test_group_data_rule_list_and_create():
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="gdradmin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)

    with patch("apps.system_mgmt.viewset.group_data_rule_viewset.log_operation"):
        create = client.post(
            f"{V}/group_data_rule/",
            {
                "name": "规则1",
                "app": "cmdb",
                "group_id": 5,
                "group_name": "组5",
                "rules": {"a": 1},
            },
            format="json",
        )
    assert create.status_code in (200, 201)
    assert GroupDataRule.objects.filter(name="规则1").exists()

    lst = client.get(f"{V}/group_data_rule/")
    assert lst.status_code == 200


def test_group_data_rule_retrieve_disabled(super_client):
    rule = GroupDataRule.objects.create(name="r", app="cmdb", group_id=1, group_name="g", rules={})
    resp = super_client.get(f"{V}/group_data_rule/{rule.id}/")
    assert resp.status_code == 405


def test_group_data_rule_update_and_destroy(super_client):
    rule = GroupDataRule.objects.create(name="r", app="cmdb", group_id=1, group_name="g", rules={})
    with patch("apps.system_mgmt.viewset.group_data_rule_viewset.log_operation"), patch(
        "apps.system_mgmt.viewset.group_data_rule_viewset.clear_users_permission_cache"
    ):
        upd = super_client.put(
            f"{V}/group_data_rule/{rule.id}/",
            {"name": "r-new", "app": "cmdb", "group_id": 1, "group_name": "g", "rules": {}},
            format="json",
        )
        assert upd.status_code == 200
        rule.refresh_from_db()
        assert rule.name == "r-new"

        dele = super_client.delete(f"{V}/group_data_rule/{rule.id}/")
        assert dele.status_code in (200, 204)
        assert not GroupDataRule.objects.filter(id=rule.id).exists()


def test_group_data_rule_get_app_module(super_client):
    fake_client = type("C", (), {"get_module_list": staticmethod(lambda: [{"display_name": "模块A"}])})()
    with patch.object(
        __import__("apps.system_mgmt.viewset.group_data_rule_viewset", fromlist=["GroupDataRuleViewSet"]).GroupDataRuleViewSet,
        "get_client",
        return_value=fake_client,
    ):
        resp = super_client.get(f"{V}/group_data_rule/get_app_module/?app=cmdb")
    assert resp.status_code == 200
    assert resp.json()["result"] is True


# ---------------------------------------------------------------------------
# custom_menu_group
# ---------------------------------------------------------------------------
def test_custom_menu_group_list_and_create(super_client):
    with patch("apps.system_mgmt.viewset.custom_menu_group_viewset.log_operation"):
        create = super_client.post(
            f"{V}/custom_menu_group/",
            {"display_name": "菜单A", "app": "cmdb", "menus": []},
            format="json",
        )
    assert create.status_code in (200, 201)
    grp = CustomMenuGroup.objects.get(display_name="菜单A", app="cmdb")
    assert grp.is_build_in is False

    lst = super_client.get(f"{V}/custom_menu_group/")
    assert lst.status_code == 200


def test_custom_menu_group_update_builtin_forbidden(super_client):
    grp = CustomMenuGroup.objects.create(display_name="内置", app="cmdb", is_build_in=True, menus=[])
    resp = super_client.put(
        f"{V}/custom_menu_group/{grp.id}/",
        {"display_name": "x", "app": "cmdb", "menus": []},
        format="json",
    )
    assert resp.status_code == 403


def test_custom_menu_group_destroy_builtin_forbidden(super_client):
    grp = CustomMenuGroup.objects.create(display_name="内置2", app="cmdb", is_build_in=True, menus=[])
    resp = super_client.delete(f"{V}/custom_menu_group/{grp.id}/")
    assert resp.status_code == 403


def test_custom_menu_group_change_enable(super_client):
    other = CustomMenuGroup.objects.create(display_name="老的", app="cmdb", is_enabled=True, is_build_in=False, menus=[])
    grp = CustomMenuGroup.objects.create(display_name="新的", app="cmdb", is_enabled=False, is_build_in=False, menus=[])
    with patch("apps.system_mgmt.viewset.custom_menu_group_viewset.log_operation"):
        resp = super_client.post(
            f"{V}/custom_menu_group/{grp.id}/change_enable/", {"is_enabled": True}, format="json"
        )
    assert resp.status_code == 200
    grp.refresh_from_db()
    other.refresh_from_db()
    # 启用新的会禁用同 app 其它
    assert grp.is_enabled is True
    assert other.is_enabled is False


def test_custom_menu_group_change_enable_missing_param(super_client):
    grp = CustomMenuGroup.objects.create(display_name="g", app="cmdb", is_build_in=False, menus=[])
    resp = super_client.post(f"{V}/custom_menu_group/{grp.id}/change_enable/", {}, format="json")
    assert resp.status_code == 400


def test_custom_menu_group_copy(super_client):
    grp = CustomMenuGroup.objects.create(
        display_name="原始", app="cmdb", is_build_in=False, menus=[{"id": 1}]
    )
    with patch("apps.system_mgmt.viewset.custom_menu_group_viewset.log_operation"):
        resp = super_client.post(f"{V}/custom_menu_group/{grp.id}/copy/", {}, format="json")
    assert resp.status_code == 200
    assert CustomMenuGroup.objects.filter(app="cmdb", display_name="原始_copy").exists()


def test_custom_menu_group_get_menus(super_client):
    CustomMenuGroup.objects.create(
        display_name="启用的", app="cmdb", is_enabled=True, is_build_in=False, menus=[{"id": 1}]
    )
    resp = super_client.get(f"{V}/custom_menu_group/get_menus/?app=cmdb")
    assert resp.status_code == 200
    assert resp.json()["data"]["menus"] == [{"id": 1}]


def test_custom_menu_group_get_menus_not_found(super_client):
    resp = super_client.get(f"{V}/custom_menu_group/get_menus/?app=nonexistent")
    assert resp.status_code == 404


def test_custom_menu_group_get_menus_missing_app(super_client):
    resp = super_client.get(f"{V}/custom_menu_group/get_menus/")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# login_module
# ---------------------------------------------------------------------------
def test_login_module_list(super_client):
    LoginModule.objects.create(name="lm1", source_type="wechat", other_config={})
    resp = super_client.get(f"{V}/login_module/")
    assert resp.status_code == 200


def test_login_module_create_requires_domain(super_client):
    resp = super_client.post(
        f"{V}/login_module/",
        {"name": "ldapX", "source_type": "ldap", "other_config": {}},
        format="json",
    )
    # 缺 domain -> result False
    assert resp.json()["result"] is False


def test_login_module_sync_data():
    """sync_data 未通过 @action 路由，直接调用 viewset 方法验证下发 celery 任务。"""
    import types

    from apps.system_mgmt.viewset.login_module_viewset import LoginModuleViewSet

    lm = LoginModule.objects.create(name="syncmod", source_type="ldap", other_config={}, enabled=True)
    vs = LoginModuleViewSet()
    vs.loader = None
    vs.get_object = lambda: lm
    request = types.SimpleNamespace(
        user=types.SimpleNamespace(username="a", domain="domain.com", is_superuser=True), META={}, data={}
    )
    with patch(
        "apps.system_mgmt.viewset.login_module_viewset.sync_user_and_group_by_login_module"
    ) as m_task, patch("apps.system_mgmt.viewset.login_module_viewset.log_operation"):
        resp = vs.sync_data(request)
    import json

    assert json.loads(resp.content)["result"] is True
    m_task.delay.assert_called_once_with(lm.id)


def test_login_module_destroy(super_client):
    lm = LoginModule.objects.create(name="delmod", source_type="wechat", other_config={})
    with patch("apps.system_mgmt.viewset.login_module_viewset.log_operation"):
        resp = super_client.delete(f"{V}/login_module/{lm.id}/")
    assert resp.status_code in (200, 204)
    assert not LoginModule.objects.filter(id=lm.id).exists()


# ---------------------------------------------------------------------------
# operation_log (GroupFilterMixin -> needs current_team cookie)
# ---------------------------------------------------------------------------
def test_operation_log_list(super_client):
    resp = super_client.get(f"{V}/operation_log/")
    assert resp.status_code == 200


def test_operation_log_retrieve_disabled(super_client):
    log = OperationLog.objects.create(
        username="x", domain="domain.com", source_ip="127.0.0.1", app="cmdb", action_type="create", summary="s"
    )
    resp = super_client.get(f"{V}/operation_log/{log.id}/")
    assert resp.status_code == 405


def test_operation_log_export_excel(super_client):
    resp = super_client.post(f"{V}/operation_log/export_excel/", {"selected_ids": []}, format="json")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]


# ---------------------------------------------------------------------------
# error_log
# ---------------------------------------------------------------------------
def test_error_log_list(super_client):
    resp = super_client.get(f"{V}/error_log/")
    assert resp.status_code == 200


def test_error_log_write_methods_disabled(super_client):
    log = ErrorLog.objects.create(username="x", app="cmdb", module="m", error_message="e", domain="domain.com")
    # retrieve 禁用
    assert super_client.get(f"{V}/error_log/{log.id}/").status_code == 405
    # create 禁用
    assert super_client.post(f"{V}/error_log/", {}, format="json").status_code == 405
