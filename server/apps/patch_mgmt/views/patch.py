"""补丁库视图。"""

import json

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.constants import GovernanceTaskStatus, OSType, PackageStatus
from apps.patch_mgmt.filters.patch import PatchFilter
from apps.patch_mgmt.models import GovernanceTask, Patch, WindowsPatchDetail
from apps.patch_mgmt.serializers.patch import PatchDetailSerializer, PatchListSerializer
from apps.patch_mgmt.services.manual_windows_patch_write import (
    ManualWindowsPatchStorageFailure,
    create_manual_windows_patch,
    update_manual_windows_patch,
)
from apps.patch_mgmt.services.windows_package import (
    WindowsPackageError,
    replace_failed_windows_package,
    store_windows_package,
)
from apps.patch_mgmt.utils.operation_log import log_patch_created, log_patch_deleted, log_patch_updated
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response


class PatchViewSet(AuthViewSet):
    """补丁主记录视图集"""

    # select_related 拉取 OneToOne 详情，prefetch_related 拉取 M2M 源
    queryset = Patch.objects.select_related("windows_detail", "linux_detail").prefetch_related("sources").all()
    serializer_class = PatchListSerializer
    filterset_class = PatchFilter
    search_fields = ["title"]
    ORGANIZATION_FIELD = "team"
    permission_key = "patch"
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def _manual_windows_metadata(self, request):
        raw_metadata = request.data.get("metadata")
        try:
            metadata = (
                raw_metadata
                if isinstance(raw_metadata, dict)
                else json.loads(raw_metadata or "")
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError({"metadata": "补丁元数据必须是有效的 JSON 对象"}) from exc
        if not isinstance(metadata, dict):
            raise ValidationError({"metadata": "补丁元数据必须是 JSON 对象"})

        if not metadata.get("team"):
            current_team = self._parse_current_team_cookie(request)
            if current_team:
                metadata["team"] = [current_team]
        return metadata

    def _patch_response(self, patch, *, response_status=status.HTTP_200_OK):
        patch = self.get_queryset().get(pk=patch.pk)
        return Response(
            PatchDetailSerializer(patch, context=self.get_serializer_context()).data,
            status=response_status,
        )

    def _storage_failure_response(self, failure):
        patch = self.get_queryset().get(pk=failure.patch.pk)
        return Response(
            {
                "detail": failure.detail,
                "patch": PatchDetailSerializer(
                    patch,
                    context=self.get_serializer_context(),
                ).data,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PatchDetailSerializer
        return PatchListSerializer

    @HasPermission("patch-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("patch-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("patch-Add")
    def create(self, request, *args, **kwargs):
        if "metadata" in request.data:
            metadata = self._manual_windows_metadata(request)
            try:
                patch = create_manual_windows_patch(
                    metadata=metadata,
                    uploaded_file=request.FILES.get("file"),
                    context=self.get_serializer_context(),
                )
            except ManualWindowsPatchStorageFailure as failure:
                log_patch_created(request, metadata.get("title", ""))
                return self._storage_failure_response(failure)
            log_patch_created(request, metadata.get("title", ""))
            return self._patch_response(
                patch,
                response_status=status.HTTP_201_CREATED,
            )

        request.data["pkg_status"] = (
            PackageStatus.DOWNLOADING
            if request.data.get("os_type") == OSType.WINDOWS
            else PackageStatus.READY
        )
        if "team" not in request.data or not request.data.get("team"):
            current_team = self._parse_current_team_cookie(request)
            if current_team:
                request.data["team"] = [current_team]
        response = super().create(request, *args, **kwargs)
        log_patch_created(request, request.data.get("title", ""))
        return response

    @HasPermission("patch-Edit")
    def update(self, request, *args, **kwargs):
        if "metadata" in request.data:
            metadata = self._manual_windows_metadata(request)
            try:
                patch = update_manual_windows_patch(
                    patch=self.get_object(),
                    metadata=metadata,
                    uploaded_file=request.FILES.get("file"),
                    context=self.get_serializer_context(),
                )
            except ManualWindowsPatchStorageFailure as failure:
                log_patch_updated(request, metadata.get("title", ""))
                return self._storage_failure_response(failure)
            log_patch_updated(request, metadata.get("title", ""))
            return self._patch_response(patch)

        response = super().update(request, *args, **kwargs)
        log_patch_updated(request, request.data.get("title", ""))
        return response

    @HasPermission("patch-Delete")
    def destroy(self, request, *args, **kwargs):
        patch = self.get_object()
        if patch.baseline_requirements.exists():
            return Response(
                {"detail": "该补丁已被基线引用，请先从基线中移除"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        active_tasks = GovernanceTask.objects.filter(
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
        ).only("patch_list", "risk_snapshot")
        if any(
            str(patch.id) in {str(value) for value in (task.patch_list or [])}
            or any(
                str(item.get("patch_id") or "") == str(patch.id)
                for item in (task.risk_snapshot or [])
                if isinstance(item, dict)
            )
            for task in active_tasks
        ):
            return Response(
                {"detail": "该补丁正在执行任务中，暂不能删除"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title = patch.title
        if patch.os_type == OSType.WINDOWS:
            try:
                detail = patch.windows_detail
            except WindowsPatchDetail.DoesNotExist:
                detail = None
            if detail and detail.package_file:
                try:
                    detail.package_file.delete(save=False)
                except Exception:
                    return Response(
                        {"detail": "补丁文件删除失败，请稍后重试"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        response = super().destroy(request, *args, **kwargs)
        log_patch_deleted(request, title)
        return response

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    @HasPermission("patch-Add")
    def upload_package(self, request, pk=None):
        patch = self.get_object()
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "请选择补丁包"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            store_windows_package(patch, uploaded_file)
        except WindowsPackageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch.refresh_from_db()
        return Response(PatchDetailSerializer(patch, context={"request": request}).data)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    @HasPermission("patch-Edit")
    def replace_package(self, request, pk=None):
        patch = self.get_object()
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "请选择补丁包"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            replace_failed_windows_package(patch, uploaded_file)
        except WindowsPackageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch.refresh_from_db()
        return Response(PatchDetailSerializer(patch, context={"request": request}).data)
