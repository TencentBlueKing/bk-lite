from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Menu, Role

CMDB_APP = "cmdb"
VIEW_MENU = "asset_info-View"
EXPORT_MENU = "asset_info-Export"
BUILTIN_ROLES = frozenset({"admin", "normal", "manager"})


def prepare_asset_export_grant():
    """导出菜单还不存在时，记下哪些角色已经有资产查看。菜单已存在则不再补授权。"""
    if Menu.objects.filter(app=CMDB_APP, name=EXPORT_MENU).exists():
        return None
    view = Menu.objects.filter(app=CMDB_APP, name=VIEW_MENU).first()
    if view is None:
        return {}
    view_id = str(view.id)
    return {role.id: view_id in {str(menu_id) for menu_id in (role.menu_list or [])} for role in Role.objects.filter(app=CMDB_APP).order_by("id")}


def grant_asset_export_from_view(snapshot):
    """把当时已有资产查看的自定义角色补上资产导出。内置角色以菜单清单为准，可重复执行。"""
    if not snapshot:
        return []
    export = Menu.objects.filter(app=CMDB_APP, name=EXPORT_MENU).first()
    if export is None:
        return []
    export_id = export.id
    export_key = str(export_id)
    changed = []
    for role in Role.objects.filter(app=CMDB_APP, id__in=snapshot).order_by("id"):
        if role.name in BUILTIN_ROLES or not snapshot.get(role.id):
            continue
        current = list(role.menu_list or [])
        if export_key in {str(menu_id) for menu_id in current}:
            continue
        current.append(export_id)
        role.menu_list = current
        changed.append(role)
    if changed:
        Role.objects.bulk_update(changed, ["menu_list"], batch_size=100)
        logger.info("event=cmdb_asset_export_grant roles=%s", len(changed))
    return changed
