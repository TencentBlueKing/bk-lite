"""补丁管理目标过滤器"""

from django_filters import rest_framework as filters

from apps.patch_mgmt.constants import ComplianceStatus
from apps.patch_mgmt.models import PatchTarget


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
        """按与列表序列化完全相同的只读投影语义过滤。"""
        valid = {item[0] for item in ComplianceStatus.CHOICES}
        if value not in valid:
            return queryset.none()
        from apps.patch_mgmt.services.risk_service import compute_host_compliance_status

        target_ids = [
            target.id
            for target in queryset.select_related("baseline_binding__baseline")
            if compute_host_compliance_status(target) == value
        ]
        return queryset.filter(id__in=target_ids)
