from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import WikiKnowledgeBase
from apps.opspilot.serializers.wiki_serializers import WikiKnowledgeBaseSerializer
from apps.opspilot.services.wiki.check_service import scan_health
from apps.opspilot.services.wiki.purpose_schema_service import generate_purpose_schema, list_templates
from apps.opspilot.services.wiki.relation_service import list_relations, rebuild_relations
from apps.opspilot.services.wiki.retrieval_service import answer as wiki_answer
from apps.opspilot.services.wiki.retrieval_service import search as wiki_search
from apps.opspilot.services.wiki.wiki_context_service import build_context
from apps.system_mgmt.utils.operation_log_utils import log_operation


class WikiKnowledgeBaseViewSet(AuthViewSet):
    """新 Wiki 知识库 CRUD + 创建流程(模板/AI 生成 Purpose+Schema)。沿用团队权限。"""

    queryset = WikiKnowledgeBase.objects.all().order_by("-id")
    serializer_class = WikiKnowledgeBaseSerializer
    ordering = ("-id",)
    search_fields = ("name",)

    def _user_group_ids(self, request):
        return [g["id"] for g in getattr(request.user, "group_list", []) or [] if isinstance(g, dict) and "id" in g]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not getattr(request.user, "is_superuser", False):
            group_ids = set(self._user_group_ids(request))
            queryset = [kb for kb in queryset if set(kb.team or []) & group_ids]
        serializer = self.get_serializer(queryset, many=True)
        return JsonResponse({"result": True, "data": serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return JsonResponse({"result": True, "data": serializer.data})

    def create(self, request, *args, **kwargs):
        params = request.data
        if not params.get("team"):
            params["team"] = [self._parse_current_team_cookie(request)]
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_operation(request, "create", "opspilot", f"新增知识库: {serializer.data.get('name', '')}")
        return JsonResponse({"result": True, "data": serializer.data}, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
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
        name = instance.name
        instance.delete()
        log_operation(request, "delete", "opspilot", f"删除知识库: {name}")
        return JsonResponse({"result": True})

    @action(methods=["GET"], detail=False)
    def templates(self, request):
        """返回创建知识库的场景模板列表。"""
        return JsonResponse({"result": True, "data": list_templates()})

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

    @action(methods=["POST"], detail=False)
    def context(self, request):
        """多智能体复用:按所选知识库 + 问题取回可注入提示词的上下文 + 引用。"""
        kb_ids = request.data.get("kb_ids") or []
        query = request.data.get("query", "")
        top_k = int(request.data.get("top_k", 5))
        return JsonResponse({"result": True, "data": build_context(kb_ids, query, top_k=top_k)})
