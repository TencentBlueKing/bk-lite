from django_filters import FilterSet, CharFilter, DateTimeFilter, ChoiceFilter

from apps.mlops.models.timeseries_predict_train_history import TimeSeriesPredictTrainHistory


class TimeSeriesPredictTrainHistoryFilter(FilterSet):
    """时间序列预测训练历史过滤器"""
    
    algorithm = ChoiceFilter(
        field_name="algorithm",
        choices=TimeSeriesPredictTrainHistory._meta.get_field('algorithm').choices,
        label="算法模型"
    )
    status = ChoiceFilter(
        field_name="status",
        choices=TimeSeriesPredictTrainHistory._meta.get_field('status').choices,
        label="任务状态"
    )
    train_data_id__name = CharFilter(field_name="train_data_id__name", lookup_expr="icontains", label="训练数据名称")
    val_data_id__name = CharFilter(field_name="val_data_id__name", lookup_expr="icontains", label="验证数据名称")
    test_data_id__name = CharFilter(field_name="test_data_id__name", lookup_expr="icontains", label="测试数据名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = TimeSeriesPredictTrainHistory
        fields = ["algorithm", "status", "train_data_id", "val_data_id", "test_data_id", "created_by"]