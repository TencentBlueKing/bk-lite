"""Playbook过滤器"""

from django_filters import rest_framework as filters

from apps.job_mgmt.models import Playbook


class PlaybookFilter(filters.FilterSet):
    """Playbook过滤器"""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    is_preset = filters.BooleanFilter(field_name="is_preset")

    class Meta:
        model = Playbook
        fields = ["name", "is_preset"]
