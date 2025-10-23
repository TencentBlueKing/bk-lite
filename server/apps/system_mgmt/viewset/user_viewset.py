from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.backends import cache
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group, Role, User, UserRule
from apps.system_mgmt.serializers.user_serializer import UserSerializer
from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.utils.viewset_utils import ViewSetUtils


class UserViewSet(ViewSetUtils):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def search_user_list(self, request):
        # 获取请求参数
        search = request.GET.get("search", "")
        group_id = request.GET.get("group_id", "")
        # 过滤用户数据
        queryset = User.objects.filter(Q(username__icontains=search) | Q(display_name__icontains=search) | Q(email__icontains=search))
        # 如果指定了用户组ID，则过滤该组内的用户
        if group_id:
            queryset = queryset.filter(group_list__contains=int(group_id))
        roles = Role.objects.all().values("id", "name", "app")
        role_map = {}
        for i in roles:
            role_map[i["id"]] = f"{i['app']}@@{i['name']}"
        data, total = self.search_by_page(queryset.order_by("-id"), request, User.display_fields())
        for i in data:
            i["roles"] = [role_map.get(role_id, "") for role_id in i["role_list"]]
        return JsonResponse({"result": True, "data": {"count": total, "users": data}})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def user_all(self, request):
        data = User.objects.all().values(*User.display_fields())
        return JsonResponse({"result": True, "data": list(data)})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def user_id_all(self, request):
        data = User.objects.all().values("id", "display_name", "username")
        return JsonResponse({"result": True, "data": list(data)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-View")
    def get_user_detail(self, request):
        pk = request.data.get("user_id")
        user = User.objects.get(id=pk)
        roles = Role.objects.filter(id__in=user.role_list).values(role_id=F("id"), role_name=F("name"), display_name=F("name"))
        groups = list(Group.objects.filter(id__in=user.group_list).values("id", "name"))
        group_rule_map = {}
        rules = UserRule.objects.filter(username=user.username).values("group_rule__group_id", "group_rule_id", "group_rule__app")
        for rule in rules:
            group_rule_map.setdefault(rule["group_rule__group_id"], {}).setdefault(rule["group_rule__app"], []).append(rule["group_rule_id"])
        for i in groups:
            i["rules"] = group_rule_map.get(i["id"], {})
        data = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "disabled": user.disabled,
            "locale": user.locale,
            "timezone": user.timezone,
            "roles": list(roles),
            "groups": groups,
        }
        return JsonResponse({"result": True, "data": data})

    # @action(detail=False, methods=["GET"])
    # def get_users_in_role(self, request, role_name: str):
    #     data = UserManage().user_list_by_role(role_name)
    #     return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Add User")
    def create_user(self, request):
        kwargs = request.data
        rules = kwargs.pop("rules", [])
        try:
            with transaction.atomic():
                User.objects.create(
                    username=kwargs["username"],
                    display_name=kwargs["lastName"],
                    email=kwargs["email"],
                    disabled=False,
                    locale=kwargs["locale"],
                    timezone=kwargs["timezone"],
                    group_list=kwargs["groups"],
                    role_list=kwargs["roles"],
                    temporary_pwd=kwargs.get("temporary_pwd", False),
                )
                if rules:
                    add_rule = [UserRule(username=kwargs["username"], group_rule_id=i) for i in rules]
                    UserRule.objects.bulk_create(add_rule, batch_size=100)
            return JsonResponse({"result": True})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def reset_password(self, request):
        try:
            password = request.data.get("password")
            temporary_pwd = request.data.get("temporary", False)
            User.objects.filter(id=request.data.get("id")).update(password=make_password(password), temporary_pwd=temporary_pwd)
            return JsonResponse({"result": True})
        except Exception as e:
            logger.exception(e)
            return JsonResponse({"result": False, "message": str(e)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Delete User")
    def delete_user(self, request):
        user_ids = request.data.get("user_ids")
        users = User.objects.filter(id__in=user_ids)
        keys = []
        for i in users:
            keys.extend(RoleManage.get_cache_keys(i.username))
        cache.delete_many(keys)
        users.delete()
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def update_user(self, request):
        params = request.data
        pk = params.pop("user_id")
        rules = params.pop("rules", [])
        keys = RoleManage.get_cache_keys(params["username"])
        with transaction.atomic():
            # 删除旧的规则
            UserRule.objects.filter(username=params["username"]).delete()
            # 更新用户信息
            if rules:
                add_rule = [UserRule(username=params["username"], group_rule_id=i) for i in rules]
                UserRule.objects.bulk_create(add_rule, batch_size=100)
            User.objects.filter(id=pk).update(
                display_name=params.get("lastName"),
                email=params.get("email"),
                locale=params.get("locale"),
                timezone=params.get("timezone"),
                group_list=params.get("groups"),
                role_list=params.get("roles"),
            )
            cache.delete_many(keys)
        return JsonResponse({"result": True})

    @action(detail=True, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def assign_user_groups(self, request):
        pk = request.data.get("user_id")
        user = User.objects.get(id=pk)
        if request.data.get("group_id") in user.group_list:
            return JsonResponse({"result": False, "message": "用户组已存在"})
        if not request.data.get("group_id"):
            return JsonResponse({"result": False, "message": "用户组不能为空"})
        user.group_list.append(request.data.get("group_id"))
        user.save()
        return JsonResponse({"result": True})

    @action(detail=True, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def unassign_user_groups(self, request):
        pk = request.data.get("user_id")
        user = User.objects.get(id=pk)
        if request.data.get("group_id") not in user.group_list:
            return JsonResponse({"result": False, "message": "用户组不存在"})
        if not request.data.get("group_id"):
            return JsonResponse({"result": False, "message": "用户组不能为空"})
        user.group_list.remove(request.data.get("group_id"))
        user.save()
        return JsonResponse({"result": True})
