import pytest

from apps.core.utils.module_scope import client_id_from_module, module_apps_from_roles, module_privilege, overlay_module_permissions
from apps.system_mgmt.models import Menu, Role

pytestmark = pytest.mark.django_db


def test_module_privilege_is_per_client_and_admin_wins():
    roles = ["cmdb--module_admin", "cmdb--module_auditor", "monitor--module_auditor", "system-manager--module_admin"]

    assert module_privilege(roles, "cmdb") == "admin"
    assert module_privilege(roles, "monitor") == "auditor"
    assert module_privilege(roles, "job") is None
    assert module_privilege(roles, "system-manager") is None
    assert module_privilege(["ops-console--module_admin"], "ops-console") is None
    assert module_privilege(roles, "") is None


def test_client_id_uses_the_app_client_not_the_python_package():
    assert client_id_from_module("apps.cmdb.views.instance") == "cmdb"
    assert client_id_from_module("apps.job_mgmt.views.target") == "job"
    assert client_id_from_module("apps.alerts.views.alert") == "alarm"
    assert client_id_from_module("apps.system_mgmt.viewset.role_viewset") == "system-manager"


def test_overlay_gives_admin_every_menu_and_keeps_auditor_on_view():
    Menu.objects.create(app="cmdb", name="asset-View", display_name="v", url="", menu_type="t", order=1)
    Menu.objects.create(app="cmdb", name="asset-Add", display_name="a", url="", menu_type="t", order=2)
    Menu.objects.create(app="monitor", name="dash-View", display_name="v", url="", menu_type="t", order=1)
    Menu.objects.create(app="monitor", name="dash-Add", display_name="a", url="", menu_type="t", order=2)

    overlaid = overlay_module_permissions(
        {"cmdb": ["asset-Add"], "monitor": ["dash-Add", "dash-View"]},
        {"cmdb"},
        {"monitor"},
    )

    assert set(overlaid["cmdb"]) == {"asset-View", "asset-Add"}
    assert overlaid["monitor"] == ["dash-View"]


def test_module_apps_drop_system_manager_and_let_admin_replace_auditor():
    rows = [
        Role(name="module_admin", app="cmdb"),
        Role(name="module_auditor", app="cmdb"),
        Role(name="module_auditor", app="monitor"),
        Role(name="module_admin", app="system-manager"),
        Role(name="module_admin", app="ops-console"),
        Role(name="admin", app="job"),
    ]

    admin_apps, auditor_apps = module_apps_from_roles(rows)

    assert admin_apps == {"cmdb"}
    assert auditor_apps == {"monitor"}
