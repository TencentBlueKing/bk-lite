"""补丁库视图。"""

import json

from django.db import transaction
from django.db.models import Q

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet, build_json_membership_query
from apps.patch_mgmt.constants import GovernanceTaskStatus, OSType, PackageStatus
from apps.patch_mgmt.exceptions import PatchBusinessError
from apps.patch_mgmt.filters.patch import PatchFilter
from apps.patch_mgmt.models import GovernanceTask, Patch, WindowsPatchDetail
from apps.patch_mgmt.serializers.patch import (
    PatchBatchDeleteSerializer,
    PatchDetailSerializer,
    PatchListSerializer,
)
from apps.patch_mgmt.services.manual_windows_patch_write import (
    ManualWindowsPatchStorageFailure,
    create_manual_windows_patch,
    update_manual_windows_patch,
)
from apps.patch_mgmt.services.target_access import GlobalSharedResourceMixin
from apps.patch_mgmt.services.windows_package import (
    WindowsPackageError,
    replace_failed_windows_package,
    store_windows_package,
)
from apps.patch_mgmt.utils.operation_log import log_patch_created, log_patch_deleted, log_patch_updated
from apps.patch_mgmt.utils.i18n import patch_message, render_business_error
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response


class PatchViewSet(GlobalSharedResourceMixin, AuthViewSet):
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
            raise ValidationError({"metadata": patch_message(request, "error.invalid_metadata_json", "Patch metadata must be a valid JSON object")}) from exc
        if not isinstance(metadata, dict):
            raise ValidationError({"metadata": patch_message(request, "error.metadata_must_be_object", "Patch metadata must be a JSON object")})

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
            except PatchBusinessError as exc:
                raise ValidationError({exc.field or "detail": render_business_error(request, exc)}) from exc
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
            except PatchBusinessError as exc:
                raise ValidationError({exc.field or "detail": render_business_error(request, exc)}) from exc
            log_patch_updated(request, metadata.get("title", ""))
            return self._patch_response(patch)

        response = super().update(request, *args, **kwargs)
        log_patch_updated(request, request.data.get("title", ""))
        return response

    @HasPermission("patch-Delete")
    def destroy(self, request, *args, **kwargs):
        patch = self.get_object()
        return self._delete_patches(request, [patch])

    def _delete_patches(self, request, patches):
        for patch in patches:
            access_error = self._validate_destroy_access(request, patch)
            if access_error is not None:
                return access_error

        patch_ids = {patch.id for patch in patches}
        if Patch.objects.filter(
            id__in=patch_ids,
            baseline_requirements__isnull=False,
        ).exists():
            return Response(
                {"detail": patch_message(request, "error.patch_referenced", "Remove this patch from all baselines before deleting it")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        external_references = Q(pk__in=[])
        candidate_references = Patch.objects.exclude(pk__in=patch_ids)
        for patch_id in patch_ids:
            external_references |= build_json_membership_query(
                candidate_references, "dependency_ids", [patch_id]
            )
            external_references |= build_json_membership_query(
                candidate_references, "replacement_ids", [patch_id]
            )
        if candidate_references.filter(external_references).exists():
            return Response(
                {
                    "detail": patch_message(
                        request,
                        "error.patch_dependency_referenced",
                        "This patch is referenced by another patch dependency or replacement relationship",
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_reference = Q(pk__in=[])
        active_tasks = GovernanceTask.objects.filter(
            status__in=GovernanceTaskStatus.ACTIVE_STATES,
        )
        for patch_id in patch_ids:
            active_reference |= Q(patch_list__contains=[patch_id])
            active_reference |= Q(risk_snapshot__contains=[{"patch_id": patch_id}])
        if active_tasks.filter(active_reference).exists():
            return Response(
                {"detail": patch_message(request, "error.patch_in_active_task", "This patch is in an active task and cannot be deleted")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for patch in patches:
            if patch.os_type != OSType.WINDOWS:
                continue
            try:
                detail = patch.windows_detail
            except WindowsPatchDetail.DoesNotExist:
                detail = None
            if not detail or not detail.package_file:
                continue
            try:
                detail.package_file.delete(save=False)
            except Exception:
                return Response(
                    {"detail": patch_message(request, "error.patch_file_delete_failed", "Failed to delete the patch file; try again later")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        deleted_count = len(patches)
        with transaction.atomic():
            for patch in patches:
                title = patch.title
                patch.delete()
                log_patch_deleted(request, title)
        return Response({"deleted_count": deleted_count}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="batch_delete")
    @HasPermission("patch-Delete")
    def batch_delete(self, request):
        self._validate_current_team_permission(request)
        serializer = PatchBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        patches_by_id = self.get_queryset().in_bulk(ids)
        missing_ids = [patch_id for patch_id in ids if patch_id not in patches_by_id]
        if missing_ids:
            return Response(
                {
                    "detail": patch_message(
                        request,
                        "error.patch_not_found",
                        "Some selected patches do not exist: {ids}",
                        ids=", ".join(str(value) for value in missing_ids),
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._delete_patches(request, [patches_by_id[patch_id] for patch_id in ids])

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    @HasPermission("patch-Edit")
    def upload_package(self, request, pk=None):
        patch = self.get_object()
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": patch_message(request, "error.patch_package_required", "Select a patch package")}, status=status.HTTP_400_BAD_REQUEST)
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
            return Response({"detail": patch_message(request, "error.patch_package_required", "Select a patch package")}, status=status.HTTP_400_BAD_REQUEST)
        try:
            replace_failed_windows_package(patch, uploaded_file)
        except WindowsPackageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch.refresh_from_db()
        return Response(PatchDetailSerializer(patch, context={"request": request}).data)
