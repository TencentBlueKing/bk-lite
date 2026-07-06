import json

from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot import tasks as _opspilot_tasks
from apps.opspilot.models import BuildRecord, KnowledgePage, Material, PageEvidence, WikiKnowledgeBase
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, CheckItemSerializer, KnowledgePageSerializer, PageVersionSerializer
from apps.opspilot.services.wiki.cascade_service import MAINTENANCE_STAGE_KEYS, cascade
from apps.opspilot.services.wiki.embedding_service import index_version, reindex_page_chunks
from apps.opspilot.services.wiki.index_rebuild_service import rebuild_page_indexes
from apps.opspilot.services.wiki.index_status_service import failed_index_stages_for_pages
from apps.opspilot.services.wiki.page_service import (
    create_manual_page,
    diff_versions,
    edit_page,
    restore_version,
    save_answer_candidate_page,
    save_answer_page,
)
from apps.system_mgmt.utils.operation_log_utils import log_operation


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _decode_evidence_locator(locator):
    locator = (locator or "").strip()
    if not locator:
        return {}, ""
    try:
        value = json.loads(locator)
    except json.JSONDecodeError:
        return {}, locator
    return (value if isinstance(value, dict) else {}), ""


def _evidence_source_payload(evidence):
    locator, locator_raw = _decode_evidence_locator(evidence.locator)
    material = evidence.material
    version = evidence.material_version
    payload = {
        "id": evidence.id,
        "material": {
            "id": material.id,
            "name": material.name,
            "material_type": material.material_type,
            "status": material.status,
        },
        "material_version": None,
        "locator": locator,
        "locator_raw": locator_raw,
        "snippet": locator.get("snippet", ""),
    }
    if version:
        payload["material_version"] = {
            "id": version.id,
            "content_hash": version.content_hash,
            "content_locator": version.content_locator,
            "created_at": version.created_at,
        }
    return payload


_MAINTENANCE_STAGE_COUNT_KEYS = {
    "relations": ("relations",),
    "page_embedding": ("indexed_pages", "cleared_pages"),
    "chunk_embedding": ("indexed_chunks", "cleared_pages"),
    "check_sweep": ("auto_resolved",),
    "deleted_page_prune": ("pruned_checks", "pruned_build_records"),
}


def _maintenance_status_from_stages(stages):
    stage_values = [stage for stage in (stages or {}).values() if isinstance(stage, dict)]
    return "partial" if any(stage.get("status") == "failed" for stage in stage_values) else "success"


def _merge_selected_maintenance_retry(previous, retry_result, selected_stages):
    if not selected_stages:
        return retry_result

    merged = dict(previous or {})
    merged["event"] = retry_result.get("event", "maintenance_retry")
    merged["affected_page_ids"] = retry_result.get("affected_page_ids") or merged.get("affected_page_ids") or []
    merged_stages = dict(merged.get("stages") if isinstance(merged.get("stages"), dict) else {})
    merged_stages.update(retry_result.get("stages") if isinstance(retry_result.get("stages"), dict) else {})
    merged["stages"] = merged_stages
    for stage in selected_stages:
        for count_key in _MAINTENANCE_STAGE_COUNT_KEYS.get(stage, ()):
            if count_key in retry_result:
                merged[count_key] = retry_result[count_key]
    merged["last_retry"] = {
        "stages": selected_stages,
        "status": retry_result.get("status", "success"),
    }
    merged["status"] = _maintenance_status_from_stages(merged_stages)
    return merged


def _parse_maintenance_retry_stages(request):
    raw = request.data.get("stages")
    if raw in (None, ""):
        return None, None
    if not isinstance(raw, list) or not raw:
        return None, JsonResponse({"result": False, "message": "stages 必须为非空数组"}, status=400)

    valid_stages = set(MAINTENANCE_STAGE_KEYS)
    parsed = []
    seen = set()
    for item in raw:
        stage = str(item or "").strip()
        if stage not in valid_stages:
            return None, JsonResponse({"result": False, "message": f"不支持的维护阶段: {stage}"}, status=400)
        if stage in seen:
            continue
        parsed.append(stage)
        seen.add(stage)
    return parsed, None


