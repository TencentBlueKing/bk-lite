from rest_framework import serializers

from apps.opspilot.models import ManualKnowledge


class ManualKnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManualKnowledge
        fields = "__all__"
