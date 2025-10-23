from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.log_clustering import *


class LogClusteringDatasetSerializer(AuthSerializer):
    """日志聚类数据集序列化器"""
    permission_key = "dataset.log_clustering_dataset"

    class Meta:
        model = LogClusteringDataset
        fields = "__all__"


class LogClusteringTrainDataSerializer(AuthSerializer):
    """日志聚类训练数据序列化器"""
    permission_key = "dataset.log_clustering_train_data"

    class Meta:
        model = LogClusteringTrainData
        fields = "__all__"


class LogClusteringTrainJobSerializer(AuthSerializer):
    """日志聚类训练任务序列化器"""
    permission_key = "dataset.log_clustering_train_job"

    class Meta:
        model = LogClusteringTrainJob
        fields = "__all__"


class LogClusteringTrainHistorySerializer(AuthSerializer):
    """日志聚类训练历史序列化器"""
    permission_key = "dataset.log_clustering_train_history"

    class Meta:
        model = LogClusteringTrainHistory
        fields = "__all__"


class LogClusteringServingSerializer(AuthSerializer):
    """日志聚类服务序列化器"""
    permission_key = "dataset.log_clustering_serving"

    class Meta:
        model = LogClusteringServing
        fields = "__all__"
