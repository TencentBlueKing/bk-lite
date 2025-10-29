from apps.mlops.models.rasa import *
from django_filters.rest_framework import FilterSet
import django_filters


class RasaDatasetFilter(FilterSet):
    """Rasa机器人数据集"""

    class Meta:
        model = RasaDatasets
        fields = {
            "name": ["exact", "icontains"],
        }


class RasaStoryFilter(FilterSet):
    class Meta:
        model = RasaStory
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }


class RasaSlotFilter(FilterSet):
    class Meta:
        model = RasaSlot
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }


class RasaRuleFilter(FilterSet):
    """
    Rasa机器人规则过滤器
    """
    class Meta:
        model = RasaRule
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }


class RasaResponseFilter(FilterSet):
    """
    Rasa机器人响应过滤器
    """
    class Meta:
        model = RasaResponse
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }


class RasaPipelineFilter(django_filters.FilterSet):
    """Rasa训练管道过滤器"""

    # 基本字段过滤
    name = django_filters.CharFilter(lookup_expr='icontains', help_text="管道名称（支持模糊搜索）")
    name_exact = django_filters.CharFilter(field_name='name', lookup_expr='exact', help_text="管道名称（精确匹配）")
    description = django_filters.CharFilter(lookup_expr='icontains', help_text="描述（支持模糊搜索）")

    # 关联数据集过滤
    dataset = django_filters.NumberFilter(field_name='datasets__id', help_text="关联的数据集ID")
    dataset_name = django_filters.CharFilter(field_name='datasets__name', lookup_expr='icontains', help_text="关联的数据集名称（模糊搜索）")
    datasets = django_filters.CharFilter(method='filter_datasets', help_text="多个数据集ID，用逗号分隔")

    # 时间范围过滤
    created_at = django_filters.DateTimeFromToRangeFilter(help_text="创建时间范围")
    updated_at = django_filters.DateTimeFromToRangeFilter(help_text="更新时间范围")

    # 创建者过滤
    created_by = django_filters.CharFilter(lookup_expr='icontains', help_text="创建者（模糊搜索）")
    updated_by = django_filters.CharFilter(lookup_expr='icontains', help_text="更新者（模糊搜索）")
    domain = django_filters.CharFilter(lookup_expr='exact', help_text="域名")

    # 自定义过滤方法
    has_datasets = django_filters.BooleanFilter(method='filter_has_datasets', help_text="是否关联了数据集")
    dataset_count = django_filters.NumberFilter(method='filter_dataset_count', help_text="关联数据集数量")
    dataset_count_gte = django_filters.NumberFilter(method='filter_dataset_count_gte', help_text="关联数据集数量大于等于")
    dataset_count_lte = django_filters.NumberFilter(method='filter_dataset_count_lte', help_text="关联数据集数量小于等于")

    # 配置相关过滤
    has_config = django_filters.BooleanFilter(method='filter_has_config', help_text="是否有配置")
    config_contains = django_filters.CharFilter(method='filter_config_contains', help_text="配置中包含的文本")

    class Meta:
        model = RasaPipeline
        fields = [
            'name', 'name_exact', 'description', 'dataset', 'dataset_name', 'datasets',
            'created_at', 'updated_at', 'created_by', 'updated_by', 'domain',
            'has_datasets', 'dataset_count', 'dataset_count_gte', 'dataset_count_lte',
            'has_config', 'config_contains'
        ]

    def filter_datasets(self, queryset, name, value):
        """
        支持多个数据集ID过滤
        参数格式: datasets=1,2,3 或 datasets=1
        """
        if not value:
            return queryset

        try:
            dataset_ids = [int(dataset_id.strip()) for dataset_id in value.split(',') if dataset_id.strip()]
            if dataset_ids:
                return queryset.filter(datasets__id__in=dataset_ids).distinct()
        except ValueError:
            # 如果转换失败，返回空结果
            return queryset.none()

        return queryset

    def filter_has_datasets(self, queryset, name, value):
        """
        过滤是否关联了数据集
        """
        if value is True:
            return queryset.filter(datasets__isnull=False).distinct()
        elif value is False:
            return queryset.filter(datasets__isnull=True)
        return queryset

    def filter_dataset_count(self, queryset, name, value):
        """
        过滤关联数据集的数量（精确匹配）
        """
        if value is not None:
            # 使用 annotations 来计算数据集数量
            from django.db.models import Count
            queryset = queryset.annotate(dataset_count=Count('datasets'))
            return queryset.filter(dataset_count=value)
        return queryset

    def filter_dataset_count_gte(self, queryset, name, value):
        """
        过滤关联数据集数量大于等于指定值
        """
        if value is not None:
            from django.db.models import Count
            queryset = queryset.annotate(dataset_count=Count('datasets'))
            return queryset.filter(dataset_count__gte=value)
        return queryset

    def filter_dataset_count_lte(self, queryset, name, value):
        """
        过滤关联数据集数量小于等于指定值
        """
        if value is not None:
            from django.db.models import Count
            queryset = queryset.annotate(dataset_count=Count('datasets'))
            return queryset.filter(dataset_count__lte=value)
        return queryset

    def filter_has_config(self, queryset, name, value):
        """
        过滤是否有配置
        """
        if value is True:
            # 配置不为空且不为 {}
            return queryset.exclude(Q(config__isnull=True) | Q(config={}))
        elif value is False:
            # 配置为空或为 {}
            return queryset.filter(Q(config__isnull=True) | Q(config={}))
        return queryset

    def filter_config_contains(self, queryset, name, value):
        """
        搜索配置中包含的文本
        将配置转为字符串进行搜索
        """
        if not value:
            return queryset

        # 在PostgreSQL中可以使用JSONField的搜索功能
        # 这里使用简单的字符串包含搜索
        from django.db.models import Q
        return queryset.extra(
            where=["CAST(config AS TEXT) LIKE %s"],
            params=[f'%{value}%']
        )


class RasaPipelineSimpleFilter(django_filters.FilterSet):
    """
    简化的管道过滤器，用于选择列表等场景
    """
    name = django_filters.CharFilter(lookup_expr='icontains')
    has_datasets = django_filters.BooleanFilter(method='filter_has_datasets')

    class Meta:
        model = RasaPipeline
        fields = ['name', 'has_datasets']

    def filter_has_datasets(self, queryset, name, value):
        """过滤是否关联了数据集"""
        if value is True:
            return queryset.filter(datasets__isnull=False).distinct()
        elif value is False:
            return queryset.filter(datasets__isnull=True)
        return queryset


class RasaFormFilter(FilterSet):
    class Meta:
        model = RasaForm
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }


class RasaEntityFilter(FilterSet):
    class Meta:
        model = RasaEntity
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
            "entity_type": ["exact"],
        }


class RasaActionFilter(FilterSet):
    class Meta:
        model = RasaAction
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }


class RasaIntentFilter(FilterSet):
    class Meta:
        model = RasaIntent
        fields = {
            "dataset": ["exact"],
            "name": ["exact", "icontains"],
        }
