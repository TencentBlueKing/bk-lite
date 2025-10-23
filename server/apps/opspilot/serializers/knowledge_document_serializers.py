from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.serializers import UsernameSerializer
from apps.opspilot.models import KnowledgeDocument, WebPageKnowledge


class KnowledgeDocumentSerializer(UsernameSerializer):
    train_status_display = serializers.SerializerMethodField()
    sync_enabled = serializers.SerializerMethodField()
    sync_time = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeDocument
        fields = "__all__"

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)

        if isinstance(instance, KnowledgeDocument):
            document_list = [instance.id]
        elif instance is None:
            document_list = []
        else:
            document_list = [i.id for i in instance if i.knowledge_source_type == "web_page"]

        web_page_doc_list = WebPageKnowledge.objects.filter(knowledge_document__in=document_list).values(
            "knowledge_document_id", "sync_enabled", "sync_time"
        )
        self.web_page_doc_map = {i["knowledge_document_id"]: i for i in web_page_doc_list}

    @staticmethod
    def get_train_status_display(obj):
        return obj.get_train_status_display()

    def get_sync_enabled(self, obj):
        if obj.knowledge_source_type == "web_page":
            return self.web_page_doc_map.get(obj.id, {}).get("sync_enabled", False)
        return False

    def get_sync_time(self, obj):
        if obj.knowledge_source_type == "web_page":
            return self.web_page_doc_map.get(obj.id, {}).get("sync_time", "")
        return ""
