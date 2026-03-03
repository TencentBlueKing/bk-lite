# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.models import Alert


class AlertModelFilter(FilterSet):
    """
    exact	精确匹配（默认值）	alert_id=123 → 只匹配 alert_id 为 "123" 的记录
    icontains	包含匹配（不区分大小写）	name="test" → 匹配包含 "test" 的所有记录
    contains	包含匹配（区分大小写）	同上，但区分大小写
    startswith	以...开头	匹配以指定字符串开头的记录
    endswith	以...结尾	匹配以指定字符串结尾的记录
    gt	大于	数值比较
    lt	小于	数值比较
    in	在列表中	匹配列表中的任意值
    """
    # inst_id = NumberFilter(field_name="inst_id", lookup_expr="exact", label="实例ID")
    title = CharFilter(field_name="title", lookup_expr="icontains", label="名称")
    content = CharFilter(field_name="content", lookup_expr="icontains", label="内容")
    alert_id = CharFilter(field_name="alert_id", lookup_expr="exact", label="告警ID")
    activate = CharFilter(method="filter_activate", label="是否查询历史告警")
    my_alert = CharFilter(method="filter_my_alert", label="我的告警")
    level = CharFilter(method="filter_level", label="告警级别")
    status = CharFilter(method="filter_status", label="告警状态")
    source_name = CharFilter(method="filter_source_name", label="告警源")
    created_at_after = CharFilter(field_name="created_at", lookup_expr="gte", label="创建时间（起始）")
    created_at_before = CharFilter(field_name="created_at", lookup_expr="lte", label="创建时间（结束）")
    incident_id = CharFilter(field_name="incident__id", lookup_expr="exact", label="事故ID")
    has_incident = CharFilter(method="filter_incident", label="是否有事故")

    class Meta:
        model = Alert
        fields = ["title", "content", "alert_id", "activate", "my_alert", "level", "status", "source_name",
                  "created_at_after", "created_at_before", "incident_id"]

    @staticmethod
    def filter_activate(qs, field_name, value):
        """查询类型 """
        return qs.exclude(status__in=AlertStatus.CLOSED_STATUS)

    def filter_my_alert(self, qs, field_name, value):
        """查询我的告警"""
        username = self.request.user.username
        return qs.filter(operator__contains=username)

    def filter_level(self, qs, field_name, value):
        """支持多选的告警级别过滤"""
        if value:
            # 支持逗号分隔的多个值
            levels = [level.strip() for level in value.split(',')]
            return qs.filter(level__in=levels)
        return qs

    def filter_status(self, qs, field_name, value):
        """支持多选的告警状态过滤"""
        if value:
            # 支持逗号分隔的多个值
            statuses = [status.strip() for status in value.split(',')]
            return qs.filter(status__in=statuses)
        return qs

    def filter_source_name(self, qs, field_name, value):
        """支持多选的告警源过滤"""
        if value:
            # 支持逗号分隔的多个值
            source_names = [source.strip() for source in value.split(',')]
            return qs.filter(source_name__in=source_names)
        return qs

    def filter_incident(self, qs, field_name, value):
        """过滤是否有事故"""
        if value.lower() == "true":
            return qs.filter(incident__isnull=False)
        elif value.lower() == "false":
            return qs.filter(incident__isnull=True)
        return qs
