from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import CustomMenuGroup
from apps.system_mgmt.serializers.custom_menu_group_serializer import CustomMenuGroupListSerializer, CustomMenuGroupSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class CustomMenuGroupFilter(FilterSet):
    """自定义菜单组筛选器"""

    app = filters.CharFilter(field_name="app", lookup_expr="exact")
    display_name = filters.CharFilter(field_name="display_name", lookup_expr="icontains")
    is_enabled = filters.CharFilter(method="filter_is_enabled")

    class Meta:
        model = CustomMenuGroup
        fields = ["app", "display_name", "is_enabled"]

    def filter_is_enabled(self, queryset, name, value):
        """
        筛选启用状态
        不传：返回全部
        传入 '0' 或 '1'：转换为布尔值后筛选
        """
        if value in ["0", "1"]:
            is_enabled = bool(int(value))
            return queryset.filter(is_enabled=is_enabled)
        return queryset


class CustomMenuGroupViewSet(MaintainerViewSet):
    """自定义菜单组视图集"""

    queryset = CustomMenuGroup.objects.all().order_by("app", "id")
    serializer_class = CustomMenuGroupSerializer
    filterset_class = CustomMenuGroupFilter

    def get_serializer_class(self):
        """根据不同操作返回不同的序列化器"""
        if self.action == "list":
            return CustomMenuGroupListSerializer
        return CustomMenuGroupSerializer

    @HasPermission("custom_menu_group_list-Add")
    def create(self, request, *args, **kwargs):
        """创建自定义菜单组"""
        response = super().create(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 201:
            menu_name = response.data.get("display_name", "")
            log_operation(request, "create", "menu", f"新增菜单: {menu_name}")

        return response

    @HasPermission("custom_menu_group_list-Edit")
    def update(self, request, *args, **kwargs):
        """更新自定义菜单组"""
        instance = self.get_object()

        # 检查是否为内置菜单组
        if instance.is_build_in:
            return JsonResponse({"result": False, "message": self.loader.get("error.cannot_modify_builtin_menu_group")}, status=403)

        response = super().update(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 200:
            menu_name = response.data.get("display_name", "")
            log_operation(request, "update", "menu", f"编辑菜单: {menu_name}")

        return response

    @HasPermission("custom_menu_group_list-Edit")
    def partial_update(self, request, *args, **kwargs):
        """部分更新自定义菜单组"""
        instance = self.get_object()

        # 检查是否为内置菜单组
        if instance.is_build_in:
            return JsonResponse({"result": False, "message": self.loader.get("error.cannot_modify_builtin_menu_group")}, status=403)

        return super().partial_update(request, *args, **kwargs)

    @HasPermission("custom_menu_group_list-Delete")
    def destroy(self, request, *args, **kwargs):
        """删除自定义菜单组"""
        instance = self.get_object()

        # 检查是否为内置菜单组
        if instance.is_build_in:
            return JsonResponse({"result": False, "message": self.loader.get("error.cannot_delete_builtin_menu_group")}, status=403)

        menu_name = instance.display_name
        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            log_operation(request, "delete", "menu", f"删除菜单: {menu_name}")

        return response

    @HasPermission("custom_menu_group_list-View")
    def list(self, request, *args, **kwargs):
        """列表查询"""
        return super().list(request, *args, **kwargs)

    @HasPermission("custom_menu_group_list-View")
    def retrieve(self, request, *args, **kwargs):
        """详情查询"""
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @HasPermission("custom_menu_group_list-Edit")
    def change_enable(self, request, pk=None):
        """
        切换菜单组启用状态
        请求参数: {"is_enabled": true/false}
        如果启用，会自动禁用同一 app 下其他已启用的菜单组
        """
        instance = self.get_object()
        is_enabled = request.data.get("is_enabled")

        if is_enabled is None:
            return JsonResponse({"result": False, "message": "缺少 is_enabled 参数"}, status=400)

        # 如果要启用
        if is_enabled:
            # 禁用同一 app 下其他已启用的菜单组
            CustomMenuGroup.objects.filter(app=instance.app, is_enabled=True).exclude(id=instance.id).update(is_enabled=False)

            instance.is_enabled = True
            instance.save()
            message = self.loader.get("success.menu_group_enabled")

            # 记录操作日志
            log_operation(request, "execute", "menu", f"启用菜单: {instance.display_name}")
        else:
            # 禁用当前菜单组
            instance.is_enabled = False
            instance.save()
            message = self.loader.get("success.menu_group_disabled")

        return JsonResponse({"result": True, "data": CustomMenuGroupSerializer(instance).data, "message": message})

    @action(detail=True, methods=["post"])
    @HasPermission("custom_menu_group_list-Add")
    def copy(self, request, pk=None):
        """
        复制菜单组
        请求参数: {"display_name": "新名称"}（可选）
        如果不传 display_name，则使用原名称 + _copy，如果重复则添加数字后缀
        """
        instance = self.get_object()

        # 获取新的 display_name
        new_display_name = request.data.get("display_name")
        menus = request.data.get("menus", [])

        if not new_display_name:
            # 生成带 _copy 后缀的名称
            base_name = f"{instance.display_name}_copy"
            new_display_name = base_name

            # 检查名称是否存在，如果存在则添加数字后缀
            counter = 0
            while CustomMenuGroup.objects.filter(app=instance.app, display_name=new_display_name).exists():
                new_display_name = f"{base_name}{counter}"
                counter += 1
        else:
            # 检查传入的名称是否已存在
            if CustomMenuGroup.objects.filter(app=instance.app, display_name=new_display_name).exists():
                return JsonResponse({"result": False, "message": f"应用 {instance.app} 下已存在名称为 {new_display_name} 的菜单组"}, status=400)

        if not menus:
            menus = instance.menus.copy()
        # 复制菜单组
        new_instance = CustomMenuGroup.objects.create(
            display_name=new_display_name,
            app=instance.app,
            is_enabled=False,  # 复制的菜单组默认不启用
            is_build_in=False,  # 复制的菜单组不是内置的
            menus=menus,
            description=instance.description,
            created_by=request.user.username if hasattr(request.user, "username") else "",
            updated_by=request.user.username if hasattr(request.user, "username") else "",
        )

        # 记录操作日志
        log_operation(request, "create", "menu", f"复制菜单: {instance.display_name} -> {new_display_name}")

        return JsonResponse({"result": True, "data": CustomMenuGroupSerializer(new_instance).data, "message": "菜单组复制成功"})

    @action(detail=False, methods=["get"])
    @HasPermission("custom_menu_group_list-View")
    def get_menus(self, request):
        """
        获取指定应用的启用菜单组的菜单树

        请求参数:
            app: 应用名称（必填）

        返回第一个启用的菜单组的 menus 字段和是否内置标识
        """
        app = request.GET.get("app")

        if not app:
            return JsonResponse({"result": False, "message": "缺少 app 参数"}, status=400)

        # 获取该应用下第一个启用的菜单组
        menu_group = CustomMenuGroup.objects.filter(app=app, is_enabled=True).first()

        if not menu_group:
            return JsonResponse({"result": False, "message": f"未找到应用 {app} 的启用菜单组"}, status=404)

        # 直接返回 menus 字段和是否内置标识，不做任何转换
        menus = menu_group.menus if isinstance(menu_group.menus, list) else []

        return JsonResponse({"result": True, "data": {"is_build_in": menu_group.is_build_in, "menus": menus}, "message": "success"})
