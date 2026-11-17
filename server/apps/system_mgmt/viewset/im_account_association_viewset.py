from django.db import transaction
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.models import IMAccountAssociation, IMNotificationSyncRun
from apps.system_mgmt.serializers.im_account_association_serializer import IMAccountAssociationSerializer
from apps.system_mgmt.serializers.im_notification_channel_serializer import (
    AccountAssociationSyncRunListSerializer,
    AccountAssociationUserMappingSerializer,
)
from apps.system_mgmt.services.im_notification_service import create_account_association_sync_run
from apps.system_mgmt.tasks import execute_im_notification_sync_run_task
from apps.system_mgmt.utils.operation_log_utils import log_operation
from config.drf.pagination import CustomPageNumberPagination

ACCOUNT_ASSOCIATION_IN_USE = "This account association is still used and cannot be deleted"


def optional_instance_id(raw):
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    if not text.isdigit():
        raise ValueError("integration instance must be an integer")
    return int(text)


class IMAccountAssociationViewSet(MaintainerViewSet):
    latest_sync_run_id = IMNotificationSyncRun.objects.filter(account_association_id=OuterRef("pk")).order_by("-started_at", "-id").values("id")[:1]
    queryset = (
        IMAccountAssociation.objects.select_related("integration_instance")
        .prefetch_related(
            Prefetch(
                "sync_runs",
                queryset=IMNotificationSyncRun.objects.filter(id=Subquery(latest_sync_run_id)),
                to_attr="_prefetched_latest_run",
            )
        )
        .all()
        .order_by("name", "id")
    )
    serializer_class = IMAccountAssociationSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            instance_id = optional_instance_id(self.request.query_params.get("integration_instance"))
        except ValueError:
            raise ValidationError({"integration_instance": "Integration instance must be an integer"})
        if instance_id is not None:
            queryset = queryset.filter(integration_instance_id=instance_id)
        return queryset

    @HasPermission("user_sync-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("user_sync-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("user_sync-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "user_sync", f"新增账号关联: {response.data.get('name', '')}")
        return response

    @HasPermission("user_sync-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, partial=True, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "user_sync", f"编辑账号关联: {response.data.get('name', '')}")
        return response

    @HasPermission("user_sync-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        name = obj.name
        try:
            with transaction.atomic():
                obj.delete_sync_periodic_task()
                response = super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return JsonResponse({"result": False, "code": "ACCOUNT_ASSOCIATION_IN_USE", "message": ACCOUNT_ASSOCIATION_IN_USE}, status=409)
        if response.status_code in (200, 204):
            log_operation(request, "delete", "user_sync", f"删除账号关联: {name}")
        return response

    @action(methods=["POST"], detail=True, url_path="update_association")
    @HasPermission("user_sync-Edit")
    def update_association(self, request, *args, **kwargs):
        association = self.get_object()
        result = create_account_association_sync_run(association.id)
        if not result.get("result"):
            return JsonResponse(result, status=400)
        execute_im_notification_sync_run_task.delay(result["data"]["run_id"])
        return JsonResponse(result, status=200)

    @action(methods=["GET"], detail=True)
    @HasPermission("user_sync-View")
    def mappings(self, request, *args, **kwargs):
        queryset = self.get_object().user_mappings.select_related("user").all()
        page = self.paginate_queryset(queryset)
        serializer = AccountAssociationUserMappingSerializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False, url_path="records")
    @HasPermission("user_sync-View")
    def list_records(self, request, *args, **kwargs):
        search = str(request.query_params.get("search") or "").strip()
        visible = self.filter_queryset(self.get_queryset())
        queryset = IMNotificationSyncRun.objects.select_related("account_association").filter(account_association__in=visible)
        if search:
            queryset = queryset.filter(Q(account_association__name__icontains=search) | Q(summary__icontains=search))
        queryset = queryset.order_by("-started_at", "-id")
        page = self.paginate_queryset(queryset)
        serializer = AccountAssociationSyncRunListSerializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(methods=["GET"], detail=True)
    @HasPermission("user_sync-View")
    def records(self, request, *args, **kwargs):
        queryset = (
            IMNotificationSyncRun.objects.select_related("account_association")
            .filter(account_association=self.get_object())
            .order_by("-started_at", "-id")
        )
        page = self.paginate_queryset(queryset)
        serializer = AccountAssociationSyncRunListSerializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
