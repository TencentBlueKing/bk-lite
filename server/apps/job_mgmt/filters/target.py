"""目标管理过滤器"""

from django_filters import rest_framework as filters

from apps.job_mgmt.models import Target


class TargetFilter(filters.FilterSet):
    """目标过滤器"""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    ip = filters.CharFilter(field_name="ip", lookup_expr="icontains")
    os_type = filters.CharFilter(field_name="os_type", lookup_expr="exact")
    driver = filters.CharFilter(field_name="driver", lookup_expr="exact")
    source = filters.CharFilter(field_name="source", lookup_expr="exact")
    node_id = filters.CharFilter(field_name="node_id", lookup_expr="exact")
    cloud_region_id = filters.NumberFilter(field_name="cloud_region_id", lookup_expr="exact")
    credential_source = filters.CharFilter(field_name="credential_source", lookup_expr="exact")
    ssh_credential_type = filters.CharFilter(field_name="ssh_credential_type", lookup_expr="exact")

    class Meta:
        model = Target
        fields = [
            "name",
            "ip",
            "os_type",
            "driver",
            "source",
            "node_id",
            "cloud_region_id",
            "credential_source",
            "ssh_credential_type",
        ]
