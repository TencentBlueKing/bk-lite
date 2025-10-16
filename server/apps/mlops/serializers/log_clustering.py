from django_filters import FilterSet, CharFilter, DateTimeFilter, ChoiceFilter, NumberFilter, BooleanFilter
from apps.mlops.models.log_clustering import *


class LogClusteringDatasetFilter(FilterSet):
    """日志聚类数据集过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="数据集名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = LogClusteringDataset
        fields = ["name", "created_by"]


class LogClusteringTrainJobFilter(FilterSet):
    """日志聚类训练任务过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="任务名称")
    status = ChoiceFilter(
        field_name="status",
        choices=LogClusteringTrainJob._meta.get_field('status').choices,
        label="任务状态"
    )
    algorithm = ChoiceFilter(
        field_name="algorithm",
        choices=LogClusteringTrainJob._meta.get_field('algorithm').choices,
        label="算法模型"
    )
    train_data_id__name = CharFilter(field_name="train_data_id__name", lookup_expr="icontains", label="训练数据名称")
    cluster_count_min = NumberFilter(field_name="cluster_count", lookup_expr="gte", label="最小聚类数量")
    cluster_count_max = NumberFilter(field_name="cluster_count", lookup_expr="lte", label="最大聚类数量")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = LogClusteringTrainJob
        fields = ["name", "status", "algorithm", "train_data_id", "cluster_count", "created_by"]


class LogClusteringTrainHistoryFilter(FilterSet):
    """日志聚类训练历史过滤器"""

    algorithm = ChoiceFilter(
        field_name="algorithm",
        choices=LogClusteringTrainHistory._meta.get_field('algorithm').choices,
        label="算法模型"
    )
    status = ChoiceFilter(
        field_name="status",
        choices=LogClusteringTrainHistory._meta.get_field('status').choices,
        label="任务状态"
    )
    train_data_id__name = CharFilter(field_name="train_data_id__name", lookup_expr="icontains", label="训练数据名称")
    val_data_id__name = CharFilter(field_name="val_data_id__name", lookup_expr="icontains", label="验证数据名称")
    test_data_id__name = CharFilter(field_name="test_data_id__name", lookup_expr="icontains", label="测试数据名称")
    cluster_count_min = NumberFilter(field_name="cluster_count", lookup_expr="gte", label="最小聚类数量")
    cluster_count_max = NumberFilter(field_name="cluster_count", lookup_expr="lte", label="最大聚类数量")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = LogClusteringTrainHistory
        fields = ["algorithm", "status", "train_data_id", "val_data_id", "test_data_id", "cluster_count", "created_by"]


class LogClusteringTrainDataFilter(FilterSet):
    """日志聚类训练数据过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="训练数据名称")
    dataset__name = CharFilter(field_name="dataset__name", lookup_expr="icontains", label="数据集名称")
    is_train_data = BooleanFilter(field_name="is_train_data", label="是否为训练数据")
    is_val_data = BooleanFilter(field_name="is_val_data", label="是否为验证数据")
    is_test_data = BooleanFilter(field_name="is_test_data", label="是否为测试数据")
    log_count_min = NumberFilter(field_name="log_count", lookup_expr="gte", label="最小日志条数")
    log_count_max = NumberFilter(field_name="log_count", lookup_expr="lte", label="最大日志条数")
    log_source = CharFilter(field_name="log_source", lookup_expr="icontains", label="日志来源")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = LogClusteringTrainData
        fields = ["name", "dataset", "is_train_data", "is_val_data", "is_test_data", "log_count", "log_source", "created_by"]


class LogClusteringServingFilter(FilterSet):
    """日志聚类服务过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="服务名称")
    status = ChoiceFilter(
        field_name="status",
        choices=LogClusteringServing._meta.get_field('status').choices,
        label="服务状态"
    )
    model_version = CharFilter(field_name="model_version", lookup_expr="icontains", label="模型版本")
    log_clustering_train_job__name = CharFilter(
        field_name="log_clustering_train_job__name",
        lookup_expr="icontains",
        label="训练任务名称"
    )
    api_endpoint = CharFilter(field_name="api_endpoint", lookup_expr="icontains", label="API端点")
    max_requests_per_minute_min = NumberFilter(field_name="max_requests_per_minute", lookup_expr="gte", label="最小请求频率")
    max_requests_per_minute_max = NumberFilter(field_name="max_requests_per_minute", lookup_expr="lte", label="最大请求频率")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = LogClusteringServing
        fields = ["name", "status", "model_version", "log_clustering_train_job", "api_endpoint", "max_requests_per_minute", "created_by"]
