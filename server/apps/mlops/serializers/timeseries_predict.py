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


class TimeSeriesPredictServingSerializer(AuthSerializer):
    """时间序列预测服务序列化器"""
    permission_key = "dataset.timeseries_predict_serving"

    class Meta:
        model = TimeSeriesPredictServing
        fields = "__all__"
