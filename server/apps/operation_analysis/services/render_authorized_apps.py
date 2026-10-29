"""订阅渲染身份的模块许可列表。

与登录态 get_client 对齐：按执行创建者的角色收应用，再走 EE license filter。
渲染页不挂 ClientProvider，不能自己打 get_client。
"""

from __future__ import annotations


def resolve_execution_authorized_app_names(*, username: str, domain: str) -> list[str]:
    from apps.core.utils.user_group import normalize_user_group_ids
    from apps.system_mgmt.models.app import App
    from apps.system_mgmt.models.role import Role
    from apps.system_mgmt.models.user import User
    from apps.system_mgmt.nats.common import get_user_all_roles

    user = User.objects.filter(username=username, domain=domain).first()
    if user is None:
        return []
    # get_user_all_roles 只认整数组织 ID。部分用户记录和分享夹具是 {id, name}，
    # 不归一化会在打开分享时 500。只改内存对象，不回写用户。
    user.group_list = normalize_user_group_ids(user.group_list)

    apps = App.objects.all()
    role_ids = get_user_all_roles(user)
    roles = Role.objects.filter(id__in=role_ids)
    role_names = [f"{role.app}--{role.name}" if role.app else role.name for role in roles]
    is_superuser = "admin" in role_names or "system-manager--admin" in role_names
    if not is_superuser:
        app_name_list = list(Role.objects.filter(id__in=role_ids).values_list("app", flat=True).distinct())
        if "" not in app_name_list:
            apps = apps.filter(name__in=app_name_list)

    # 与 get_client 的 .values() 一致，license filter 能看到 is_build_in 等字段。
    payload = [item for item in apps.order_by("id").values() if item.get("name")]
    try:
        mod = __import__("apps.core.enterprise.license_filter", fromlist=["filter_clients_by_license"])
        payload = mod.filter_clients_by_license(payload)
    except (ImportError, ModuleNotFoundError):
        pass
    return [item["name"] for item in payload if isinstance(item, dict) and item.get("name")]
