import re

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from rest_framework.decorators import action

try:
    # EE 增强判断：优先加载 enterprise 脱敏实现，缺失时回退到 CE 默认行为。
    from apps.system_mgmt.enterprise.sensitive_info import apply_sensitive_info_mask, apply_sensitive_info_mask_to_list
except (ImportError, ModuleNotFoundError):
    apply_sensitive_info_mask = None
    apply_sensitive_info_mask_to_list = None

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.permission_cache import clear_user_permission_cache, clear_users_permission_cache
from apps.rpc.cmdb import CMDB
from apps.system_mgmt.models import Group, Role, User, UserRule
from apps.system_mgmt.serializers.user_serializer import UserSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.utils.viewset_utils import ViewSetUtils


def _normalize_group_ids(groups):
    normalized = []
    invalid = []
    for group_id in groups or []:
        try:
            normalized.append(int(group_id))
        except (TypeError, ValueError):
            invalid.append(group_id)
    return normalized, invalid


def _validate_selected_groups(groups, loader):
    if not groups:
        return loader.get("error.group_selection_required", "At least one group must be selected")

    normalized_groups, invalid_ids = _normalize_group_ids(groups)
    group_queryset = Group.objects.filter(id__in=normalized_groups)
    group_map = {group.id: group for group in group_queryset}

    missing_group_ids = [group_id for group_id in normalized_groups if group_id not in group_map]
    all_invalid_ids = invalid_ids + missing_group_ids
    if all_invalid_ids:
        return loader.get("error.invalid_group_ids", "Invalid group IDs: {ids}").format(ids=all_invalid_ids)

    if not any(not group.is_virtual for group in group_map.values()):
        return loader.get("error.normal_group_required", "At least one normal group must be selected")

    return None


