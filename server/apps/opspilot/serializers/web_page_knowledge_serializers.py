from rest_framework import serializers

from apps.opspilot.models import WebPageKnowledge


class WebPageKnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebPageKnowledge
        fields = [
            "id",
            "url",
            "knowledge_document",
            "max_depth",
            "sync_enabled",
            "sync_time",
            "last_run_time",
        ]
