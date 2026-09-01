import json

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot import tasks as _opspilot_tasks
from apps.opspilot.models import BuildRecord, KnowledgePage, Material, WikiKnowledgeBase
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, WikiKnowledgeBaseSerializer
from apps.opspilot.services.wiki.active_generation_query_service import ActiveGenerationReadError
from apps.opspilot.services.wiki.build_generation_service import BuildGenerationError
from apps.opspilot.services.wiki.check_service import scan_health
from apps.opspilot.services.wiki.directory_enable_service import WikiDirectoryEnableError, enable_wiki_directory
from apps.opspilot.services.wiki.directory_readiness_service import audit_knowledge_base_readiness
from apps.opspilot.services.wiki.embedding_service import chunk_semantic_search as wiki_chunk_search
from apps.opspilot.services.wiki.embedding_service import index_version
from apps.opspilot.services.wiki.embedding_service import reindex_chunks as wiki_reindex_chunks
from apps.opspilot.services.wiki.embedding_service import reindex_page_chunks
from apps.opspilot.services.wiki.embedding_service import semantic_search as wiki_semantic_search
from apps.opspilot.services.wiki.graph_service import analyze_graph, build_graph
from apps.opspilot.services.wiki.index_rebuild_service import rebuild_page_indexes
from apps.opspilot.services.wiki.kb_delete_service import delete_knowledge_base
from apps.opspilot.services.wiki.markdown_export_service import QuotaExceededError
from apps.opspilot.services.wiki.markdown_import_governance_service import (
    MarkdownImportGovernanceError,
    execute_markdown_import,
    preflight_markdown_import,
)
from apps.opspilot.services.wiki.material_build_queue_service import has_active_runner, kb_has_user_build_in_progress, release_stale_runner_lease
from apps.opspilot.services.wiki.native_markdown_export_service import build_native_markdown_export_zip
from apps.opspilot.services.wiki.overview_service import get_overview
from apps.opspilot.services.wiki.parsed_media_service import sign_media_locators
from apps.opspilot.services.wiki.purpose_schema_service import generate_purpose_schema, list_templates
from apps.opspilot.services.wiki.rebuild_service import create_rebuild_record, running_build_record
from apps.opspilot.services.wiki.relation_service import list_relations
from apps.opspilot.services.wiki.retrieval_service import answer as wiki_answer
from apps.opspilot.services.wiki.retrieval_service import hybrid_search as wiki_hybrid_search
from apps.opspilot.services.wiki.retrieval_service import search as wiki_search
from apps.opspilot.services.wiki.retrieval_service import stream_answer as wiki_stream_answer
from apps.opspilot.services.wiki.rollback_service import RollbackServiceError, execute_generation_rollback, preview_generation_rollback
from apps.opspilot.services.wiki.structure_service import StructureServiceError, bootstrap_knowledge_base
from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key, title_alias_map
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded
from apps.opspilot.services.wiki.wiki_context_service import build_context
from apps.opspilot.viewsets.wiki_team_scope import WikiTeamScopeMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation
from config.drf.renderers import CustomRenderer, EventStreamRenderer


def _int_param(params, key, default, minimum=0):
    try:
        value = int(params.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(value, minimum)


def _optional_int_param(params, key, minimum=1):
    raw = params.get(key)
    if raw in (None, ""):
        return None

    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return max(value, minimum)


def _bool_param(params, key, default=False):
    raw = params.get(key)
    if raw is None:
        return bool(default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _governance_error(error, status=409):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": getattr(error, "code", "wiki_governance_error"),
            "retryable": bool(getattr(error, "retryable", False)),
            "details": dict(getattr(error, "details", {}) or {}),
        },
        status=status,
    )


def _rollback_error(error):
    return JsonResponse(
        {
            "result": False,
            "message": str(error),
            "code": error.code,
            "retryable": error.retryable,
            "details": error.details,
        },
        status=error.status_code,
    )


