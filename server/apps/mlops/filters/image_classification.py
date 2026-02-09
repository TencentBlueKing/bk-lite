from django_filters import (
    BooleanFilter,
    CharFilter,
    ChoiceFilter,
    DateTimeFilter,
    FilterSet,
    NumberFilter,
)
from django_filters.filters import DateFromToRangeFilter

from apps.mlops.models.image_classification import *


class ImageClassificationDatasetFilter(FilterSet):
    """图片分类数据集过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="数据集名称")
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建者名称"
    )
    created_at_start = DateTimeFilter(
        field_name="created_at", lookup_expr="gte", label="创建时间开始"
    )
    created_at_end = DateTimeFilter(
        field_name="created_at", lookup_expr="lte", label="创建时间结束"
    )

    class Meta:
        model = ImageClassificationDataset
        fields = ["name", "created_by"]


class ImageClassificationTrainDataFilter(FilterSet):
    """图片分类训练数据过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="训练数据名称")
    dataset = NumberFilter(field_name="dataset__id", label="数据集ID")
    dataset__name = CharFilter(
        field_name="dataset__name", lookup_expr="icontains", label="数据集名称"
    )
    is_train_data = BooleanFilter(field_name="is_train_data", label="是否为训练数据")
    is_val_data = BooleanFilter(field_name="is_val_data", label="是否为验证数据")
    is_test_data = BooleanFilter(field_name="is_test_data", label="是否为测试数据")
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建者"
    )
    created_at_start = DateTimeFilter(
        field_name="created_at", lookup_expr="gte", label="创建时间开始"
    )
    created_at_end = DateTimeFilter(
        field_name="created_at", lookup_expr="lte", label="创建时间结束"
    )

    class Meta:
        model = ImageClassificationTrainData
        fields = [
            "name",
            "dataset",
            "is_train_data",
            "is_val_data",
            "is_test_data",
            "created_by",
        ]


class ImageClassificationDatasetReleaseFilter(FilterSet):
    """图片分类数据集发布版本过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="版本名称")
    version = CharFilter(field_name="version", lookup_expr="icontains", label="版本号")
    dataset = NumberFilter(field_name="dataset__id", label="数据集ID")
    dataset__name = CharFilter(
        field_name="dataset__name", lookup_expr="icontains", label="数据集名称"
    )
    status = ChoiceFilter(
        field_name="status",
        choices=[
            ("pending", "待发布"),
            ("published", "已发布"),
            ("failed", "发布失败"),
            ("archived", "归档"),
        ],
        label="发布状态",
    )
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建者"
    )
    created_at = DateFromToRangeFilter(field_name="created_at", label="创建时间范围")

    class Meta:
        model = ImageClassificationDatasetRelease
        fields = ["name", "version", "dataset", "status", "created_by"]


class ImageClassificationTrainJobFilter(FilterSet):
    """图片分类训练任务过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="任务名称")
    algorithm = CharFilter(
        field_name="algorithm", lookup_expr="exact", label="算法模型"
    )
    status = ChoiceFilter(
        field_name="status",
        choices=[
            ("pending", "待训练"),
            ("running", "训练中"),
            ("completed", "已完成"),
            ("failed", "训练失败"),
        ],
        label="任务状态",
    )
    dataset_version = NumberFilter(
        field_name="dataset_version__id", label="数据集版本ID"
    )
    dataset__name = CharFilter(
        field_name="dataset_version__dataset__name",
        lookup_expr="icontains",
        label="数据集名称",
    )
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建者"
    )
    created_at = DateFromToRangeFilter(field_name="created_at", label="创建时间范围")

    class Meta:
        model = ImageClassificationTrainJob
        fields = ["name", "algorithm", "status", "dataset_version", "created_by"]


class ImageClassificationServingFilter(FilterSet):
    """图片分类服务过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="服务名称")
    train_job = NumberFilter(field_name="train_job__id", label="训练任务ID")
    train_job__name = CharFilter(
        field_name="train_job__name", lookup_expr="icontains", label="训练任务名称"
    )
    train_job__algorithm = CharFilter(
        field_name="train_job__algorithm",
        lookup_expr="exact",
        label="算法模型",
    )
    status = ChoiceFilter(
        field_name="status",
        choices=[("active", "Active"), ("inactive", "Inactive")],
        label="服务状态",
    )
    port = NumberFilter(field_name="port", label="服务端口")
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建者"
    )
    created_at = DateFromToRangeFilter(field_name="created_at", label="创建时间范围")

    class Meta:
        model = ImageClassificationServing
        fields = ["name", "train_job", "status", "port", "created_by"]
