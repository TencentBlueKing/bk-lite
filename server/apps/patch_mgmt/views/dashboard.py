"""补丁管理 Dashboard 视图"""

from django.db.models import Count, Prefetch
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response

from collections import defaultdict

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.patch_mgmt.constants import (
    ComplianceStatus,
    GovernanceTaskStatus,
    GovernanceTaskType,
    PatchSeverity,
    RiskCompliance,
)
from apps.patch_mgmt.models import (
    BaselineRequirement,
    GovernanceTask,
    GovernanceTaskHost,
    HostBaselineBinding,
    Patch,
)
from apps.patch_mgmt.serializers.governance import GovernanceTaskListSerializer
from apps.patch_mgmt.services.execution_record_service import (
    filter_execution_record_roots,
)
from apps.patch_mgmt.services.risk_service import compute_host_compliance_status, compute_risk_items
from apps.patch_mgmt.services.target_access import target_access_scope


class PatchDashboardViewSet(AuthViewSet):
    """补丁管理 Dashboard 视图集"""

    queryset = GovernanceTask.objects.none()
    serializer_class = GovernanceTaskListSerializer
    permission_key = "patch_dashboard"

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    @action(detail=False, methods=["get"])
    @HasPermission("patch_dashboard-View")
    def stats(self, request):
        """汇总补丁管理关键指标"""
        target_qs = target_access_scope(request).queryset("View")
        target_ids = set(target_qs.values_list("id", flat=True))
        operable_target_ids = set(
            target_access_scope(request)
            .queryset("Operate")
            .values_list("id", flat=True)
        )
        visible_target_ids = target_qs.values("id")
        binding_qs = HostBaselineBinding.objects.filter(
            target_id__in=visible_target_ids
        )
        baseline_ids = set(binding_qs.values_list("baseline_id", flat=True))
        patch_qs = Patch.objects.filter(
            baseline_requirements__baseline_id__in=baseline_ids
        ).distinct()
        patch_ids = set(patch_qs.values_list("id", flat=True))
        task_qs = GovernanceTask.objects.filter(
            host_results__target_id__in=visible_target_ids
        ).distinct()

        target_total = len(target_ids)
        patch_total = len(patch_ids)
        host_binding_filter = {"target_id__in": target_ids}

        high_severity_missing = BaselineRequirement.objects.filter(
            patch__severity__in=(PatchSeverity.CRITICAL, PatchSeverity.IMPORTANT),
            baseline_id__in=baseline_ids,
        ).count()

        affected_targets = HostBaselineBinding.objects.filter(**host_binding_filter).count()
        # 真实合规分布（按 binding.compliance_status 聚合，evaluating 按运行中任务计算）
        binding_status_qs = HostBaselineBinding.objects.filter(**host_binding_filter)
        status_counts = defaultdict(int)
        for binding in binding_status_qs.select_related("target"):
            status_counts[compute_host_compliance_status(binding.target)] += 1
        compliant_hosts = status_counts[ComplianceStatus.COMPLIANT]
        non_compliant_hosts = status_counts[ComplianceStatus.NON_COMPLIANT]
        pending_hosts = status_counts[ComplianceStatus.PENDING]
        failed_hosts = status_counts[ComplianceStatus.FAILED]
        unknown_hosts = status_counts[ComplianceStatus.UNKNOWN]
        not_applicable_hosts = status_counts[ComplianceStatus.NOT_APPLICABLE]
        unconfigured_hosts = target_qs.filter(baseline_binding__isnull=True).count()

        evaluating_hosts = status_counts[ComplianceStatus.EVALUATING]

        # 评估覆盖率 = 已评估主机 / 纳管主机（已绑定 binding 即可视为"已纳入评估"）
        coverage_rate = round((affected_targets / target_total) * 100) if target_total > 0 else 0
        # 合规率 = 合规 / (合规 + 不合规)，其他状态不计入
        denom = compliant_hosts + non_compliant_hosts
        compliance_rate = round((compliant_hosts / denom) * 100) if denom > 0 else 0

        pending_reboot_targets = binding_qs.filter(
            pending_reboot_count__gt=0
        ).count()

        failed_install_tasks = task_qs.filter(
            status=GovernanceTaskStatus.FAILED, task_type="install"
        ).count()
        failed_tasks = task_qs.filter(
            status=GovernanceTaskStatus.FAILED
        ).count()

        # 真实风险项（按团队过滤）
        all_risk_items = compute_risk_items()
        risk_items = [
            item
            for item in all_risk_items
            if item.host_id in target_ids
        ]
        missing_risk_items = [i for i in risk_items if i.compliance == RiskCompliance.MISSING]
        pending_risk_count = len(missing_risk_items)

        severity_dist = (
            patch_qs
            .values("severity")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        severity_names = dict(PatchSeverity.CHOICES)
        patch_severity_distribution = [
            {
                "severity": item["severity"],
                "severity_display": severity_names.get(item["severity"], item["severity"]),
                "count": item["count"],
            }
            for item in severity_dist
        ]

        compliance_distribution = [
            {"label": "合规", "count": compliant_hosts, "color": "success", "filter": "compliant"},
            {"label": "不合规", "count": non_compliant_hosts, "color": "error", "filter": "non_compliant"},
            {"label": "待评估", "count": pending_hosts, "color": "default", "filter": "pending"},
            {"label": "评估中", "count": evaluating_hosts, "color": "processing", "filter": "evaluating"},
            {"label": "评估失败", "count": failed_hosts, "color": "default", "filter": "failed"},
            {"label": "无法判定", "count": unknown_hosts, "color": "warning", "filter": "unknown"},
            {"label": "不适用", "count": not_applicable_hosts, "color": "default", "filter": "not_applicable"},
            {"label": "未配置", "count": unconfigured_hosts, "color": "warning", "filter": "unconfigured"},
        ]

        # 与「风险治理 / 执行记录」使用同一根记录、权限、排序和状态口径。
        visible_host_qs = GovernanceTaskHost.objects.filter(
            target_id__in=visible_target_ids
        ).select_related("task")
        recent_roots = list(
            filter_execution_record_roots(task_qs)
            .select_related("source_record")
            .prefetch_related(
                Prefetch(
                    "host_results",
                    queryset=visible_host_qs,
                    to_attr="_visible_host_results",
                )
            )
            .order_by("-created_at")[:10]
        )
        serialized_recent = GovernanceTaskListSerializer(
            recent_roots,
            many=True,
            context={
                "request": request,
                "visible_target_ids": target_ids,
                "operable_target_ids": operable_target_ids,
            },
        ).data
        recent_tasks = [
            {
                "id": task["id"],
                "name": task["name"],
                "task_type": task["task_type"],
                "task_type_display": task["task_type_display"],
                "execution_mode": task["execution_mode"],
                "execution_window_start": task["execution_window_start"],
                "execution_window_end": task["execution_window_end"],
                "status": task["record_status_display"],
                "status_code": task["record_status"],
                "status_color": task["record_status_color"],
                "created_at": task["created_at"],
            }
            for task in serialized_recent
        ]

        # TOP 风险补丁：基于真实缺失风险项聚合
        severity_rank = {
            PatchSeverity.CRITICAL: 5,
            PatchSeverity.IMPORTANT: 4,
            PatchSeverity.MODERATE: 3,
            PatchSeverity.LOW: 2,
            PatchSeverity.UNSPECIFIED: 1,
        }
        by_patch: dict[int, list] = defaultdict(list)
        for item in missing_risk_items:
            by_patch[item.patch_id].append(item)

        sorted_patches = sorted(
            by_patch.items(),
            key=lambda kv: (severity_rank.get(kv[1][0].patch_severity, 0), len(kv[1])),
            reverse=True,
        )[:10]

        top_risks = []
        for patch_id, items in sorted_patches:
            first = items[0]
            parts = [p for p in [first.kb_number, first.pkg_name] if p]
            patch_label = " · ".join(parts + [first.patch_title]) if parts else first.patch_title
            severity_display = dict(PatchSeverity.CHOICES).get(first.patch_severity, first.patch_severity)
            top_risks.append({
                "id": patch_id,
                "patch": patch_label,
                "hosts": len(items),
                "sev": severity_display,
                "severity": first.patch_severity,
            })

        return Response({
            "high_severity_missing": high_severity_missing,
            "affected_targets": affected_targets,
            "pending_reboot_targets": pending_reboot_targets,
            "failed_install_tasks": failed_install_tasks,
            "recent_scan_status": None,
            "recent_scan_coverage": None,
            "target_total": target_total,
            "patch_total": patch_total,
            "compliance_rate": compliance_rate,
            "coverage_rate": coverage_rate,
            "non_compliant_hosts": non_compliant_hosts,
            "unconfigured_hosts": unconfigured_hosts,
            "pending_risk_count": pending_risk_count,
            "failed_tasks": failed_tasks,
            "compliant_hosts": compliant_hosts,
            "pending_hosts": pending_hosts,
            "evaluating_hosts": evaluating_hosts,
            "failed_hosts": failed_hosts,
            "unknown_hosts": unknown_hosts,
            "not_applicable_hosts": not_applicable_hosts,
            "compliance_distribution": compliance_distribution,
            "scan_tasks": {"total": 0, "running": 0, "pending": 0, "completed": 0, "failed": 0},
            "install_tasks": {"total": 0, "running": 0, "pending": 0, "success": 0, "failed": 0},
            "patch_severity_distribution": patch_severity_distribution,
            "scan_result_distribution": [],
            "recent_tasks": recent_tasks,
            "top_risks": top_risks,
        })
