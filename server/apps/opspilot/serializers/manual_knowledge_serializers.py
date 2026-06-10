from rest_framework import serializers

from apps.opspilot.models import ManualKnowledge


class ManualKnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualKnowledge
        fields = ["id", "content", "knowledge_document"]
