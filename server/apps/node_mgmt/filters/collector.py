from django_filters import rest_framework as filters
from apps.node_mgmt.models.sidecar import Collector


class CollectorFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains', label='采集器名称')
    node_operating_system = filters.CharFilter(field_name='node_operating_system', lookup_expr='exact',
                                               label='操作系统')
    tags = filters.CharFilter(method='filter_tags', label='标签')

    class Meta:
        model = Collector
        fields = ['name', 'node_operating_system', 'tags']

    def filter_tags(self, queryset, name, value):
        """
        支持按标签过滤（精确匹配，AND 逻辑）
        - 单个标签: ?tags=tag1
        - 多个标签(逗号分隔，全部匹配): ?tags=tag1,tag2

        注意：使用精确匹配，避免 "aabb" 匹配到 "aabbc"
        性能优化：只查询 id 和 tags 字段，减少内存占用
        """
        if not value:
            return queryset

        # 支持逗号分隔的多个标签
        tags_list = [tag.strip() for tag in value.split(',') if tag.strip()]

        if not tags_list:
            return queryset

        # 性能优化：只查询需要的字段（id 和 tags），而不是加载完整对象
        matching_ids = []
        for collector_id, collector_tags in queryset.values_list('id', 'tags'):
            if collector_tags is None:
                collector_tags = []
            # 检查是否所有查询标签都在采集器的标签列表中（精确匹配，AND 逻辑）
            if all(tag in collector_tags for tag in tags_list):
                matching_ids.append(collector_id)

        # 如果没有匹配，返回空查询集
        if not matching_ids:
            return queryset.none()

        return queryset.filter(id__in=matching_ids)
