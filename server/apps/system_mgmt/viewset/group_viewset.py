from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from rest_framework.decorators import action
from dataclasses import asdict

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.rpc.cmdb import CMDB
from apps.system_mgmt.models import Group, User, UserSyncSource
from apps.system_mgmt.serializers.group_serializer import GroupSerializer
from apps.system_mgmt.services.archived_group_query import ArchivedGroupQuery
from apps.system_mgmt.services.group_archive_service import GroupArchiveService
from apps.system_mgmt.utils.group_filter_mixin import get_user_group_ids
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.viewset_utils import ViewSetUtils


class GroupViewSet(LanguageViewSet, ViewSetUtils):
    """组织 ViewSet - 禁用所有内置 CRUD 接口，仅使用自定义 action

    权限校验：
    - 所有接口需要对应的 HasPermission 装饰器
    - get_detail/get_group_detail_with_roles 校验用户是否有权限访问指定组
    """

    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    # 仅允许 GET (actions), POST (actions)
    # 禁用所有内置 CRUD 方法
    http_method_names = ["get", "post", "options"]

    def _loader(self, request):
        return getattr(self, "loader", None) or LanguageLoader(
            app="system_mgmt", default_lang=getattr(getattr(request, "user", None), "locale", "en") or "en"
        )

    def _require_group_id(self, request):
        raw = request.data.get("id") if hasattr(request.data, "get") else None
        try:
            group_id = int(raw)
        except (TypeError, ValueError):
            message = self._loader(request).get("error.invalid_group_id")
            return None, JsonResponse({"result": False, "message": message}, status=400)
        if group_id <= 0:
            message = self._loader(request).get("error.invalid_group_id")
            return None, JsonResponse({"result": False, "message": message}, status=400)
        return group_id, None

    @staticmethod
    def _json_archive_result(result: dict):
        body = dict(result)
        if body.get("result"):
            body.pop("http_status", None)
            return JsonResponse(body)
        status = int(body.pop("http_status", 400) or 400)
        return JsonResponse(body, status=status)

    def _get_user_group_ids(self, user):
        """获取用户有权限的组ID集合"""
        return get_user_group_ids(user)

    def _validate_group_permission(self, request, group_id):
        """校验用户是否有权限访问指定组

        Args:
            request: 请求对象
            group_id: 要校验的组ID

        Returns:
            tuple: (is_valid, error_response)
        """
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        if group_id not in user_group_ids:
            message = self._loader(request).get("error.no_permission_access_group")
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def list(self, request, *args, **kwargs):
        """禁用内置 list 接口 - 使用 search_group_list action"""
        return JsonResponse({"result": False, "message": self._loader(request).get("error.api_not_enabled")}, status=405)

    def retrieve(self, request, *args, **kwargs):
        """禁用内置 retrieve 接口 - 使用 get_detail action"""
        return JsonResponse({"result": False, "message": self._loader(request).get("error.api_not_enabled")}, status=405)

    def create(self, request, *args, **kwargs):
        """禁用内置 create 接口 - 使用 create_group action"""
        return JsonResponse({"result": False, "message": self._loader(request).get("error.api_not_enabled")}, status=405)

    def update(self, request, *args, **kwargs):
        """禁用内置 update 接口 - 使用 update_group action"""
        return JsonResponse({"result": False, "message": self._loader(request).get("error.api_not_enabled")}, status=405)

    def partial_update(self, request, *args, **kwargs):
        """禁用内置 partial_update 接口 - 使用 update_group action"""
        return JsonResponse({"result": False, "message": self._loader(request).get("error.api_not_enabled")}, status=405)

    def destroy(self, request, *args, **kwargs):
        """禁用内置 destroy 接口 - 使用 delete_groups action"""
        return JsonResponse({"result": False, "message": self._loader(request).get("error.api_not_enabled")}, status=405)

    def _get_active_group_or_error(self, request, group_id, *, prefetch_roles=False):
        queryset = GroupUtils.active_queryset()
        if prefetch_roles:
            queryset = queryset.prefetch_related("roles")
        try:
            return queryset.get(id=group_id), None
        except Group.DoesNotExist:
            message = self._loader(request).get("error.group_not_exist")
            return None, JsonResponse({"result": False, "message": message}, status=404)

    @action(detail=False, methods=["GET"])
    def get_teams(self, request):
        raw_groups = request.user.group_list or []
        ordered_ids = []
        items_by_id = {}
        for item in raw_groups:
            group_id = item.get("id") if isinstance(item, dict) else item
            try:
                group_id = int(group_id)
            except (TypeError, ValueError):
                continue
            if group_id in items_by_id:
                continue
            ordered_ids.append(group_id)
            items_by_id[group_id] = item
        active_ids = set(GroupUtils.active_queryset(id__in=ordered_ids).values_list("id", flat=True))
        data = [items_by_id[group_id] for group_id in ordered_ids if group_id in active_ids]
        return JsonResponse({"result": True, "data": data})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def search_group_list(self, request):
        # 构建嵌套组结构（仅活动组织）
        groups = [i["id"] for i in request.user.group_list]
        queryset = GroupUtils.active_queryset().prefetch_related("roles")
        if not request.user.is_superuser:
            queryset = queryset.filter(id__in=groups).exclude(name="OpsPilotGuest", parent_id=0)
        groups_data = GroupUtils.build_group_tree(queryset, request.user.is_superuser, groups)
        return JsonResponse({"result": True, "data": groups_data})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def get_detail(self, request):
        group_id = int(request.GET["group_id"])
        # 校验用户是否有权限访问该组
        is_valid, error_response = self._validate_group_permission(request, group_id)
        if not is_valid:
            return error_response

        group, error_response = self._get_active_group_or_error(request, group_id)
        if error_response is not None:
            return error_response
        return JsonResponse(
            {"result": True, "data": {"name": group.name, "id": group.id, "parent_id": group.parent_id, "is_virtual": group.is_virtual}}
        )

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Add Group")
    def create_group(self, request):
        params = request.data
        parent_id = params.get("parent_group_id") or 0
        group_name = params.get("group_name")

        # 权限校验
        if not self._check_create_permission(request.user, parent_id):
            message = self.loader.get("error.no_permission_create_group")
            return JsonResponse({"result": False, "message": message})
        if parent_id and Group.objects.filter(id=parent_id, is_delete=True).exists():
            return JsonResponse(
                {"result": False, "message": self._loader(request).get("error.cannot_create_under_archived_group")}
            )
        if parent_id and Group.objects.filter(id=parent_id, sync_source__isnull=False).exists():
            return JsonResponse({"result": False, "message": self._loader(request).get("error.synced_group_child_creation_forbidden")})

        # 虚拟组校验并确定新组的虚拟属性
        is_virtual, error_response = self._validate_virtual_group_creation(parent_id, params.get("is_virtual", False))
        if error_response:
            return error_response

        # 创建组
        group = Group.objects.create(parent_id=parent_id, name=group_name, is_virtual=is_virtual)

        # 记录操作日志
        log_operation(request, "create", "system-manager", f"新增组织: {group_name}")

        # 返回结果
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "id": group.id,
                    "name": group.name,
                    "parent_id": group.parent_id,
                    "is_virtual": group.is_virtual,
                    "subGroupCount": 0,
                    "subGroups": [],
                },
            }
        )

    @staticmethod
    def _check_create_permission(user, parent_id):
        """检查用户是否有权限在指定父组下创建子组

        Args:
            user: 当前用户
            parent_id: 父组ID

        Returns:
            bool: 是否有权限
        """
        if user.is_superuser:
            return True

        if parent_id == 0:
            return True

        user_group_ids = [i["id"] for i in user.group_list]
        return parent_id in user_group_ids

    def _validate_virtual_group_creation(self, parent_id, request_is_virtual):
        """校验虚拟组创建规则并确定新组的虚拟属性

        Args:
            parent_id: 父组ID
            request_is_virtual: 请求中的is_virtual参数

        Returns:
            tuple: (is_virtual, error_response)
                  is_virtual: 新组是否为虚拟组
                  error_response: 错误响应，如果为None表示校验通过
        """
        # 顶级组：禁止手动创建虚拟组
        if parent_id == 0:
            if request_is_virtual:
                message = self.loader.get("error.cannot_create_top_level_virtual_group")
                return False, JsonResponse({"result": False, "message": message})
            return False, None

        # 非顶级组：检查父组
        try:
            parent_group = Group.objects.get(id=parent_id)
        except Group.DoesNotExist:
            message = self.loader.get("error.parent_group_not_found")
            return False, JsonResponse({"result": False, "message": message})

        # 父组不是虚拟组，子组也不是虚拟组
        if not parent_group.is_virtual:
            return False, None

        # 父组是虚拟组，检查是否为顶级虚拟组
        if parent_group.parent_id != 0:
            # 父组是虚拟子组，禁止创建
            message = self.loader.get("error.cannot_create_under_virtual_subgroup")
            return False, JsonResponse({"result": False, "message": message})

        # 父组是顶级虚拟组，子组继承虚拟属性
        return True, None

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Edit Group")
    def update_group(self, request):
        obj, error_response = self._get_active_group_or_error(request, request.data.get("group_id"))
        if error_response is not None:
            return error_response
        role_ids = request.data.get("role_ids", [])
        group_name = request.data.get("group_name")
        if obj.name == "Default" and obj.parent_id == 0:
            message = self.loader.get("error.default_group_cannot_modify")
            return JsonResponse({"result": False, "message": message})
        if obj.sync_source_id and obj.parent_id != 0 and group_name != obj.name:
            return JsonResponse({"result": False, "message": self._loader(request).get("error.synced_child_group_name_immutable")})
        if not request.user.is_superuser:
            groups = [i["id"] for i in request.user.group_list]
            if request.data.get("group_id") not in groups:
                message = self.loader.get("error.no_permission_edit_group")
                return JsonResponse({"result": False, "message": message})

        # 准备更新的字段
        update_fields = {"name": group_name}

        # 如果请求中包含 is_virtual 字段，则更新
        if "is_virtual" in request.data:
            update_fields["is_virtual"] = request.data.get("is_virtual", False)

        # 如果请求中包含 allow_inherit_roles 字段，则更新
        if "allow_inherit_roles" in request.data:
            update_fields["allow_inherit_roles"] = request.data.get("allow_inherit_roles", False)

        with transaction.atomic():
            Group.objects.filter(id=request.data.get("group_id")).update(**update_fields)
            if obj.sync_source_id and obj.parent_id == 0 and group_name != obj.name:
                UserSyncSource.objects.filter(id=obj.sync_source_id).update(root_group_name=group_name)

            # 更新组的角色
            if isinstance(role_ids, list):
                obj.roles.set(role_ids)
                # 清除该组织及其后代组织中所有用户的权限缓存和菜单缓存
                group_id = request.data.get("group_id")
                affected_group_ids = GroupUtils.get_group_with_descendants(group_id)
                affected_users_query = Q()
                for affected_group_id in affected_group_ids:
                    affected_users_query |= Q(group_list__contains=int(affected_group_id))
                affected_users = User.objects.filter(affected_users_query).values("id", "username", "domain")
                affected_users_list = list(affected_users)
                if affected_users_list:
                    clear_users_permission_cache(affected_users_list)
                    menu_cache_keys = [f"menus-user:{user['id']}" for user in affected_users_list]
                    transaction.on_commit(lambda: cache.delete_many(menu_cache_keys), robust=True)

        # 同步组织数据到CMDB
        try:
            CMDB().sync_display_fields(organizations=[{"id": request.data.get("group_id"), "name": group_name}])
        except Exception as e:
            logger.exception(e)

        # 记录操作日志
        log_operation(request, "update", "system-manager", f"编辑组织: {group_name}")

        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Delete Group")
    def delete_groups(self, request):
        group_id, error_response = self._require_group_id(request)
        if error_response is not None:
            return error_response
        result = GroupArchiveService.archive_subtree(actor=request.user, group_id=group_id, request=request)
        return self._json_archive_result(result)

    def _parse_archived_list_page(self, request):
        loader = self._loader(request)
        try:
            page = int(request.GET.get("page", 1))
            page_size = int(request.GET.get("page_size", 50))
        except (TypeError, ValueError):
            return None, JsonResponse({"result": False, "message": loader.get("error.invalid_pagination")}, status=400)
        if page < 1 or page_size < 1 or page_size > 100:
            return None, JsonResponse({"result": False, "message": loader.get("error.invalid_pagination")}, status=400)
        return (page, page_size), None

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-Delete Group")
    def list_archived_groups(self, request):
        pagination, error_response = self._parse_archived_list_page(request)
        if error_response is not None:
            return error_response
        page, page_size = pagination
        listed = ArchivedGroupQuery.list_archived_roots(actor=request.user, page=page, page_size=page_size)
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "items": [asdict(item) for item in listed.items],
                    "count": listed.count,
                    "page": listed.page,
                    "page_size": listed.page_size,
                },
            }
        )

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Delete Group")
    def restore_archived_groups(self, request):
        group_id, error_response = self._require_group_id(request)
        if error_response is not None:
            return error_response
        result = GroupArchiveService.restore_archived_root(
            actor=request.user, group_id=group_id, request=request
        )
        return self._json_archive_result(result)

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Delete Group")
    def permanently_delete_archived_groups(self, request):
        group_id, error_response = self._require_group_id(request)
        if error_response is not None:
            return error_response
        result = GroupArchiveService.permanently_delete_archived_root(
            actor=request.user, group_id=group_id, request=request
        )
        return self._json_archive_result(result)

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-View")
    def get_group_detail_with_roles(self, request):
        group_id = request.data.get("group_id")

        # 校验用户是否有权限访问该组
        is_valid, error_response = self._validate_group_permission(request, int(group_id))
        if not is_valid:
            return error_response

        group, error_response = self._get_active_group_or_error(request, group_id, prefetch_roles=True)
        if error_response is not None:
            return error_response

        own_role_ids = list(group.roles.values_list("id", flat=True))

        inherited_role_ids = []
        inherited_role_source_map = {}
        if group.parent_id:
            # 与 NATS 继承链一致：归档父不进入角色继承投影
            all_groups = {
                g.id: g for g in GroupUtils.active_queryset().prefetch_related("roles")
            }
            visited = set()
            current_parent_id = group.parent_id
            while current_parent_id and current_parent_id not in visited:
                visited.add(current_parent_id)
                parent = all_groups.get(current_parent_id)
                if not parent or not parent.allow_inherit_roles:
                    break
                for role in parent.roles.all():
                    if role.id not in inherited_role_ids:
                        inherited_role_ids.append(role.id)
                        inherited_role_source_map[str(role.id)] = parent.name
                current_parent_id = parent.parent_id or 0

        return JsonResponse(
            {
                "result": True,
                "data": {
                    "group_id": group.id,
                    "group_name": group.name,
                    "allow_inherit_roles": group.allow_inherit_roles,
                    "own_role_ids": own_role_ids,
                    "inherited_role_ids": inherited_role_ids,
                    "inherited_role_source": ", ".join(dict.fromkeys(inherited_role_source_map.values())),
                    "inherited_role_source_map": inherited_role_source_map,
                },
            }
        )

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-View")
    def batch_get_group_detail_with_roles(self, request):
        """批量获取多个组织的角色详情，避免前端逐个请求"""
        group_ids = request.data.get("group_ids", [])
        if not group_ids or not isinstance(group_ids, list):
            return JsonResponse({"result": False, "message": self._loader(request).get("error.group_ids_list_required")}, status=400)

        # 活动组织投影：继承链与目标组织均排除 is_delete=True（与 NATS 一致）
        all_groups = {g.id: g for g in GroupUtils.active_queryset().prefetch_related("roles")}

        # 对象级权限收口：非超管仅可读取自身有权访问的组织，未授权 group_id 直接跳过。
        # 与单组织接口 get_group_detail_with_roles 的 _validate_group_permission 同一套校验，
        # 避免批量入口绕过对象级权限泄露跨组织角色配置。superuser 返回 None 表示放行全部。
        authorized_group_ids = self._get_user_group_ids(request.user)

        results = []
        for gid in group_ids:
            gid = int(gid)
            if authorized_group_ids is not None and gid not in authorized_group_ids:
                continue
            group = all_groups.get(gid)
            if not group:
                continue

            own_role_ids = list(group.roles.values_list("id", flat=True))

            inherited_role_ids = []
            inherited_role_source_map = {}
            if group.parent_id:
                visited = set()
                current_parent_id = group.parent_id
                while current_parent_id and current_parent_id not in visited:
                    visited.add(current_parent_id)
                    parent = all_groups.get(current_parent_id)
                    if not parent or not parent.allow_inherit_roles:
                        break
                    for role in parent.roles.all():
                        if role.id not in inherited_role_ids:
                            inherited_role_ids.append(role.id)
                            inherited_role_source_map[str(role.id)] = parent.name
                    current_parent_id = parent.parent_id or 0

            results.append(
                {
                    "group_id": group.id,
                    "group_name": group.name,
                    "allow_inherit_roles": group.allow_inherit_roles,
                    "own_role_ids": own_role_ids,
                    "inherited_role_ids": inherited_role_ids,
                    "inherited_role_source": ", ".join(dict.fromkeys(inherited_role_source_map.values())),
                    "inherited_role_source_map": inherited_role_source_map,
                }
            )

        return JsonResponse({"result": True, "data": results})
