from django_filters import FilterSet, CharFilter

from apps.monitor.models import MonitorPlugin


class MonitorPluginFilter(FilterSet):
    monitor_object_id = CharFilter(
        field_name="monitor_object",
        lookup_expr="exact",
        label="监控对象",
        required=False,  # 设置为非必填
        method="filter_monitor_object",  # 使用自定义过滤方法
    )
    # 注意:已移除 name 字段的 icontains 过滤
    # 改为由 views/plugin.py 的 list 视图,在 i18n 翻译后对五字段
    # (name / display_name / description / display_description / parent_object_display_name)
    # 做内存 icontains 匹配,语义为「按当前可见文本搜索」。
    # 若仍在 DB 侧按 name 过滤,中文/英文/父对象 tag 等翻译后字段无法命中,搜索体验差。
    template_type = CharFilter(field_name="template_type", lookup_expr="exact", label="模板类型")
    template_id = CharFilter(field_name="template_id", lookup_expr="icontains", label="模板ID")

    def filter_monitor_object(self, queryset, name, value):
        """自定义过滤方法：为空时返回全部，否则按监控对象ID过滤"""
        if value:
            return queryset.filter(monitor_object=value)
        return queryset

    class Meta:
        model = MonitorPlugin
        fields = ["monitor_object_id", "template_type", "template_id"]
