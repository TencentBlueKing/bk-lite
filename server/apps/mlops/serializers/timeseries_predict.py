from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.timeseries_predict import *


class TimeSeriesPredictDatasetSerializer(AuthSerializer):
    """时间序列预测数据集序列化器"""
    permission_key = "dataset.timeseries_predict_dataset"

    class Meta:
        model = TimeSeriesPredictDataset
        fields = "__all__"


class TimeSeriesPredictTrainJobSerializer(AuthSerializer):
    """时间序列预测训练任务序列化器"""
    permission_key = "dataset.timeseries_predict_train_job"

    class Meta:
        model = TimeSeriesPredictTrainJob
        fields = "__all__"


class TimeSeriesPredictTrainHistorySerializer(AuthSerializer):
    """时间序列预测训练历史序列化器"""
    permission_key = "dataset.timeseries_predict_train_history"

    class Meta:
        model = TimeSeriesPredictTrainHistory
        fields = "__all__"


class TimeSeriesPredictTrainDataSerializer(AuthSerializer):
    """时间序列预测训练数据序列化器"""
    permission_key = "dataset.timeseries_predict_train_data"

    class Meta:
        model = TimeSeriesPredictTrainData
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """
        初始化序列化器，从请求上下文中获取 include_train_data 参数
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.include_train_data = request.query_params.get('include_train_data', 'false').lower() == 'true'
            self.include_metadata = request.query_params.get('include_metadata', 'false').lower() == 'true'
        else:
            self.include_train_data = False
            self.include_metadata = False

    def to_representation(self, instance):
        """
        自定义返回数据，根据 include_train_data 参数动态控制 train_data 字段
        """
        representation = super().to_representation(instance)
        if not self.include_train_data:
            representation.pop("train_data", None)  # 移除 train_data 字段
        if not self.include_metadata:
            representation.pop("metadata", None)  # 移除 metadata 字段
        return representation

class TimeSeriesPredictServingSerializer(AuthSerializer):
    """时间序列预测服务序列化器"""
    permission_key = "dataset.timeseries_predict_serving"

    class Meta:
        model = TimeSeriesPredictServing
        fields = "__all__"
