from django.http import JsonResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.console_mgmt.models import Notification
from apps.console_mgmt.serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """通知消息视图集"""

    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        """获取通知列表，按时间倒序"""
        queryset = super().get_queryset()

        # 支持按模块过滤
        app_module = self.request.query_params.get("app_module")
        if app_module:
            queryset = queryset.filter(app_module=app_module)

        # 支持查询未读消息
        unread_only = self.request.query_params.get("unread_only")
        if unread_only is not None and unread_only.lower() == "true":
            queryset = queryset.filter(is_read=False)

        return queryset.order_by("-notification_time")

    def create(self, request, *args, **kwargs):
        """禁用创建接口，通过 RPC 创建"""
        return Response({"detail": "请使用 RPC 接口创建通知"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def update(self, request, *args, **kwargs):
        """禁用完整更新"""
        return Response({"detail": "不支持完整更新"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        """禁用部分更新，使用自定义的 mark_as_read 接口"""
        return Response({"detail": "请使用 mark_as_read 接口标记已读"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(methods=["post"], detail=True)
    def mark_as_read(self, request, pk=None):
        """
        标记通知为已读
        只允许从未读改为已读，不允许改回未读
        """
        notification = self.get_object()

        if notification.is_read:
            return JsonResponse({"result": True, "message": "该通知已是已读状态"})

        notification.mark_as_read()
        return JsonResponse({"result": True, "message": "标记已读成功"})

    @action(methods=["post"], detail=False)
    def mark_all_as_read(self, request):
        """批量标记所有未读通知为已读"""
        updated_count = Notification.objects.filter(is_read=False).update(is_read=True)
        return JsonResponse({"result": True, "message": f"已标记 {updated_count} 条通知为已读"})

    @action(methods=["post"], detail=False)
    def mark_batch_as_read(self, request):
        """批量标记指定通知为已读"""
        ids = request.data.get("ids", [])
        if not ids:
            return JsonResponse({"result": False, "message": "请提供通知ID列表"}, status=status.HTTP_400_BAD_REQUEST)

        updated_count = Notification.objects.filter(id__in=ids, is_read=False).update(is_read=True)
        return JsonResponse({"result": True, "message": f"已标记 {updated_count} 条通知为已读"})

    @action(methods=["get"], detail=False)
    def unread_count(self, request):
        """获取未读通知数量"""
        count = Notification.objects.filter(is_read=False).count()
        return JsonResponse({"result": True, "data": {"count": count}})
