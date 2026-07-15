from rest_framework import serializers

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, MaterialVersion, PageVersion, WikiKnowledgeBase
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
    related_pages = serializers.SerializerMethodField()
    related = serializers.SerializerMethodField()
    candidate_version = serializers.SerializerMethodField()
    decision_context = serializers.SerializerMethodField()
    candidate = serializers.SerializerMethodField()
    current_knowledge = serializers.SerializerMethodField()
    new_knowledge = serializers.SerializerMethodField()
    decision_type = serializers.SerializerMethodField()
    decision_action = serializers.SerializerMethodField()
    decision_operator = serializers.SerializerMethodField()
    decision_processed_at = serializers.SerializerMethodField()
    decision_rule = serializers.SerializerMethodField()

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
            "current_knowledge",
            "new_knowledge",
            "suggested_actions",
            "assignee",
            "due_at",
            "action_type",
            "decision_key",
            "decision_context",
            "decision_type",
            "decision_action",
            "decision_operator",
            "decision_processed_at",
            "decision_rule",
            "created_at",
            "updated_at",
        ]

    @staticmethod
    def _copy_scalar_fields(value, fields):
        value = value if isinstance(value, dict) else {}
        return {key: value[key] for key in fields if key in value and (isinstance(value[key], (str, int, float, bool)) or value[key] is None)}

    def _sanitize_identity(self, obj, identity):
        identity = identity if isinstance(identity, dict) else {}
        page = self._get_page(obj, identity.get("page_id"))
        if page is None:
            return None
        value = {
            "page_id": page.id,
            "title": page.title,
            "page_type": page.page_type,
            "contribution": page.contribution,
        }
        version_id = identity.get("current_version_id")
        if version_id and PageVersion.objects.filter(id=version_id, page=page).exists():
            value["current_version_id"] = version_id
        for key in ("body_hash", "canonical_title", "canonical_title_key", "compact_title_key"):
            if isinstance(identity.get(key), str):
                value[key] = identity[key]
        return value

    def _sanitize_material_snapshot(self, obj, snapshot):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        material = Material.objects.filter(
            id=snapshot.get("material_id"),
            knowledge_base_id=obj.knowledge_base_id,
        ).first()
        if material is None:
            return None
        value = {
            "material_id": material.id,
            "content_hash": material.content_hash or "",
        }
        version_id = snapshot.get("material_version_id")
        version = MaterialVersion.objects.filter(id=version_id, material=material).first() if version_id else None
        if version is not None:
            value["material_version_id"] = version.id
            value["content_hash"] = version.content_hash or material.content_hash or ""
        return value

    def get_candidate_version(self, obj):
        candidate = obj.candidate_version
        if candidate is None or self._get_page(obj, candidate.page_id) is None:
            return None
        return candidate.id

    def get_related(self, obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        value = self._copy_scalar_fields(
            related,
            (
                "title",
                "summary",
                "description",
                "reason",
                "why",
                "trigger_source",
                "source_label",
                "impact_scope",
                "impact",
                "recoverability",
                "recovery",
                "canonical_title",
            ),
        )
        page_ids = related.get("pages") if isinstance(related.get("pages"), list) else []
        value["pages"] = [page_id for page_id in page_ids if self._get_page(obj, page_id) is not None]
        material_values = related.get("materials") if isinstance(related.get("materials"), list) else []
        material_ids = [item.get("material_id") or item.get("id") if isinstance(item, dict) else item for item in material_values]
        materials = Material.objects.filter(
            id__in=[item for item in material_ids if type(item) is int],
            knowledge_base_id=obj.knowledge_base_id,
        )
        value["materials"] = [{"id": item.id, "name": item.name} for item in materials]
        resolution = related.get("resolution")
        if isinstance(resolution, dict):
            value["resolution"] = self._copy_scalar_fields(
                resolution,
                ("action", "operator", "processed_at", "reason"),
            )
        return value

    def get_decision_context(self, obj):
        context = obj.decision_context if isinstance(obj.decision_context, dict) else {}
        value = self._copy_scalar_fields(
            context,
            (
                "decision_type",
                "subject_key",
                "schema_fingerprint",
                "summary",
                "reason",
                "trigger_source",
                "impact_scope",
                "recoverability",
                "current_body_hash",
                "candidate_body_hash",
            ),
        )
        identity = self._sanitize_identity(obj, context.get("page_identity"))
        if identity is not None:
            value["page_identity"] = identity
        identities = [item for item in (self._sanitize_identity(obj, raw) for raw in (context.get("page_identities") or [])) if item is not None]
        if identities:
            value["page_identities"] = identities
        target_identity = self._sanitize_identity(obj, context.get("target_identity"))
        if target_identity is not None:
            value["target_identity"] = target_identity
        incoming = self._sanitize_material_snapshot(obj, context.get("incoming"))
        if incoming is not None:
            value["incoming"] = incoming
        participants = [
            item for item in (self._sanitize_material_snapshot(obj, raw) for raw in (context.get("participants") or [])) if item is not None
        ]
        if participants:
            value["participants"] = participants

        candidate = obj.candidate_version
        candidate_page = self._get_page(obj, getattr(candidate, "page_id", None))
        if candidate is not None and candidate_page is not None:
            if context.get("candidate_version_id") == candidate.id:
                value["candidate_version_id"] = candidate.id
            locked_version_id = context.get("locked_current_version_id")
            if (
                locked_version_id
                and PageVersion.objects.filter(
                    id=locked_version_id,
                    page=candidate_page,
                ).exists()
            ):
                value["locked_current_version_id"] = locked_version_id
        return value

    def _get_page(self, obj, page_id):
        if not page_id:
            return None
        cache = self.context.setdefault("_wiki_check_page_cache", {})
        cache_key = (obj.knowledge_base_id, page_id)
        if cache_key not in cache:
            cache[cache_key] = (
                KnowledgePage.objects.select_related("current_version")
                .filter(
                    id=page_id,
                    knowledge_base_id=obj.knowledge_base_id,
                )
                .first()
            )
        return cache[cache_key]

    def _page_card(self, page, *, version=None, identity=None, excluded_material_id=None):
        if page is None:
            return None
        identity = identity if isinstance(identity, dict) else {}
        version = version or page.current_version
        evidences = list(page.evidences.select_related("material").filter(material__knowledge_base_id=page.knowledge_base_id).order_by("id"))
        if excluded_material_id:
            evidences = [item for item in evidences if item.material_id != excluded_material_id]
        source_names = list(dict.fromkeys(item.material.name for item in evidences if item.material_id))
        source_label = identity.get("source_label") or ", ".join(source_names)
        source_count = identity.get("source_count")
        if source_count is None:
            source_count = len(evidences)
        relation_count = identity.get("relation_count")
        if relation_count is None:
            relation_count = page.relations_out.count() + page.relations_in.count()
        contribution = identity.get("contribution") or page.contribution
        title = identity.get("title") or page.title
        page_type = identity.get("page_type") or page.page_type
        return {
            "id": page.id,
            "page_id": page.id,
            "title": title,
            "page_type": page_type,
            "body": (version.body if version else "") or "",
            "version_id": getattr(version, "id", None),
            "version_label": f"v{version.no}" if version else "",
            "source_label": source_label,
            "source_count": source_count,
            "relation_count": relation_count,
            "contribution": contribution,
        }

    def _identity_card(self, obj, identity):
        if not isinstance(identity, dict):
            return None
        page = self._get_page(obj, identity.get("page_id"))
        if page is None:
            return None
        version = None
        if identity.get("current_version_id"):
            version = PageVersion.objects.filter(
                id=identity["current_version_id"],
                page=page,
            ).first()
        return self._page_card(page, version=version, identity=identity)

    def get_related_pages(self, obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        return [card for card in (self._page_card(self._get_page(obj, page_id)) for page_id in related.get("pages", []) or []) if card is not None]

    def get_candidate(self, obj):
        candidate = obj.candidate_version
        if candidate is None or self._get_page(obj, candidate.page_id) is None:
            return None
        return {"id": candidate.id, "body": candidate.body or ""}

    def get_current_knowledge(self, obj):
        context = obj.decision_context if isinstance(obj.decision_context, dict) else {}
        if self.get_decision_type(obj) == "page_identity":
            target_identity = context.get("target_identity")
            if not target_identity:
                identities = context.get("page_identities") or []
                target_identity = identities[0] if identities else None
            return self._identity_card(obj, target_identity)

        page_snapshot = context.get("page_identity") if isinstance(context.get("page_identity"), dict) else {}
        candidate = obj.candidate_version
        page = self._get_page(obj, page_snapshot.get("page_id") or getattr(candidate, "page_id", None))
        if page is None:
            return None
        version = None
        if context.get("locked_current_version_id"):
            version = PageVersion.objects.filter(
                id=context["locked_current_version_id"],
                page=page,
            ).first()
        incoming = context.get("incoming") if isinstance(context.get("incoming"), dict) else {}
        return self._page_card(
            page,
            version=version,
            excluded_material_id=incoming.get("material_id"),
        )

    def get_new_knowledge(self, obj):
        context = obj.decision_context if isinstance(obj.decision_context, dict) else {}
        if self.get_decision_type(obj) == "page_identity":
            target = context.get("target_identity") if isinstance(context.get("target_identity"), dict) else {}
            target_page_id = target.get("page_id")
            identities = context.get("page_identities") or []
            source_identity = next(
                (identity for identity in identities if identity.get("page_id") != target_page_id),
                None,
            )
            return self._identity_card(obj, source_identity)

        candidate = obj.candidate_version
        if candidate is None:
            return None
        page = self._get_page(obj, candidate.page_id)
        card = self._page_card(page, version=candidate)
        if card is None:
            return None
        incoming = context.get("incoming") if isinstance(context.get("incoming"), dict) else {}
        material = Material.objects.filter(
            id=incoming.get("material_id"),
            knowledge_base_id=obj.knowledge_base_id,
        ).first()
        incoming_snapshot = self._sanitize_material_snapshot(obj, incoming)
        card.update(
            {
                "source_label": material.name if material else "",
                "source_count": 1 if material else 0,
                "material_id": material.id if material else None,
                "material_version_id": (incoming_snapshot.get("material_version_id") if incoming_snapshot is not None else None),
                "content_hash": (incoming_snapshot.get("content_hash", "") if incoming_snapshot is not None else ""),
            }
        )
        return card

    def _get_decision_rule(self, obj):
        cache = self.context.setdefault("_wiki_decision_rule_cache", {})
        if obj.id in cache:
            return cache[obj.id]
        prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("decision_rules")
        if prefetched is not None:
            rule = max(
                (item for item in prefetched if item.knowledge_base_id == obj.knowledge_base_id),
                key=lambda item: item.id,
                default=None,
            )
        else:
            rule = (
                obj.decision_rules.filter(
                    knowledge_base_id=obj.knowledge_base_id,
                )
                .order_by("-id")
                .first()
            )
        cache[obj.id] = rule
        return rule

    @staticmethod
    def _get_frozen_rule_snapshot(obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        snapshot = related.get("rule_snapshot")
        return dict(snapshot) if isinstance(snapshot, dict) else None

    def get_decision_type(self, obj):
        context = obj.decision_context if isinstance(obj.decision_context, dict) else {}
        frozen_type = context.get("decision_type")
        if frozen_type:
            return frozen_type
        if obj.check_type in {"cannot_merge", "material_update"}:
            return "knowledge_conflict"
        if obj.check_type in {"duplicate", "conflict"}:
            return "page_identity"
        return ""

    def get_decision_action(self, obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        resolution = related.get("resolution") if isinstance(related.get("resolution"), dict) else {}
        if resolution.get("action"):
            return resolution["action"]
        snapshot = self._get_frozen_rule_snapshot(obj)
        if snapshot is not None:
            return snapshot.get("action") or ""
        rule = self._get_decision_rule(obj)
        return rule.action if rule is not None else ""

    def get_decision_operator(self, obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        resolution = related.get("resolution") if isinstance(related.get("resolution"), dict) else {}
        if resolution.get("operator"):
            return resolution["operator"]
        snapshot = self._get_frozen_rule_snapshot(obj)
        if snapshot is not None:
            return snapshot.get("operator") or obj.updated_by or ""
        rule = self._get_decision_rule(obj)
        if rule is not None:
            result = rule.result_snapshot if isinstance(rule.result_snapshot, dict) else {}
            return result.get("operator") or rule.updated_by or rule.created_by or obj.updated_by or ""
        return obj.updated_by or ""

    def get_decision_processed_at(self, obj):
        related = obj.related if isinstance(obj.related, dict) else {}
        resolution = related.get("resolution") if isinstance(related.get("resolution"), dict) else {}
        if resolution.get("processed_at"):
            return resolution["processed_at"]
        if obj.status == "open":
            return None
        return serializers.DateTimeField().to_representation(obj.updated_at)

    def get_decision_rule(self, obj):
        snapshot = self._get_frozen_rule_snapshot(obj)
        if snapshot is not None:
            serialized_rule = {
                "id": snapshot.get("id"),
                "status": snapshot.get("status") or "",
                "action": snapshot.get("action") or "",
                "match_snapshot": snapshot.get("match_snapshot") or {},
                "result_snapshot": snapshot.get("result_snapshot") or {},
                "replay_count": snapshot.get("replay_count") or 0,
                "last_replayed_at": snapshot.get("last_replayed_at"),
                "revoked_reason": snapshot.get("revoked_reason") or "",
            }
            rule = self._get_decision_rule(obj)
            if rule is None:
                return serialized_rule
            live_result = rule.result_snapshot if isinstance(rule.result_snapshot, dict) else {}
            serialized_rule.update(
                {
                    "id": rule.id,
                    "status": rule.status,
                    "replay_count": rule.replay_count,
                    "last_replayed_at": (serializers.DateTimeField().to_representation(rule.last_replayed_at) if rule.last_replayed_at else None),
                    "revoked_reason": live_result.get("revoked_reason") or "",
                }
            )
            return serialized_rule
        rule = self._get_decision_rule(obj)
        if rule is None:
            return None
        result_snapshot = rule.result_snapshot if isinstance(rule.result_snapshot, dict) else {}
        last_replayed_at = serializers.DateTimeField().to_representation(rule.last_replayed_at) if rule.last_replayed_at else None
        return {
            "id": rule.id,
            "status": rule.status,
            "action": rule.action,
            "match_snapshot": rule.match_snapshot,
            "result_snapshot": rule.result_snapshot,
            "replay_count": rule.replay_count,
            "last_replayed_at": last_replayed_at,
            "revoked_reason": result_snapshot.get("revoked_reason") or "",
        }


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
