"""系统管理菜单展示名与顺序：稳定权限名、记录 ID、角色授权集合不变。"""

import json
from pathlib import Path

import pytest

from apps.system_mgmt.management.commands.init_realm_resource import create_resource, extend_menus_by_install_apps
from apps.system_mgmt.models import App, Menu, Role

MENU_PATH = Path("support-files/system_mgmt/menus/system-manager.json")
USER_CHILD_IDS = ["user_group", "login_auth", "user_sync", "user_fields"]
SECURITY_CHILD_IDS = ["security_settings", "super_admin", "network_white_list"]
SETTING_CHILD_IDS = [
    "audit_log",
    "error_logs",
    "openapi_docs",
    "api_secret_key",
]
FROZEN_CHILD_IDS = {
    "user_group",
    "user_fields",
    "user_sync",
    "login_auth",
    "security_settings",
    "super_admin",
    "audit_log",
    "error_logs",
    "network_white_list",
    "openapi_docs",
    "api_secret_key",
}


def _payload():
    return json.loads(MENU_PATH.read_text(encoding="utf-8"))


def test_system_manager_menu_json_keeps_stable_ids_and_new_order():
    payload = _payload()
    names = [item["name"] for item in payload["menus"]]
    assert names == [
        "Organization",
        "Security",
        "Credential",
        "Application",
        "Channel",
        "Integration Center",
        "Setting",
    ]

    organization = next(item for item in payload["menus"] if item["name"] == "Organization")
    security = next(item for item in payload["menus"] if item["name"] == "Security")
    setting = next(item for item in payload["menus"] if item["name"] == "Setting")

    assert [child["id"] for child in organization["children"]] == USER_CHILD_IDS
    assert [child["id"] for child in security["children"]] == SECURITY_CHILD_IDS
    assert [child["id"] for child in setting["children"]] == SETTING_CHILD_IDS
    assert setting["icon"] == "settings-fill"
    child_ids = {child["id"] for group in payload["menus"] for child in group["children"]}
    assert FROZEN_CHILD_IDS <= child_ids

    setting_by_id = {child["id"]: child["name"] for child in setting["children"]}
    security_by_id = {child["id"]: child for child in security["children"]}
    token = next(child for child in setting["children"] if child["id"] == "api_secret_key")
    assert setting_by_id["api_secret_key"] == "API Token"
    assert token["operation"] == ["View", "Add", "Delete"]
    assert setting_by_id["openapi_docs"] == "API Documentation"
    assert "network_white_list" not in setting_by_id
    assert security_by_id["network_white_list"]["name"] == "Network Whitelist"
    assert security_by_id["network_white_list"]["operation"] == ["View", "Add", "Edit", "Delete"]
    assert security_by_id["security_settings"]["operation"] == ["View", "Edit", "Add", "Delete"]
    assert security_by_id["super_admin"]["operation"] == ["View", "Add", "Delete"]

    roles_by_name = {item["name"]: item["menus"] for item in payload["roles"]}
    assert roles_by_name["audit"] == ["audit_log-View", "error_logs-View"]
    assert "super_admin-View" not in roles_by_name["security"]
    assert "network_white_list-View" not in roles_by_name["security"]
    assert "api_secret_key-View" not in roles_by_name["security"]


def test_enterprise_setting_append_matches_frontend_order_and_titles():
    payload = extend_menus_by_install_apps(_payload(), {"system_mgmt", "license_mgmt"})
    setting = next(item for item in payload["menus"] if item["name"] == "Setting")
    organization = next(item for item in payload["menus"] if item["name"] == "Organization")
    security = next(item for item in payload["menus"] if item["name"] == "Security")

    appended = setting["children"][-2:]
    assert [child["id"] for child in appended] == ["portal_settings", "license_mgmt"]
    assert [child["name"] for child in appended] == ["Portal Settings", "License Management"]
    assert appended[0]["operation"] == ["View", "Edit"]
    assert appended[1]["operation"] == ["View", "Add", "Edit", "Delete"]
    assert [child["id"] for child in setting["children"][:-2]] == SETTING_CHILD_IDS
    assert [child["id"] for child in organization["children"]] == USER_CHILD_IDS
    assert [child["id"] for child in security["children"]] == [
        "security_settings",
        "super_admin",
        "sensitive_info",
        "network_white_list",
    ]
    assert security["children"][2] == {
        "id": "sensitive_info",
        "name": "Sensitive Info",
        "operation": ["View", "Edit", "Add", "Delete"],
    }

    security_role = next(item for item in payload["roles"] if item["name"] == "security")
    for menu_name in ("sensitive_info-View", "sensitive_info-Add", "sensitive_info-Edit", "sensitive_info-Delete"):
        assert menu_name in security_role["menus"]
    assert "super_admin-View" not in security_role["menus"]
    assert "network_white_list-View" not in security_role["menus"]


