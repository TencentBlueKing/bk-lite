from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot import tasks as _opspilot_tasks
from apps.opspilot.models import BuildRecord, KnowledgePage, Material, MaterialVersion, PageEvidence
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, MaterialSerializer
from apps.opspilot.services.wiki.embedding_service import index_version, reindex_page_chunks
from apps.opspilot.services.wiki.index_rebuild_service import rebuild_page_indexes
from apps.opspilot.services.wiki.material_build_queue_service import MaterialBuildQueueError, enqueue_material_builds
from apps.opspilot.services.wiki.material_service import load_parsed_markdown
from apps.opspilot.services.wiki.material_source_service import MaterialSourceError, source_metadata
from apps.opspilot.services.wiki.parsed_media_service import _bare_media_locator_spans, rewrite_media_urls_for_display, sign_media_locators
from apps.opspilot.services.wiki.update_service import handle_material_deletion, preview_material_deletion, preview_material_update, propose_update
from apps.opspilot.viewsets.wiki_team_scope import WikiTeamScopeMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation

# 列表排序优先级(越小越靠前):
# 构建中 > 排队中 > 构建失败 > 未构建 > 已构建；组内 -id。
_MATERIAL_LIST_BUILDING_STATUSES = ("parsing", "building")
_MATERIAL_LIST_QUEUED_STATUSES = ("queued",)
_MATERIAL_LIST_FAILED_STATUSES = (
    "parse_failed",
    "build_failed",
    "failed",
    "invalid",
    "partial",
)
_MATERIAL_LIST_PENDING_STATUSES = ("pending", "done", "updated")
_MATERIAL_LIST_BUILT_STATUSES = ("built",)
_MATERIAL_STATUS_GROUPS = {
    "pending": _MATERIAL_LIST_PENDING_STATUSES,
    "queued": _MATERIAL_LIST_QUEUED_STATUSES,
    "building": _MATERIAL_LIST_BUILDING_STATUSES,
    "built": _MATERIAL_LIST_BUILT_STATUSES,
    "failed": _MATERIAL_LIST_FAILED_STATUSES,
}


def _split_query_values(request, key):
    values = []
    for item in request.GET.getlist(key) or ([] if request.GET.get(key) in (None, "") else [request.GET.get(key)]):
        for part in str(item).split(","):
            part = part.strip()
            if part:
                values.append(part)
    return values


def resolve_material_status_filters(request):
    """解析资料列表状态筛选:支持 status(原始) 与 status_group(展示分组),均可多选。"""
    raw_statuses = _split_query_values(request, "status")
    group_statuses = []
    for group in _split_query_values(request, "status_group"):
        group_statuses.extend(_MATERIAL_STATUS_GROUPS.get(group, ()))
    merged = []
    for status in [*raw_statuses, *group_statuses]:
        if status not in merged:
            merged.append(status)
    return merged


