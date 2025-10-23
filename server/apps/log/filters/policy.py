import django_filters
from apps.log.models.policy import Policy, Alert, Event, EventRawData


class PolicyFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    alert_type = django_filters.CharFilter(lookup_expr='exact')
    alert_level = django_filters.CharFilter(lookup_expr='exact')
    collect_type = django_filters.NumberFilter(field_name='collect_type__id')
    notice = django_filters.BooleanFilter()
    created_by = django_filters.CharFilter(lookup_expr='icontains')
    created_at = django_filters.DateTimeFromToRangeFilter()

    class Meta:
        model = Policy
        fields = ['name', 'alert_type', 'alert_level', 'collect_type', 'notice', 'created_by', 'created_at']


class AlertFilter(django_filters.FilterSet):
    policy = django_filters.NumberFilter(field_name='policy__id')
    policy_name = django_filters.CharFilter(field_name='policy__name', lookup_expr='icontains')
    collect_type = django_filters.NumberFilter(field_name='collect_type__id', required=False)
    level = django_filters.CharFilter(lookup_expr='exact')
    levels = django_filters.CharFilter(method='filter_levels')  # 支持多选级别
    status = django_filters.CharFilter(lookup_expr='exact')
    source_id = django_filters.CharFilter(lookup_expr='icontains')
    content = django_filters.CharFilter(lookup_expr='icontains')  # 支持内容搜索
    start_event_time = django_filters.DateTimeFromToRangeFilter()
    end_event_time = django_filters.DateTimeFromToRangeFilter()
    created_at = django_filters.DateTimeFromToRangeFilter()

    class Meta:
        model = Alert
        fields = ['policy', 'policy_name', 'collect_type', 'level', 'levels', 'status', 'source_id', 'content',
                 'start_event_time', 'end_event_time', 'created_at']

    def filter_levels(self, queryset, name, value):
        """
        支持告警级别多选过滤
        参数格式: levels=critical,warning,info 或 levels=critical
        """
        if not value:
            return queryset
        
        level_list = [level.strip() for level in value.split(',') if level.strip()]
        if level_list:
            return queryset.filter(level__in=level_list)
        return queryset


class EventFilter(django_filters.FilterSet):
    policy = django_filters.NumberFilter(field_name='policy__id')
    alert = django_filters.CharFilter(field_name='alert__id')
    alert_id = django_filters.CharFilter(field_name='alert__id')  # 添加 alert_id 作为别名，使接口更清晰
    source_id = django_filters.CharFilter(lookup_expr='icontains')
    level = django_filters.CharFilter(lookup_expr='exact')
    event_time = django_filters.DateTimeFromToRangeFilter()
    created_at = django_filters.DateTimeFromToRangeFilter()

    class Meta:
        model = Event
        fields = ['policy', 'alert', 'alert_id', 'source_id', 'level', 'event_time', 'created_at']


class EventRawDataFilter(django_filters.FilterSet):
    event_id = django_filters.CharFilter(field_name='event__id')

    class Meta:
        model = EventRawData
        fields = ['event_id']
