from io import StringIO

import pytest
from django.core.management import call_command

from apps.system_mgmt.models import CustomMenuGroup, Menu, Role

pytestmark = pytest.mark.django_db


def _create_menu(name, app="opspilot", menu_type="Knowledge"):
    return Menu.objects.create(
        name=name,
        display_name=f"{name}-display",
        order=1,
        app=app,
        menu_type=menu_type,
    )


def _collect_names(nodes):
    names = []
    for node in nodes:
        names.append(node.get("name"))
        names.extend(_collect_names(node.get("children") or []))
    return names


def test_cleanup_opspilot_legacy_knowledge_menus_dry_run_does_not_change_data():
    legacy_menu = _create_menu("knowledge_list-View")
    role = Role.objects.create(name="normal", app="opspilot", menu_list=[legacy_menu.id])
    group = CustomMenuGroup.objects.create(
        display_name="custom",
        app="opspilot",
        is_enabled=True,
        is_build_in=False,
        menus=[{"name": "knowledge_list", "display_name": "Legacy Knowledge", "url": "/opspilot/knowledge"}],
    )

    out = StringIO()
    call_command("cleanup_opspilot_legacy_knowledge_menus", "--dry-run", stdout=out)

    assert "DRY-RUN" in out.getvalue()
    assert Menu.objects.filter(id=legacy_menu.id).exists()
    role.refresh_from_db()
    group.refresh_from_db()
    assert role.menu_list == [legacy_menu.id]
    assert group.menus[0]["name"] == "knowledge_list"


def test_cleanup_opspilot_legacy_knowledge_menus_migrates_roles_and_deletes_old_menus():
    legacy_view = _create_menu("knowledge_list-View")
    legacy_train = _create_menu("knowledge_document-Train")
    legacy_delete = _create_menu("knowledge_document-Delete")
    legacy_other_app_role_ref = _create_menu("knowledge_setting-View")
    unrelated = _create_menu("asset_info-View", app="cmdb", menu_type="Asset")
    opspilot_role = Role.objects.create(
        name="normal",
        app="opspilot",
        menu_list=[legacy_view.id, unrelated.id, legacy_train.id, legacy_delete.id],
    )
    other_role = Role.objects.create(
        name="foreign",
        app="cmdb",
        menu_list=[legacy_other_app_role_ref.id, unrelated.id],
    )

    call_command("cleanup_opspilot_legacy_knowledge_menus")

    assert not Menu.objects.filter(name__startswith="knowledge_", app="opspilot").exists()
    wiki_names = {"wiki_list-View", "wiki_list-Add", "wiki_list-Edit", "wiki_list-Delete"}
    wiki_menus = {item.name: item.id for item in Menu.objects.filter(app="opspilot", name__in=wiki_names)}
    assert set(wiki_menus) == wiki_names

    opspilot_role.refresh_from_db()
    assert legacy_view.id not in opspilot_role.menu_list
    assert legacy_train.id not in opspilot_role.menu_list
    assert legacy_delete.id not in opspilot_role.menu_list
    assert unrelated.id in opspilot_role.menu_list
    assert wiki_menus["wiki_list-View"] in opspilot_role.menu_list
    assert wiki_menus["wiki_list-Edit"] in opspilot_role.menu_list
    assert wiki_menus["wiki_list-Delete"] in opspilot_role.menu_list
    assert len(opspilot_role.menu_list) == len(set(opspilot_role.menu_list))

    other_role.refresh_from_db()
    assert legacy_other_app_role_ref.id not in other_role.menu_list
    assert unrelated.id in other_role.menu_list
    assert not set(wiki_menus.values()).intersection(other_role.menu_list)


def test_cleanup_opspilot_legacy_knowledge_menus_updates_custom_menu_groups():
    CustomMenuGroup.objects.create(
        display_name="custom",
        app="opspilot",
        is_enabled=True,
        is_build_in=False,
        menus=[
            {"name": "bot_list", "display_name": "Bot", "url": "/opspilot/studio"},
            {
                "name": "knowledge_list",
                "display_name": "Legacy Knowledge",
                "url": "/opspilot/knowledge",
                "children": [{"name": "knowledge_document", "url": "/opspilot/knowledge/document"}],
            },
            {"name": "provide_list", "display_name": "Model", "url": "/opspilot/model"},
        ],
    )

    call_command("cleanup_opspilot_legacy_knowledge_menus")

    group = CustomMenuGroup.objects.get(app="opspilot", display_name="custom")
    names = _collect_names(group.menus)
    assert "knowledge_list" not in names
    assert "knowledge_document" not in names
    assert "bot_list" in names
    assert "provide_list" in names
    assert "wiki_list" in names
