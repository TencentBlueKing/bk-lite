from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification_train_data import ClassificationTrainData


class ClassificationTrainDataSerializer(AuthSerializer):
    """分类任务训练数据序列化器"""
    permission_key = "dataset.classification_train_data"
    
    class Meta:
        model = ClassificationTrainData
        fields = "__all__"