def _filter_build_records_by_maintenance(records, maintenance_status, maintenance_stage, maintenance_stage_status):
    if not any([maintenance_status, maintenance_stage, maintenance_stage_status]):
        return records

    filtered = []
    for record in records:
        maintenance = record.maintenance if isinstance(record.maintenance, dict) else {}
        if maintenance_status and maintenance.get("status") != maintenance_status:
            continue

        stages = maintenance.get("stages") if isinstance(maintenance.get("stages"), dict) else {}
        if maintenance_stage:
            stage = stages.get(maintenance_stage)
            if not isinstance(stage, dict):
                continue
            if maintenance_stage_status and stage.get("status") != maintenance_stage_status:
                continue
        elif maintenance_stage_status and not any(
            isinstance(stage, dict) and stage.get("status") == maintenance_stage_status for stage in stages.values()
        ):
            continue
        filtered.append(record)
    return filtered


def _retry_build_record_maintenance(record, selected_stages=None):
    maintenance = record.maintenance if isinstance(record.maintenance, dict) else {}
    affected_page_ids = list(record.affected_pages or maintenance.get("affected_page_ids") or [])
    if not affected_page_ids:
        return None

    previous_event = maintenance.get("event") or record.trigger
    cascade_kwargs = {"stages": selected_stages} if selected_stages else {}
    retry_result = cascade(record.knowledge_base, affected_page_ids, "maintenance_retry", **cascade_kwargs)
    merged_maintenance = _merge_selected_maintenance_retry(maintenance, retry_result, selected_stages)
    inputs = dict(record.inputs or {})
    inputs["maintenance_retry_of"] = previous_event
    if selected_stages:
        inputs["maintenance_retry_stages"] = selected_stages
    record.inputs = inputs
    record.affected_pages = affected_page_ids
    record.maintenance = merged_maintenance
    record.status = merged_maintenance.get("status") or record.status
    record.stage = "done"
    record.progress = 100
    record.save(update_fields=["inputs", "affected_pages", "maintenance", "status", "stage", "progress", "updated_at"])
    return record


