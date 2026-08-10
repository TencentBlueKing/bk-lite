"""补丁管理目标视图"""

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.constants import GovernanceTaskStatus
from apps.patch_mgmt.filters.patch_target import PatchTargetFilter
from apps.patch_mgmt.models import GovernanceTaskHost, HostBaselineBinding, PatchTarget
from apps.patch_mgmt.serializers.patch_target import (
    PatchTargetConnectivitySerializer,
    PatchTargetSerializer,
)
from apps.patch_mgmt.services.target_connectivity import probe_target_data, target_connection_data
from apps.patch_mgmt.services.target_deletion import purge_target_governance_history
from apps.patch_mgmt.services.target_access import (
    TargetRootedResourceMixin,
    require_target_ids,
)
from apps.patch_mgmt.utils.i18n import patch_message
from apps.patch_mgmt.utils.operation_log import (
    log_target_created,
    log_target_purged,
    log_target_updated,
)

logger = logging.getLogger("app")


class PatchTargetViewSet(TargetRootedResourceMixin, AuthViewSet):
    """补丁管理目标视图集"""

    queryset = PatchTarget.objects.prefetch_related("baseline_binding__baseline")
    serializer_class = PatchTargetSerializer
    filterset_class = PatchTargetFilter
    search_fields = ["ip", "name"]
    ORGANIZATION_FIELD = "team"
    permission_key = "patch_target"
    CONNECTION_FIELDS = {
        "ip",
        "os_type",
        "source_type",
        "node_id",
        "cloud_region_id",
        "ssh_port",
        "ssh_user",
        "ssh_credential_type",
        "ssh_password",
        "ssh_key_passphrase",
        "ssh_key_file",
        "winrm_port",
        "winrm_scheme",
        "winrm_transport",
        "winrm_user",
        "winrm_password",
        "winrm_cert_validation",
    }

    @HasPermission("patch_target-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("patch_target-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("patch_target-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        log_target_created(request, request.data.get("name", ""))
        self._trigger_connectivity_probe(response.data.get("id"))
        return response

    @HasPermission("patch_target-Edit")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        changed_connection = any(
            field in request.data
            and request.data.get(field) not in (None, "")
            and str(request.data.get(field)) != str(getattr(instance, field))
            for field in self.CONNECTION_FIELDS
        )
        response = super().update(request, *args, **kwargs)
        log_target_updated(request, response.data.get("name", ""))
        if changed_connection:
            from apps.patch_mgmt.constants import ConnectivityStatus

            target = self.get_object()
            target.connectivity_status = ConnectivityStatus.UNKNOWN
            target.last_checked_at = None
            target.save(
                update_fields=["connectivity_status", "last_checked_at", "updated_at"]
            )
            self._trigger_connectivity_probe(target.id)
            response.data["connectivity_status"] = ConnectivityStatus.UNKNOWN
            response.data["last_detected_at"] = None
        return response

    @HasPermission("patch_target-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        target_id = self.get_object().id
        target = PatchTarget.objects.select_for_update().get(pk=target_id)
        if GovernanceTaskHost.objects.filter(
            target_id=target.id,
            task__status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).exists():
            return Response(
                {
                    "code": "target_has_active_task",
                    "message": patch_message(
                        request,
                        "error.target_has_active_task",
                        "This target has an unfinished task. Wait for it to finish or cancel it before deleting the target",
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        has_pending_reboot = HostBaselineBinding.objects.filter(
            target_id=target.id,
            pending_reboot_count__gt=0,
        ).exists()
        if has_pending_reboot:
            return Response(
                {
                    "code": "target_pending_reboot",
                    "message": patch_message(
                        request,
                        "error.target_pending_reboot",
                        "This target has patches pending reboot. Complete reboot remediation before deleting the target",
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        if target.ssh_key_file:
            try:
                target.ssh_key_file.delete(save=False)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to delete SSH key while deleting patch target target_id=%s",
                    target.id,
                )
                return Response(
                    {
                        "code": "target_key_cleanup_failed",
                        "message": patch_message(
                            request,
                            "error.target_key_cleanup_failed",
                            "Failed to clean up the target SSH key. Try again later",
                        ),
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        purge_target_governance_history(target.id)
        target.delete()
        log_target_purged(request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="imported-node-ids")
    @HasPermission("patch_target-View")
    def imported_node_ids(self, request):
        """返回已纳入的节点列表（轻量：仅 node_id + name），不受分页限制。"""
        from apps.patch_mgmt.constants import PatchTargetSource

        qs = self.get_queryset_by_permission(
            request,
            self.get_queryset().filter(
                source_type=PatchTargetSource.NODE_MGMT,
                node_id__isnull=False,
            ),
            permission_key="patch_target",
        ).values("node_id", "name")
        items = [{"node_id": str(o["node_id"]), "name": o["name"]} for o in qs]
        return Response({"items": items})

    @action(detail=False, methods=["post"])
    @HasPermission("patch_target-Add")
    def batch_create(self, request):
        """批量创建目标（用于节点纳入）。"""
        from rest_framework import status as drf_status
        from rest_framework.exceptions import ValidationError as DRFValidationError

        targets = request.data.get("targets") or []
        if not isinstance(targets, list) or not targets:
            raise DRFValidationError({"targets": [patch_message(request, "error.nodes_required", "Select at least one node")]})
        serializer = self.get_serializer(data=targets, many=True)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data:
            self._validate_org_field_permission(request, item.get("team", []))
        created = serializer.save()
        for t in created:
            log_target_created(request, t.name)
            self._trigger_connectivity_probe(t.id)
        return Response(serializer.data, status=drf_status.HTTP_201_CREATED)

    @staticmethod
    def _trigger_connectivity_probe(target_id):
        """异步触发目标连通性探测。"""
        try:
            from apps.patch_mgmt.tasks import probe_target_connectivity
            probe_target_connectivity.delay(target_id)
        except Exception:  # noqa: BLE001
            pass

    @action(
        detail=False,
        methods=["post"],
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    @HasPermission("patch_target-Add")
    def test_connectivity(self, request):
        """使用创建表单中的未保存参数测试目标连通性。"""
        serializer = PatchTargetConnectivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = probe_target_data(serializer.validated_data)
        from apps.patch_mgmt.constants import ConnectivityStatus

        return Response({
            "connectivity_status": (
                ConnectivityStatus.CONNECTED if result.reachable else ConnectivityStatus.FAILED
            ),
            "port": result.port,
            "detail": result.detail,
            "transport": result.transport,
            "stage": result.stage,
            "reason_code": result.reason_code,
        })

    @action(
        detail=True,
        methods=["post"],
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    @HasPermission("patch_target-Edit")
    def check_connectivity(self, request, pk=None):
        """执行真实 SSH/WinRM 认证探测并写回结果。"""
        from django.utils import timezone

        from apps.patch_mgmt.constants import ConnectivityStatus
        from apps.patch_mgmt.services.target_connectivity import probe_target

        target = self.get_object()
        require_target_ids(request, [target.id], "Operate")
        if request.data:
            serializer = PatchTargetConnectivitySerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            connection_data = target_connection_data(target)
            connection_data.update(serializer.validated_data)
            result = probe_target_data(connection_data)
        else:
            result = probe_target(target)
        target.connectivity_status = (
            ConnectivityStatus.CONNECTED if result.reachable else ConnectivityStatus.FAILED
        )
        target.last_checked_at = timezone.now()
        target.save(update_fields=["connectivity_status", "last_checked_at", "updated_at"])

        binding = getattr(target, "baseline_binding", None)
        if binding is not None:
            binding.last_detected_at = timezone.now()
            binding.save(update_fields=["last_detected_at", "updated_at"])

        return Response({
            "target_id": target.id,
            "connectivity_status": target.connectivity_status,
            "port": result.port,
            "detail": result.detail,
            "transport": result.transport,
            "stage": result.stage,
            "reason_code": result.reason_code,
        })
