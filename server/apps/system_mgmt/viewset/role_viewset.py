from django.db.models import Q
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.backends import cache
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import Group, Menu, Role, User
from apps.system_mgmt.serializers.role_serializer import RoleSerializer
from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.utils.viewset_utils import ViewSetUtils


class RoleViewSet(LanguageViewSet, ViewSetUtils):
    queryset = Role.objects.exclude(app="")
    serializer_class = RoleSerializer

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-View")
    def search_role_list(self, request):
        client_id = request.data.get("client_id", [])
        if not isinstance(client_id, list):
            client_id = [client_id]
        data = Role.objects.filter(app__in=client_id).values("id", "name").order_by("id")
        return JsonResponse({"result": True, "data": list(data)})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-View")
    def get_role_tree(self, request):
        client_list = request.data.get("client_list", [])
        return_data = []
        client_ids = [i["name"] for i in client_list]
        roles = Role.objects.filter(app__in=client_ids).values("id", "name", "app").order_by("id")
        role_map = {}
        for i in roles:
            role_map.setdefault(i["app"], []).append(
                {
                    "id": i["id"],
                    "name": i["name"],
                }
            )
        for client_obj in client_list:
            app_role = role_map.get(client_obj["name"], [])
            return_data.append({"id": client_obj["id"] * 886, "name": client_obj["name"], "children": app_role})
        return JsonResponse({"result": True, "data": return_data})

    @action(detail=False, methods=["GET"])
    @HasPermission("application_role-View")
    def search_role_users(self, request):
        search = request.GET.get("search", "")
        role_id = request.GET.get("role_id", "0")
        # 过滤用户数据
        queryset = (
            User.objects.filter(role_list__contains=int(role_id))
            .filter(Q(username__icontains=search) | Q(display_name__icontains=search) | Q(email__icontains=search))
            .order_by("-id")
        )
        data, total = self.search_by_page(queryset, request, User.display_fields())
        return JsonResponse({"result": True, "data": {"items": data, "count": total}})

    @action(detail=False, methods=["GET"])
    @HasPermission("application_role-View")
    def get_all_menus(self, request):
        client_id = request.GET.get("client_id")
        data = RoleManage().get_all_menus(client_id, is_superuser=True)
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    @HasPermission("application_role-View")
    def get_role_menus(self, request):
        role_id = request.GET.get("role_id")
        menus = Role.objects.get(id=role_id).menu_list
        return_data = Menu.objects.filter(id__in=menus).values_list("name", flat=True)
        return JsonResponse({"result": True, "data": list(return_data)})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Add")
    def create_role(self, request):
        role_obj = Role.objects.create(
            app=request.data.get("client_id"),
            name=request.data["name"],
        )
        return_data = {"id": role_obj.id, "name": role_obj.name}
        return JsonResponse({"result": True, "data": return_data})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Delete")
    def delete_role(self, request):
        role_id = request.data.get("role_id")
        role_name = request.data.get("role_name")
        if role_name in ["admin", "normal"]:
            return JsonResponse({"result": False, "message": self.loader.get("error.cannot_delete_admin_normal_roles")})
        users = User.objects.filter(role_list__contains=int(role_id)).values_list("username", flat=True)
        if users:
            msg = "、".join([i["username"] for i in list(users)])
            return JsonResponse({"result": False, "message": self.loader.get("error.role_used_by_users").format(users=msg)})
        Role.objects.filter(id=role_id).delete()
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Edit")
    def update_role(self, request):
        Role.objects.filter(id=request.data.get("role_id")).update(name=request.data.get("role_name"))
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Add user")
    def add_user(self, request):
        role_id = request.data.get("role_id")
        user_ids = request.data.get("user_ids")
        is_superuser = request.data.get("is_superuser") or False
        if is_superuser:
            role_id = Role.objects.get(name="admin", app="").id
        user_list = User.objects.filter(id__in=user_ids)
        for i in user_list:
            if role_id not in i.role_list:
                i.role_list.append(int(role_id))
        User.objects.bulk_update(user_list, ["role_list"], batch_size=100)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Remove user")
    def delete_user(self, request):
        pk = int(request.data.get("role_id") or 0)
        user_ids = request.data.get("user_ids")
        is_superuser = request.data.get("is_superuser") or False
        if is_superuser:
            pk = Role.objects.get(name="admin", app="").id
        user_list = User.objects.filter(id__in=user_ids)
        for i in user_list:
            if pk in i.role_list:
                i.role_list.remove(pk)
        User.objects.bulk_update(user_list, ["role_list"], batch_size=100)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Edit Permission")
    def set_role_menus(self, request):
        params = request.data
        role_id = params.get("role_id")
        menus = params.get("menus")
        role_obj = Role.objects.get(id=role_id)
        menu_ids = Menu.objects.filter(app=role_obj.app, name__in=menus).values_list("id", flat=True)
        role_obj.menu_list = list(menu_ids)
        role_obj.save()
        cache_key = f"all_menus_{role_obj.app}"
        keys = RoleManage.get_cache_keys(cache_key)
        user_menu_cache = "menus-user:"
        keys.extend(RoleManage.get_cache_keys(user_menu_cache))
        cache.delete_many(keys)
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Edit")
    def batch_assign_group_roles(self, request):
        """
        批量为组织分配角色
        """
        try:
            group_ids = request.data.get("group_ids", [])
            role_id = request.data.get("role_id")

            if not group_ids or not role_id:
                return JsonResponse({"result": False, "message": self.loader.get("error.group_ids_role_id_required")})

            # 验证组织是否存在
            groups = Group.objects.filter(id__in=group_ids)
            if len(groups) != len(group_ids):
                return JsonResponse({"result": False, "message": self.loader.get("error.some_groups_not_exist")})

            # 验证角色是否存在
            try:
                role = Role.objects.get(id=role_id)
            except Role.DoesNotExist:
                return JsonResponse({"result": False, "message": self.loader.get("error.some_roles_not_exist")})

            # 使用ManyToMany关系批量分配角色
            for group in groups:
                group.roles.add(role)

            return JsonResponse({"result": True})

        except Exception as e:
            logger.exception(f"批量分配组织角色失败: {e}")
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["POST"])
    @HasPermission("application_role-Edit")
    def revoke_group_roles(self, request):
        """
        回收组织的角色
        """
        try:
            group_ids = request.data.get("group_ids", [])
            role_id = request.data.get("role_id")

            if not group_ids or not role_id:
                return JsonResponse({"result": False, "message": self.loader.get("error.group_ids_role_id_required")})

            # 验证组织是否存在
            groups = Group.objects.filter(id__in=group_ids)
            if len(groups) != len(group_ids):
                return JsonResponse({"result": False, "message": self.loader.get("error.some_groups_not_exist")})

            # 验证角色是否存在
            try:
                role = Role.objects.get(id=role_id)
            except Role.DoesNotExist:
                return JsonResponse({"result": False, "message": self.loader.get("error.some_roles_not_exist")})

            # 使用ManyToMany关系回收角色
            for group in groups:
                group.roles.remove(role)

            return JsonResponse({"result": True})

        except Exception as e:
            logger.exception(f"回收组织角色失败: {e}")
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def get_role_groups(self, request):
        """
        查询指定角色下的组织列表，支持分页和组名筛选
        """
        try:
            role_id = request.GET.get("role_id")
            search = request.GET.get("search", "")
            if not role_id:
                return JsonResponse({"result": False, "message": self.loader.get("error.role_id_required")})

            # 验证角色是否存在
            try:
                role = Role.objects.get(id=role_id)
            except Role.DoesNotExist:
                return JsonResponse({"result": False, "message": self.loader.get("error.some_roles_not_exist")})
            # 获取拥有该角色的组织，支持按组名筛选
            queryset = role.group_set.all()
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(display_name__icontains=search))

            queryset = queryset.order_by("-id")

            # 使用分页功能
            data, total = self.search_by_page(queryset, request, ["id", "name", "parent_id"])

            return JsonResponse({"result": True, "data": {"items": data, "count": total}})

        except Exception as e:
            logger.exception(f"查询角色组织失败: {e}")
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def get_groups_roles(self, request):
        """
        查询一批组织的角色列表（去重）
        """
        try:
            group_ids = request.data.get("group_ids", [])

            if not isinstance(group_ids, list):
                return JsonResponse({"result": False, "message": "group_ids must be a list"})

            if not group_ids:
                return JsonResponse({"result": True, "data": []})

            # 查询这批组织的所有角色，去重
            roles = Role.objects.filter(group__id__in=group_ids).distinct().values("id", "name", "app").order_by("id")

            return JsonResponse({"result": True, "data": list(roles)})

        except Exception as e:
            logger.exception(f"查询组织角色列表失败: {e}")
            return JsonResponse({"result": False, "message": str(e)})