def order_materials_for_list(queryset):
    """资料列表默认排序:构建中 > 排队中 > 失败 > 未构建 > 已构建,组内 -id。"""
    return queryset.annotate(
        list_priority=Case(
            When(status__in=_MATERIAL_LIST_BUILDING_STATUSES, then=Value(0)),
            When(status__in=_MATERIAL_LIST_QUEUED_STATUSES, then=Value(1)),
            When(status__in=_MATERIAL_LIST_FAILED_STATUSES, then=Value(2)),
            When(status__in=_MATERIAL_LIST_PENDING_STATUSES, then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by("list_priority", "-id")


class WikiMaterialViewSet(WikiTeamScopeMixin, AuthViewSet):
    """Wiki 资料 CRUD + 摄取(解析 + AI 摘要)。按 knowledge_base 维度组织。"""

    queryset = Material.objects.all().order_by("-id")
    serializer_class = MaterialSerializer
    ordering = ("-id",)

    @HasPermission("wiki_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        search = (request.GET.get("search") or "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        status_filters = resolve_material_status_filters(request)
        if status_filters:
            queryset = queryset.filter(status__in=status_filters)
        queryset = order_materials_for_list(queryset)
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        total = queryset.count()
        page_items = list(queryset[(page - 1) * page_size : (page - 1) * page_size + page_size])
        # 最新构建时间字段由 MaterialSerializer.__init__ 一次预取,避免列表 N+1
        serializer = self.get_serializer(page_items, many=True)
        return JsonResponse({"result": True, "data": {"count": total, "items": serializer.data}})

    @HasPermission("wiki_list-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return JsonResponse({"result": True, "data": self.get_serializer(instance).data})

    @staticmethod
    def _enqueue_ingest(material, llm_model_id):
        """资料置「解析中」并投递异步解析任务(loader/OCR/LLM 较重,不阻塞前台)。"""
        material.status = "parsing"
        material.save(update_fields=["status", "updated_at"])
        _opspilot_tasks.wiki_ingest_material_task.delay(material.id, llm_model_id)

    @staticmethod
    def _clean_name(value, fallback):
        value = str(value or "").strip()
        return value or fallback

    @staticmethod
    def _to_bool(value):
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @staticmethod
    def _normalize_sync_policy(value):
        if not isinstance(value, dict):
            return {"enabled": False, "interval_hours": 24}
        try:
            interval_hours = int(value.get("interval_hours") or 24)
        except (TypeError, ValueError):
            interval_hours = 24
        interval_hours = min(max(interval_hours, 1), 720)
        return {
            "enabled": WikiMaterialViewSet._to_bool(value.get("enabled")),
            "interval_hours": interval_hours,
        }

    @HasPermission("wiki_list-Edit")
    def update(self, request, *args, **kwargs):
        material = self.get_object()
        data = request.data
        update_fields = []
        original_text = material.text_content or ""

        if material.material_type == "text":
            if "name" in data:
                material.name = self._clean_name(data.get("name"), material.name)
                update_fields.append("name")
            if "text_content" in data:
                material.text_content = str(data.get("text_content") or "")
                update_fields.append("text_content")
                if material.text_content != original_text:
                    material.status = "updated"
                    update_fields.append("status")
        elif material.material_type == "web":
            if "name" in data:
                material.name = self._clean_name(data.get("name"), material.name)
                update_fields.append("name")
            if "sync_policy" in data:
                material.sync_policy = self._normalize_sync_policy(data.get("sync_policy"))
                update_fields.append("sync_policy")
        elif material.material_type == "file" and "ocr_enhance" in data:
            next_ocr_enhance = self._to_bool(data.get("ocr_enhance"))
            if next_ocr_enhance != material.ocr_enhance:
                material.ocr_enhance = next_ocr_enhance
                material.status = "updated"
                update_fields.extend(["ocr_enhance", "status"])

        if update_fields:
            material.updated_by = getattr(request.user, "username", "")
            update_fields.extend(["updated_by", "updated_at"])
            material.save(update_fields=list(dict.fromkeys(update_fields)))

        log_operation(request, "update", "opspilot", f"编辑资料: {material.name}")
        return JsonResponse({"result": True, "data": self.get_serializer(material).data})

    @HasPermission("wiki_list-Edit")
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @HasPermission("wiki_list-Edit")
    def create(self, request, *args, **kwargs):
        knowledge_base = self.accessible_knowledge_base_or_none(request.data.get("knowledge_base"))
        if knowledge_base is None:
            return JsonResponse({"result": False, "message": "知识库不存在"}, status=400)

        data = request.data
        try:
            metadata = source_metadata(
                knowledge_base,
                source_relative_path=data.get("source_relative_path"),
                fallback_name=data.get("name") or getattr(data.get("file"), "name", "") or "material",
                classification_root_id=data.get("classification_root") or data.get("classification_root_id"),
            )
        except MaterialSourceError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=400)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        material = serializer.save(
            source_relative_path=metadata["source_relative_path"],
            source_identity=metadata["source_identity"],
            source_folder_path=metadata["source_folder_path"],
            classification_root=metadata["classification_root"],
        )
        # 新资料保持 pending；管理员点击「构建」后由统一任务依次解析并构建。
        serializer = self.get_serializer(material)
        log_operation(request, "create", "opspilot", f"新增资料: {material.name}")
        return JsonResponse({"result": True, "data": serializer.data}, status=201)

    @HasPermission("wiki_list-Edit")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        material_id = instance.id
        name = instance.name
        build = handle_material_deletion(instance, operator=getattr(request.user, "username", ""))
        log_operation(request, "delete", "opspilot", f"删除资料: {name}")
        counts = build.counts or {}
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "deleted": True,
                    "material_id": material_id,
                    "build_record_id": build.id,
                    "status": build.status,
                    "counts": counts,
                    "maintenance": build.maintenance or {},
                    "pending_review": counts.get("pending_review", 0),
                },
            }
        )

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def delete_impact(self, request, pk=None):
        """删除资料前的只读影响预览:受影响页面、会失去来源页面、共享来源保护页面。"""
        material = self.get_object()
        return JsonResponse({"result": True, "data": preview_material_deletion(material)})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def update_impact(self, request, pk=None):
        """资料更新前的只读影响预览:受影响页面预计统一进入人工审核。"""
        material = self.get_object()
        return JsonResponse({"result": True, "data": preview_material_update(material)})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def ingest(self, request, pk=None):
        """手动触发资料解析(异步:抽取文本 + AI 摘要)。资料置「解析中」,前端轮询出结果。"""
        material = self.get_object()
        self._enqueue_ingest(material, material.knowledge_base.llm_model_id)
        return JsonResponse({"result": True, "data": self.get_serializer(material).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def build(self, request, pk=None):
        """从该资料构建知识页面(Schema 驱动)。

        async=true(前端默认):加入知识库串行构建队列,同 KB 顺序执行、跨 KB 可并发;
        async=false:同步执行(测试/脚本),不走队列。
        """
        material = self.get_object()
        operator = getattr(request.user, "username", "")
        source_status = material.status
        if source_status in {"parsing", "building", "queued"}:
            return JsonResponse(
                {
                    "result": False,
                    "code": "material_build_in_progress",
                    "message": "资料正在构建中，请勿重复提交",
                    "retryable": True,
                },
                status=409,
            )
        if request.data.get("async"):
            try:
                result = enqueue_material_builds(
                    knowledge_base_id=material.knowledge_base_id,
                    material_ids=[material.pk],
                    operator=operator,
                )
            except MaterialBuildQueueError as error:
                return JsonResponse(
                    {
                        "result": False,
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                        "retryable": error.status_code >= 500,
                    },
                    status=error.status_code,
                )
            except Exception:  # noqa: BLE001 - traceback 由 kick 持有
                return JsonResponse(
                    {
                        "result": False,
                        "code": "task_dispatch_failed",
                        "message": "知识构建任务投递失败，请稍后重试",
                        "retryable": True,
                    },
                    status=503,
                )
            material.refresh_from_db()
            return JsonResponse(
                {
                    "result": True,
                    "data": {
                        **self.get_serializer(material).data,
                        "queue": result,
                    },
                }
            )

        with transaction.atomic():
            material = Material.objects.select_for_update().get(pk=material.pk)
            if material.status in {"parsing", "building", "queued"}:
                return JsonResponse(
                    {
                        "result": False,
                        "code": "material_build_in_progress",
                        "message": "资料正在构建中，请勿重复提交",
                        "retryable": True,
                    },
                    status=409,
                )
            material.status = "parsing"
            material.error_message = ""
            material.save(update_fields=["status", "error_message", "updated_at"])
        build_id = _opspilot_tasks.wiki_build_material_task.run(
            material.id,
            material.knowledge_base.llm_model_id,
            operator,
            classification_root_id=material.classification_root_id,
            ensure_parsed=True,
            source_status=source_status,
        )
        record = BuildRecord.objects.get(pk=build_id)
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False, url_path="batch_build")
    def batch_build(self, request):
        """批量将资料加入知识库串行构建队列。同 KB 顺序执行，跨 KB 可并发。"""
        try:
            kb_id = int(request.data.get("knowledge_base") or 0)
        except (TypeError, ValueError):
            kb_id = 0
        material_ids = request.data.get("material_ids") or []
        if not kb_id:
            return JsonResponse({"result": False, "message": "knowledge_base 必填"}, status=400)
        if self.accessible_knowledge_base_or_none(kb_id) is None:
            return JsonResponse({"result": False, "message": "知识库不存在或无权限"}, status=404)
        try:
            result = enqueue_material_builds(
                knowledge_base_id=kb_id,
                material_ids=material_ids,
                operator=getattr(request.user, "username", ""),
            )
        except MaterialBuildQueueError as error:
            return JsonResponse(
                {
                    "result": False,
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                },
                status=error.status_code,
            )
        except Exception:  # noqa: BLE001 - traceback 由 kick 持有
            return JsonResponse(
                {
                    "result": False,
                    "code": "task_dispatch_failed",
                    "message": "知识构建任务投递失败，请稍后重试",
                    "retryable": True,
                },
                status=503,
            )
        return JsonResponse({"result": True, "data": result})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def propose_update(self, request, pk=None):
        """资料更新后安全合并:AI 页面直接更新,含人工编辑的生成候选待审。"""
        material = self.get_object()
        record = propose_update(
            material,
            llm_model_id=material.knowledge_base.llm_model_id,
            operator=getattr(request.user, "username", ""),
        )
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def reindex(self, request, pk=None):
        """按资料重建其贡献页面的索引,只处理仍启用的知识页面。"""
        material = self.get_object()
        kb = material.knowledge_base
        if not kb.embed_provider_id:
            return JsonResponse({"result": False, "message": "知识库未配置向量模型,无法重建索引"}, status=400)

        evidences = (
            PageEvidence.objects.filter(material=material, page__status="active").select_related("page", "page__current_version").order_by("page_id")
        )
        pages = []
        seen = set()
        for evidence in evidences:
            if evidence.page_id in seen:
                continue
            pages.append(evidence.page)
            seen.add(evidence.page_id)
        record = rebuild_page_indexes(
            kb,
            pages,
            trigger="material_reindex",
            event="material_reindex",
            operator=getattr(request.user, "username", ""),
            inputs={"material_id": material.id, "material_name": material.name},
            index_fn=index_version,
            chunk_index_fn=reindex_page_chunks,
        )
        log_operation(request, "execute", "opspilot", f"重建资料关联索引: {material.name}")
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=False, url_path="batch_create")
    def batch_create(self, request):
        """批量创建资料(支持多文件):每条独立处理,返回 items + errors 汇总,失败不影响其他记录创建。

        POST 表单字段:
        - knowledge_base: int (必填)
        - ocr_enhance: bool (默认 False,仅 file 生效)
        - files: File[] (multipart,多文件)

        返回 {result, data: {items: [Material...], errors: [{name, error}]}}。
        """
        kb_id = request.data.get("knowledge_base")
        if not kb_id:
            return JsonResponse({"result": False, "message": "knowledge_base 必填"}, status=400)
        kb = self.accessible_knowledge_base_or_none(kb_id)
        if kb is None:
            return JsonResponse({"result": False, "message": "知识库不存在"}, status=400)

        ocr_enhance = str(request.data.get("ocr_enhance", "")).lower() in ("1", "true", "yes")
        files = request.FILES.getlist("files")
        if not files:
            return JsonResponse({"result": False, "message": "files 必填,至少上传一个文件"}, status=400)
        source_relative_paths = request.data.getlist("source_relative_paths")
        if source_relative_paths and len(source_relative_paths) != len(files):
            return JsonResponse(
                {"result": False, "message": "source_relative_paths 必须与 files 一一对应"},
                status=400,
            )
        classification_root_id = request.data.get("classification_root_id") or request.data.get("classification_root")

        items = []
        errors = []
        for index, f in enumerate(files):
            try:
                metadata = source_metadata(
                    kb,
                    source_relative_path=source_relative_paths[index] if source_relative_paths else None,
                    fallback_name=f.name,
                    classification_root_id=classification_root_id,
                )
                # 每条记录包在独立 savepoint 中:失败只回滚当前 savepoint,不污染整批事务
                with transaction.atomic():
                    material = Material.objects.create(
                        knowledge_base=kb,
                        name=f.name,
                        material_type="file",
                        file=f,
                        ocr_enhance=ocr_enhance,
                        status="pending",
                        source_relative_path=metadata["source_relative_path"],
                        source_identity=metadata["source_identity"],
                        source_folder_path=metadata["source_folder_path"],
                        classification_root=metadata["classification_root"],
                    )
            except Exception as exc:  # noqa: BLE001 - 批量任务逐条隔离失败
                logger.exception("wiki batch_create 失败 file=%s kb=%s", f.name, kb_id)
                errors.append({"name": f.name, "error": str(exc)})
                continue
            # 批量上传同样只创建资料；解析与知识生成由「构建」统一触发。
            items.append(MaterialSerializer(material).data)
        log_operation(
            request,
            "create",
            "opspilot",
            f"批量新增资料: 成功 {len(items)} 条,失败 {len(errors)} 条",
        )
        return JsonResponse(
            {"result": True, "data": {"items": items, "errors": errors}},
            status=201 if items and not errors else 200,
        )

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def info(self, request, pk=None):
        """资料详情(spec 4.2):原文/文件链接、AI 解读、版本、贡献的知识页面。"""
        material = self.get_object()
        versions = [
            {
                "id": v.id,
                "content_hash": v.content_hash,
                "content_locator": v.content_locator,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in MaterialVersion.objects.filter(material=material).order_by("-id")
        ]
        page_ids = list(PageEvidence.objects.filter(material=material).values_list("page_id", flat=True).distinct())
        pages = [{"id": p.id, "title": p.title, "page_type": p.page_type, "status": p.status} for p in KnowledgePage.objects.filter(id__in=page_ids)]
        try:
            file_url = material.file.url if material.file else ""
        except Exception:
            file_url = ""
        original = material.text_content if material.material_type == "text" else (material.url or "")
        # MarkItDown 解析后的完整 markdown（含图片增强描述），来源详情以此为准；
        # for_display 会把 wiki/media 路径签发为可加载 URL。
        parsed_markdown = load_parsed_markdown(material, for_display=True) or ""
        # ai_summary 也可能引用 wiki/media（摄取时从正文摘取），展示前同样签发
        ai_summary = rewrite_media_urls_for_display(material.ai_summary or "")
        bare_left = _bare_media_locator_spans(parsed_markdown) + _bare_media_locator_spans(ai_summary)
        if bare_left:
            logger.warning(
                "material %s info 仍含未签发 wiki/media count=%s sample=%s",
                material.id,
                len(bare_left),
                bare_left[0][2],
            )
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "material": self.get_serializer(material).data,
                    "original": original,
                    "parsed_markdown": parsed_markdown,
                    "file_url": file_url,
                    "ai_summary": ai_summary,
                    "versions": versions,
                    "contributed_pages": pages,
                },
            }
        )

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=True)
    def sign_media(self, request, pk=None):
        """批量把 wiki/media locator 签发为可加载 URL（前端展示兜底）。"""
        material = self.get_object()
        locators = request.data.get("locators") if isinstance(request.data, dict) else None
        if not isinstance(locators, list):
            return JsonResponse({"result": False, "message": "locators 必须为列表"}, status=400)
        urls = sign_media_locators(
            locators,
            knowledge_base_id=material.knowledge_base_id,
            material_id=material.id,
        )
        return JsonResponse({"result": True, "data": {"urls": urls}})
