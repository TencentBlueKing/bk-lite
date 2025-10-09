from django_filters import FilterSet, CharFilter, DateTimeFilter
from django_filters import FilterSet, CharFilter, BooleanFilter, NumberFilter
from apps.mlops.models.anomaly_detection import *


class AnomalyDetectionDatasetFilter(FilterSet):
    """异常检测数据集过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="数据集名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = AnomalyDetectionDataset
        fields = ["name", "created_by"]


class AnomalyDetectionTrainJobFilter(FilterSet):
    class Meta:
        model = AnomalyDetectionTrainJob
        fields = {
            "name": ["exact", "icontains"],
            "status": ["exact"],
            "algorithm": ["exact"],
        }


class AnomalyDetectionTrainDataFilter(FilterSet):
    """异常检测训练数据过滤器"""

    name = CharFilter(field_name="name", lookup_expr="icontains", label="训练数据名称")
    dataset = NumberFilter(field_name="dataset__id", label="数据集ID")
    dataset_name = CharFilter(field_name="dataset__name", lookup_expr="icontains", label="数据集名称")
    is_train_data = BooleanFilter(field_name="is_train_data", label="是否为训练数据")
    is_val_data = BooleanFilter(field_name="is_val_data", label="是否为验证数据")
    is_test_data = BooleanFilter(field_name="is_test_data", label="是否为测试数据")

    class Meta:
        model = AnomalyDetectionTrainData
        fields = [
            "name", "dataset", "dataset_name",
            "is_train_data", "is_val_data", "is_test_data"
        ]


class AnomalyDetectionServingFilter(FilterSet):
    """异常检测服务过滤器"""

    class Meta:
        model = AnomalyDetectionServing
        fields = {
            "name": ["exact", "icontains"],
            "anomaly_detection_train_job": ["exact"],
            "status": ["exact"],
        }
