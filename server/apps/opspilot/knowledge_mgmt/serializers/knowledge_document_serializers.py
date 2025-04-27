from rest_framework import serializers

from apps.opspilot.models import KnowledgeDocument


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    train_status_display = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeDocument
        fields = "__all__"

    @staticmethod
    def get_train_status_display(obj):
        return obj.get_train_status_display()
