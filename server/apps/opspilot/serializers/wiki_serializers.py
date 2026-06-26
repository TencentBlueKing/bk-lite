from rest_framework import serializers

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, PageVersion, WikiKnowledgeBase


class WikiKnowledgeBaseSerializer(serializers.ModelSerializer):
    team_name = serializers.SerializerMethodField()

    def get_team_name(self, obj):
        if not obj.team:
            return []
        from apps.system_mgmt.models import Group

        return list(Group.objects.filter(id__in=obj.team).values_list("name", flat=True))

    class Meta:
        model = WikiKnowledgeBase
        fields = [
            "id",
            "name",
            "introduction",
            "team",
            "team_name",
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
            "file",
            "url",
            "sync_policy",
            "text_content",
            "content_hash",
            "ai_summary",
            "status",
            "error_message",
            "created_by",
            "created_at",
            "updated_at",
        ]
        # file 必须可写,否则 multipart 上传的文件会被序列化器丢弃(create 后 file=None,解析必失败)
        read_only_fields = ["id", "content_hash", "ai_summary", "status", "error_message", "created_by", "created_at", "updated_at"]


class KnowledgePageSerializer(serializers.ModelSerializer):
    body = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgePage
        fields = [
            "id",
            "knowledge_base",
            "page_type",
            "title",
            "tags",
            "contribution",
            "update_method",
            "status",
            "current_version",
            "body",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_body(self, obj):
        return obj.current_version.body if obj.current_version_id else ""


class CheckItemSerializer(serializers.ModelSerializer):
    # 涉及页面的标题/正文 与 候选版本正文:供前端展示内容、做「当前 vs 候选」对比,无需逐个再查
    related_pages = serializers.SerializerMethodField()
    candidate = serializers.SerializerMethodField()

    class Meta:
        model = CheckItem
        fields = [
            "id",
            "knowledge_base",
            "check_type",
            "status",
            "related",
            "related_pages",
            "candidate_version",
            "candidate",
            "suggested_actions",
            "created_at",
            "updated_at",
        ]

    def get_related_pages(self, obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        page_ids = related.get("pages", []) or []
        pages = {p.id: p for p in KnowledgePage.objects.filter(id__in=page_ids)}
        result = []
        for pid in page_ids:  # 保持 related 中的顺序
            p = pages.get(pid)
            if not p:
                continue
            cur = p.current_version
            result.append(
                {"id": p.id, "title": p.title, "page_type": p.page_type, "body": (cur.body if cur else "") or ""}
            )
        return result

    def get_candidate(self, obj):
        cand = obj.candidate_version
        if not cand:
            return None
        return {"id": cand.id, "body": cand.body or ""}


class PageVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageVersion
        fields = ["id", "page", "no", "body", "change_type", "is_current", "created_by", "created_at"]


class BuildRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildRecord
        fields = [
            "id",
            "knowledge_base",
            "trigger",
            "operator",
            "inputs",
            "stage",
            "progress",
            "counts",
            "affected_pages",
            "errors",
            "status",
            "created_at",
            "updated_at",
        ]
