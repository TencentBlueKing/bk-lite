"""风险治理视图

风险项是动态计算的，不存模型，每次请求实时聚合。
为了接入 DRF router（需要 queryset/serializer_class 非空），用 GovernanceTask 占位，
但 list/retrieve 都被完全重写，不会触发标准 ModelViewSet 行为。
"""

from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.models import GovernanceTask, Patch, PatchBaseline, PatchTarget
from apps.patch_mgmt.serializers.governance import GovernanceTaskListSerializer
from apps.patch_mgmt.services.risk_service import (
    aggregate_by_baseline,
    aggregate_by_host,
    aggregate_by_patch,
    compute_risk_items,
    filter_risk_items,
)
from apps.patch_mgmt.utils.data_permissions import require_authorized_ids


def _paginate(data, params):
    """简单分页器，与 list view 的响应保持一致。"""
    try:
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 50))
    except (TypeError, ValueError):
        page, page_size = 1, 50
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    total = len(data)
    items = data[(page - 1) * page_size : page * page_size]
    return {
        "results": items,
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_risk_items": total,
    }


class RiskViewSet(AuthViewSet):
    """风险治理视图集

    动态计算风险项，支持三视角聚合：主机/补丁/基线。
    不存储风险项，每次请求实时计算。
    """

    # 占位：Risk 不存模型，list/retrieve 均被完全重写，DRF router 仅靠这两个属性注册 URL
    queryset = GovernanceTask.objects.none()
    serializer_class = GovernanceTaskListSerializer
    permission_key = "patch_risk"

    def _scoped_items(self, request):
        """仅返回同时具备主机、补丁和基线数据权限的风险项。"""
        target_ids = set(
            self.get_queryset_by_permission(
                request, PatchTarget.objects.all(), permission_key="patch_target"
            ).values_list("id", flat=True)
        )
        patch_ids = set(
            self.get_queryset_by_permission(
                request, Patch.objects.all(), permission_key="patch"
            ).values_list("id", flat=True)
        )
        baseline_ids = set(
            self.get_queryset_by_permission(
                request, PatchBaseline.objects.all(), permission_key="patch_baseline"
            ).values_list("id", flat=True)
        )
        return [
            item
            for item in compute_risk_items()
            if item.host_id in target_ids
            and item.patch_id in patch_ids
            and item.baseline_id in baseline_ids
        ]

    @HasPermission("patch_risk-View")
    def list(self, request, *args, **kwargs):
        """风险项列表（三视角）"""
        view = request.query_params.get("view", "patch")
        items = self._scoped_items(request)
        items = filter_risk_items(items, request.query_params)

        if view == "host":
            data = aggregate_by_host(items)
        elif view == "baseline":
            data = aggregate_by_baseline(items)
        else:
            data = aggregate_by_patch(items)

        payload = _paginate(data, request.query_params)
        payload["view"] = view
        return Response(payload)

    @HasPermission("patch_risk-View")
    def retrieve(self, request, pk=None):
        """单条风险项详情（按视角展开）

        pk 是聚合后的 key，格式：'h-{host_id}' / 'p-{patch_id}' / 'b-{baseline_id}'
        """
        view = request.query_params.get("view", "patch")
        items = self._scoped_items(request)

        if view == "host":
            data = aggregate_by_host(items)
        elif view == "baseline":
            data = aggregate_by_baseline(items)
        else:
            data = aggregate_by_patch(items)

        for item in data:
            if str(item.get("key")) == str(pk):
                return Response(item)
        return Response({"detail": "未找到"}, status=404)

    @action(detail=False, methods=["get"])
    @HasPermission("patch_risk-View")
    def summary(self, request):
        """风险汇总（供首页与待治理页头部统计）"""
        items = self._scoped_items(request)
        by_remediation: dict[str, int] = {}
        by_compliance: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for it in items:
            by_remediation[it.remediation] = by_remediation.get(it.remediation, 0) + 1
            by_compliance[it.compliance] = by_compliance.get(it.compliance, 0) + 1
            sev = it.patch_severity or "unspecified"
            by_severity[sev] = by_severity.get(sev, 0) + 1
        return Response({
            "total": len(items),
            "by_remediation": by_remediation,
            "by_compliance": by_compliance,
            "by_severity": by_severity,
        })

    @action(detail=False, methods=["post"])
    @HasPermission("patch_risk-Add")
    def remediate(self, request):
        """一键治理（创建 install 治理任务）

        请求体：
        {
          "items": [{"host_id": 1, "patch_id": 101}, ...],
          "execution_mode": "now" | "window",
          "execution_window_start": "...",   # optional
          "execution_window_end": "...",     # optional
          "auto_reboot": false,
          "name": "可选-任务名"                 # optional
        }
        """
        from apps.patch_mgmt.services.governance_service import (
            HostBusyError,
            create_remediation_task,
        )

        items = request.data.get("items") or []
        if not isinstance(items, list) or not items:
            return Response({"detail": "items 不能为空"}, status=400)
        require_authorized_ids(
            self,
            request,
            PatchTarget.objects.all(),
            [item.get("host_id") for item in items],
            "patch_target",
        )
        require_authorized_ids(
            self,
            request,
            Patch.objects.all(),
            [item.get("patch_id") for item in items],
            "patch",
        )
        try:
            task = create_remediation_task(request, items, request.data)
        except HostBusyError as exc:
            return Response(
                {"code": "host_busy", "detail": str(exc), "target_ids": exc.target_ids},
                status=409,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"task_id": task.id, "name": task.name, "status": task.status}, status=201)

    @action(detail=False, methods=["post"])
    @HasPermission("patch_risk-Add")
    def reboot(self, request):
        """一键重启（创建 reboot 治理任务）

        请求体：
        {
          "target_ids": [1, 2, 3],
          "execution_window_start": "...",
          "execution_window_end": "...",
          "name": "可选-任务名"
        }
        """
        from apps.patch_mgmt.services.governance_service import HostBusyError, create_reboot_task

        target_ids = request.data.get("target_ids") or []
        if not isinstance(target_ids, list) or not target_ids:
            return Response({"detail": "target_ids 不能为空"}, status=400)
        require_authorized_ids(
            self, request, PatchTarget.objects.all(), target_ids, "patch_target"
        )
        try:
            task = create_reboot_task(request, target_ids, request.data)
        except HostBusyError as exc:
            return Response(
                {"code": "host_busy", "detail": str(exc), "target_ids": exc.target_ids},
                status=409,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"task_id": task.id, "name": task.name, "status": task.status}, status=201)
