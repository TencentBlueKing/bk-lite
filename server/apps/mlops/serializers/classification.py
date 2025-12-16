from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification import *


class ClassificationDatasetSerializer(AuthSerializer):
    """分类任务数据集序列化器"""
    permission_key = "dataset.classification_dataset"
    
    class Meta:
        model = ClassificationDataset
        fields = "__all__"

class ClassificationServingSerializer(AuthSerializer):
    """分类任务服务序列化器"""
    permission_key = "dataset.classification_serving"
    
    class Meta:
        model = ClassificationServing
        fields = "__all__"

class ClassificationTrainDataSerializer(AuthSerializer):
    """分类任务训练数据序列化器"""
    permission_key = "dataset.classification_train_data"
    
    class Meta:
        model = ClassificationTrainData
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

class ClassificationTrainHistorySerializer(AuthSerializer):
    """分类任务训练历史记录序列化器"""
    permission_key = "dataset.classification_train_history"
    
    class Meta:
        model = ClassificationTrainHistory
        fields = "__all__"

class ClassificationTrainJobSerializer(AuthSerializer):
    """分类任务训练作业序列化器"""
    permission_key = "dataset.classification_train_job"
    
    class Meta:
        model = ClassificationTrainJob
        fields = "__all__"