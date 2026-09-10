from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cmdb.models.scan_model import SCAN_DATABASE_TYPES, ScanExecution, ScanHit, ScanTask
from apps.cmdb.serializers.scan_serializer import (
    ScanExecutionSerializer,
    ScanHitPagination,
    ScanHitSerializer,
    ScanPagination,
    ScanTaskListSerializer,
    ScanTaskSerializer,
)
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class ScanTaskViewSet(AuthViewSet):
    queryset = ScanTask.objects.all()
    serializer_class = ScanTaskSerializer
    pagination_class = ScanPagination
    permission_classes = [IsAuthenticated]
    ordering = ["-updated_at"]
    search_fields = ["name"]
    permission_key = "task"

    def get_queryset(self):
        return ScanTask.objects.prefetch_related(
            Prefetch(
                "executions",
                queryset=ScanExecution.objects.order_by("-id"),
                to_attr="prefetched_executions",
            )
        )

    def get_serializer_class(self):
        if self.action == "list":
            return ScanTaskListSerializer
        return ScanTaskSerializer

    @HasPermission("auto_collection-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("auto_collection-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @HasPermission("auto_collection-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("auto_collection-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("auto_collection-Edit")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("auto_collection-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return WebUtils.response_success()

    def _get_execution(self, eid):
        return get_object_or_404(ScanExecution.objects.select_related("task"), pk=eid)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=True, url_path="exec")
    def exec_scan(self, request, *args, **kwargs):
        task = self.get_object()
        execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_PENDING)
        execution_id = execution.id
        transaction.on_commit(lambda: _delay_trigger_scan(execution_id))
        serializer = ScanExecutionSerializer(execution, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)")
    def execution_detail(self, request, eid=None):
        execution = self._get_execution(eid)
        serializer = ScanExecutionSerializer(execution, context={"request": request})
        return Response(serializer.data)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/hits")
    def execution_hits(self, request, eid=None):
        execution = self._get_execution(eid)
        queryset = (
            ScanHit.objects.filter(execution=execution)
            .filter(
                Q(status=ScanHit.STATUS_SUCCESS)
                | Q(
                    status=ScanHit.STATUS_FAILED,
                    credential_id="",
                    family_run__model_id__in=SCAN_DATABASE_TYPES,
                )
            )
            .select_related("family_run", "execution__task")
            .order_by("family_run__model_id", "host", "id")
        )
        paginator = ScanHitPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        if page is None:
            raise BaseAppException("命中清单必须分页")
        serializer = ScanHitSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/generate_collect")
    def generate_collect(self, request, eid=None):
        """已有 CI 的勾选行单独生成采集（写入并生成走 write_cmdb_and_generate_collect）。"""
        execution = self._get_execution(eid)
        hit_ids = _hit_ids_from_request(request)
        from apps.cmdb.services.scan_collect_generate import ScanCollectGenerateService

        result = ScanCollectGenerateService.generate(
            execution,
            hit_ids,
            operator=getattr(request.user, "username", "") or "",
            request=request,
        )
        return WebUtils.response_success(result)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/push_monitor")
    def push_monitor(self, request, eid=None):
        """必须已有 CI，不代写。"""
        execution = self._get_execution(eid)
        hit_ids = _hit_ids_from_request(request)
        from apps.cmdb.services.scan_push_monitor import ScanPushMonitorService

        result = ScanPushMonitorService.push(
            execution,
            hit_ids,
            request=request,
            operator=getattr(request.user, "username", "") or "",
        )
        return WebUtils.response_success(result)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/write_cmdb")
    def write_cmdb(self, request, eid=None):
        """勾选行写入 CMDB；清单 uuid 不在图里时会重写。"""
        execution = self._get_execution(eid)
        hit_ids = _hit_ids_from_request(request)
        from apps.cmdb.services.scan_write_ci_service import ScanWriteCiService

        result = ScanWriteCiService.write(execution, hit_ids)
        return WebUtils.response_success(result)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/write_cmdb_and_generate_collect")
    def write_cmdb_and_generate_collect(self, request, eid=None):
        """写入成功的行再按族生成采集；写失败行不进生成。"""
        execution = self._get_execution(eid)
        hit_ids = _hit_ids_from_request(request)
        from apps.cmdb.services.scan_write_ci_service import ScanWriteCiService

        result = ScanWriteCiService.write_and_generate(
            execution,
            hit_ids,
            request=request,
            operator=getattr(request.user, "username", "") or "",
        )
        return WebUtils.response_success(result)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/classify_hits")
    def classify_hits(self, request, eid=None):
        execution = self._get_execution(eid)
        hit_ids = _hit_ids_from_request(request)
        data = request.data if hasattr(request, "data") else {}
        cmdb_model_id = str(data.get("cmdb_model_id") or "").strip() if isinstance(data, dict) else ""
        from apps.cmdb.services.scan_classify_service import classify_hits as classify_scan_hits

        result = classify_scan_hits(execution, hit_ids, cmdb_model_id)
        return WebUtils.response_success(result)

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path=r"executions/(?P<eid>[0-9]+)/rematch_soid")
    def rematch_soid(self, request, eid=None):
        execution = self._get_execution(eid)
        data = request.data if hasattr(request, "data") else {}
        soid = str(data.get("soid") or "").strip() if isinstance(data, dict) else ""
        raw_hit_ids = data.get("hit_ids") if isinstance(data, dict) else None
        hit_ids = None
        if raw_hit_ids is not None:
            hit_ids = _hit_ids_from_request(request)
        from apps.cmdb.services.scan_classify_service import rematch_soid as rematch_scan_soid

        result = rematch_scan_soid(execution, soid, hit_ids=hit_ids)
        return WebUtils.response_success(result)


def _hit_ids_from_request(request) -> list[int]:
    data = request.data if hasattr(request, "data") else {}
    raw = data.get("hit_ids") if isinstance(data, dict) else None
    if raw is None:
        raise BaseAppException("请选择命中行")
    if not isinstance(raw, list) or not raw:
        raise BaseAppException("请选择命中行")
    ids = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError) as exc:
            raise BaseAppException("hit_ids 必须是整数列表") from exc
    return ids


def _delay_trigger_scan(execution_id):
    from apps.cmdb.tasks.celery_tasks import trigger_scan_execution

    trigger_scan_execution.delay(execution_id)