class UserViewSet(ViewSetUtils):
    """用户 ViewSet - 禁用所有内置 CRUD 接口，仅使用自定义 action

    权限校验：
    - 所有接口需要对应的 HasPermission 装饰器
    - user_all/user_id_all 限制为用户有权限的组成员
    - get_user_detail/update_user/delete_user/reset_password 校验目标用户属于有权限的组
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    # 仅允许 GET (actions), POST (actions)
    # 禁用所有内置 CRUD 方法
    http_method_names = ["get", "post", "options"]

    def _get_loader(self, request):
        """获取语言加载器"""
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        return LanguageLoader(app="system_mgmt", default_lang=locale)

    def _get_user_group_ids(self, user):
        """获取用户有权限的组ID集合"""
        if getattr(user, "is_superuser", False):
            return None  # superuser 返回 None 表示有权限访问所有组
        return {g["id"] for g in getattr(user, "group_list", [])}

    def _validate_target_user_permission(self, request, target_user):
        """校验当前用户是否有权限访问目标用户

        Args:
            request: 请求对象
            target_user: 目标用户对象（User model instance）

        Returns:
            tuple: (is_valid, error_response)
        """
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        target_group_ids = set(target_user.group_list or [])

        # 检查目标用户的组是否与当前用户的组有交集
        if not user_group_ids.intersection(target_group_ids):
            loader = self._get_loader(request)
            message = loader.get("error.no_permission_access_user", "无权访问该用户")
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _filter_users_by_accessible_groups(self, queryset, user):
        """按用户有权限的组筛选用户列表

        Args:
            queryset: 原始查询集
            user: 当前用户对象

        Returns:
            QuerySet: 筛选后的查询集
        """
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        # 构建查询条件：group_list 与用户有权限的组有交集
        query = Q()
        for group_id in user_group_ids:
            query |= Q(group_list__contains=group_id)
        return queryset.filter(query)

    def list(self, request, *args, **kwargs):
        """禁用内置 list 接口 - 使用 search_user_list action"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)

    def retrieve(self, request, *args, **kwargs):
        """禁用内置 retrieve 接口 - 使用 get_user_detail action"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)

    def create(self, request, *args, **kwargs):
        """禁用内置 create 接口 - 使用 create_user action"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)

    def update(self, request, *args, **kwargs):
        """禁用内置 update 接口 - 使用 update_user action"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)

    def partial_update(self, request, *args, **kwargs):
        """禁用内置 partial_update 接口 - 使用 update_user action"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)

    def destroy(self, request, *args, **kwargs):
        """禁用内置 destroy 接口 - 使用 delete_user action"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)

    @staticmethod
    def _is_valid_phone(phone):
        if phone is None:
            return True
        if not isinstance(phone, str):
            return False

        normalized_phone = phone.strip()
        if not normalized_phone:
            return True
        if re.fullmatch(r"[0-9+\-()\s]+", normalized_phone) is None:
            return False

        digits_only = re.sub(r"[+\-()\s]", "", normalized_phone)
        return digits_only.isdigit() and 7 <= len(digits_only) <= 15

    @staticmethod
    def _mask_user_payload(data, request):
        # EE 增强判断：有 enterprise 脱敏实现时按授权结果处理；缺失时保持 CE 原始返回。
        if apply_sensitive_info_mask is None:
            return data
        return apply_sensitive_info_mask(data, getattr(request, "user", None))

    @staticmethod
    def _mask_user_payload_list(data, request):
        # EE 增强判断：列表查询同样优先走 enterprise 脱敏实现；缺失时回退到 CE 原始数据。
        if apply_sensitive_info_mask_to_list is None:
            return data
        return apply_sensitive_info_mask_to_list(data, getattr(request, "user", None))

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

        data = self._mask_user_payload_list(data, request)

        return JsonResponse({"result": True, "data": {"count": total, "users": data}})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def user_all(self, request):
        queryset = User.objects.all()
        # 按用户有权限的组筛选
        queryset = self._filter_users_by_accessible_groups(queryset, request.user)
        data = queryset.values(*User.display_fields())
        return JsonResponse({"result": True, "data": self._mask_user_payload_list(list(data), request)})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def user_id_all(self, request):
        queryset = User.objects.all()
        # 按用户有权限的组筛选
        queryset = self._filter_users_by_accessible_groups(queryset, request.user)
        data = queryset.values("id", "display_name", "username")
        return JsonResponse({"result": True, "data": list(data)})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-View")
    def get_user_detail(self, request):
        pk = request.data.get("user_id")
        user = User.objects.get(id=pk)

        # 校验当前用户是否有权限访问目标用户
        is_valid, error_response = self._validate_target_user_permission(request, user)
        if not is_valid:
            return error_response

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
            group_id = rule["group_rule__group_id"]
            app = rule["group_rule__app"]
            group_rule_map.setdefault(group_id, {}).setdefault(app, []).append(rule["group_rule_id"])
        for i in groups:
            i["rules"] = group_rule_map.get(i["id"], {})
        data["groups"] = groups

        group_role_ids = []
        if user.group_list:
            user_groups = Group.objects.filter(id__in=user.group_list).prefetch_related("roles")
            group_role_id_set = set()
            for g in user_groups:
                for role in g.roles.all():
                    group_role_id_set.add(role.id)
            group_role_ids = list(group_role_id_set)
        data["group_role_ids"] = group_role_ids

        data = self._mask_user_payload(data, request)

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

        groups = kwargs.get("groups", [])
        group_validation_error = _validate_selected_groups(groups, loader)
        if group_validation_error:
            return JsonResponse({"result": False, "message": group_validation_error})
        groups, _ = _normalize_group_ids(groups)

        # 校验 roles ID 是否真实存在
        roles = kwargs.get("roles", [])
        if roles:
            valid_role_ids = set(Role.objects.filter(id__in=roles).values_list("id", flat=True))
            invalid_role_ids = set(roles) - valid_role_ids
            if invalid_role_ids:
                message = loader.get("error.invalid_role_ids", "Invalid role IDs: {ids}").format(ids=list(invalid_role_ids))
                return JsonResponse({"result": False, "message": message})
        if not self._is_valid_phone(kwargs.get("phone")):
            return JsonResponse({"result": False, "message": "手机号格式不正确"})
        is_superuser = kwargs.pop("is_superuser", False)
        if is_superuser:
            roles = [Role.objects.get(name="admin", app="").id]
        with transaction.atomic():
            User.objects.create(
                username=kwargs["username"],
                display_name=kwargs["lastName"],
                email=kwargs["email"],
                phone=kwargs.get("phone"),
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
            log_operation(request, "create", "user", f"新增用户: {kwargs['username']} ({kwargs['lastName']})")
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

        # 校验当前用户是否有权限访问目标用户
        is_valid, error_response = self._validate_target_user_permission(request, user)
        if not is_valid:
            return error_response

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

        # 校验当前用户是否有权限访问所有目标用户
        for user in users:
            is_valid, error_response = self._validate_target_user_permission(request, user)
            if not is_valid:
                return error_response

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
        log_operation(request, "delete", "user", f"批量删除用户: {', '.join(usernames)} (共{len(usernames)}个)")
        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit User")
    def update_user(self, request):
        params = request.data
        pk = params.pop("user_id")
        rules = params.pop("rules", [])
        locale = getattr(request.user, "locale", "en") if hasattr(request, "user") else "en"
        loader = LanguageLoader(app="system_mgmt", default_lang=locale)

        # 获取目标用户并校验权限
        target_user = User.objects.get(id=pk)
        is_valid, error_response = self._validate_target_user_permission(request, target_user)
        if not is_valid:
            return error_response

        groups = params.get("groups", [])
        group_validation_error = _validate_selected_groups(groups, loader)
        if group_validation_error:
            return JsonResponse({"result": False, "message": group_validation_error})
        groups, _ = _normalize_group_ids(groups)
        params["groups"] = groups
        is_superuser = params.pop("is_superuser", False)
        admin_role_id = Role.objects.get(name="admin", app="").id
        if not self._is_valid_phone(params.get("phone")):
            return JsonResponse({"result": False, "message": "手机号格式不正确"})
        if is_superuser:
            params["roles"] = [admin_role_id]
        else:
            role_ids = params.get("roles") or []
            params["roles"] = [role_id for role_id in role_ids if role_id != admin_role_id]
        with transaction.atomic():
            # 删除旧的规则
            UserRule.objects.filter(username=params["username"]).delete()
            # 更新用户信息
            if rules:
                add_rule = [UserRule(username=params["username"], group_rule_id=i) for i in rules]
                UserRule.objects.bulk_create(add_rule, batch_size=100)
            update_fields = {
                "display_name": params.get("lastName"),
                "locale": params.get("locale"),
                "timezone": params.get("timezone"),
                "group_list": params.get("groups"),
                "role_list": params.get("roles"),
            }
            if "email" in params:
                update_fields["email"] = params["email"]
            if "phone" in params:
                update_fields["phone"] = params["phone"]

            User.objects.filter(id=pk).update(**update_fields)
            # 清除用户菜单缓存（缓存键格式为 menus-user:{user_id}）
            cache.delete(f"menus-user:{pk}")

            # 同步用户数据到 CMDB
            try:
                CMDB().sync_display_fields(users=[{"id": pk, "username": params["username"], "display_name": params.get("lastName")}])
            except Exception as e:
                logger.exception(e)
            # 记录操作日志
            log_operation(request, "update", "user", f"编辑用户: {params['username']}")

            # 清除权限缓存
            clear_user_permission_cache(params["username"], params.get("domain", "domain.com"))

        return JsonResponse({"result": True})
