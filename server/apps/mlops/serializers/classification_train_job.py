from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification_train_job import ClassificationTrainJob


class ClassificationTrainJobSerializer(AuthSerializer):
    """分类任务训练作业序列化器"""
    permission_key = "dataset.classification_train_job"
    
    class Meta:
        model = ClassificationTrainJob
        fields = "__all__"