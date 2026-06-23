from django.http import JsonResponse
from rest_framework.decorators import action

from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import Material
from apps.opspilot.serializers.wiki_serializers import BuildRecordSerializer, MaterialSerializer
from apps.opspilot.services.wiki.build_service import build_from_material
from apps.opspilot.services.wiki.material_service import ingest_material
from apps.opspilot.services.wiki.update_service import handle_material_deletion, propose_update
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
        serializer = self.get_serializer(queryset, many=True)
        return JsonResponse({"result": True, "data": serializer.data})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return JsonResponse({"result": True, "data": self.get_serializer(instance).data})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        material = serializer.instance
        # 文本/文件资料创建后同步摄取(解析 + AI 摘要),前端上传即得结果,无需再手动点"解析";
        # 网页资料需外网抓取、耗时不可控,仍走手动 ingest。(规模化后文件解析可改 Celery 异步)
        if material.material_type in ("text", "file"):
            ingest_material(material, llm_model_id=material.knowledge_base.llm_model_id)
            serializer = self.get_serializer(material)
        log_operation(request, "create", "opspilot", f"新增资料: {material.name}")
        return JsonResponse({"result": True, "data": serializer.data}, status=201)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        name = instance.name
        build = handle_material_deletion(instance, operator=getattr(request.user, "username", ""))
        log_operation(request, "delete", "opspilot", f"删除资料: {name}")
        return JsonResponse({"result": True, "data": {"pending_review": build.counts.get("pending_review", 0)}})

    @action(methods=["POST"], detail=True)
    def ingest(self, request, pk=None):
        """手动触发资料摄取(解析 + AI 摘要)。"""
        material = self.get_object()
        ingest_material(material, llm_model_id=material.knowledge_base.llm_model_id)
        return JsonResponse({"result": True, "data": self.get_serializer(material).data})

    @action(methods=["POST"], detail=True)
    def build(self, request, pk=None):
        """从该资料构建知识页面(Schema 驱动生成)。async=true 时走 Celery 异步,否则同步返回构建记录。"""
        material = self.get_object()
        operator = getattr(request.user, "username", "")
        if request.data.get("async"):
            from apps.opspilot.tasks import wiki_build_material_task

            wiki_build_material_task.delay(material.id, material.knowledge_base.llm_model_id, operator)
            return JsonResponse({"result": True, "data": {"async": True}})
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
