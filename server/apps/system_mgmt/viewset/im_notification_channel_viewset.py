from django.db.models import Prefetch, Q
from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun
from apps.system_mgmt.serializers.im_notification_channel_serializer import (
    IMNotificationChannelSerializer,
    IMNotificationSyncRunSerializer,
    IMNotificationUserMappingSerializer,
)
from apps.system_mgmt.services.im_notification_service import (
    create_im_notification_sync_run,
    send_im_notification,
    send_im_notification_to_users,
)
from apps.system_mgmt.tasks import execute_im_notification_sync_run_task
from apps.system_mgmt.utils.operation_log_utils import log_operation
from config.drf.pagination import CustomPageNumberPagination


class IMNotificationChannelViewSet(MaintainerViewSet):
    queryset = (
        IMNotificationChannel.objects.select_related("integration_instance")
        .prefetch_related(
            Prefetch(
                "sync_runs",
                queryset=IMNotificationSyncRun.objects.order_by("-started_at", "-id")[:1],
                to_attr="_prefetched_latest_run",
            )
        )
        .all()
        .order_by("name", "id")
    )
    serializer_class = IMNotificationChannelSerializer
    pagination_class = CustomPageNumberPagination
    ordering = ("-id",)

    def _get_user_group_ids(self, user):
        if getattr(user, "is_superuser", False):
            return None
        return {g["id"] for g in getattr(user, "group_list", [])}

    def _filter_by_accessible_teams(self, queryset, user):
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        query = Q()
        for group_id in user_group_ids:
            query |= Q(team__contains=group_id)
        return queryset.filter(query)

    def _validate_channel_permission(self, request, channel):
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        channel_team_ids = set(channel.team or [])

        if not user_group_ids or not user_group_ids.intersection(channel_team_ids):
            message = (
                self.loader.get("error.no_permission_access_team", "无权访问该团队数据")
                if self.loader
                else "无权访问该团队数据"
            )
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _validate_team_in_user_scope(self, request, team_values):
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        if not user_group_ids:
            return False, JsonResponse({"result": False, "message": "无权访问该团队数据"}, status=403)

        normalized = []
        if isinstance(team_values, (int, str)):
            team_values = [team_values]
        for value in team_values or []:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                continue

        invalid = set(normalized) - user_group_ids
        if invalid:
            message = (
                self.loader.get("error.no_permission_for_groups", "您没有以下组织的权限")
                if self.loader
                else "您没有以下组织的权限"
            )
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    @HasPermission("channel_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = self._filter_by_accessible_teams(queryset, request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @HasPermission("channel_list-View")
    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    @HasPermission("channel_list-Add")
    def create(self, request, *args, **kwargs):
        team_values = request.data.get("team")
        is_valid, error_response = self._validate_team_in_user_scope(request, team_values)
        if not is_valid:
            return error_response

        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "channel", f"新增IM应用通知: {response.data.get('name', '')}")
        return response

    @HasPermission("channel_list-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response

        team_values = request.data.get("team") or getattr(obj, "team", None)
        is_valid, error_response = self._validate_team_in_user_scope(request, team_values)
        if not is_valid:
            return error_response

        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "channel", f"编辑IM应用通知: {response.data.get('name', '')}")
        return response

    @HasPermission("channel_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, obj)
        if not is_valid:
            return error_response

        channel_name = obj.name
        obj.delete_sync_periodic_task()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code in (200, 204):
            log_operation(request, "delete", "channel", f"删除IM应用通知: {channel_name}")
        return response

    @action(methods=["POST"], detail=True)
    @HasPermission("channel_list-Edit")
    def sync_mappings(self, request, *args, **kwargs):
        channel = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response
        result = create_im_notification_sync_run(channel.id)
        if not result.get("result"):
            return JsonResponse(result, status=400)
        run_id = result["data"]["run_id"]
        execute_im_notification_sync_run_task.delay(run_id)
        return JsonResponse(result, status=200)

    @action(methods=["GET"], detail=True)
    @HasPermission("channel_list-View")
    def mappings(self, request, *args, **kwargs):
        channel = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response
        queryset = channel.user_mappings.all()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = IMNotificationUserMappingSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = IMNotificationUserMappingSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(methods=["GET"], detail=True)
    @HasPermission("channel_list-View")
    def records(self, request, *args, **kwargs):
        channel = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response
        queryset = IMNotificationSyncRun.objects.filter(channel=channel).order_by("-started_at", "-id")
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = IMNotificationSyncRunSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = IMNotificationSyncRunSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=True)
    @HasPermission("channel_list-Edit")
    def test_send(self, request, *args, **kwargs):
        channel = self.get_object()
        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response
        result = send_im_notification(
            channel.id,
            title=request.data.get("title", "Test Message"),
            content=request.data.get("content", "This is a test message"),
            receivers=request.data.get("receivers") or [request.user.id],
        )
        status = 200 if result.get("result") else 400
        return JsonResponse(result, status=status)

    @action(methods=["POST"], detail=False)
    @HasPermission("channel_list-Edit")
    def send(self, request, *args, **kwargs):
        channel_id = request.data.get("channel_id")
        user_ids = request.data.get("user_ids") or []
        title = request.data.get("title", "")
        content = request.data.get("content", "")

        try:
            channel_id = int(channel_id)
            user_ids = [int(uid) for uid in user_ids]
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "Invalid channel_id or user_ids"}, status=400)

        channel = IMNotificationChannel.objects.filter(id=channel_id).first()
        if not channel:
            return JsonResponse({"result": False, "message": "IM notification channel not found"}, status=404)

        is_valid, error_response = self._validate_channel_permission(request, channel)
        if not is_valid:
            return error_response

        result = send_im_notification_to_users(channel_id, user_ids, title, content)
        status = 200 if result.get("result") else 400
        return JsonResponse(result, status=status)
