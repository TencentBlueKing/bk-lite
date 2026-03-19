"""作业执行过滤器"""

from django_filters import rest_framework as filters

from apps.job_mgmt.models import JobExecution


class JobExecutionFilter(filters.FilterSet):
    """作业执行过滤器"""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    job_type = filters.CharFilter(field_name="job_type", lookup_expr="exact")
    status = filters.CharFilter(field_name="status", lookup_expr="exact")
    created_at_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = JobExecution
        fields = ["name", "job_type", "status", "created_at_after", "created_at_before"]
