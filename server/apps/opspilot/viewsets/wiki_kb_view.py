import base64
import zipfile

from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import action

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot import tasks as _opspilot_tasks
from apps.opspilot.models import BuildRecord, KnowledgePage, WikiKnowledgeBase
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, WikiKnowledgeBaseSerializer
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.check_service import scan_health
from apps.opspilot.services.wiki.embedding_service import chunk_semantic_search as wiki_chunk_search
from apps.opspilot.services.wiki.embedding_service import index_version
from apps.opspilot.services.wiki.embedding_service import reindex_chunks as wiki_reindex_chunks
from apps.opspilot.services.wiki.embedding_service import reindex_page_chunks
from apps.opspilot.services.wiki.embedding_service import semantic_search as wiki_semantic_search
from apps.opspilot.services.wiki.graph_service import analyze_graph, build_graph
from apps.opspilot.services.wiki.index_rebuild_service import rebuild_page_indexes
from apps.opspilot.services.wiki.markdown_export_service import QuotaExceededError, build_markdown_export_zip
from apps.opspilot.services.wiki.markdown_import_service import import_markdown_archive
from apps.opspilot.services.wiki.overview_service import get_overview
from apps.opspilot.services.wiki.parsed_storage_service import delete_knowledge_base_parsed_markdown
from apps.opspilot.services.wiki.purpose_schema_service import generate_purpose_schema, list_templates
from apps.opspilot.services.wiki.rebuild_service import create_rebuild_record, running_build_record
from apps.opspilot.services.wiki.relation_service import list_relations, rebuild_relations
from apps.opspilot.services.wiki.retrieval_service import answer as wiki_answer
from apps.opspilot.services.wiki.retrieval_service import hybrid_search as wiki_hybrid_search
from apps.opspilot.services.wiki.retrieval_service import search as wiki_search
from apps.opspilot.services.wiki.title_service import canonical_title, compact_title_key, title_alias_map
from apps.opspilot.services.wiki.wiki_context_service import build_context
from apps.opspilot.viewsets.wiki_team_scope import WikiTeamScopeMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation


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


