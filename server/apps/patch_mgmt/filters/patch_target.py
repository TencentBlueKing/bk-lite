"""补丁管理目标过滤器"""

from django.db.models import Exists, OuterRef, Q
from django_filters import rest_framework as filters

from apps.patch_mgmt.constants import ComplianceStatus, GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import GovernanceTask, PatchTarget


class PatchTargetFilter(filters.FilterSet):
    """补丁管理目标过滤器"""

    ip = filters.CharFilter(field_name="ip", lookup_expr="icontains")
    os_type = filters.CharFilter(field_name="os_type", lookup_expr="exact")
    connectivity_status = filters.CharFilter(
        field_name="connectivity_status", lookup_expr="exact"
    )
    compliance_status = filters.CharFilter(method="filter_compliance_status")
    baseline_id = filters.NumberFilter(field_name="baseline_binding__baseline_id")

    class Meta:
        model = PatchTarget
        fields = ["ip", "os_type", "connectivity_status", "compliance_status", "baseline_id"]

    def filter_compliance_status(self, queryset, name, value):
        """合规状态为序列化器计算字段，按 HostBaselineBinding 近似过滤。

        与 ``compute_host_compliance_status`` 语义对齐：
        - evaluating：已绑定且存在进行中的 assess/verify 任务
        - pending：已绑定但从未评估过（last_evaluated_at 为空）
        - compliant：compliance_status = compliant 或 pending 但已评估且 missing_count = 0
        - non_compliant：compliance_status = non_compliant 或 pending 但已评估且 missing_count > 0
        - failed：compliance_status = failed
        - unconfigured：未绑定基线
        """
        active_assessment = Exists(
            GovernanceTask.objects.filter(
                host_results__target_id=OuterRef("id"),
                task_type__in=(GovernanceTaskType.ASSESS, GovernanceTaskType.VERIFY),
                status__in=GovernanceTaskStatus.ACTIVE_STATES,
            )
        )

        if value == ComplianceStatus.UNCONFIGURED:
            return queryset.filter(baseline_binding__isnull=True)

        queryset = queryset.filter(baseline_binding__isnull=False)
        if value == ComplianceStatus.EVALUATING:
            return queryset.annotate(_active_assessment=active_assessment).filter(_active_assessment=True)

        # 其他状态均需排除正在评估中的目标
        queryset = queryset.annotate(_active_assessment=active_assessment).filter(_active_assessment=False)

        if value == ComplianceStatus.FAILED:
            return queryset.filter(baseline_binding__compliance_status=ComplianceStatus.FAILED)
        if value == ComplianceStatus.PENDING:
            return queryset.filter(
                baseline_binding__compliance_status=ComplianceStatus.PENDING,
                baseline_binding__last_evaluated_at__isnull=True,
            )
        if value == ComplianceStatus.COMPLIANT:
            return queryset.filter(
                Q(baseline_binding__compliance_status=ComplianceStatus.COMPLIANT)
                | Q(
                    baseline_binding__compliance_status=ComplianceStatus.PENDING,
                    baseline_binding__last_evaluated_at__isnull=False,
                    baseline_binding__missing_count=0,
                )
            )
        if value == ComplianceStatus.NON_COMPLIANT:
            return queryset.filter(
                Q(baseline_binding__compliance_status=ComplianceStatus.NON_COMPLIANT)
                | Q(
                    baseline_binding__compliance_status=ComplianceStatus.PENDING,
                    baseline_binding__last_evaluated_at__isnull=False,
                    baseline_binding__missing_count__gt=0,
                )
            )
        return queryset
