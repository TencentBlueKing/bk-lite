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
