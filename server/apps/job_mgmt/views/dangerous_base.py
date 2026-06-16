"""高危条目（命令规则 / 路径）公共视图基类。

dangerous_rule / dangerous_path 两个 ViewSet 仅 model、serializer、权限串、
日志文案不同，本基类参数化这些差异，消除两段近乎雷同的 CRUD。

注意：``HasPermission`` 在类定义时绑定字面量权限串，无法下沉到基类，
因此子类仍需保留 ``@HasPermission`` 装饰的薄方法，方法体调用基类的
``*_with_log`` 实现。
"""

from rest_framework import status

from apps.core.utils.viewset_utils import AuthViewSet
from apps.system_mgmt.utils.operation_log_utils import log_operation


class BaseDangerousItemViewSet(AuthViewSet):
    """高危条目公共视图基类。

    子类需声明：

    - ``queryset`` / ``serializer_class`` / ``filterset_class`` / ``search_fields``
    - ``create_serializer_class`` / ``update_serializer_class``
    - ``dangerous_log_label``：日志文案，如 "危险规则" / "危险路径"
    - ``dangerous_name_field``：日志取名字段，如 "name" / "pattern"
    """

    ORGANIZATION_FIELD = "team"
    permission_key = "job"

    # 由子类提供
    create_serializer_class = None
    update_serializer_class = None
    dangerous_log_label = ""
    dangerous_name_field = "name"

    def get_serializer_class(self):
        if self.action == "create":
            return self.create_serializer_class
        if self.action in ("update", "partial_update"):
            return self.update_serializer_class
        return self.serializer_class

    def _resolve_item_name(self, response, request):
        """从响应体或请求体取条目名称，用于操作日志。"""
        if isinstance(response.data, dict) and response.data.get(self.dangerous_name_field):
            return response.data.get(self.dangerous_name_field)
        return request.data.get(self.dangerous_name_field, "")

    def create_with_log(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            name = self._resolve_item_name(response, request)
            log_operation(request, "create", "job", f"新增{self.dangerous_log_label}: {name}")
        return response

    def update_with_log(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            name = self._resolve_item_name(response, request)
            log_operation(request, "update", "job", f"编辑{self.dangerous_log_label}: {name}")
        return response

    def destroy_with_log(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT):
            name = getattr(instance, self.dangerous_name_field, "")
            log_operation(request, "delete", "job", f"删除{self.dangerous_log_label}: {name}")
        return response
