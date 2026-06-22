from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IntegrationInstance, IntegrationInstanceStatusChoices
from apps.system_mgmt.serializers.im_notification_channel_serializer import (
    IMNotificationChannelSerializer,
    IMNotificationSyncRunSerializer,
    IMNotificationUserMappingSerializer,
)
from apps.system_mgmt.services.im_notification_service import create_im_notification_sync_run, send_im_notification
from apps.system_mgmt.tasks import execute_im_notification_sync_run_task
from apps.system_mgmt.utils.operation_log_utils import log_operation
from config.drf.pagination import CustomPageNumberPagination


class IMNotificationChannelViewSet(MaintainerViewSet):
    queryset = IMNotificationChannel.objects.select_related("integration_instance").all().order_by("name", "id")
    serializer_class = IMNotificationChannelSerializer
    pagination_class = CustomPageNumberPagination
    ordering = ("-id",)

    @HasPermission("channel_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("channel_list-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "channel", f"新增IM应用通知: {response.data.get('name', '')}")
        return response

    @HasPermission("channel_list-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "channel", f"编辑IM应用通知: {response.data.get('name', '')}")
        return response

    @HasPermission("channel_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        channel_name = obj.name
        obj.delete_sync_periodic_task()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "delete", "channel", f"删除IM应用通知: {channel_name}")
        return response

    @action(methods=["GET"], detail=False)
    @HasPermission("channel_list-View")
    def available_instances(self, request, *args, **kwargs):
        instances = []
        for item in IntegrationInstance.objects.all().order_by("name", "id"):
            if not item.enabled:
                continue
            if item.status != IntegrationInstanceStatusChoices.READY:
                continue
            if item.capability_status.get("im_notification") != IntegrationInstanceStatusChoices.READY:
                continue
            instances.append({"id": item.id, "name": item.name, "provider_key": item.provider_key})
        return Response(instances)

    @action(methods=["POST"], detail=True)
    @HasPermission("channel_list-Edit")
    def sync_mappings(self, request, *args, **kwargs):
        channel = self.get_object()
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
        result = send_im_notification(
            channel.id,
            title=request.data.get("title", "Test Message"),
            content=request.data.get("content", "This is a test message"),
            receivers=request.data.get("receivers") or [request.user.id],
        )
        status = 200 if result.get("result") else 400
        return JsonResponse(result, status=status)
