from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.serializers.group_serializer import GroupSerializer
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.system_mgmt.utils.viewset_utils import ViewSetUtils


class GroupViewSet(LanguageViewSet, ViewSetUtils):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def search_group_list(self, request):
        # 构建嵌套组结构
        groups = [i["id"] for i in request.user.group_list]
        queryset = Group.objects.prefetch_related("roles").all()
        if not request.user.is_superuser:
            queryset = queryset.filter(id__in=groups).exclude(name="OpsPilotGuest", parent_id=0)
        groups_data = GroupUtils.build_group_tree(queryset, request.user.is_superuser, groups)
        return JsonResponse({"result": True, "data": groups_data})

    @action(detail=False, methods=["GET"])
    @HasPermission("user_group-View")
    def get_detail(self, request):
        group = Group.objects.get(id=request.GET["group_id"])
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "name": group.name,
                    "id": group.id,
                    "parent_id": group.parent_id,
                    "is_virtual": group.is_virtual,
                },
            }
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

        # 虚拟组校验并确定新组的虚拟属性
        is_virtual, error_response = self._validate_virtual_group_creation(parent_id, params.get("is_virtual", False))
        if error_response:
            return error_response

        # 创建组
        group = Group.objects.create(parent_id=parent_id, name=group_name, is_virtual=is_virtual)

        # 记录操作日志
        log_operation(request, "create", "group", f"新增组织: {group_name}")

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
        obj = Group.objects.get(id=request.data.get("group_id"))
        role_ids = request.data.get("role_ids", [])
        if obj.name == "Default" and obj.parent_id == 0:
            message = self.loader.get("error.default_group_cannot_modify")
            return JsonResponse({"result": False, "message": message})
        if not request.user.is_superuser:
            groups = [i["id"] for i in request.user.group_list]
            if request.data.get("group_id") not in groups:
                message = self.loader.get("error.no_permission_edit_group")
                return JsonResponse({"result": False, "message": message})

        # 准备更新的字段
        update_fields = {"name": request.data.get("group_name")}

        # 如果请求中包含 is_virtual 字段，则更新
        if "is_virtual" in request.data:
            update_fields["is_virtual"] = request.data.get("is_virtual", False)

        Group.objects.filter(id=request.data.get("group_id")).update(**update_fields)

        # 更新组的角色
        if isinstance(role_ids, list):
            obj.roles.set(role_ids)

        # 记录操作日志
        log_operation(request, "update", "group", f"编辑组织: {request.data.get('group_name')}")

        return JsonResponse({"result": True})

    @action(detail=False, methods=["POST"])
    @HasPermission("user_group-Delete Group")
    def delete_groups(self, request):
        kwargs = request.data
        group_id = int(kwargs["id"])
        obj = Group.objects.get(id=group_id)
        if obj.name == "Default" and obj.parent_id == 0:
            message = self.loader.get("error.default_group_cannot_delete")
            return JsonResponse({"result": False, "message": message})
        if obj.is_virtual and obj.parent_id == 0:
            message = self.loader.get("error.default_group_cannot_delete")
            return JsonResponse({"result": False, "message": message})
        if not request.user.is_superuser:
            groups = [i["id"] for i in request.user.group_list]
            if group_id not in groups:
                message = self.loader.get("error.no_permission_delete_group")
                return JsonResponse({"result": False, "message": message})
        # 一次性获取所有组
        all_groups = Group.objects.all().values("id", "parent_id")

        # 构建父子关系映射
        child_map = {}
        for group in all_groups:
            parent_id = group["parent_id"]
            if parent_id not in child_map:
                child_map[parent_id] = []
            child_map[parent_id].append(group["id"])

        # 收集所有需要删除的组ID(当前组及其所有子组)
        groups_to_delete = []

        def collect_groups_to_delete(parent_id):
            groups_to_delete.append(parent_id)
            # 查找所有子组(从内存映射中)
            if parent_id in child_map:
                for child_id in child_map[parent_id]:
                    collect_groups_to_delete(child_id)

        # 开始收集
        collect_groups_to_delete(group_id)

        # 一次性检查这些组中是否有用户
        users = User.objects.filter(group_list__overlap=groups_to_delete).exists()
        if users:
            message = self.loader.get("error.group_has_users_remove_first")
            return JsonResponse({"result": False, "message": message})

        # 删除所有收集到的组
        Group.objects.filter(id__in=groups_to_delete).delete()

        # 记录操作日志
        log_operation(request, "delete", "group", f"删除组织: {obj.name} (包含{len(groups_to_delete)}个子组)")
        return JsonResponse({"result": True})