class WikiKnowledgeBaseViewSet(WikiTeamScopeMixin, AuthViewSet):
    """新 Wiki 知识库 CRUD + 创建流程(模板/AI 生成 Purpose+Schema)。沿用团队权限。"""

    queryset = WikiKnowledgeBase.objects.all().order_by("-id")
    serializer_class = WikiKnowledgeBaseSerializer
    ordering = ("-id",)
    search_fields = ("name",)
    team_scope_field = "id"

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

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return JsonResponse({"result": True, "data": serializer.data})

    def create(self, request, *args, **kwargs):
        params = request.data.copy()
        if not params.get("team"):
            params["team"] = [self._parse_current_team_cookie(request)]
        self.validate_team_assignment(params.get("team"))
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_operation(request, "create", "opspilot", f"新增知识库: {serializer.data.get('name', '')}")
        return JsonResponse({"result": True, "data": serializer.data}, status=201)

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

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if running_build_record(instance):
            return JsonResponse({"result": False, "message": "知识库存在运行中的构建任务,请等待完成后再操作"}, status=400)
        knowledge_base_id = instance.id
        name = instance.name
        instance.delete()
        delete_knowledge_base_parsed_markdown(knowledge_base_id)
        log_operation(request, "delete", "opspilot", f"删除知识库: {name}")
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=False)
    def templates(self, request):
        """返回创建知识库的场景模板列表。"""
        return JsonResponse({"result": True, "data": list_templates()})

    @action(methods=["GET"], detail=True)
    def export_markdown(self, request, pk=None):
        """导出当前知识库启用中的知识页面为 Markdown zip。带配额审计。"""
        kb = self.get_object()
        try:
            content, count = build_markdown_export_zip(kb)
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

    @action(methods=["POST"], detail=True)
    def import_markdown(self, request, pk=None):
        """导入 Markdown 或 Markdown zip 为内部知识页面,并触发增量维护。

        治理增强:同步导入失败时(解析/级联异常),自动落 BuildRecord(stage=failed)
        并投递 Celery 异步重试任务(最多 3 次退避)。OperationLog 记录尝试与最终结果。
        """
        kb = self.get_object()
        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"result": False, "message": "file 必填"}, status=400)
        operator = getattr(request.user, "username", "")
        content = upload.read()
        try:
            result = import_markdown_archive(kb, content, filename=upload.name, operator=operator)
        except (UnicodeDecodeError, ValueError, zipfile.BadZipFile) as exc:
            log_operation(
                request,
                "create",
                "opspilot",
                f"导入 Markdown 失败(可重试): 知识库={kb.name} file={upload.name} error={exc}",
            )
            return JsonResponse({"result": False, "message": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 - 任何意外都进重试队列
            logger.exception("wiki markdown 导入意外失败,投递重试")
            record = BuildRecord.objects.create(
                knowledge_base=kb,
                trigger="markdown_import",
                operator=operator,
                inputs={"filename": upload.name},
                stage="failed",
                progress=0,
                errors=[f"导入异常: {exc}"],
                status="failed",
            )
            try:
                encoded = base64.b64encode(content).decode("ascii")
                _opspilot_tasks.wiki_retry_markdown_import_task.delay(kb.id, record.id, encoded, upload.name, operator)
            except Exception:  # noqa: BLE001 - 重试队列投递失败不阻塞返回
                logger.exception("wiki markdown 重试任务投递失败")
            log_operation(
                request,
                "create",
                "opspilot",
                f"导入 Markdown 投递重试: 知识库={kb.name} build_record={record.id}",
            )
            return JsonResponse(
                {
                    "result": False,
                    "code": "import_retry",
                    "message": "导入异常,已加入重试队列",
                    "data": {"build_record": BuildRecordSerializer(record).data},
                },
                status=202,
            )

        maintenance = cascade(kb, result.page_ids, "markdown_import") if result.page_ids else {}
        status = maintenance.get("status", "success") if result.page_ids else "success"
        record = BuildRecord.objects.create(
            knowledge_base=kb,
            trigger="markdown_import",
            operator=operator,
            inputs={"filename": upload.name, **result.as_dict()},
            stage="done",
            progress=100,
            counts={"created": result.created, "updated": result.updated, "skipped": result.skipped},
            affected_pages=result.page_ids,
            maintenance=maintenance,
            status=status,
        )
        log_operation(
            request,
            "create",
            "opspilot",
            f"导入 Markdown 成功: 知识库={kb.name} 创建={result.created} 更新={result.updated} 跳过={result.skipped}",
        )
        return JsonResponse(
            {
                "result": True,
                "data": {
                    **result.as_dict(),
                    "build_record": BuildRecordSerializer(record).data,
                },
            }
        )

    @action(methods=["POST"], detail=False)
    def generate_purpose_schema(self, request):
        """根据模板 + 用户描述,AI 生成 purpose_md / schema_md 草稿(无模型/失败时回退模板骨架)。"""
        purpose, schema = generate_purpose_schema(
            template_key=request.data.get("template_key", "general"),
            description=request.data.get("description", ""),
            llm_model_id=request.data.get("llm_model_id"),
        )
        return JsonResponse({"result": True, "data": {"purpose_md": purpose, "schema_md": schema}})

    @action(methods=["GET", "POST"], detail=True)
    def search(self, request, pk=None):
        """在知识库内检索(知识页面 + 资料摘要)。"""
        kb = self.get_object()
        query = request.data.get("query") if request.method == "POST" else request.GET.get("query", "")
        results = wiki_search(kb, query or "", top_k=int(request.GET.get("top_k", 5)))
        return JsonResponse({"result": True, "data": results})

    @action(methods=["POST"], detail=True)
    def hybrid_search(self, request, pk=None):
        """混合检索:关键词召回 + 语义重排 + RRF 融合(知识库需配置 EmbedProvider 才启用语义)。"""
        kb = self.get_object()
        results = wiki_hybrid_search(kb, request.data.get("query", ""), top_k=int(request.data.get("top_k", 5)))
        return JsonResponse({"result": True, "data": results})

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

    @action(methods=["POST"], detail=True)
    def semantic_search(self, request, pk=None):
        """纯语义检索:基于已存储的页面嵌入做余弦相似检索(需先 reindex 且配置 EmbedProvider)。"""
        kb = self.get_object()
        results = wiki_semantic_search(kb, request.data.get("query", ""), top_k=int(request.data.get("top_k", 5)))
        return JsonResponse({"result": True, "data": results})

    @action(methods=["POST"], detail=True)
    def reindex_chunks(self, request, pk=None):
        """构建/刷新分块索引:按标题切分页面正文,块级嵌入入库(细粒度语义检索)。"""
        kb = self.get_object()
        n_pages, n_chunks = wiki_reindex_chunks(kb)
        return JsonResponse({"result": True, "data": {"pages": n_pages, "chunks": n_chunks}})

    @action(methods=["POST"], detail=True)
    def chunk_search(self, request, pk=None):
        """块级语义检索:返回最相关的页面分块(含所属标题),需先 reindex_chunks。"""
        kb = self.get_object()
        results = wiki_chunk_search(kb, request.data.get("query", ""), top_k=int(request.data.get("top_k", 5)))
        return JsonResponse({"result": True, "data": results})

    @action(methods=["POST"], detail=True)
    def qa(self, request, pk=None):
        """问答试用:检索 + 作答 + 引用(可追溯到资料)。"""
        kb = self.get_object()
        result = wiki_answer(kb, request.data.get("query", ""), llm_model_id=kb.llm_model_id)
        return JsonResponse({"result": True, "data": result})

    @action(methods=["POST"], detail=True)
    def scan(self, request, pk=None):
        """系统检查扫描:发现孤立页面、缺来源等并写入检查事项。"""
        kb = self.get_object()
        created = scan_health(kb)
        return JsonResponse({"result": True, "data": {"created": len(created)}})

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

    @action(methods=["POST"], detail=True)
    def rebuild(self, request, pk=None):
        """Schema 变更后全量重建:归档旧 AI 页、保留并标记人工页、按新 Schema 重生成。"""
        kb = self.get_object()
        if running_build_record(kb):
            return JsonResponse({"result": False, "message": "知识库存在运行中的构建任务,请等待完成后再操作"}, status=400)
        operator = getattr(request.user, "username", "")
        record = create_rebuild_record(kb, operator=operator)
        _opspilot_tasks.wiki_rebuild_kb_task.delay(kb.id, kb.llm_model_id, operator, record.id)
        return JsonResponse({"result": True, "data": BuildRecordSerializer(record).data})

    @action(methods=["POST"], detail=True)
    def rebuild_relations(self, request, pk=None):
        """重建页面关系(共享资料/正文引用)。"""
        kb = self.get_object()
        created = rebuild_relations(kb)
        return JsonResponse({"result": True, "data": {"relations": len(created)}})

    @action(methods=["GET"], detail=True)
    def relations(self, request, pk=None):
        """返回知识库的页面关系边(供校验与图谱)。"""
        kb = self.get_object()
        return JsonResponse({"result": True, "data": list_relations(kb)})

    @action(methods=["GET"], detail=True)
    def graph(self, request, pk=None):
        """返回知识图谱:节点 + 边 + 连通分量社区 + 洞察。"""
        kb = self.get_object()
        return JsonResponse({"result": True, "data": build_graph(kb)})

    @action(methods=["GET"], detail=True)
    def graph_analysis(self, request, pk=None):
        """返回 4 信号关联度加权图 + 标签传播社区 + 洞察。"""
        kb = self.get_object()
        return JsonResponse({"result": True, "data": analyze_graph(kb)})

    @action(methods=["GET"], detail=True)
    def overview(self, request, pk=None):
        """概览工作区:页面/资料/构建/检查/关系统计 + 健康摘要。"""
        kb = self.get_object()
        return JsonResponse({"result": True, "data": get_overview(kb)})

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
        return JsonResponse(
            {
                "result": True,
                "data": build_context(
                    kb_ids,
                    query,
                    top_k=top_k,
                    graph_hops=graph_hops,
                    token_budget=token_budget,
                    retrieval_mode=retrieval_mode,
                ),
            }
        )
