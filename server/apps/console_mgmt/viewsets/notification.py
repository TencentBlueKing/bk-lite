import os

from django.db.models import BooleanField, Exists, OuterRef, Q
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.console_mgmt.models import Notification, NotificationRead
from apps.console_mgmt.serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """通知消息视图集（按用户隔离已读/删除状态）"""

    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()
    http_method_names = ["get", "post", "delete"]

    def _annotate_user_read(self, queryset):
        """为 queryset 标注当前用户的已读状态"""
        user = self.request.user
        user_read = NotificationRead.objects.filter(
            notification=OuterRef("pk"),
            user=user,
            is_read=True,
        )
        return queryset.annotate(
            user_is_read=Exists(user_read, output_field=BooleanField()),
        )

    def get_queryset(self):
        """获取通知列表，排除当前用户已删除的通知"""
        user = self.request.user
        deleted = NotificationRead.objects.filter(
            notification=OuterRef("pk"),
            user=user,
            is_deleted=True,
        )
        queryset = Notification.objects.exclude(Exists(deleted))

        # 按模块过滤
        app_module = self.request.query_params.get("app_module")
        if app_module:
            queryset = queryset.filter(app_module=app_module)

        queryset = self._annotate_user_read(queryset)

        # 仅未读
        unread_only = self.request.query_params.get("unread_only")
        if unread_only is not None and unread_only.lower() == "true":
            queryset = queryset.filter(user_is_read=False)

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

    def destroy(self, request, *args, **kwargs):
        """软删除：仅标记当前用户已删除，不影响其他用户"""
        notification = self.get_object()
        NotificationRead.objects.update_or_create(
            notification=notification,
            user=request.user,
            defaults={"is_deleted": True},
        )
        return JsonResponse({"result": True, "message": "删除成功"})

    @action(methods=["post"], detail=True)
    def mark_as_read(self, request, pk=None):
        """标记单条通知为已读（当前用户）"""
        notification = self.get_object()
        read_state, created = NotificationRead.objects.get_or_create(
            notification=notification,
            user=request.user,
            defaults={"is_read": True, "read_at": timezone.now()},
        )
        if not created and not read_state.is_read:
            read_state.is_read = True
            read_state.read_at = timezone.now()
            read_state.save(update_fields=["is_read", "read_at"])

        return JsonResponse({"result": True, "message": "标记已读成功"})

    @action(methods=["post"], detail=False)
    def mark_all_as_read(self, request):
        """批量标记所有未读通知为已读（当前用户）

        集合运算全部留在 DB 侧，不将 ID 物化到 Python 内存：
        1. UPDATE：将已存在但 is_read=False 的 NotificationRead 行直接更新；
        2. bulk_create：对尚无 NotificationRead 行的通知批量插入（用子查询过滤）；
        3. COUNT：用 DB 聚合取已标记数量，不再对 queryset 调用 len()。
        """
        user = request.user
        now = timezone.now()

        # 步骤 1：更新已有的 is_read=False 记录（纯 DB UPDATE，不拉数据到内存）
        updated_count = NotificationRead.objects.filter(
            user=user, is_read=False,
        ).update(is_read=True, read_at=now)

        # 步骤 2：找出完全没有 NotificationRead 行的通知，批量插入
        # 用子查询：exclude 掉已有任意 NotificationRead 的通知
        existing_notification_ids = NotificationRead.objects.filter(user=user).values("notification_id")
        new_notifications = Notification.objects.exclude(id__in=existing_notification_ids)

        # 分批插入，避免单次 INSERT 过大（每批最多 MAX_BATCH 条）
        MAX_BATCH = int(os.getenv("MARK_ALL_READ_BATCH_SIZE", 2000))
        created_count = 0
        batch = []
        for nid in new_notifications.values_list("id", flat=True).iterator(chunk_size=MAX_BATCH):
            batch.append(NotificationRead(notification_id=nid, user=user, is_read=True, read_at=now))
            if len(batch) >= MAX_BATCH:
                NotificationRead.objects.bulk_create(batch, ignore_conflicts=True)
                created_count += len(batch)
                batch = []
        if batch:
            NotificationRead.objects.bulk_create(batch, ignore_conflicts=True)
            created_count += len(batch)

        total = updated_count + created_count
        return JsonResponse({"result": True, "message": f"已标记 {total} 条通知为已读"})

    @action(methods=["post"], detail=False)
    def mark_batch_as_read(self, request):
        """批量标记指定通知为已读（当前用户）"""
        ids = request.data.get("ids", [])
        if not ids:
            return JsonResponse({"result": False, "message": "请提供通知ID列表"}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        now = timezone.now()
        existing = set(
            NotificationRead.objects.filter(user=user, notification_id__in=ids)
            .values_list("notification_id", flat=True)
        )
        if existing:
            NotificationRead.objects.filter(
                user=user, notification_id__in=existing, is_read=False,
            ).update(is_read=True, read_at=now)
        new_ids = set(ids) - existing
        if new_ids:
            NotificationRead.objects.bulk_create([
                NotificationRead(notification_id=nid, user=user, is_read=True, read_at=now)
                for nid in new_ids
            ], ignore_conflicts=True)

        return JsonResponse({"result": True, "message": f"已标记 {len(ids)} 条通知为已读"})

    @action(methods=["get"], detail=False)
    def unread_count(self, request):
        """获取当前用户的未读通知数量（单次 SQL：用 Exists 子查询替代三次独立查询）"""
        user = request.user
        deleted_or_read = NotificationRead.objects.filter(
            notification=OuterRef("pk"),
            user=user,
        ).filter(
            Q(is_deleted=True) | Q(is_read=True)
        )
        count = Notification.objects.exclude(Exists(deleted_or_read)).count()
        return JsonResponse({"result": True, "data": {"count": count}})
