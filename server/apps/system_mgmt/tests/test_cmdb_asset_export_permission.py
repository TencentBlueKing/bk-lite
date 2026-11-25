import logging

import pytest

from apps.system_mgmt.models import Menu, Role
from apps.system_mgmt.services.cmdb_asset_export_permission import grant_asset_export_from_view, prepare_asset_export_grant


def _menu(name):
    return Menu.objects.create(name=name, display_name=name, url="", app="cmdb", menu_type="Asset")


@pytest.mark.django_db
def test_custom_view_role_gains_export_once_and_builtin_roles_stay(caplog):
    view = _menu("asset_info-View")
    custom = Role.objects.create(name="ops", app="cmdb", menu_list=[view.id])
    normal = Role.objects.create(name="normal", app="cmdb", menu_list=[view.id])
    bare = Role.objects.create(name="lookup", app="cmdb", menu_list=[])

    snapshot = prepare_asset_export_grant()
    export = _menu("asset_info-Export")
    with caplog.at_level(logging.INFO, logger="system-manager"):
        changed = grant_asset_export_from_view(snapshot)
        grant_asset_export_from_view(snapshot)

    custom.refresh_from_db()
    normal.refresh_from_db()
    bare.refresh_from_db()
    assert custom.menu_list == [view.id, export.id]
    assert normal.menu_list == [view.id]
    assert bare.menu_list == []
    assert [role.id for role in changed] == [custom.id]
    grant_logs = [record for record in caplog.records if record.name == "system-manager"]
    assert len(grant_logs) == 1
    assert grant_logs[0].msg == "event=cmdb_asset_export_grant roles=%s"
    assert grant_logs[0].args == (1,)
    assert grant_logs[0].getMessage() == "event=cmdb_asset_export_grant roles=1"
    assert "SECRET" not in caplog.text

    custom.menu_list = [view.id]
    custom.save(update_fields=["menu_list"])
    assert prepare_asset_export_grant() is None
