# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.models import Level


class LevelModelFilter(FilterSet):
    type = CharFilter(field_name="level_type", lookup_expr="exact", label="类型")

    class Meta:
        model = Level
        fields = ["type"]
