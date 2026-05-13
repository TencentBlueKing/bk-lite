from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.opspilot.models import KnowledgeBase, KnowledgeGraph
from apps.opspilot.serializers.knowledge_graph_serializers import KnowledgeGraphSerializer
from apps.opspilot.tasks import rebuild_graph_community_by_instance
from apps.opspilot.utils.graph_utils import GraphUtils


class KnowledgeGraphFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    knowledge_base_id = filters.NumberFilter(field_name="knowledge_base_id", lookup_expr="exact")


class KnowledgeGraphViewSet(MaintainerViewSet):
    """知识图谱 ViewSet - 禁用未使用的 list/update/destroy 接口，添加 current_team 权限验证"""

    queryset = KnowledgeGraph.objects.all()
    serializer_class = KnowledgeGraphSerializer
    filterset_class = KnowledgeGraphFilter
    ordering = ("-id",)
    # 仅允许 GET (retrieve), POST (create, actions), PATCH (partial_update)
    # 禁用 PUT (update), DELETE (destroy), GET list
    http_method_names = ["get", "post", "patch", "options"]

    def _validate_knowledge_base_permission(self, request, knowledge_base):
        """验证用户对知识库的 current_team 权限"""
        if request.user.is_superuser:
            return
        current_team = self._parse_current_team_cookie(request)
        user_group_ids = {g["id"] for g in getattr(request.user, "group_list", [])}
        if current_team not in user_group_ids:
            raise PermissionDenied(self.loader.get("error.no_permission_access_team") if self.loader else "无权访问该团队数据")
        if current_team not in knowledge_base.team:
            raise PermissionDenied(self.loader.get("error.no_permission_access_knowledge_base") if self.loader else "无权访问该知识库")

    def list(self, request, *args, **kwargs):
        """禁用 list 接口"""
        return JsonResponse({"result": False, "message": self.loader.get("error.api_not_enabled") if self.loader else "接口未启用"}, status=405)

    @action(methods=["GET"], detail=False)
    @HasPermission("knowledge_document-View")
    def get_details(self, request):
        """获取图谱详情 - 验证 knowledge_base 的 current_team 权限"""
        knowledge_base_id = request.query_params.get("knowledge_base_id")
        knowledge_base = KnowledgeBase.objects.filter(id=knowledge_base_id).first()
        if not knowledge_base:
            return JsonResponse(
                {"result": False, "message": self.loader.get("error.knowledge_base_not_found") if self.loader else "知识库不存在"}, status=404
            )
        self._validate_knowledge_base_permission(request, knowledge_base)

        obj = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base_id).first()
        if not obj:
            return JsonResponse({"result": True, "data": {"is_exists": False}})
        if obj.status == "pending":
            return JsonResponse(
                {
                    "result": True,
                    "data": {"graph": {}, "graph_id": obj.id, "is_exists": True, "status": obj.status},
                }
            )
        res = GraphUtils.get_graph(obj.id)
        if not res["result"]:
            return JsonResponse(res)
        return_data = {"graph": res["data"], "graph_id": obj.id, "status": obj.status, "is_exists": True}
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Delete")
    def delete_graph(self, request):
        """删除图谱 - 验证 knowledge_base 的 current_team 权限"""
        knowledge_base_id = request.data.get("knowledge_base_id")
        knowledge_base = KnowledgeBase.objects.filter(id=knowledge_base_id).first()
        if not knowledge_base:
            return JsonResponse(
                {"result": False, "message": self.loader.get("error.knowledge_base_not_found") if self.loader else "知识库不存在"}, status=404
            )
        self._validate_knowledge_base_permission(request, knowledge_base)

        instance = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base_id).first()
        if not instance:
            return JsonResponse(
                {"result": False, "message": self.loader.get("error.knowledge_graph_not_found") if self.loader else "知识图谱不存在"}, status=404
            )

        if instance.status == "training":
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("error.knowledge_graph_training") if self.loader else "Knowledge graph is training, cannot delete",
                }
            )
        try:
            GraphUtils.delete_graph(instance)
        except Exception as e:
            return JsonResponse({"result": False, "message": str(e)}, status=500)
        instance.delete()
        return JsonResponse({"result": True})

    @action(methods=["POST"], detail=False)
    @HasPermission("knowledge_document-Train, knowledge_document-Set")
    def rebuild_graph_community(self, request):
        """重建图谱社区 - 验证 knowledge_base 的 current_team 权限"""
        knowledge_base_id = request.data.get("knowledge_base_id")
        knowledge_base = KnowledgeBase.objects.filter(id=knowledge_base_id).first()
        if not knowledge_base:
            return JsonResponse(
                {"result": False, "message": self.loader.get("error.knowledge_base_not_found") if self.loader else "知识库不存在"}, status=404
            )
        self._validate_knowledge_base_permission(request, knowledge_base)

        graph_obj = KnowledgeGraph.objects.filter(knowledge_base_id=knowledge_base_id).first()
        if not graph_obj:
            return JsonResponse(
                {"result": False, "message": self.loader.get("error.knowledge_graph_not_found") if self.loader else "Knowledge graph not found"}
            )
        if graph_obj.status != "completed":
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("error.knowledge_graph_not_completed") if self.loader else "Knowledge graph is not completed",
                }
            )
        try:
            rebuild_graph_community_by_instance.delay(graph_obj.id)
            return JsonResponse({"result": True})
        except Exception as e:
            return JsonResponse({"result": False, "message": str(e)})
