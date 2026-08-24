"""基线管理过滤器。"""

from django_filters import rest_framework as filters

from apps.patch_mgmt.constants import OSType
from apps.patch_mgmt.models import PatchBaseline


class PatchBaselineFilter(filters.FilterSet):
    patch_ids = filters.CharFilter(method="filter_patch_ids")
    os_type = filters.ChoiceFilter(choices=OSType.CHOICES)

    def filter_patch_ids(self, queryset, name, value):
        if not value:
            return queryset
        try:
            patch_ids = list(
                dict.fromkeys(
                    int(item)
                    for item in str(value).split(",")
                    if item.strip()
                )
            )
        except (TypeError, ValueError):
            return queryset.none()
        if not patch_ids or len(patch_ids) > 500:
            return queryset.none()
        return queryset.filter(requirements__patch_id__in=patch_ids).distinct()

    class Meta:
        model = PatchBaseline
        fields = ["patch_ids", "os_type"]
