from django_filters import FilterSet, CharFilter, DateTimeFilter, BooleanFilter

from apps.mlops.models.timeseries_predict_train_data import TimeSeriesPredictTrainData


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