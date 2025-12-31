from django_filters import FilterSet, CharFilter, DateTimeFilter, ChoiceFilter, BooleanFilter
from apps.mlops.models.timeseries_predict import *


class TimeSeriesPredictDatasetFilter(FilterSet):
    """时间序列预测数据集过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="数据集名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = TimeSeriesPredictDataset
        fields = ["name", "created_by"]


class TimeSeriesPredictTrainJobFilter(FilterSet):
    """时间序列预测训练任务过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="任务名称")
    status = ChoiceFilter(
        field_name="status",
        choices=TimeSeriesPredictTrainJob._meta.get_field('status').choices,
        label="任务状态"
    )
    algorithm = ChoiceFilter(
        field_name="algorithm",
        choices=TimeSeriesPredictTrainJob._meta.get_field('algorithm').choices,
        label="算法模型"
    )
    dataset_version__version = CharFilter(field_name="dataset_version__version", lookup_expr="icontains", label="数据集版本号")
    dataset_version__dataset__name = CharFilter(field_name="dataset_version__dataset__name", lookup_expr="icontains", label="数据集名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = TimeSeriesPredictTrainJob
        fields = ["name", "status", "algorithm", "dataset_version", "created_by"]


class TimeSeriesPredictTrainDataFilter(FilterSet):
    """时间序列预测训练数据过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="训练数据名称")
    dataset__name = CharFilter(field_name="dataset__name", lookup_expr="icontains", label="数据集名称")
    is_train_data = BooleanFilter(field_name="is_train_data", label="是否为训练数据")
    is_val_data = BooleanFilter(field_name="is_val_data", label="是否为验证数据")
    is_test_data = BooleanFilter(field_name="is_test_data", label="是否为测试数据")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = TimeSeriesPredictTrainData
        fields = ["name", "dataset", "is_train_data", "is_val_data", "is_test_data", "created_by"]


class TimeSeriesPredictServingFilter(FilterSet):
    """时间序列预测服务过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="服务名称")
    status = ChoiceFilter(
        field_name="status",
        choices=TimeSeriesPredictServing._meta.get_field('status').choices,
        label="服务状态"
    )
    model_version = CharFilter(field_name="model_version", lookup_expr="icontains", label="模型版本")
    time_series_predict_train_job__name = CharFilter(
        field_name="time_series_predict_train_job__name",
        lookup_expr="icontains",
        label="训练任务名称"
    )
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = TimeSeriesPredictServing
        fields = ["name", "status", "model_version", "time_series_predict_train_job", "created_by"]


class TimeSeriesPredictDatasetReleaseFilter(FilterSet):
    """时间序列预测数据集发布版本过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="发布版本名称")
    version = CharFilter(field_name="version", lookup_expr="icontains", label="版本号")
    status = ChoiceFilter(
        field_name="status",
        choices=TimeSeriesPredictDatasetRelease._meta.get_field('status').choices,
        label="发布状态"
    )
    dataset__name = CharFilter(field_name="dataset__name", lookup_expr="icontains", label="数据集名称")
    dataset = CharFilter(field_name="dataset", label="数据集ID")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = TimeSeriesPredictDatasetRelease
        fields = ["name", "version", "status", "dataset", "created_by"]
