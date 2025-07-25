from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.knowledge_mgmt.models import KnowledgeGraph
from apps.opspilot.tasks import create_graph, update_graph


class KnowledgeGraphSerializer(UsernameSerializer):
    class Meta:
        model = KnowledgeGraph
        fields = "__all__"

    def create(self, validated_data):
        instance = super().create(validated_data)
        create_graph.delay(instance.id)
        return instance

    def update(self, instance, validated_data):
        old_doc_list = instance.doc_list[:]
        instance = super().update(instance, validated_data)
        update_graph.delay(instance.id, old_doc_list)
        return instance
