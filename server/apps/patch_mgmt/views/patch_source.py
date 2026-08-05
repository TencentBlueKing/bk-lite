"""补丁源视图"""

import logging

from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.filters.patch_source import PatchSourceFilter
from apps.patch_mgmt.models import PatchSource
from apps.patch_mgmt.serializers.patch_source import (
    PatchSourceConnectivitySerializer,
    PatchSourceSerializer,
)
from apps.patch_mgmt.services.connectivity_prober import probe_source
from apps.patch_mgmt.utils.operation_log import log_source_changed
from apps.patch_mgmt.utils.data_permissions import require_authorized_ids
from apps.patch_mgmt.utils.i18n import patch_message


class PatchSourceViewSet(AuthViewSet):
    """补丁源配置视图集"""

    queryset = PatchSource.objects.all()
    serializer_class = PatchSourceSerializer
    filterset_class = PatchSourceFilter
    search_fields = ["name"]
    ORGANIZATION_FIELD = "team"
    permission_key = "patch_source"
    CONNECTION_FIELDS = {
        "source_type",
        "url",
        "distro_name",
        "os_version",
        "arch",
        "proxy_host",
        "proxy_port",
        "auth_user",
        "auth_password",
    }

    @staticmethod
    def _require_builtin_manager(request, source):
        if source.is_builtin and not getattr(request.user, "is_superuser", False):
            raise PermissionDenied(
                patch_message(
                    request,
                    "error.builtin_source_superuser_required",
                    "Only platform superusers can manage built-in patch sources",
                )
            )

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        """内置源全局可见，自定义源仍使用原有团队/实例权限。"""
        custom_queryset = super().get_queryset_by_permission(
            request,
            queryset.filter(is_builtin=False),
            permission_key=permission_key,
        )
        custom_ids = custom_queryset.values_list("id", flat=True)
        return queryset.filter(Q(is_builtin=True) | Q(id__in=custom_ids))

    @HasPermission("patch_source-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        custom_queryset = self.get_queryset_by_permission(
            request, queryset.filter(is_builtin=False)
        )
        custom_ids = custom_queryset.values_list("id", flat=True)
        visible_queryset = queryset.filter(
            Q(is_builtin=True) | Q(id__in=custom_ids)
        ).order_by(self.ORDERING_FIELD)
        return self._list(visible_queryset)

    @HasPermission("patch_source-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_builtin:
            return Response(self.get_serializer(instance).data)
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("patch_source-Add")
    def create(self, request, *args, **kwargs):
        # 前端不传 team 时，自动填入 current_team，否则 team=[] 导致列表查不到
        if "team" not in request.data or not request.data.get("team"):
            current_team = self._parse_current_team_cookie(request)
            if current_team:
                request.data["team"] = [current_team]
        response = super().create(request, *args, **kwargs)
        log_source_changed(request, "create", request.data.get("name", ""))
        self._enqueue_connectivity_probe(response.data.get("id"))
        return response

    @HasPermission("patch_source-Edit")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        self._require_builtin_manager(request, instance)
        changed_connection = any(
            field in request.data
            and request.data.get(field) not in (None, "")
            and str(request.data.get(field)) != str(getattr(instance, field))
            for field in self.CONNECTION_FIELDS
        )
        # AuthViewSet 的超管分支会丢失 partial 标记；补丁源页面统一使用
        # PATCH，因此在本模块内保留局部更新语义。
        if getattr(request.user, "is_superuser", False) and kwargs.get("partial"):
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            response = Response(serializer.data)
        else:
            response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        log_source_changed(request, "update", instance.name)
        if changed_connection:
            from apps.patch_mgmt.constants import ConnectivityStatus

            instance.connectivity_status = ConnectivityStatus.UNKNOWN
            instance.last_checked_at = None
            instance.save(
                update_fields=[
                    "connectivity_status",
                    "last_checked_at",
                    "updated_at",
                ]
            )
            self._enqueue_connectivity_probe(instance.id)
            response.data["connectivity_status"] = ConnectivityStatus.UNKNOWN
            response.data["last_checked_at"] = None
        return response

    @staticmethod
    def _enqueue_connectivity_probe(source_id):
        """提交后台连通性探测，保存接口不等待外部网络。"""
        if not source_id:
            return
        try:
            from apps.patch_mgmt.tasks import check_patch_source_connectivity

            check_patch_source_connectivity.delay(source_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("提交连通性探测失败 source_id=%s: %s", source_id, exc)

    def _probe_connectivity(self, source_id):
        """同步探测补丁源连通性，写回 connectivity_status。"""
        try:
            from apps.patch_mgmt.models import PatchSource
            from apps.patch_mgmt.services.connectivity_prober import probe_source
            from apps.patch_mgmt.services.source_sync_service import SourceSyncService

            source = PatchSource.objects.get(pk=source_id)
            result = probe_source(source)
            if result is not None:
                SourceSyncService.record_connectivity_result(source, result.reachable)
        except Exception as exc:  # noqa: BLE001
            logger.warning("连通性探测失败 source_id=%s: %s", source_id, exc)

    @action(detail=False, methods=["post"])
    @HasPermission("patch_source-Add")
    def test_connectivity(self, request):
        """使用新增表单中的未保存参数执行协议级连通性测试。"""
        serializer = PatchSourceConnectivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = PatchSource(**serializer.validated_data)
        result = probe_source(source)
        return Response({
            "connectivity_status": (
                "connected" if result and result.reachable else "failed"
            ),
            "detail": result.detail if result else patch_message(request, "error.source_address_required", "No source address is available for testing"),
            "status_code": result.status_code if result else None,
        })

    @HasPermission("patch_source-Delete")
    def destroy(self, request, *args, **kwargs):
        source = self.get_object()
        if source.is_builtin:
            raise PermissionDenied(
                patch_message(
                    request,
                    "error.builtin_source_delete_forbidden",
                    "Built-in patch sources cannot be deleted",
                )
            )
        log_source_changed(request, "delete", source.name)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @HasPermission("patch_source-Edit")
    def set_enabled(self, request, pk=None):
        """启停切换：仅传 is_enabled，避免 PUT/PATCH 全量更新缺必填字段报 400。"""
        from rest_framework import status as drf_status
        from rest_framework.exceptions import ValidationError as DRFValidationError

        instance = self.get_object()
        self._require_builtin_manager(request, instance)
        require_authorized_ids(
            self, request, PatchSource.objects.all(), [instance.id], "patch_source"
        )
        is_enabled = request.data.get("is_enabled")
        if not isinstance(is_enabled, bool):
            raise DRFValidationError({"is_enabled": [patch_message(request, "error.boolean_required", "This field is required and must be a boolean")]})
        instance.is_enabled = is_enabled
        instance.save(update_fields=["is_enabled", "updated_at", "updated_by"])
        log_source_changed(request, "update", instance.name)
        return Response(
            PatchSourceSerializer(instance, context={"request": request}).data,
            status=drf_status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    @HasPermission("patch_source-Edit")
    def sync(self, request, pk=None):
        """同步补丁源到补丁库。

        - Linux yum/dnf/apt: 同步安全公告元数据
        - WSUS: 同步已批准补丁元数据

        同步执行，返回 {total, created, updated, ...}。
        """
        from rest_framework import status as drf_status

        from apps.patch_mgmt.services.linux_repo_sync import RepoSyncError
        from apps.patch_mgmt.services.source_sync_service import (
            SourceSyncError,
            SourceSyncService,
        )

        source = self.get_object()
        self._require_builtin_manager(request, source)
        if source.is_builtin:
            return Response(
                {
                    "error": patch_message(
                        request,
                        "error.builtin_source_selected_ingest_required",
                        "Use preview and selected ingestion for built-in patch sources",
                    )
                },
                status=drf_status.HTTP_400_BAD_REQUEST,
            )
        require_authorized_ids(
            self, request, PatchSource.objects.all(), [source.id], "patch_source"
        )
        try:
            if source.is_linux_source:
                result = SourceSyncService.sync_linux_repo(source)
            elif source.source_type == "wsus":
                result = SourceSyncService.sync_wsus(source)
            else:
                return Response(
                    {"error": patch_message(request, "error.source_sync_unsupported", "This source type does not support synchronization (yum/dnf/apt/WSUS only)")},
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )
        except (SourceSyncError, RepoSyncError) as exc:
            return Response({"error": str(exc)}, status=drf_status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 兜底,避免 500
            logger.warning("sync 失败 source_id=%s: %s", source.id, exc, exc_info=True)
            return Response({"error": patch_message(request, "error.sync_failed", "Sync failed: {detail}", detail=str(exc))}, status=drf_status.HTTP_400_BAD_REQUEST)
        log_source_changed(request, "sync", source.name)
        return Response(result)

    @action(detail=True, methods=["post"])
    @HasPermission("patch_source-View")
    def preview_sync(self, request, pk=None):
        """预览补丁源的候选补丁（不写库），供补丁库「同步入库」抽屉展示。

        请求体: {"search": "openssl", "page": 1, "page_size": 20}
        返回: {"items": [...], "total": N, "page": 1, "page_size": 20}
        """
        from rest_framework import status as drf_status

        from apps.patch_mgmt.services.linux_repo_sync import RepoSyncError
        from apps.patch_mgmt.services.source_sync_service import SourceSyncError, SourceSyncService

        source = self.get_object()
        if not source.is_builtin:
            require_authorized_ids(
                self,
                request,
                PatchSource.objects.all(),
                [source.id],
                "patch_source",
                operation="View",
            )
        search = (request.data.get("search") or "").strip().lower()
        page = int(request.data.get("page") or 1)
        page_size = int(request.data.get("page_size") or 20)

        try:
            candidates = SourceSyncService.preview_sync_candidates(source)
        except (SourceSyncError, RepoSyncError) as exc:
            return Response({"error": str(exc)}, status=drf_status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            logger.warning("preview_sync 失败 source_id=%s: %s", source.id, exc, exc_info=True)
            return Response({"error": patch_message(request, "error.fetch_failed", "Fetch failed: {detail}", detail=str(exc))}, status=drf_status.HTTP_400_BAD_REQUEST)

        if search:
            candidates = [
                c for c in candidates
                if search in c.get("name", "").lower()
            ]

        total = len(candidates)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = candidates[start:end]

        return Response({
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        })

    @action(detail=True, methods=["post"])
    @HasPermission("patch-Add")
    def ingest(self, request, pk=None):
        """将选中的候选补丁入库（创建 Patch 记录）。

        - Linux yum/dnf/apt：同步执行，返回 {created, updated, skipped, total}。
        - WSUS：提交后台 Celery 任务异步入库补丁元数据，返回 {accepted, task_id}。

        请求体: {"keys": ["ALSA-2023:6595", "ALSA-2023:6593"]}
        """
        from rest_framework import status as drf_status
        from rest_framework.exceptions import ValidationError as DRFValidationError

        from apps.patch_mgmt.services.linux_repo_sync import RepoSyncError
        from apps.patch_mgmt.services.source_sync_service import SourceSyncError, SourceSyncService
        from apps.patch_mgmt.tasks import ingest_patch_source

        source = self.get_object()
        current_team = self._validate_current_team_permission(request)
        if not source.is_builtin:
            require_authorized_ids(
                self,
                request,
                PatchSource.objects.all(),
                [source.id],
                "patch_source",
                operation="View",
            )
        keys = request.data.get("keys") or []
        severity_overrides = request.data.get("severity_overrides") or {}
        if not isinstance(keys, list) or not keys:
            raise DRFValidationError({"keys": [patch_message(request, "error.patch_keys_required", "Select at least one patch")]})

        # WSUS 需远程获取并批量写入元数据，继续走异步任务。
        if source.source_type == "wsus":
            task = ingest_patch_source.delay(source.id, [str(k) for k in keys])
            log_source_changed(request, "sync", source.name)
            return Response({"accepted": True, "task_id": task.id})

        try:
            result = SourceSyncService.ingest_selected(
                source,
                [str(k) for k in keys],
                severity_overrides=severity_overrides,
                team_id=current_team,
            )
        except (SourceSyncError, RepoSyncError) as exc:
            return Response({"error": str(exc)}, status=drf_status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest 失败 source_id=%s: %s", source.id, exc, exc_info=True)
            return Response({"error": patch_message(request, "error.ingest_failed", "Ingestion failed: {detail}", detail=str(exc))}, status=drf_status.HTTP_400_BAD_REQUEST)
        log_source_changed(request, "sync", source.name)
        return Response(result)

    @action(detail=True, methods=["post"])
    @HasPermission("patch_source-Edit")
    def check_connectivity(self, request, pk=None):
        """用编辑表单参数测试连接；缺省字段复用库中配置且不写回。"""
        source = self.get_object()
        self._require_builtin_manager(request, source)
        require_authorized_ids(
            self, request, PatchSource.objects.all(), [source.id], "patch_source"
        )
        submitted = dict(request.data)
        if hasattr(request.data, "dict"):
            submitted = request.data.dict()
        serializer = PatchSourceConnectivitySerializer(
            source, data=submitted, partial=True
        )
        serializer.is_valid(raise_exception=True)
        values = {
            field: getattr(source, field)
            for field in self.CONNECTION_FIELDS
            if field != "auth_password"
        }
        values["auth_password"] = source.get_auth_password()
        overrides = dict(serializer.validated_data)
        # 编辑态的密码组件在用户点击编辑后可能提交空字符串。空值表示沿用已保存
        # 的密码，不能覆盖数据库中的凭据；未保存过密码时仍会由完整校验报错。
        if not overrides.get("auth_password"):
            overrides.pop("auth_password", None)
        values.update(overrides)
        candidate_serializer = PatchSourceConnectivitySerializer(data=values)
        candidate_serializer.is_valid(raise_exception=True)
        candidate = PatchSource(**candidate_serializer.validated_data)
        result = probe_source(candidate)
        return Response({
            "source_id": source.id,
            "connectivity_status": "connected" if result and result.reachable else "failed",
            "last_checked_at": None,
            "detail": result.detail if result else patch_message(request, "error.source_address_required", "No source address is available for testing"),
            "status_code": result.status_code if result else None,
        })

    @action(detail=False, methods=["post"], url_path="check_connectivity")
    @HasPermission("patch_source-Edit")
    def batch_check_connectivity(self, request):
        """批量探测补丁源连通性。

        请求体：{ "source_ids": [1, 2, 3] }
        返回：[{ "source_id": 1, "connectivity_status": "connected", ... }, ...]
        """
        from rest_framework import status as drf_status
        from rest_framework.exceptions import ValidationError as DRFValidationError

        from apps.patch_mgmt.tasks import check_patch_source_connectivity

        source_ids = request.data.get("source_ids") or []
        if not isinstance(source_ids, list) or not source_ids:
            raise DRFValidationError({"source_ids": [patch_message(request, "error.source_ids_required", "Select at least one patch source")]})

        builtin_sources = PatchSource.objects.filter(
            id__in=source_ids, is_builtin=True
        )
        if builtin_sources.exists() and not getattr(request.user, "is_superuser", False):
            raise PermissionDenied(
                patch_message(
                    request,
                    "error.builtin_source_superuser_required",
                    "Only platform superusers can manage built-in patch sources",
                )
            )

        results = []
        allowed_source_ids = require_authorized_ids(
            self,
            request, PatchSource.objects.all(), source_ids, "patch_source"
        )
        for source_id in allowed_source_ids:
            try:
                source = self.get_queryset().get(pk=source_id)
                check_patch_source_connectivity(source.id)
                source.refresh_from_db()
                results.append({
                    "source_id": source.id,
                    "connectivity_status": source.connectivity_status,
                    "last_checked_at": source.last_checked_at,
                })
            except PatchSource.DoesNotExist:
                results.append({
                    "source_id": source_id,
                    "connectivity_status": "unknown",
                    "last_checked_at": None,
                    "error": patch_message(request, "error.source_not_found", "Patch source not found"),
                })

        return Response(results, status=drf_status.HTTP_200_OK)
