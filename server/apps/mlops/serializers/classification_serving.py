from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification_serving import ClassificationServing


class ClassificationServingSerializer(AuthSerializer):
    """分类任务服务序列化器"""
    permission_key = "dataset.classification_serving"
    
    class Meta:
        model = ClassificationServing
        fields = "__all__"