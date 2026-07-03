# flake8: noqa
from .common import *  # noqa: F401,F403


@nats_client.register
def get_user_menus(client_id, roles, username, is_superuser):
    client = RoleManage()
    # client_id used directly below
    menus = []
    if not is_superuser:
        menu_ids = []
        role_menus = Role.objects.filter(app=client_id, id__in=roles).values_list("menu_list", flat=True)
        for i in role_menus:
            menu_ids.extend(i)
        menus = list(Menu.objects.filter(app=client_id, id__in=list(set(menu_ids))).values_list("name", flat=True))
    user_menus = client.get_all_menus(client_id, user_menus=menus, username=username, is_superuser=is_superuser)
    return {"result": True, "data": user_menus}


@nats_client.register
def get_client(client_id="", username="", domain="domain.com"):
    app_list = App.objects.all()

    if client_id:
        app_list = app_list.filter(name__in=client_id.split(";"))

    if username:
        user = User.objects.filter(username=username, domain=domain).first()
        if not user:
            return {"result": False, "message": "User not found"}
        # 获取用户所有角色（个人角色 + 组角色）
        all_role_ids = get_user_all_roles(user)
        role_list = Role.objects.filter(id__in=all_role_ids)
        role_names = [f"{role.app}--{role.name}" if role.app else role.name for role in role_list]
        is_superuser = "admin" in role_names or "system-manager--admin" in role_names
        if not is_superuser:
            app_name_list = list(Role.objects.filter(id__in=all_role_ids).values_list("app", flat=True).distinct())
            if "" not in app_name_list:
                app_list = app_list.filter(name__in=app_name_list)
    return_data = list(app_list.order_by("id").values())
    return {"result": True, "data": return_data}


@nats_client.register
def get_client_detail(client_id):
    app_obj = App.objects.filter(name=client_id).first()
    if not app_obj:
        return {"result": False, "message": "Client not found"}
    return {
        "result": True,
        "data": {
            "id": app_obj.id,
            "name": app_obj.name,
            "display_name": app_obj.display_name,
            "description": app_obj.description,
            "description_cn": app_obj.description_cn,
        },
    }
