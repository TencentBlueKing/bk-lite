from django.db import transaction
from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot import tasks as _opspilot_tasks
from apps.opspilot.models import KnowledgePage, Material, MaterialVersion, PageEvidence
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, MaterialSerializer
from apps.opspilot.services.wiki.build_service import build_from_material
from apps.opspilot.services.wiki.embedding_service import index_version, reindex_page_chunks
from apps.opspilot.services.wiki.index_rebuild_service import rebuild_page_indexes
from apps.opspilot.services.wiki.material_service import ingest_material
from apps.opspilot.services.wiki.update_service import handle_material_deletion, preview_material_deletion, preview_material_update, propose_update
from apps.system_mgmt.utils.operation_log_utils import log_operation


class WikiMaterialViewSet(AuthViewSet):
    """Wiki 资料 CRUD + 摄取(解析 + AI 摘要)。按 knowledge_base 维度组织。"""

    queryset = Material.objects.all().order_by("-id")
    serializer_class = MaterialSerializer
    ordering = ("-id",)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        kb_id = request.GET.get("knowledge_base")
        if kb_id:
            queryset = queryset.filter(knowledge_base_id=kb_id)
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        total = queryset.count()
        page_items = queryset[(page - 1) * page_size : (page - 1) * page_size + page_size]
        serializer = self.get_serializer(page_items, many=True)
        return JsonResponse({"result": True, "data": {"count": total, "items": serializer.data}})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return JsonResponse({"result": True, "data": self.get_serializer(instance).data})

    @staticmethod
    def _enqueue_ingest(material, llm_model_id):
        """资料置「解析中」并投递异步解析任务(loader/OCR/LLM 较重,不阻塞前台)。"""
        material.status = "parsing"
        material.save(update_fields=["status", "updated_at"])
        _opspilot_tasks.wiki_ingest_material_task.delay(material.id, llm_model_id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        material = serializer.instance
        llm_model_id = material.knowledge_base.llm_model_id
        # 文本解析瞬时(无 loader/OCR/外网),同步摄取即得摘要;
        # 文件解析较重(loader/OCR/LLM),转 Celery 异步,资料先置「解析中」,前端轮询出结果;
        # 网页解析需外网抓取、耗时不可控,仍走手动 ingest。
        if material.material_type == "text":
            ingest_material(material, llm_model_id=llm_model_id)
            serializer = self.get_serializer(material)
        elif material.material_type == "file":
            self._enqueue_ingest(material, llm_model_id)
            serializer = self.get_serializer(material)
        log_operation(request, "create", "opspilot", f"新增资料: {material.name}")
        return JsonResponse({"result": True, "data": serializer.data}, status=201)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        name = instance.name
        build = handle_material_deletion(instance, operator=getattr(request.user, "username", ""))
        log_operation(request, "delete", "opspilot", f"删除资料: {name}")
        return JsonResponse({"result": True, "data": {"pending_review": build.counts.get("pending_review", 0)}})

    @action(methods=["GET"], detail=True)
    def delete_impact(self, request, pk=None):
        """删除资料前的只读影响预览:受影响页面、会失去来源页面、共享来源保护页面。"""
        material = self.get_object()
        return JsonResponse({"result": True, "data": preview_material_deletion(material)})

    @action(methods=["GET"], detail=True)
    def update_impact(self, request, pk=None):
        """资料更新前的只读影响预览:受影响页面预计统一进入人工审核。"""
        material = self.get_object()
        return JsonResponse({"result": True, "data": preview_material_update(material)})

    @action(methods=["POST"], detail=True)
    def ingest(self, request, pk=None):
        """手动触发资料解析(异步:抽取文本 + AI 摘要)。资料置「解析中」,前端轮询出结果。"""
        material = self.get_object()
        self._enqueue_ingest(material, material.knowledge_base.llm_model_id)
        return JsonResponse({"result": True, "data": self.get_serializer(material).data})

    @action(methods=["POST"], detail=True)
    def build(self, request, pk=None):
        """从该资料构建知识页面(Schema 驱动)。async=true 走 Celery 异步(前端默认),资料置「构建中」、前端轮询出结果;否则同步返回构建记录(供测试/脚本)。"""
        material = self.get_object()
        operator = getattr(request.user, "username", "")
        if request.data.get("async"):
            material.status = "building"
            material.save(update_fields=["status", "updated_at"])
            _opspilot_tasks.wiki_build_material_task.delay(material.id, material.knowledge_base.llm_model_id, operator)
            return JsonResponse({"result": True, "data": self.get_serializer(material).data})
        record = build_from_material(
            material,
            llm_model_id=material.knowledge_base.llm_model_id,
            operator=operator,
        )
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

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

        ocr_enhance = str(request.data.get("ocr_enhance", "")).lower() in ("1", "true", "yes")
        files = request.FILES.getlist("files")
        if not files:
            return JsonResponse({"result": False, "message": "files 必填,至少上传一个文件"}, status=400)

        items = []
        errors = []
        for f in files:
            try:
                # 每条记录包在独立 savepoint 中:失败只回滚当前 savepoint,不污染整批事务
                with transaction.atomic():
                    material = Material.objects.create(
                        knowledge_base_id=kb_id,
                        name=f.name,
                        material_type="file",
                        file=f,
                        ocr_enhance=ocr_enhance,
                        status="parsing",
                    )
            except Exception as exc:  # noqa: BLE001 - 批量任务逐条隔离失败
                logger.exception("wiki batch_create 失败 file=%s kb=%s", f.name, kb_id)
                errors.append({"name": f.name, "error": str(exc)})
                continue
            # 投递异步解析(loader/OCR/LLM 较重);任务投递失败不阻塞记录创建
            try:
                _opspilot_tasks.wiki_ingest_material_task.delay(material.id, material.knowledge_base.llm_model_id)
            except Exception:  # noqa: BLE001
                logger.exception("wiki batch_create 投递解析任务失败 material_id=%s", material.id)
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
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "material": self.get_serializer(material).data,
                    "original": original,
                    "file_url": file_url,
                    "ai_summary": material.ai_summary,
                    "versions": versions,
                    "contributed_pages": pages,
                },
            }
        )
