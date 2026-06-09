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
        fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "introduction",
            "team",
            "embed_model",
            "enable_rerank",
            "rerank_top_k",
            "rerank_model",
            "search_type",
            "score_threshold",
            "enable_naive_rag",
            "enable_qa_rag",
            "enable_graph_rag",
            "rag_recall_mode",
            "rag_size",
            "qa_size",
            "graph_size",
            # 只读派生字段（保持现有读取输出不变）
            "permissions",
            "team_name",
            "is_training",
        ]

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self.training_document = list(
            KnowledgeDocument.objects.filter(train_status=DocumentStatus.TRAINING).values_list("knowledge_base_id", flat=True).distinct()
        )

    def get_is_training(self, instance: KnowledgeBase):
        return instance.id in self.training_document
