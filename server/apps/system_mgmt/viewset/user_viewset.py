from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_cache import clear_user_permission_cache, clear_users_permission_cache
from apps.rpc.cmdb import CMDB
from apps.system_mgmt.models import Group, Role, User, UserRule
from apps.system_mgmt.serializers.user_serializer import UserSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.password_validator import PasswordValidator
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
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 10))
        is_superuser = request.GET.get("is_superuser", "0") == "1"

        # 过滤用户数据
        queryset = User.objects.filter(Q(username__icontains=search) | Q(display_name__icontains=search) | Q(email__icontains=search))

        # 如果筛选超级用户，则过滤包含超管角色的用户
        if is_superuser:
            super_role_id = Role.objects.get(app="", name="admin").id
            queryset = queryset.filter(role_list__contains=super_role_id)

        # 如果指定了用户组ID，则过滤该组内的用户
        if group_id:
            queryset = queryset.filter(group_list__contains=int(group_id))

        # 排序
        queryset = queryset.order_by("-id")

        # 分页
        total = queryset.count()
        start = (page - 1) * page_size
        end = page * page_size
        users = queryset[start:end]

        # 使用 UserSerializer 序列化数据（自动包含 group_role_list）
        serializer = UserSerializer(users, many=True)
        data = serializer.data

        # 添加角色信息（保持原有逻辑）
        roles = Role.objects.all().values("id", "name", "app")
        role_map = {}
        for i in roles:
            role_map[i["id"]] = f"{i['app']}@@{i['name']}"

        for user_data in data:
            user_data["roles"] = [role_map.get(role_id, "") for role_id in user_data.get("role_list", [])]

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

        # 使用 UserSerializer 序列化用户数据（自动包含 group_role_list 和 is_superuser）
        serializer = UserSerializer(user)
        data = serializer.data

        # 添加角色详情
        roles = Role.objects.filter(id__in=user.role_list).values(role_id=F("id"), role_name=F("name"), display_name=F("name"))
        data["roles"] = list(roles)

        # 添加用户组详情及规则
        groups = list(Group.objects.filter(id__in=user.group_list).values("id", "name"))
        group_rule_map = {}
        rules = UserRule.objects.filter(username=user.username).values("group_rule__group_id", "group_rule_id", "group_rule__app")
        for rule in rules:
            group_rule_map.setdefault(rule["group_rule__group_id"], {}).setdefault(rule["group_rule__app"], []).append(rule["group_rule_id"])
        for i in groups:
            i["rules"] = group_rule_map.get(i["id"], {})
        data["groups"] = groups

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

        # 获取用户语言设置
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        loader = LanguageLoader(app="system_mgmt", default_lang=locale)

        # 校验 groups ID 是否真实存在
        groups = kwargs.get("groups", [])
        if groups:
            valid_group_ids = set(Group.objects.filter(id__in=groups).values_list("id", flat=True))
            invalid_group_ids = set(groups) - valid_group_ids
            if invalid_group_ids:
                message = loader.get("error.invalid_group_ids", "Invalid group IDs: {ids}").format(ids=list(invalid_group_ids))
                return JsonResponse({"result": False, "message": message})

        # 校验 roles ID 是否真实存在
        roles = kwargs.get("roles", [])
        if roles:
            valid_role_ids = set(Role.objects.filter(id__in=roles).values_list("id", flat=True))
            invalid_role_ids = set(roles) - valid_role_ids
            if invalid_role_ids:
                message = loader.get("error.invalid_role_ids", "Invalid role IDs: {ids}").format(ids=list(invalid_role_ids))
                return JsonResponse({"result": False, "message": message})

        with transaction.atomic():
            User.objects.create(
                username=kwargs["username"],
                display_name=kwargs["lastName"],
                email=kwargs["email"],
                disabled=False,
                locale=kwargs["locale"],
                timezone=kwargs["timezone"],
                group_list=groups,
                role_list=roles,
                temporary_pwd=kwargs.get("temporary_pwd", False),
            )
            if rules:
                add_rule = [UserRule(username=kwargs["username"], group_rule_id=i) for i in rules]
                UserRule.objects.bulk_create(add_rule, batch_size=100)

            # 记录操作日志
            log_operation(
                request,
                "create",
                "user",
                f"新增用户: {kwargs['username']} ({kwargs['lastName']})",
            )
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def reset_password(self, request):
        password = request.data.get("password")
        temporary_pwd = request.data.get("temporary", False)
        user_id = request.data.get("id")

        # 校验密码是否为空
        if not password:
            raise ValueError("密码不能为空")

        # 校验密码复杂度
        is_valid, error_message = PasswordValidator.validate_password(password)
        if not is_valid:
            raise ValueError(error_message)

        user = User.objects.get(id=user_id)
        user.password = make_password(password)
        user.temporary_pwd = temporary_pwd
        user.save()  # 使用save方法自动更新password_last_modified

        # 记录操作日志
        log_operation(request, "update", "user", f"重置用户密码: {user.username}")
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Delete User")
    def delete_user(self, request):
        user_ids = request.data.get("user_ids")
        users = User.objects.filter(id__in=user_ids)
        usernames = list(users.values_list("username", flat=True))

        # 收集需要删除的用户信息（id, username和domain）
        user_info_list = list(users.values("id", "username", "domain"))

        # 直接构造用户菜单缓存键删除（缓存键格式为 menus-user:{user_id}）
        menu_cache_keys = [f"menus-user:{user['id']}" for user in user_info_list]
        if menu_cache_keys:
            cache.delete_many(menu_cache_keys)

        # 批量删除用户相关的UserRule（避免N+1：使用Q对象组合条件）
        if user_info_list:
            user_rule_filter = Q()
            for user_info in user_info_list:
                user_rule_filter |= Q(username=user_info["username"], domain=user_info["domain"])
            UserRule.objects.filter(user_rule_filter).delete()

        # 删除用户
        users.delete()

        # 清除权限缓存（批量清除）
        if user_info_list:
            clear_users_permission_cache(user_info_list)

        # 记录操作日志
        log_operation(
            request,
            "delete",
            "user",
            f"批量删除用户: {', '.join(usernames)} (共{len(usernames)}个)",
        )
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def update_user(self, request):
        params = request.data
        pk = params.pop("user_id")
        rules = params.pop("rules", [])
        is_superuser = params.pop("is_superuser", False)
        if is_superuser:
            params["roles"] = [Role.objects.get(name="admin", app="").id]
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
            # 清除用户菜单缓存（缓存键格式为 menus-user:{user_id}）
            cache.delete(f"menus-user:{pk}")

            # 同步用户数据到CMDB
            CMDB().sync_display_fields(
                users=[
                    {
                        "id": pk,
                        "username": params["username"],
                        "display_name": params.get("lastName"),
                    }
                ]
            )
            # 记录操作日志
            log_operation(request, "update", "user", f"编辑用户: {params['username']}")

            # 清除权限缓存
            clear_user_permission_cache(params["username"])

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

        # 清除权限缓存
        clear_user_permission_cache(user.username, user.domain)

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

        # 清除权限缓存
        clear_user_permission_cache(user.username, user.domain)

        return JsonResponse({"result": True})
