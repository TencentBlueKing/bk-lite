from copy import copy

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.logger import logger
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices, UserSyncRun, UserSyncSource
from apps.system_mgmt.serializers.user_sync_source_serializer import UserSyncRunSerializer, UserSyncSourceSerializer
from apps.system_mgmt.services.user_sync_service import (
    ALL_DEPARTMENT_SELECTION_ID,
    flatten_department_ids,
    preview_user_sync,
    sync_source_now,
    get_user_sync_root_department_input_mode,
)
from apps.system_mgmt.utils.operation_log_utils import log_operation


class UserSyncSourceViewSet(MaintainerViewSet):
    queryset = UserSyncSource.objects.select_related("integration_instance").prefetch_related("runs").all().order_by("name", "id")
    serializer_class = UserSyncSourceSerializer

    @HasPermission("user_sync-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("user_sync-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code == 201:
            log_operation(request, "create", "system-manager", f"新增用户同步源: {response.data.get('name', '')}")
        return response

    @HasPermission("user_sync-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            log_operation(request, "update", "system-manager", f"编辑用户同步源: {response.data.get('name', '')}")
        return response

    @HasPermission("user_sync-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.delete_sync_periodic_task()
        source_name = obj.name
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 204:
            log_operation(request, "delete", "system-manager", f"删除用户同步源: {source_name}")
        return response

    @action(methods=["GET"], detail=False)
    @HasPermission("user_sync-View")
    def available_instances(self, request, *args, **kwargs):
        instances = []
        for item in IntegrationInstance.objects.all().order_by("name", "id"):
            if not item.enabled:
                continue
            if item.status != IntegrationInstanceStatusChoices.READY:
                continue
            if item.capability_status.get("user_sync") != IntegrationInstanceStatusChoices.READY:
                continue
            instances.append({"id": item.id, "name": item.name, "provider_key": item.provider_key})
        return Response(instances)

    @action(methods=["GET"], detail=False, url_path="department_options")
    @HasPermission("user_sync-View")
    def department_options(self, request, *args, **kwargs):
        integration_instance_id = request.query_params.get("integration_instance")
        current_root_department_id = str(request.query_params.get("current_root_department_id") or "")
        department_id_type = str(request.query_params.get("department_id_type") or "")

        if not integration_instance_id:
            return JsonResponse({"result": False, "message": "Integration instance is required"}, status=400)

        integration_instance = IntegrationInstance.objects.filter(id=integration_instance_id).first()
        if not integration_instance:
            return JsonResponse({"result": False, "message": "Integration instance not found"}, status=404)
        if (
            not integration_instance.enabled
            or integration_instance.status != IntegrationInstanceStatusChoices.READY
            or integration_instance.capability_status.get("user_sync") != IntegrationInstanceStatusChoices.READY
        ):
            return JsonResponse({"result": False, "message": "Integration instance user_sync capability is not ready"}, status=400)

        input_mode = get_user_sync_root_department_input_mode(integration_instance.provider_key)
        if input_mode == "manual_input":
            return JsonResponse(
                {
                    "result": False,
                    "message": "Current provider uses manual_input mode and does not support department tree options",
                },
                status=400,
            )

        runtime_service = RuntimeApplicationService()
        result = runtime_service.execute(
            provider_key=integration_instance.provider_key,
            capability_key="user_sync",
            operation="list_departments",
            config=integration_instance.get_runtime_config(),
            business_config={
                "root_department_id": current_root_department_id,
                "department_id_type": department_id_type,
            },
        )
        if not result.success:
            return JsonResponse({"result": False, "message": result.summary, "errors": result.errors}, status=400)

        payload = result.payload
        all_department_id = str(payload.get("all_department_id") or "")
        available_department_ids = flatten_department_ids(payload.get("items") or [])
        if current_root_department_id == ALL_DEPARTMENT_SELECTION_ID:
            selected_id = ALL_DEPARTMENT_SELECTION_ID
            selection_missing = False
        elif current_root_department_id == all_department_id and all_department_id:
            selected_id = ALL_DEPARTMENT_SELECTION_ID
            selection_missing = False
        elif current_root_department_id in available_department_ids:
            selected_id = current_root_department_id
            selection_missing = False
        else:
            selected_id = str(payload.get("selected_id") or "")
            selection_missing = bool(payload.get("selection_missing"))
        return Response(
            {
                "items": payload.get("items") or [],
                "selected_id": selected_id,
                "selection_missing": selection_missing,
            }
        )

    @action(methods=["GET"], detail=False, url_path="records")
    @HasPermission("user_sync-View")
    def list_records(self, request, *args, **kwargs):
        source_queryset = self.filter_queryset(self.get_queryset())
        visible_sources = self.get_queryset_by_permission(request, source_queryset)
        queryset = UserSyncRun.objects.select_related("source").filter(source__in=visible_sources).order_by("-started_at", "-id")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserSyncRunSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = UserSyncRunSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=True)
    @HasPermission("user_sync-Edit")
    def sync_now(self, request, *args, **kwargs):
        source = self.get_object()
        sync_source_now(source.id)
        log_operation(request, "execute", "system-manager", f"执行用户同步: {source.name}")
        return JsonResponse({"result": True, "message": "User sync task has been initiated"})

    @action(methods=["GET"], detail=True)
    @HasPermission("user_sync-View")
    def records(self, request, *args, **kwargs):
        source = self.get_object()
        serializer = UserSyncRunSerializer(source.runs.all()[:20], many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False)
    @HasPermission("user_sync-View")
    def preview(self, request, *args, **kwargs):
        """Dry-run preview: fetch provider data without persisting anything or creating a run.

        Accepts either:
        - {"source_id": <id>, ...overrides} to preview an existing source with optional overrides
        - {full source payload} to preview a new source configuration
        """
        source_id = request.data.get("source_id")

        if source_id:
            source = UserSyncSource.objects.select_related("integration_instance").filter(id=source_id).first()
            if not source:
                logger.warning(f"User sync preview source not found: source_id={source_id}, payload={request.data}")
                return JsonResponse({"result": False, "message": "User sync source not found"}, status=404)
            serializer = UserSyncSourceSerializer(instance=source, data=request.data, partial=True)
        else:
            source = None
            serializer = UserSyncSourceSerializer(data=request.data)

        if not serializer.is_valid():
            logger.warning(f"User sync preview payload invalid: payload={request.data}, errors={serializer.errors}")
            return JsonResponse({"result": False, "message": "Invalid payload", "errors": serializer.errors}, status=400)

        validated = serializer.validated_data
        if source is not None:
            # Apply validated overrides to an in-memory copy; never save
            preview_source = copy(source)
            for attr_name, value in validated.items():
                setattr(preview_source, attr_name, value)
        else:
            preview_source = UserSyncSource(
                integration_instance=validated["integration_instance"],
                name=validated.get("name", ""),
                business_config=validated.get("business_config", {}),
                root_group_name=validated.get("root_group_name", ""),
            )

        result = preview_user_sync(preview_source)
        logger.info(
            f"User sync preview result: source_id={source_id or 'new'}, "
            f"payload={request.data}, result={result}"
        )
        return JsonResponse(result)
