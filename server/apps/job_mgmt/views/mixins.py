"""ViewSet 通用 mixin。

抽取 :mod:`views` 中重复出现的批量删除、团队解析等模式，
让子 ViewSet 只声明必要的差异（serializer / permission / 日志标签 / 钩子）。
"""

from typing import Optional, Tuple, Type

from rest_framework import serializers, status
from rest_framework.response import Response

from apps.system_mgmt.utils.operation_log_utils import log_operation


class TeamResolveMixin:
    """从请求解析用户归属团队（API-Secret 或会话 cookie）。

    供开放接口（``OpenFileUploadView`` / ``OpenFileDeleteView``，APIView + API-Secret 鉴权）
    复用：按团队归属上传文件、校验删除权限。

    解析优先级：

    - API-Secret 认证（``request.api_pass`` 为真）：直接用 ``group_list[0]``
      （即 ``UserAPISecret.team``）；
    - 会话认证：优先 ``current_team`` cookie（需校验用户有权访问），否则回退 ``group_list[0]``。

    注意：``DistributionFileViewSet`` 走 ``AuthViewSet._validate_current_team_permission``
    （仅会话、强制 current_team、命中即抛 ``PermissionDenied``），语义比本 mixin 更严格，
    故不复用本 mixin —— 强行统一会放宽其鉴权，属对外行为变更。
    """

    def resolve_user_team(self, request) -> Tuple[Optional[int], Optional[str]]:
        """解析用户团队。

        Returns:
            ``(team_id, None)`` 成功；``(None, error_message)`` 失败。
        """
        group_list = getattr(request.user, "group_list", [])

        # 提取 group_ids（兼容 [int] 和 [{"id": int}] 两种格式）
        user_group_ids = []
        for g in group_list:
            if isinstance(g, dict):
                user_group_ids.append(g["id"])
            else:
                user_group_ids.append(g)

        if not user_group_ids:
            return None, "用户未关联团队"

        # API Secret 认证：直接使用 group_list[0]（即 UserAPISecret.team）
        if getattr(request, "api_pass", False):
            return user_group_ids[0], None

        # 会话认证：优先使用 current_team cookie
        current_team_str = request.COOKIES.get("current_team")
        if current_team_str:
            try:
                current_team = int(current_team_str)
            except (TypeError, ValueError):
                return None, "current_team 参数非法"

            # 校验用户是否有权限访问该 team
            if not getattr(request.user, "is_superuser", False):
                if current_team not in user_group_ids:
                    return None, "无权访问该团队数据"

            return current_team, None

        # 没有 current_team，使用 group_list[0]
        return user_group_ids[0], None


class BatchDeleteMixin:
    """统一的批量删除实现助手。

    使用方式（保留子类对 ``@action`` / ``@HasPermission`` 的精确控制）：

    .. code-block:: python

        class TargetViewSet(BatchDeleteMixin, AuthViewSet):
            batch_delete_serializer_class = TargetBatchDeleteSerializer
            batch_delete_log_label = "目标"

            @action(detail=False, methods=["post"])
            @HasPermission("target-Delete")
            def batch_delete(self, request):
                return self.perform_batch_delete(request)

    子类可覆盖：

    - :meth:`pre_batch_delete` 做删除前清理（如 MinIO 文件、PeriodicTask）；
    - :meth:`get_batch_delete_queryset` 自定义删除范围（默认按 ViewSet
      ``filter_queryset`` 限定鉴权范围）。
    """

    batch_delete_serializer_class: Optional[Type[serializers.Serializer]] = None
    batch_delete_log_label: str = ""

    def pre_batch_delete(self, instances):
        """删除前钩子，默认 no-op。子类可清理外部资源。"""
        return None

    def get_batch_delete_queryset(self, ids):
        """默认基于 ViewSet 的 ``filter_queryset`` 限定权限范围。"""
        queryset = self.filter_queryset(self.get_queryset())
        return queryset.filter(id__in=ids)

    def perform_batch_delete(self, request) -> Response:
        """执行批量删除的实际逻辑。子类的 ``@action`` 方法内调用。"""
        serializer_class = self.batch_delete_serializer_class
        if serializer_class is None:
            raise NotImplementedError(f"{type(self).__name__} 使用 BatchDeleteMixin 时必须声明 batch_delete_serializer_class")
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]

        instances = self.get_batch_delete_queryset(ids)
        self.pre_batch_delete(instances)

        deleted_count, _ = instances.delete()
        response = Response({"deleted_count": deleted_count}, status=status.HTTP_200_OK)
        if response.status_code == status.HTTP_200_OK and self.batch_delete_log_label:
            log_operation(request, "delete", "job", f"批量删除{self.batch_delete_log_label}: (共{deleted_count}个)")
        return response
