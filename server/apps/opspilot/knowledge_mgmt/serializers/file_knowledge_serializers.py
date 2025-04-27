from rest_framework import serializers

from apps.opspilot.models import FileKnowledge


class FileKnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileKnowledge
        fields = "__all__"
