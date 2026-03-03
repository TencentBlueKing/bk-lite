# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.sys_setting import SystemSetting


class SystemSettingModelFilter(FilterSet):
    search = CharFilter(field_name="key", lookup_expr="exact", label="系统设置键")

    class Meta:
        model = SystemSetting
        fields = ["search"]
