from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.enum import DocumentStatus
from apps.opspilot.models import KnowledgeBase, KnowledgeDocument


class KnowledgeBaseSerializer(TeamSerializer, AuthSerializer):
    permission_key = "knowledge"

    is_training = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBase
        fields = "__all__"

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self.training_document = list(
            KnowledgeDocument.objects.filter(train_status=DocumentStatus.TRAINING).values_list("knowledge_base_id", flat=True).distinct()
        )

    def get_is_training(self, instance: KnowledgeBase):
        return instance.id in self.training_document
