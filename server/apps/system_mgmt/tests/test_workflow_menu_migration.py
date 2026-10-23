import pytest

from apps.system_mgmt.models import CustomMenuGroup, Menu, Role
from apps.system_mgmt.services.workflow_menu_migration import apply_workflow_menu_permission_split, snapshot_workflow_menu_grants

APP = "workflow"


def _menu(name):
    return Menu.objects.create(name=name, display_name=name, url="", app=APP, menu_type="Workflow")


@pytest.mark.django_db
def test_custom_role_grants_and_custom_menus_split_without_touching_builtin_roles():
    old_names = ["workflow-View", "workflow-Add", "workflow-Execute", "workflow-Approve"]
    new_names = [
        "workflow_home-View",
        "workflow_market-View",
        "workflow_market-Add",
        "workflow_execution-View",
        "workflow_execution-Execute",
        "workflow_execution-Approve",
    ]
    menus = {name: _menu(name) for name in [*old_names, *new_names]}
    granted = [menus[name].id for name in old_names]
    custom = Role.objects.create(name="auditor", app=APP, menu_list=list(granted))
    normal = Role.objects.create(name="normal", app=APP, menu_list=list(granted))
    group = CustomMenuGroup.objects.create(
        display_name="自定义菜单",
        app=APP,
        menus=[
            {
                "title": "流程",
                "url": "/workflow/workflows",
                "name": "workflow",
                "children": [
                    {
                        "title": "流程",
                        "url": "/workflow/workflows/",
                        "name": "workflow",
                        "withParentPermission": True,
                    },
                    {
                        "title": "模版",
                        "url": "/workflow/market",
                        "name": "workflow",
                        "withParentPermission": True,
                    },
                ],
            },
            {"title": "首页", "url": "/workflow/home", "name": "workflow"},
            {"title": "入口", "url": "/workflow", "name": "workflow"},
        ],
    )

    snapshot = snapshot_workflow_menu_grants()
    approve_id = menus["workflow-Approve"].id
    menus["workflow-Approve"].delete()
    apply_workflow_menu_permission_split(snapshot)
    apply_workflow_menu_permission_split(snapshot)

    custom.refresh_from_db()
    normal.refresh_from_db()
    group.refresh_from_db()
    assert set(custom.menu_list) == {menus[name].id for name in [*old_names, *new_names] if name != "workflow-Approve"} | {approve_id}
    assert normal.menu_list == granted
    assert group.menus[0]["children"][0]["name"] == "workflow"
    assert "withParentPermission" not in group.menus[0]["children"][0]
    assert group.menus[0]["children"][1]["name"] == "workflow_market"
    assert "withParentPermission" not in group.menus[0]["children"][1]
    assert group.menus[1]["name"] == "workflow_home"
    assert group.menus[2]["name"] == "workflow_entry"