class WikiKnowledgeBaseViewSet(WikiTeamScopeMixin, AuthViewSet):
    """新 Wiki 知识库 CRUD + 创建流程(模板/AI 生成 Purpose+Schema)。沿用团队权限。"""

    queryset = WikiKnowledgeBase.objects.all().order_by("-id")
    serializer_class = WikiKnowledgeBaseSerializer
    ordering = ("-id",)
    search_fields = ("name",)
    team_scope_field = "id"

    @HasPermission("wiki_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        search = (request.GET.get("search") or "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        items = list(queryset)
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            page_size = max(int(request.GET.get("page_size", 20)), 1)
        except (TypeError, ValueError):
            page, page_size = 1, 20
        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        serializer = self.get_serializer(page_items, many=True)
        return JsonResponse({"result": True, "data": {"count": total, "items": serializer.data}})

    @HasPermission("wiki_list-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return JsonResponse({"result": True, "data": serializer.data})

    @HasPermission("wiki_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data.copy()
        if not params.get("team"):
            params["team"] = [self._parse_current_team_cookie(request)]
        self.validate_team_assignment(params.get("team"))
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        operator = getattr(request.user, "username", "") or ""
        try:
            with transaction.atomic():
                self.perform_create(serializer)
                bootstrap_knowledge_base(
                    serializer.instance,
                    operator=operator,
                )
        except StructureServiceError as error:
            return _governance_error(error, status=error.status_code)
        log_operation(request, "create", "opspilot", f"新增知识库: {serializer.data.get('name', '')}")
        return JsonResponse({"result": True, "data": serializer.data}, status=201)

    @HasPermission("wiki_list-Edit")
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if "team" in request.data:
            self.validate_team_assignment(request.data.get("team"))
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        log_operation(request, "update", "opspilot", f"编辑知识库: {serializer.data.get('name', '')}")
        return JsonResponse({"result": True, "data": serializer.data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def rollback_preview(self, request, pk=None):
        knowledge_base = self.get_object()
        try:
            data = preview_generation_rollback(
                knowledge_base,
                request.data,
            )
        except RollbackServiceError as error:
            return _rollback_error(error)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def rollback_execute(self, request, pk=None):
        knowledge_base = self.get_object()
        operator = getattr(request.user, "username", "") or ""
        try:
            data = execute_generation_rollback(
                knowledge_base,
                request.data,
                operator=operator,
            )
        except RollbackServiceError as error:
            return _rollback_error(error)
        log_operation(
            request,
            "execute",
            "opspilot",
            (f"回退知识库 generation: {knowledge_base.name} " f"-> {data['active_generation']['id']}"),
        )
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def directory_readiness(self, request, pk=None):
        knowledge_base = self.get_object()
        enable_check = str(request.query_params.get("enable_check", "")).strip().lower() in {"1", "true", "yes"}
        readiness = audit_knowledge_base_readiness(
            knowledge_base,
            enable_check=enable_check,
        )
        return JsonResponse({"result": True, "data": readiness.to_dict()})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def directory_enable(self, request, pk=None):
        knowledge_base = self.get_object()
        operator = getattr(request.user, "username", "") or ""
        try:
            enabled = enable_wiki_directory(
                knowledge_base,
                operator=operator,
            )
        except WikiDirectoryEnableError as error:
            return _governance_error(error, status=409)
        except Exception as error:
            readiness = getattr(error, "result", None)
            if readiness is None:
                raise
            return JsonResponse(
                {
                    "result": False,
                    "message": str(error),
                    "code": getattr(error, "code", "wiki_directory_not_ready"),
                    "retryable": False,
                    "details": {"readiness": readiness.to_dict()},
                },
                status=422,
            )
        data = {
            "knowledge_base_id": enabled.knowledge_base_id,
            "directory_enabled": enabled.directory_enabled,
            "migration_state": "enabled",
            "changed": enabled.changed,
            "readiness": enabled.readiness.to_dict(),
        }
        log_operation(request, "execute", "opspilot", f"启用知识目录: {knowledge_base.name}")
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("wiki_list-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if running_build_record(instance):
            return JsonResponse({"result": False, "message": "知识库存在运行中的构建任务,请等待完成后再操作"}, status=400)
        knowledge_base_id = instance.id
        name = instance.name
        try:
            delete_knowledge_base(instance)
        except ProtectedError:
            return JsonResponse(
                {
                    "result": False,
                    "message": "知识库仍被受保护引用占用，无法删除，请稍后重试或联系管理员",
                    "code": "knowledge_base_protected",
                },
                status=409,
            )
        except Exception as error:  # noqa: BLE001 - 返回可读失败，避免裸 500
            return JsonResponse(
                {
                    "result": False,
                    "message": f"删除知识库失败: {error}",
                    "code": "knowledge_base_delete_failed",
                },
                status=500,
            )
        log_operation(request, "delete", "opspilot", f"删除知识库: {name}")
        return JsonResponse({"result": True, "data": {"id": knowledge_base_id}})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=False)
    def templates(self, request):
        """返回创建知识库的场景模板列表。"""
        return JsonResponse({"result": True, "data": list_templates()})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def export_markdown(self, request, pk=None):
        """导出当前知识库启用中的知识页面为 Markdown zip。带配额审计。"""
        kb = self.get_object()
        try:
            content, count = build_native_markdown_export_zip(kb)
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        except QuotaExceededError as exc:
            # 审计失败导出尝试:留给运维/安全审计
            log_operation(
                request,
                "execute",
                "opspilot",
                f"导出 Markdown 超限: 知识库={kb.name} code={exc.code} detail={exc.message}",
            )
            return JsonResponse(
                {"result": False, "code": exc.code, "message": exc.message},
                status=400,
            )
        log_operation(
            request,
            "execute",
            "opspilot",
            f"导出 Markdown: 知识库={kb.name} pages={count} bytes={len(content)}",
        )
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="wiki-kb-{kb.id}-markdown.zip"'
        return response

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def import_markdown_preflight(self, request, pk=None):
        knowledge_base = self.get_object()
        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"result": False, "message": "file 必填"}, status=400)
        operator = getattr(request.user, "username", "") or ""
        raw_options = request.data.get("options") or "{}"
        try:
            options = json.loads(raw_options) if isinstance(raw_options, str) else dict(raw_options)
            for field in ("classification_root_id", "target_directory_id"):
                if request.data.get(field) not in (None, ""):
                    options[field] = int(request.data.get(field))
            if request.data.get("restore_structure") not in (None, ""):
                options["restore_structure"] = _bool_param(request.data, "restore_structure")
            data = preflight_markdown_import(
                knowledge_base,
                upload.read(),
                filename=upload.name,
                actor=operator,
                options=options,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            return JsonResponse({"result": False, "message": str(error), "code": "import_options_invalid"}, status=400)
        except MarkdownImportGovernanceError as error:
            return _governance_error(error, status=error.status_code)
        log_operation(
            request,
            "create",
            "opspilot",
            f"预检 Markdown 导入: 知识库={knowledge_base.name} file={upload.name}",
        )
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def import_markdown_execute(self, request, pk=None):
        knowledge_base = self.get_object()
        upload = request.FILES.get("file")
        token = request.data.get("token")
        if not upload or not token:
            return JsonResponse({"result": False, "message": "file 与 token 必填"}, status=400)
        operator = getattr(request.user, "username", "") or ""
        try:
            data = execute_markdown_import(
                knowledge_base,
                token,
                upload.read(),
                filename=upload.name,
                actor=operator,
            )
        except MarkdownImportGovernanceError as error:
            return _governance_error(error, status=error.status_code)
        except BuildGenerationError as error:
            return _governance_error(error, status=409 if error.retryable else 422)
        log_operation(
            request,
            "create",
            "opspilot",
            f"执行 Markdown 导入: 知识库={knowledge_base.name} generation={data.get('generation_id')}",
        )
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def import_markdown(self, request, pk=None):
        """兼容旧入口：只执行安全预检，不再绕过一次性 token 直接写入。"""

        return self.import_markdown_preflight(request, pk=pk)

    @HasPermission("wiki_list-Add")
    @action(methods=["POST"], detail=False)
    def generate_purpose_schema(self, request):
        """根据模板 + 用户描述,AI 生成 purpose_md / schema_md 草稿(无模型/失败时回退模板骨架)。"""
        purpose, schema = generate_purpose_schema(
            template_key=request.data.get("template_key", "general"),
            description=request.data.get("description", ""),
            llm_model_id=request.data.get("llm_model_id"),
        )
        return JsonResponse({"result": True, "data": {"purpose_md": purpose, "schema_md": schema}})

    @HasPermission("wiki_list-View")
    @action(methods=["GET", "POST"], detail=True)
    def search(self, request, pk=None):
        """在知识库内检索(知识页面 + 资料摘要)。"""
        kb = self.get_object()
        params = request.data if request.method == "POST" else request.GET
        query = params.get("query", "")
        try:
            results = wiki_search(
                kb,
                query or "",
                top_k=_int_param(params, "top_k", 5, minimum=1),
                directory_id=_optional_int_param(params, "directory_id"),
                include_descendants=_bool_param(params, "include_descendants"),
            )
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        return JsonResponse({"result": True, "data": results})

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=True)
    def hybrid_search(self, request, pk=None):
        """混合检索:关键词召回 + 语义重排 + RRF 融合(知识库需配置 EmbedProvider 才启用语义)。"""
        kb = self.get_object()
        try:
            results = wiki_hybrid_search(
                kb,
                request.data.get("query", ""),
                top_k=int(request.data.get("top_k", 5)),
            )
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        return JsonResponse({"result": True, "data": results})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def reindex(self, request, pk=None):
        """重建知识库全部有效页面的页面级和 chunk 级索引,并落构建记录供诊断追踪。"""
        kb = self.get_object()
        if not kb.embed_provider_id:
            return JsonResponse({"result": False, "message": "知识库未配置向量模型,无法重建索引"}, status=400)
        pages = list(KnowledgePage.objects.filter(knowledge_base=kb, status="active").select_related("current_version").order_by("id"))
        record = rebuild_page_indexes(
            kb,
            pages,
            trigger="kb_reindex",
            event="kb_reindex",
            operator=getattr(request.user, "username", ""),
            inputs={"knowledge_base_id": kb.id, "knowledge_base_name": kb.name},
            index_fn=index_version,
            chunk_index_fn=reindex_page_chunks,
        )
        log_operation(request, "execute", "opspilot", f"重建知识库索引: {kb.name}")
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=True)
    def semantic_search(self, request, pk=None):
        """纯语义检索:基于已存储的页面嵌入做余弦相似检索(需先 reindex 且配置 EmbedProvider)。"""
        kb = self.get_object()
        results = wiki_semantic_search(kb, request.data.get("query", ""), top_k=int(request.data.get("top_k", 5)))
        return JsonResponse({"result": True, "data": results})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def reindex_chunks(self, request, pk=None):
        """构建/刷新分块索引:按标题切分页面正文,块级嵌入入库(细粒度语义检索)。"""
        kb = self.get_object()
        n_pages, n_chunks = wiki_reindex_chunks(kb)
        return JsonResponse({"result": True, "data": {"pages": n_pages, "chunks": n_chunks}})

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=True)
    def chunk_search(self, request, pk=None):
        """块级语义检索:返回最相关的页面分块(含所属标题),需先 reindex_chunks。"""
        kb = self.get_object()
        results = wiki_chunk_search(kb, request.data.get("query", ""), top_k=int(request.data.get("top_k", 5)))
        return JsonResponse({"result": True, "data": results})

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=True)
    def qa(self, request, pk=None):
        """问答试用:检索 + 作答 + 引用(可追溯到资料)。"""
        kb = self.get_object()
        try:
            result = wiki_answer(
                kb,
                request.data.get("query", ""),
                llm_model_id=kb.llm_model_id,
            )
        except (WikiBudgetExceeded, ActiveGenerationReadError) as error:
            return _governance_error(error, status=422)
        return JsonResponse({"result": True, "data": result})

    @HasPermission("wiki_list-View")
    @action(
        methods=["POST"],
        detail=True,
        renderer_classes=[CustomRenderer, EventStreamRenderer],
    )
    def qa_stream(self, request, pk=None):
        """检索测试流式回答:SSE meta/delta/done/error。"""
        kb = self.get_object()
        query = request.data.get("query", "")

        def event_stream():
            try:
                for event in wiki_stream_answer(
                    kb,
                    query,
                    llm_model_id=kb.llm_model_id,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except (WikiBudgetExceeded, ActiveGenerationReadError) as error:
                payload = {
                    "event": "error",
                    "code": getattr(error, "code", "wiki_qa_error"),
                    "message": str(error),
                    "details": getattr(error, "details", None),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as error:
                payload = {
                    "event": "error",
                    "code": "wiki_qa_stream_failed",
                    "message": str(error) or "wiki qa stream failed",
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def scan(self, request, pk=None):
        """系统检查扫描:发现孤立页面、缺来源等并写入检查事项。"""
        kb = self.get_object()
        created = scan_health(kb)
        return JsonResponse({"result": True, "data": {"created": len(created)}})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True, url_path="preview_merge")
    def preview_merge(self, request, pk=None):
        """合并预览:按 title_aliases 规则归一 KB 内所有 active 页面,返回会被合并到同一规范标题的页面集合(不写库)。"""
        kb = self.get_object()
        alias_map = title_alias_map(kb)
        # {compact_title_key(canonical): {canonical_label, pages: [{id, title, status}]}}
        buckets = {}
        active_pages = KnowledgePage.objects.filter(knowledge_base=kb, status="active").order_by("title").only("id", "title", "status")
        for page in active_pages:
            canonical = canonical_title(kb, page.title)
            # 用 compact_title_key 做桶 key,与 title_alias_map 的 key 形式一致(否则 alias_only 判定会失败)
            key = compact_title_key(canonical or page.title)
            bucket = buckets.setdefault(key, {"canonical": canonical or page.title, "pages": []})
            bucket["pages"].append({"id": page.id, "title": page.title, "status": page.status})

        merges = []
        # 只保留"会被合并的"桶(2+ 个页面共享同一规范标题)与"孤页但命中别名表"的桶
        for key, bucket in buckets.items():
            if len(bucket["pages"]) > 1:
                # 多页共享规范标题:这些页面将被合并
                merges.append(
                    {
                        "canonical": bucket["canonical"],
                        "merged_pages": [p["title"] for p in bucket["pages"]],
                        "page_ids": [p["id"] for p in bucket["pages"]],
                        "rule": "duplicate_canonical",
                    }
                )
            elif key in alias_map and bucket["pages"][0]["title"] != bucket["canonical"]:
                # 单页但标题命中别名表(说明页面用了别名,需要规范化为 canonical)
                merges.append(
                    {
                        "canonical": bucket["canonical"],
                        "merged_pages": [bucket["pages"][0]["title"]],
                        "page_ids": [bucket["pages"][0]["id"]],
                        "rule": "alias_only",
                    }
                )
        merges.sort(key=lambda item: (-len(item["page_ids"]), item["canonical"]))
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "merges": merges,
                    "total_canonical_groups": len(merges),
                    "active_page_count": active_pages.count(),
                },
            }
        )

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def rebuild(self, request, pk=None):
        """Schema 变更后全量重建:归档旧 AI 页、保留并标记人工页、按新 Schema 重生成。"""
        kb = self.get_object()
        operator = getattr(request.user, "username", "")
        try:
            with transaction.atomic():
                kb = WikiKnowledgeBase.objects.select_for_update().get(pk=kb.pk)
                if kb_has_user_build_in_progress(kb.pk) or has_active_runner(kb.pk):
                    return JsonResponse(
                        {
                            "result": False,
                            "message": "知识库存在运行中的构建任务,请等待完成后再操作",
                            "code": "knowledge_base_build_in_progress",
                        },
                        status=400,
                    )
                release_stale_runner_lease(kb.pk)
                # 可空 FK 不能和 FOR UPDATE 一起 select_related，PostgreSQL 会拒绝外连接空值边。
                materials = list(Material.objects.select_for_update().filter(knowledge_base=kb).order_by("id"))
                task_identity = _opspilot_tasks._freeze_wiki_task_identity(
                    kb,
                    materials,
                )
                record = create_rebuild_record(kb, operator=operator)
                _opspilot_tasks._persist_wiki_task_identity(record, task_identity)
        except BuildGenerationError as error:
            return _governance_error(
                error,
                status=409 if error.retryable else 422,
            )

        try:
            _opspilot_tasks.wiki_rebuild_kb_task.delay(
                kb.id,
                kb.llm_model_id,
                operator,
                record.id,
                None,
                task_identity,
            )
        except Exception as error:
            with transaction.atomic():
                WikiKnowledgeBase.objects.select_for_update().get(pk=kb.pk)
                failed = BuildRecord.objects.select_for_update().get(pk=record.pk)
                _opspilot_tasks._fail_wiki_task_build(
                    failed,
                    "task_dispatch_failed",
                    str(error),
                    retryable=True,
                )
            return _governance_error(
                BuildGenerationError(
                    "task_dispatch_failed",
                    "重建任务下发失败，请重试",
                    retryable=True,
                ),
                status=503,
            )
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

    @HasPermission("wiki_list-Edit")
    @action(methods=["POST"], detail=True)
    def rebuild_relations(self, request, pk=None):
        """重建页面关系(共享资料/正文引用)。"""
        kb = self.get_object()
        from apps.opspilot.services.wiki.relation_governance_service import rebuild_active_generation_relations

        try:
            result = rebuild_active_generation_relations(
                kb,
                operator=getattr(request.user, "username", "") or "",
            )
        except BuildGenerationError as error:
            return _governance_error(error, status=409 if error.retryable else 422)
        return JsonResponse(
            {
                "result": True,
                "data": {
                    "generation_id": result["generation_id"],
                    "relations": result["relations"]["relation_count"],
                    "build_record_id": result["build_record"].pk,
                },
            }
        )

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def relations(self, request, pk=None):
        """返回知识库的页面关系边(供校验与图谱)。"""
        kb = self.get_object()
        try:
            data = list_relations(kb)
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def graph(self, request, pk=None):
        """返回知识图谱:节点 + 边 + 连通分量社区 + 洞察。"""
        kb = self.get_object()
        try:
            data = build_graph(
                kb,
                directory_id=_optional_int_param(request.GET, "directory_id"),
                include_descendants=_bool_param(request.GET, "include_descendants"),
            )
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def graph_analysis(self, request, pk=None):
        """返回 4 信号关联度加权图 + 标签传播社区 + 洞察。"""
        kb = self.get_object()
        try:
            data = analyze_graph(
                kb,
                directory_id=_optional_int_param(request.GET, "directory_id"),
                include_descendants=_bool_param(request.GET, "include_descendants"),
            )
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["GET"], detail=True)
    def overview(self, request, pk=None):
        """概览工作区:页面/资料/构建/检查/关系统计 + 健康摘要。"""
        kb = self.get_object()
        try:
            data = get_overview(kb)
        except ActiveGenerationReadError as error:
            return _governance_error(error, status=409)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=False)
    def context(self, request):
        """多智能体复用:按所选知识库 + 问题取回可注入提示词的上下文 + 引用。"""
        kb_ids = request.data.get("kb_ids") or []
        if not isinstance(kb_ids, list):
            return JsonResponse({"result": False, "message": "kb_ids 必须为数组"}, status=400)
        try:
            kb_ids = list(dict.fromkeys(int(kb_id) for kb_id in kb_ids))
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "kb_ids 必须为整数数组"}, status=400)
        self.ensure_knowledge_base_ids_accessible(kb_ids)
        query = request.data.get("query", "")
        top_k = _int_param(request.data, "top_k", 5, minimum=1)
        graph_hops = _int_param(request.data, "graph_hops", 1, minimum=0)
        token_budget = _optional_int_param(request.data, "token_budget", minimum=1)
        retrieval_mode = request.data.get("retrieval_mode", "keyword")
        directory_id = _optional_int_param(request.data, "directory_id")
        include_descendants = _bool_param(request.data, "include_descendants")
        if directory_id is not None and len(kb_ids) != 1:
            return JsonResponse(
                {
                    "result": False,
                    "message": "目录范围检索一次只能选择一个知识库",
                    "code": "directory_scope_requires_single_knowledge_base",
                },
                status=422,
            )
        try:
            data = build_context(
                kb_ids,
                query,
                top_k=top_k,
                graph_hops=graph_hops,
                token_budget=token_budget,
                retrieval_mode=retrieval_mode,
                directory_id=directory_id,
                include_descendants=include_descendants,
            )
        except (WikiBudgetExceeded, ActiveGenerationReadError) as error:
            return _governance_error(error, status=422)
        return JsonResponse({"result": True, "data": data})

    @HasPermission("wiki_list-View")
    @action(methods=["POST"], detail=True)
    def sign_media(self, request, pk=None):
        """按知识库批量签发 wiki/media（知识页正文展示兜底）。"""
        kb = self.get_object()
        locators = request.data.get("locators") if isinstance(request.data, dict) else None
        if not isinstance(locators, list):
            return JsonResponse({"result": False, "message": "locators 必须为列表"}, status=400)
        urls = sign_media_locators(locators, knowledge_base_id=kb.id)
        return JsonResponse({"result": True, "data": {"urls": urls}})
