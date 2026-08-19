from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.system_mgmt.models import CustomMenuGroup, Menu, Role

pytestmark = pytest.mark.django_db


def _menu(name, order):
    return Menu.objects.create(
        name=name,
        display_name=f"{name}-display",
        order=order,
        app="patch",
        menu_type="Settings",
    )


def test_patch_settings_command_migrates_split_on_repeated_startup():
    source_view = _menu("patch_source-View", 1)
    source_edit = _menu("patch_source-Edit", 2)
    scan_view = _menu("patch_scan_setting-View", 3)
    scan_edit = _menu("patch_scan_setting-Edit", 4)
    role = Role.objects.create(
        name="custom",
        app="patch",
        menu_list=[source_view.id, source_edit.id],
    )
    group = CustomMenuGroup.objects.create(
        display_name="custom",
        app="patch",
        is_enabled=True,
        menus=[
            {
                "name": "patch_source",
                "title": "Settings",
                "url": "/patch-manager/settings",
            }
        ],
    )

    with patch("apps.patch_mgmt.management.commands.migrate_patch_settings_split.clear_all_permission_cache") as clear_permission_cache:
        call_command("migrate_patch_settings_split")
        call_command("migrate_patch_settings_split")

    role.refresh_from_db()
    assert role.menu_list.count(scan_view.id) == 1
    assert role.menu_list.count(scan_edit.id) == 1
    assert clear_permission_cache.call_count == 1

    group.refresh_from_db()
    assert group.menus[0]["name"] == "patch_settings"
    assert [child["name"] for child in group.menus[0]["children"]] == [
        "patch_source",
        "patch_scan_setting",
    ]
