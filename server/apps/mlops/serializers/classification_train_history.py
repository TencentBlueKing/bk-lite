from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification_train_history import ClassificationTrainHistory


class ClassificationTrainHistorySerializer(AuthSerializer):
    """分类任务训练历史记录序列化器"""
    permission_key = "dataset.classification_train_history"
    
    class Meta:
        model = ClassificationTrainHistory
        fields = "__all__"