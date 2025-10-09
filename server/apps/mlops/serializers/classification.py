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