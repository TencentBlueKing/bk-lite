from django_filters import BaseInFilter, CharFilter, DateTimeFromToRangeFilter, FilterSet, NumberFilter

from apps.cmdb.models.change_record import ChangeRecord


class CharInFilter(BaseInFilter, CharFilter):
    pass


class ChangeRecordFilter(FilterSet):
    inst_id = NumberFilter(field_name="inst_id", lookup_expr="exact", label="实例ID")
    model_id = CharFilter(field_name="model_id", lookup_expr="exact", label="模型ID")
    type = CharFilter(field_name="type", lookup_expr="exact", label="变更类型")
    operator = CharFilter(field_name="operator", lookup_expr="icontains", label="操作者")
    message = CharFilter(field_name="message", lookup_expr="icontains", label="概述")
    model_object = CharFilter(field_name="model_object", lookup_expr="exact", label="模型对象")
    scenario = CharFilter(field_name="scenario", lookup_expr="exact", label="变更场景")
    scenarios = CharInFilter(field_name="scenario", lookup_expr="in", label="变更场景(多选, 逗号分隔)")
    created_at = DateTimeFromToRangeFilter(
        field_name="created_at", lookup_expr="range", label="创建时间区间"
    )

    class Meta:
        model = ChangeRecord
        fields = [
            "inst_id",
            "model_id",
            "type",
            "operator",
            "created_at",
            "message",
            "model_object",
            "scenario",
            "scenarios",
        ]
