"""补丁管理 Dashboard 视图"""

from django.db.models import Count, Exists, OuterRef
from django.utils import timezone
from rest_framework.decorators import action
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
    HostBaselineBinding,
    Patch,
    PatchBaseline,
    PatchTarget,
)
from apps.patch_mgmt.serializers.governance import GovernanceTaskListSerializer
from apps.patch_mgmt.services.risk_service import compute_risk_items


def _relative_time(value):
    """返回中文相对时间（用于最近执行记录）"""
    if not value:
        return "—"
    now = timezone.now()
    if value > now:
        return "刚刚"
    diff = now - value
    seconds = diff.total_seconds()
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    if seconds < 172800:
        return "昨天"
    return value.strftime("%m-%d")


def _task_status_color(status):
    """治理任务状态 → Ant Design Tag color"""
    return {
        GovernanceTaskStatus.PENDING: "default",
        GovernanceTaskStatus.RUNNING: "processing",
        GovernanceTaskStatus.COMPLETED: "success",
        GovernanceTaskStatus.PARTIAL_SUCCESS: "warning",
        GovernanceTaskStatus.FAILED: "error",
        GovernanceTaskStatus.CANCELLED: "default",
    }.get(status, "default")


class PatchDashboardViewSet(AuthViewSet):
    """补丁管理 Dashboard 视图集"""

    queryset = GovernanceTask.objects.none()
    serializer_class = GovernanceTaskListSerializer
    permission_key = "patch_dashboard"

    @action(detail=False, methods=["get"])
    @HasPermission("patch_dashboard-View")
    def stats(self, request):
        """汇总补丁管理关键指标"""
        target_qs = self.get_queryset_by_permission(
            request, PatchTarget.objects.all(), permission_key="patch_target"
        )
        patch_qs = self.get_queryset_by_permission(
            request, Patch.objects.all(), permission_key="patch"
        )
        baseline_qs = self.get_queryset_by_permission(
            request, PatchBaseline.objects.all(), permission_key="patch_baseline"
        )
        task_qs = self.get_queryset_by_permission(
            request, GovernanceTask.objects.all(), permission_key="patch_governance"
        )
        target_ids = set(target_qs.values_list("id", flat=True))
        patch_ids = set(patch_qs.values_list("id", flat=True))
        baseline_ids = set(baseline_qs.values_list("id", flat=True))

        target_total = len(target_ids)
        patch_total = len(patch_ids)
        host_binding_filter = {
            "target_id__in": target_ids,
            "baseline_id__in": baseline_ids,
        }

        high_severity_missing = BaselineRequirement.objects.filter(
            patch__severity__in=(PatchSeverity.CRITICAL, PatchSeverity.IMPORTANT),
            patch_id__in=patch_ids,
            baseline_id__in=baseline_ids,
        ).count()

        affected_targets = HostBaselineBinding.objects.filter(**host_binding_filter).count()
        # 真实合规分布（按 binding.compliance_status 聚合，evaluating 按运行中任务计算）
        binding_status_qs = HostBaselineBinding.objects.filter(**host_binding_filter)
        compliant_hosts = binding_status_qs.filter(compliance_status=ComplianceStatus.COMPLIANT).count()
        non_compliant_hosts = binding_status_qs.filter(compliance_status=ComplianceStatus.NON_COMPLIANT).count()
        pending_hosts = binding_status_qs.filter(compliance_status=ComplianceStatus.PENDING).count()
        failed_hosts = binding_status_qs.filter(compliance_status=ComplianceStatus.FAILED).count()
        unconfigured_hosts = target_qs.filter(baseline_binding__isnull=True).count()

        active_assessment = Exists(
            task_qs.filter(
                host_results__target_id=OuterRef("target_id"),
                task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
                status__in=GovernanceTaskStatus.ACTIVE_STATES,
            )
        )
        evaluating_hosts = (
            binding_status_qs.annotate(_active_assessment=active_assessment)
            .filter(_active_assessment=True)
            .count()
        )

        # 评估覆盖率 = 已评估主机 / 纳管主机（已绑定 binding 即可视为"已纳入评估"）
        coverage_rate = round((affected_targets / target_total) * 100) if target_total > 0 else 0
        # 合规率 = 合规 / (合规 + 不合规)，其他状态不计入
        denom = compliant_hosts + non_compliant_hosts
        compliance_rate = round((compliant_hosts / denom) * 100) if denom > 0 else 0

        pending_reboot_targets = 0

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
            and item.patch_id in patch_ids
            and item.baseline_id in baseline_ids
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
            {"label": "未配置", "count": unconfigured_hosts, "color": "warning", "filter": "unconfigured"},
        ]

        # 最近执行记录（按团队过滤）
        recent_tasks_qs = task_qs.prefetch_related("host_results").order_by("-created_at")[:10]

        def _task_in_scope(task):
            listed_target_ids = set(task.target_list or [])
            if listed_target_ids & target_ids:
                return True
            return any(hr.target_id in target_ids for hr in task.host_results.all())

        recent_tasks_qs = [task for task in recent_tasks_qs if _task_in_scope(task)]

        recent_tasks = []
        for task in recent_tasks_qs[:10]:
            total = len(task.target_list or []) or task.host_results.count() or 1
            completed = sum(1 for hr in task.host_results.all() if hr.exit_code == 0)
            if task.status == GovernanceTaskStatus.COMPLETED:
                completed = total
            elif task.status == GovernanceTaskStatus.PENDING:
                completed = 0
            status_display = dict(GovernanceTaskStatus.CHOICES).get(task.status, task.status)
            recent_tasks.append({
                "id": task.id,
                "name": task.name,
                "status": status_display,
                "status_color": _task_status_color(task.status),
                "progress": f"{completed} / {total}",
                "time": _relative_time(task.created_at),
                "created_at": task.created_at.isoformat() if task.created_at else None,
            })

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
            "compliance_distribution": compliance_distribution,
            "scan_tasks": {"total": 0, "running": 0, "pending": 0, "completed": 0, "failed": 0},
            "install_tasks": {"total": 0, "running": 0, "pending": 0, "success": 0, "failed": 0},
            "patch_severity_distribution": patch_severity_distribution,
            "scan_result_distribution": [],
            "recent_tasks": recent_tasks,
            "top_risks": top_risks,
        })
