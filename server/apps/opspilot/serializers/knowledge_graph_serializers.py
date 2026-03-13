from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import KnowledgeGraph
from apps.opspilot.tasks import create_graph, update_graph


class KnowledgeGraphSerializer(UsernameSerializer):
    class Meta:
        model = KnowledgeGraph
        fields = "__all__"

    def _get_loader(self):
        request = self.context.get("request") if self.context else None
        user = getattr(request, "user", None)
        locale = getattr(user, "locale", None) or "en"
        return LanguageLoader(app="opspilot", default_lang=locale)

    def create(self, validated_data):
        loader = self._get_loader()
        knowledge_base = validated_data.get("knowledge_base")
        if knowledge_base:
            creating_graph = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base.id, status__in=["pending", "training"]).first()
            if creating_graph:
                message = loader.get("error.knowledge_graph_pending_or_training_no_create") or "Knowledge graph is pending or training, cannot create"
                raise serializers.ValidationError({"message": message})

        validated_data["status"] = "pending"
        instance = super().create(validated_data)
        create_graph.delay(instance.id)
        return instance

    def update(self, instance, validated_data):
        loader = self._get_loader()
        if instance.status in ["pending", "training"]:
            message = loader.get("error.knowledge_graph_pending_or_training_no_update") or "Knowledge graph is pending or training, cannot update"
            raise serializers.ValidationError({"message": message})

        old_doc_list = instance.doc_list[:]
        validated_data["status"] = "pending"
        instance = super().update(instance, validated_data)
        update_graph.delay(instance.id, old_doc_list)
        return instance
