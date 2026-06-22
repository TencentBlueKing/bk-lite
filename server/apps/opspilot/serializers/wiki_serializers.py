from rest_framework import serializers

from apps.opspilot.models import Material, WikiKnowledgeBase


class WikiKnowledgeBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = WikiKnowledgeBase
        fields = [
            "id",
            "name",
            "introduction",
            "team",
            "purpose_md",
            "schema_md",
            "llm_model",
            "embed_provider",
            "generation_language",
            "generation_rules",
            "web_sync_policy",
            "risk_rules",
            "template_key",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = [
            "id",
            "knowledge_base",
            "name",
            "material_type",
            "url",
            "text_content",
            "content_hash",
            "ai_summary",
            "status",
            "error_message",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "content_hash", "ai_summary", "status", "error_message", "created_by", "created_at", "updated_at"]