@pytest.mark.django_db
def test_create_resource_updates_display_and_order_without_replacing_ids():
    payload = _payload()
    App.objects.create(name="system-manager", display_name="Setting", url="/system-manager")

    original_ids = {}
    index = 1
    for group in payload["menus"]:
        for child in group["children"]:
            for operate in child["operation"]:
                name = f"{child['id']}-{operate}"
                menu = Menu.objects.create(
                    name=name,
                    display_name=f"OLD-{name}",
                    order=index,
                    app="system-manager",
                    menu_type="OLD",
                )
                original_ids[name] = menu.id
                index += 1

    role = Role.objects.create(
        name="custom-ia",
        app="system-manager",
        menu_list=list(original_ids.values()),
    )
    original_role_menus = list(role.menu_list)

    create_resource(App.objects.get(name="system-manager"), payload["menus"])

    role.refresh_from_db()
    assert role.menu_list == original_role_menus
    assert Menu.objects.filter(app="system-manager").count() == len(original_ids)

    for name, menu_id in original_ids.items():
        menu = Menu.objects.get(id=menu_id)
        assert menu.name == name
        assert not menu.display_name.startswith("OLD-")

    token_view = Menu.objects.get(name="api_secret_key-View", app="system-manager")
    assert token_view.id == original_ids["api_secret_key-View"]
    assert token_view.display_name == "API Token-View"
    assert token_view.menu_type == "Setting"

    security_view = Menu.objects.get(name="security_settings-View", app="system-manager")
    whitelist_view = Menu.objects.get(name="network_white_list-View", app="system-manager")
    assert security_view.id == original_ids["security_settings-View"]
    assert whitelist_view.id == original_ids["network_white_list-View"]
    assert security_view.menu_type == "Security"
    assert whitelist_view.menu_type == "Security"

    docs_view = Menu.objects.get(name="openapi_docs-View", app="system-manager")
    assert docs_view.display_name == "API Documentation-View"

    login_view = Menu.objects.get(name="login_auth-View", app="system-manager")
    super_admin_view = Menu.objects.get(name="super_admin-View", app="system-manager")
    audit_view = Menu.objects.get(name="audit_log-View", app="system-manager")
    error_view = Menu.objects.get(name="error_logs-View", app="system-manager")
    assert login_view.order < super_admin_view.order < whitelist_view.order
    assert audit_view.order < error_view.order < token_view.order


@pytest.mark.django_db
def test_create_resource_updates_enterprise_display_without_replacing_ids():
    payload = extend_menus_by_install_apps(_payload(), {"license_mgmt"})
    App.objects.create(name="system-manager", display_name="Setting", url="/system-manager")

    original_ids = {}
    for name, display_name in (
        ("portal_settings-View", "OLD-Portal-View"),
        ("license_mgmt-View", "OLD-License-View"),
    ):
        menu = Menu.objects.create(
            name=name,
            display_name=display_name,
            order=99,
            app="system-manager",
            menu_type="Setting",
        )
        original_ids[name] = menu.id

    create_resource(App.objects.get(name="system-manager"), payload["menus"])

    portal = Menu.objects.get(name="portal_settings-View", app="system-manager")
    license_view = Menu.objects.get(name="license_mgmt-View", app="system-manager")
    assert portal.id == original_ids["portal_settings-View"]
    assert license_view.id == original_ids["license_mgmt-View"]
    assert portal.display_name == "Portal Settings-View"
    assert license_view.display_name == "License Management-View"
    assert portal.order < license_view.order