class WikiPageViewSet(AuthViewSet):
    """知识页面:浏览 + 人工创建/编辑/删除 + 版本查看/恢复(spec §8/§9)。"""

    queryset = KnowledgePage.objects.all().order_by("-id")
    serializer_class = KnowledgePageSerializer
    ordering = ("-id",)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        page_type = request.GET.get("page_type")
        if page_type:
            queryset = queryset.filter(page_type=page_type)
        title_filter = (request.GET.get("title") or request.GET.get("name") or "").strip()
        if title_filter:
            queryset = queryset.filter(title__icontains=title_filter)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        else:
            queryset = queryset.filter(status="active")
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        total = queryset.count()
        page_items = list(queryset.select_related("knowledge_base", "current_version")[(page - 1) * page_size : (page - 1) * page_size + page_size])
        serializer = self.get_serializer(
            page_items,
            many=True,
            context={
                **self.get_serializer_context(),
                "index_failure_lookup": failed_index_stages_for_pages(page_items),
            },
        )
        return JsonResponse({"result": True, "data": {"count": total, "items": serializer.data}})

    def retrieve(self, request, *args, **kwargs):
        page = self.get_object()
        serializer = self.get_serializer(
            page,
            context={
                **self.get_serializer_context(),
                "index_failure_lookup": failed_index_stages_for_pages([page]),
            },
        )
        return JsonResponse({"result": True, "data": serializer.data})

    def _parse_ids(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return None, JsonResponse({"result": False, "message": "ids 不能为空"}, status=400)

        parsed_ids = []
        seen = set()
        for raw_id in ids:
            try:
                page_id = int(raw_id)
            except (TypeError, ValueError):
                return None, JsonResponse({"result": False, "message": "ids 必须为整数列表"}, status=400)
            if page_id not in seen:
                parsed_ids.append(page_id)
                seen.add(page_id)
        return parsed_ids, None

    def _parse_knowledge_base(self, request):
        raw_id = request.data.get("knowledge_base") or request.data.get("knowledge_base_id")
        try:
            kb_id = int(raw_id)
        except (TypeError, ValueError):
            return None, JsonResponse({"result": False, "message": "knowledge_base 必填"}, status=400)
        kb = WikiKnowledgeBase.objects.filter(id=kb_id).first()
        if not kb:
            return None, JsonResponse({"result": False, "message": "知识库不存在"}, status=400)
        return kb, None

    def create(self, request, *args, **kwargs):
        data = request.data
        kb = WikiKnowledgeBase.objects.get(id=data["knowledge_base"])
        page = create_manual_page(
            knowledge_base=kb,
            page_type=data.get("page_type", "concept"),
            title=data["title"],
            body=data.get("body", ""),
            tags=data.get("tags") or [],
            created_by=getattr(request.user, "username", ""),
        )
        cascade(kb, [page.id], "page_create")
        log_operation(request, "create", "opspilot", f"新增知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data}, status=201)

    @action(methods=["POST"], detail=False)
    def save_answer(self, request):
        """将 QA/Bot 对话回答保存为知识页面,并保留来源对话元数据。"""
        kb, error = self._parse_knowledge_base(request)
        if error:
            return error
        data = request.data
        required_fields = [
            ("page_type", "page_type 必填"),
            ("title", "title 必填"),
            ("body", "body 必填"),
            ("source_conversation_id", "source_conversation_id 必填"),
        ]
        for field, message in required_fields:
            if not str(data.get(field) or "").strip():
                return JsonResponse({"result": False, "message": message}, status=400)

        if _truthy(data.get("as_candidate")):
            check = save_answer_candidate_page(
                knowledge_base=kb,
                page_type=data["page_type"],
                title=data["title"],
                body=data.get("body", ""),
                tags=data.get("tags") or [],
                source_conversation_id=data["source_conversation_id"],
                source_message_id=data.get("source_message_id", ""),
                source_channel=data.get("source_channel", "qa"),
                created_by=getattr(request.user, "username", ""),
            )
            log_operation(request, "create", "opspilot", f"保存问答为候选知识页面: {data['title']}")
            return JsonResponse({"result": True, "data": CheckItemSerializer(check).data}, status=201)

        page = save_answer_page(
            knowledge_base=kb,
            page_type=data["page_type"],
            title=data["title"],
            body=data.get("body", ""),
            tags=data.get("tags") or [],
            source_conversation_id=data["source_conversation_id"],
            source_message_id=data.get("source_message_id", ""),
            source_channel=data.get("source_channel", "qa"),
            created_by=getattr(request.user, "username", ""),
        )
        cascade(kb, [page.id], "qa_answer_save")
        log_operation(request, "create", "opspilot", f"保存问答为知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data}, status=201)

    def update(self, request, *args, **kwargs):
        page = self.get_object()
        if page.status == "archived":
            return JsonResponse({"result": False, "message": "已归档知识页面不可编辑,请先恢复"}, status=400)
        old_title = page.title
        edit_page(
            page,
            body=request.data.get("body"),
            title=request.data.get("title"),
            tags=request.data.get("tags"),
            updated_by=getattr(request.user, "username", ""),
        )
        page.refresh_from_db()
        deleted_titles = [old_title] if old_title != page.title else None
        cascade(page.knowledge_base, [page.id], "page_update", deleted_titles=deleted_titles)
        log_operation(request, "update", "opspilot", f"编辑知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        kb = page.knowledge_base
        page_id = page.id
        title = page.title
        page.delete()
        cascade(kb, [page_id], "page_delete", deleted_titles=[title], prune_deleted_pages=True)
        log_operation(request, "delete", "opspilot", f"删除知识页面: {title}")
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @transaction.atomic
    def batch_delete(self, request):
        """批量删除当前知识库内选中的知识页面,并复用页面删除的增量清理链路。"""
        ids, error = self._parse_ids(request)
        if error:
            return error
        kb, error = self._parse_knowledge_base(request)
        if error:
            return error

        pages = list(KnowledgePage.objects.filter(knowledge_base=kb, id__in=ids).only("id", "title"))
        pages_by_id = {page.id: page for page in pages}
        deleted_ids = [page_id for page_id in ids if page_id in pages_by_id]
        skipped_ids = [page_id for page_id in ids if page_id not in pages_by_id]
        deleted_titles = [pages_by_id[page_id].title for page_id in deleted_ids]

        if deleted_ids:
            KnowledgePage.objects.filter(knowledge_base=kb, id__in=deleted_ids).delete()
            cascade(kb, deleted_ids, "page_delete", deleted_titles=deleted_titles, prune_deleted_pages=True)

        log_operation(request, "delete", "opspilot", f"批量删除知识页面({len(deleted_ids)}项)")
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "deleted": len(deleted_ids),
                    "skipped": len(skipped_ids),
                    "skipped_ids": skipped_ids,
                },
            }
        )

    @action(methods=["POST"], detail=True)
    def reindex(self, request, pk=None):
        """重建单个知识页面的页面级和 chunk 级索引,并落构建记录供诊断/重试追踪。"""
        page = self.get_object()
        kb = page.knowledge_base
        if page.status != "active":
            return JsonResponse({"result": False, "message": "只有启用中的知识页面可以重建索引"}, status=400)
        if not kb.embed_provider_id:
            return JsonResponse({"result": False, "message": "知识库未配置向量模型,无法重建索引"}, status=400)
        if not page.current_version_id:
            return JsonResponse({"result": False, "message": "知识页面无当前版本,无法重建索引"}, status=400)

        operator = getattr(request.user, "username", "")
        build = rebuild_page_indexes(
            kb,
            [page],
            trigger="page_reindex",
            event="page_reindex",
            operator=operator,
            inputs={"page_id": page.id, "page_title": page.title},
            index_fn=index_version,
            chunk_index_fn=reindex_page_chunks,
        )
        log_operation(request, "execute", "opspilot", f"重建知识页面索引: {page.title}")
        return JsonResponse({"result": True, "data": BuildRecordSerializer(build).data})

    @action(methods=["GET"], detail=True)
    def sources(self, request, pk=None):
        """查看知识页面的资料来源和片段定位。"""
        page = self.get_object()
        evidences = PageEvidence.objects.filter(page=page).select_related("material", "material_version").order_by("id")
        sources = [_evidence_source_payload(evidence) for evidence in evidences]
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "page_id": page.id,
                    "page_title": page.title,
                    "sources": sources,
                },
            }
        )

    @action(methods=["GET"], detail=True)
    def versions(self, request, pk=None):
        """列出该页面的全部版本(用于 diff/恢复)。"""
        page = self.get_object()
        qs = page.page_versions.order_by("-no")
        return JsonResponse({"result": True, "data": PageVersionSerializer(qs, many=True).data})

    @action(methods=["GET"], detail=True)
    def diff(self, request, pk=None):
        """对比两个版本正文,返回统一 diff 行(?from=<版本id>&to=<版本id>)。"""
        page = self.get_object()
        try:
            from_id = int(request.GET.get("from"))
            to_id = int(request.GET.get("to"))
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "from/to 版本 id 必填"}, status=400)
        try:
            lines = diff_versions(page, from_id, to_id)
        except ValueError:
            return JsonResponse({"result": False, "message": "版本不存在"}, status=404)
        return JsonResponse({"result": True, "data": {"diff": lines}})

    @action(methods=["POST"], detail=True)
    def restore(self, request, pk=None):
        """恢复到指定历史版本(创建新版本,不删除历史)。"""
        page = self.get_object()
        if page.status == "archived":
            return JsonResponse({"result": False, "message": "已归档知识页面不可恢复版本,请先恢复归档"}, status=400)
        version_id = request.data.get("version_id")
        if not version_id:
            return JsonResponse({"result": False, "message": "version_id 必填"}, status=400)
        restore_version(page, version_id, operator=getattr(request.user, "username", ""))
        page.refresh_from_db()
        cascade(page.knowledge_base, [page.id], "restore")
        log_operation(request, "execute", "opspilot", f"恢复知识页面版本: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})

    @action(methods=["POST"], detail=True)
    def restore_from_archive(self, request, pk=None):
        """将已归档知识页面恢复为启用中,重新进入图谱/索引增量维护链路。"""
        page = self.get_object()
        if page.status != "archived":
            return JsonResponse({"result": False, "message": "只有已归档知识页面可以恢复"}, status=400)
        page.status = "active"
        page.update_method = "restore_archive"
        page.save(update_fields=["status", "update_method", "updated_at"])
        cascade(page.knowledge_base, [page.id], "page_restore_archive")
        log_operation(request, "execute", "opspilot", f"恢复归档知识页面: {page.title}")
        return JsonResponse({"result": True, "data": self.get_serializer(page).data})


class WikiBuildRecordViewSet(AuthViewSet):
    """构建记录:浏览 + 重试/继续/取消(spec 4.4)。"""

    queryset = BuildRecord.objects.all().order_by("-id")
    serializer_class = BuildRecordSerializer
    ordering = ("-id",)
    http_method_names = ["get", "head", "options", "post"]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        trigger_filter = request.GET.get("trigger")
        if trigger_filter:
            queryset = queryset.filter(trigger=trigger_filter)
        maintenance_status_filter = request.GET.get("maintenance_status")
        maintenance_stage_filter = request.GET.get("maintenance_stage")
        maintenance_stage_status_filter = request.GET.get("maintenance_stage_status")
        if maintenance_stage_filter and maintenance_stage_filter not in MAINTENANCE_STAGE_KEYS:
            return JsonResponse({"result": False, "message": f"不支持的维护阶段: {maintenance_stage_filter}"}, status=400)
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        if any([maintenance_status_filter, maintenance_stage_filter, maintenance_stage_status_filter]):
            filtered_items = _filter_build_records_by_maintenance(
                list(queryset),
                maintenance_status_filter,
                maintenance_stage_filter,
                maintenance_stage_status_filter,
            )
            total = len(filtered_items)
            page_items = filtered_items[(page - 1) * page_size : (page - 1) * page_size + page_size]
        else:
            total = queryset.count()
            page_items = queryset[(page - 1) * page_size : (page - 1) * page_size + page_size]
        return JsonResponse({"result": True, "data": {"count": total, "items": self.get_serializer(page_items, many=True).data}})

    def retrieve(self, request, *args, **kwargs):
        return JsonResponse({"result": True, "data": self.get_serializer(self.get_object()).data})

    @action(methods=["POST"], detail=True)
    def retry(self, request, pk=None):
        """重试/继续:对原资料重新发起构建(异步),资料置「构建中」,前端轮询出结果。"""
        record = self.get_object()
        material_id = (record.inputs or {}).get("material_id")
        material = Material.objects.filter(id=material_id).first() if material_id else None
        if not material:
            return JsonResponse({"result": False, "message": "原资料不存在,无法重试"}, status=400)
        material.status = "building"
        material.save(update_fields=["status", "updated_at"])
        operator = getattr(request.user, "username", "")
        _opspilot_tasks.wiki_build_material_task.delay(material.id, material.knowledge_base.llm_model_id, operator)
        return JsonResponse({"result": True, "data": {"async": True}})

    @action(methods=["POST"], detail=True)
    def retry_maintenance(self, request, pk=None):
        """重试构建记录的级联维护:关系、索引和检查清扫按受影响页面增量重跑。"""
        record = self.get_object()
        selected_stages, error = _parse_maintenance_retry_stages(request)
        if error:
            return error

        record = _retry_build_record_maintenance(record, selected_stages)
        if not record:
            return JsonResponse({"result": False, "message": "该构建记录没有受影响页面,无法重试维护"}, status=400)
        log_operation(request, "execute", "opspilot", f"重试构建记录维护: #{record.id}")
        return JsonResponse({"result": True, "data": self.get_serializer(record).data})

    @action(methods=["POST"], detail=False)
    def batch_retry_maintenance(self, request):
        """批量重试选中构建记录的级联维护,用于处理筛选出的失败阶段。"""
        raw_ids = request.data.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return JsonResponse({"result": False, "message": "ids 不能为空"}, status=400)
        record_ids = []
        seen = set()
        for raw_id in raw_ids:
            try:
                record_id = int(raw_id)
            except (TypeError, ValueError):
                return JsonResponse({"result": False, "message": "ids 必须为整数列表"}, status=400)
            if record_id not in seen:
                record_ids.append(record_id)
                seen.add(record_id)
        selected_stages, error = _parse_maintenance_retry_stages(request)
        if error:
            return error
        try:
            kb_id = int(request.data.get("knowledge_base") or request.data.get("knowledge_base_id"))
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "knowledge_base 必填"}, status=400)
        kb = WikiKnowledgeBase.objects.filter(id=kb_id).first()
        if not kb:
            return JsonResponse({"result": False, "message": "知识库不存在"}, status=400)

        records = BuildRecord.objects.filter(knowledge_base=kb, id__in=record_ids)
        record_map = {record.id: record for record in records}
        retried_records = []
        skipped_ids = []
        for record_id in record_ids:
            record = record_map.get(record_id)
            if not record:
                skipped_ids.append(record_id)
                continue
            retried_record = _retry_build_record_maintenance(record, selected_stages)
            if not retried_record:
                skipped_ids.append(record.id)
                continue
            retried_records.append(retried_record)
        log_operation(request, "execute", "opspilot", f"批量重试构建记录维护({len(retried_records)}项)")
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "retried": len(retried_records),
                    "skipped": len(skipped_ids),
                    "skipped_ids": skipped_ids,
                    "items": self.get_serializer(retried_records, many=True).data,
                },
            }
        )

    @action(methods=["POST"], detail=True)
    def cancel(self, request, pk=None):
        """取消:运行中的构建记录置 cancelled(运行中的 Celery 任务尽力而为,记录先落终态)。"""
        record = self.get_object()
        if record.status == "running":
            record.status = "cancelled"
            record.stage = "cancelled"
            record.save(update_fields=["status", "stage", "updated_at"])
        return JsonResponse({"result": True, "data": self.get_serializer(record).data})
