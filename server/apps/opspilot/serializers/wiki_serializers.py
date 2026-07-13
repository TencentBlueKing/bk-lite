from rest_framework import serializers

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, PageVersion, WikiKnowledgeBase
from apps.opspilot.services.wiki.index_status_service import page_index_detail


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
            "vision_model",
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
            "ocr_enhance",
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
    index_status = serializers.SerializerMethodField()
    chunk_index_status = serializers.SerializerMethodField()
    index_detail = serializers.SerializerMethodField()

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
            "index_status",
            "chunk_index_status",
            "index_detail",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_body(self, obj):
        return obj.current_version.body if obj.current_version_id else ""

    def _index_detail(self, obj):
        cache = self.context.setdefault("_wiki_index_detail_cache", {})
        if obj.id not in cache:
            cache[obj.id] = page_index_detail(obj, failure_lookup=self.context.get("index_failure_lookup"))
        return cache[obj.id]

    def get_index_status(self, obj):
        return self._index_detail(obj)["page_embedding"]["status"]

    def get_chunk_index_status(self, obj):
        return self._index_detail(obj)["chunk_embedding"]["status"]

    def get_index_detail(self, obj):
        return self._index_detail(obj)


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
            "assignee",
            "due_at",
            "action_type",
            # phase 3: 决策中心字段,前端用 decision_key 查 WikiDecisionRule,
            # decision_context 展示来源快照
            "decision_key",
            "decision_context",
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
            result.append({"id": p.id, "title": p.title, "page_type": p.page_type, "body": (cur.body if cur else "") or ""})
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
    # 输入资料的人性化名称(替代直接暴露 {"material_id":5} 这类 JSON)
    input_label = serializers.SerializerMethodField()
    affected_page_details = serializers.SerializerMethodField()

    class Meta:
        model = BuildRecord
        fields = [
            "id",
            "knowledge_base",
            "trigger",
            "operator",
            "inputs",
            "input_label",
            "stage",
            "progress",
            "counts",
            "affected_pages",
            "affected_page_details",
            "errors",
            "maintenance",
            "status",
            "created_at",
            "updated_at",
        ]

    def get_input_label(self, obj):
        """输入资料名:优先取 inputs 内已存的资料名;否则按 material_id 查库,资料已删除则回退 #id;整库重建无单一输入返回空。"""
        inputs = obj.inputs or {}
        if inputs.get("material_name"):
            return inputs["material_name"]
        mid = inputs.get("material_id")
        if mid:
            m = Material.objects.filter(id=mid).only("name").first()
            return m.name if m else f"#{mid}"
        return ""

    def get_affected_page_details(self, obj):
        """受影响页面的可读信息:保留 affected_pages 顺序,已删除页面只保留在原始 ID 列表中。"""
        page_ids = obj.affected_pages or []
        if not page_ids:
            return []
        pages = {
            p.id: p
            for p in KnowledgePage.objects.filter(id__in=page_ids).only(
                "id",
                "title",
                "page_type",
                "status",
            )
        }
        result = []
        for page_id in page_ids:
            page = pages.get(page_id)
            if not page:
                continue
            result.append(
                {
                    "id": page.id,
                    "title": page.title,
                    "page_type": page.page_type,
                    "status": page.status,
                }
            )
        return result
