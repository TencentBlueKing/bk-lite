from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification_dataset import ClassificationDataset


class ClassificationDatasetSerializer(AuthSerializer):
    """分类任务数据集序列化器"""
    permission_key = "dataset.classification_dataset"
    
    class Meta:
        model = ClassificationDataset
        fields = "__all__"