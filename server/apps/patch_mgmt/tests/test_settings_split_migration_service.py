from copy import deepcopy

import pytest

from apps.patch_mgmt.services.patch_settings_split_migration import migrate_patch_settings_split, reverse_patch_settings_split_custom_menus
from apps.system_mgmt.models import CustomMenuGroup, Menu, Role

pytestmark = pytest.mark.django_db


def _menu(name):
    return Menu.objects.create(
        name=name,
        display_name=f"{name}-display",
        order=1,
        app="patch",
        menu_type="Settings",
    )


def _permission_resources():
    return {
        name: _menu(name)
        for name in (
            "patch_source-View",
            "patch_source-Add",
            "patch_source-Edit",
            "patch_source-Delete",
            "patch_scan_setting-View",
            "patch_scan_setting-Edit",
        )
    }


def test_migrate_patch_settings_split_preserves_role_access_and_custom_menu_position():
    resources = _permission_resources()
    role = Role.objects.create(
        name="custom-maintainer",
        app="patch",
        menu_list=[
            resources["patch_source-View"].id,
            resources["patch_source-Add"].id,
            resources["patch_source-Edit"].id,
        ],
    )
    group = CustomMenuGroup.objects.create(
        display_name="custom",
        app="patch",
        is_enabled=True,
        menus=[
            {"name": "patch", "title": "补丁库", "url": "/patch-manager/library"},
            {
                "name": "patch_source",
                "title": "自定义设置",
                "url": "/patch-manager/settings",
                "icon": "custom-settings-icon",
            },
            {"name": "patch_target", "title": "目标", "url": "/patch-manager/target"},
        ],
    )

    result = migrate_patch_settings_split()

    role.refresh_from_db()
    assert role.menu_list == [
        resources["patch_source-View"].id,
        resources["patch_source-Add"].id,
        resources["patch_source-Edit"].id,
        resources["patch_scan_setting-View"].id,
        resources["patch_scan_setting-Edit"].id,
    ]
    group.refresh_from_db()
    assert [node["name"] for node in group.menus] == ["patch", "patch_settings", "patch_target"]
    settings = group.menus[1]
    assert settings["title"] == "自定义设置"
    assert settings["icon"] == "custom-settings-icon"
    assert [(child["name"], child["url"]) for child in settings["children"]] == [
        ("patch_source", "/patch-manager/settings/sources"),
        ("patch_scan_setting", "/patch-manager/settings/scan"),
    ]
    assert result.roles_updated == 1
    assert result.custom_menu_groups_updated == 1


def test_migrate_patch_settings_split_is_idempotent_and_completes_partial_role_grants():
    resources = _permission_resources()
    role = Role.objects.create(
        name="partially-migrated",
        app="patch",
        menu_list=[
            resources["patch_source-View"].id,
            resources["patch_source-Edit"].id,
            resources["patch_scan_setting-View"].id,
        ],
    )
    group = CustomMenuGroup.objects.create(
        display_name="custom",
        app="patch",
        is_enabled=True,
        menus=[{"name": "patch_source", "title": "Settings", "url": "/patch-manager/settings"}],
    )

    first = migrate_patch_settings_split()
    role.refresh_from_db()
    group.refresh_from_db()
    first_menu_list = deepcopy(role.menu_list)
    first_custom_menus = deepcopy(group.menus)
    second = migrate_patch_settings_split()

    role.refresh_from_db()
    group.refresh_from_db()
    assert resources["patch_scan_setting-Edit"].id in role.menu_list
    assert role.menu_list == first_menu_list
    assert group.menus == first_custom_menus
    assert first.roles_updated == 1
    assert first.custom_menu_groups_updated == 1
    assert second.roles_updated == 0
    assert second.custom_menu_groups_updated == 0


def test_migrate_patch_settings_split_does_not_add_removed_custom_menu():
    _permission_resources()
    original_menus = [{"name": "patch", "title": "Patch Library", "url": "/patch-manager/library"}]
    group = CustomMenuGroup.objects.create(
        display_name="without-settings",
        app="patch",
        is_enabled=True,
        menus=deepcopy(original_menus),
    )

    result = migrate_patch_settings_split()

    group.refresh_from_db()
    assert group.menus == original_menus
    assert result.custom_menu_groups_updated == 0


def test_migrate_patch_settings_split_empty_install_is_a_noop():
    _permission_resources()

    result = migrate_patch_settings_split()

    assert result.roles_updated == 0
    assert result.custom_menu_groups_updated == 0


def test_migrate_patch_settings_split_fails_closed_when_permission_resources_are_partial():
    _menu("patch_source-View")

    with pytest.raises(RuntimeError, match="补丁设置权限资源不完整"):
        migrate_patch_settings_split()


def test_migrate_patch_settings_split_updates_nested_legacy_node_in_place():
    _permission_resources()
    group = CustomMenuGroup.objects.create(
        display_name="nested",
        app="patch",
        is_enabled=True,
        menus=[
            {
                "name": "custom-group",
                "title": "Custom group",
                "children": [
                    {
                        "name": "patch_source",
                        "title": "Settings",
                        "url": "/patch-manager/settings",
                    }
                ],
            }
        ],
    )

    migrate_patch_settings_split()

    group.refresh_from_db()
    assert group.menus[0]["children"][0]["name"] == "patch_settings"
    assert group.menus[0]["children"][0]["children"][1]["name"] == "patch_scan_setting"


def test_reverse_patch_settings_split_restores_legacy_custom_menu_leaf():
    _permission_resources()
    group = CustomMenuGroup.objects.create(
        display_name="rollback",
        app="patch",
        is_enabled=True,
        menus=[
            {
                "name": "patch_source",
                "title": "自定义设置",
                "url": "/patch-manager/settings",
                "icon": "custom-settings-icon",
            }
        ],
    )
    migrate_patch_settings_split()

    result = reverse_patch_settings_split_custom_menus()

    group.refresh_from_db()
    assert group.menus == [
        {
            "name": "patch_source",
            "title": "自定义设置",
            "url": "/patch-manager/settings",
            "icon": "custom-settings-icon",
        }
    ]
    assert result.custom_menu_groups_updated == 1
