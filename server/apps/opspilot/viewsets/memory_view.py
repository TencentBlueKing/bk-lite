from django.http import JsonResponse
from langchain_core.messages import HumanMessage, SystemMessage
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import LLMModel
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.serializers.memory_serializer import MemorySerializer, MemorySpaceSerializer, WorkflowMemorySpaceOptionSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class MemorySpaceViewSet(AuthViewSet):
    queryset = MemorySpace.objects.all()
    serializer_class = MemorySpaceSerializer
    ordering = ("-id",)
    search_fields = ("name",)
    permission_key = "memory"

    @HasPermission("memory_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("memory_list-View")
    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_detail(request, *args, **kwargs)
        return JsonResponse({"result": True, "data": serializer.data})

    @HasPermission("memory_list-View")
    @action(methods=["GET"], detail=False, url_path="workflow_options")
    def workflow_options(self, request):
        """返回工作流记忆节点可选择的记忆空间，不按 current_team 过滤。"""
        queryset = MemorySpace.objects.all().order_by("-id")
        serializer = WorkflowMemorySpaceOptionSerializer(queryset, many=True)
        return JsonResponse({"result": True, "data": serializer.data})

    @HasPermission("memory_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data
        if not params.get("team"):
            params["team"] = [self._parse_current_team_cookie(request)]
        self._validate_org_field_permission(request, params["team"])
        response = super().create(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            space_name = response.data.get("name") if isinstance(response.data, dict) else params.get("name", "")
            log_operation(request, "create", "opspilot", f"新增记忆空间: {space_name}")
        return response

    @HasPermission("memory_list-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            space_name = response.data.get("name") if isinstance(response.data, dict) else request.data.get("name", "")
            log_operation(request, "update", "opspilot", f"编辑记忆空间: {space_name}")
        return response

    @HasPermission("memory_list-Edit")
    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            space_name = response.data.get("name") if isinstance(response.data, dict) else request.data.get("name", "")
            log_operation(request, "update", "opspilot", f"编辑记忆空间: {space_name}")
        return response

    @HasPermission("memory_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            log_operation(request, "delete", "opspilot", f"删除记忆空间: {obj.name}")
        return response

    @HasPermission("memory_list-Edit")
    @action(methods=["POST"], detail=False, url_path="test_write")
    def test_write(self, request):
        """测试记忆写入：使用传入的 write_rule 和 model_id，通过 LLM 处理输入内容并返回结果"""
        input_text = request.data.get("input", "")
        write_rule = request.data.get("write_rule", "")
        model_id = request.data.get("model_id")

        if not input_text:
            return JsonResponse({"result": False, "message": "input 为必填项"}, status=400)

        if not write_rule:
            return JsonResponse({"result": True, "data": {"result": input_text}})

        if not model_id:
            return JsonResponse({"result": False, "message": "model_id 为必填项"}, status=400)

        try:
            llm_model = LLMModel.objects.get(id=model_id)
        except LLMModel.DoesNotExist:
            return JsonResponse({"result": False, "message": "配置的模型不存在"}, status=404)

        # 构建 LLM 请求
        try:
            llm_request = BasicLLMRequest(
                openai_api_base=llm_model.openai_api_base,
                openai_api_key=llm_model.openai_api_key,
                model=llm_model.model_name,
                protocol_type=llm_model.protocol_type,
                vendor_type=llm_model.vendor.vendor_type if llm_model.vendor_id else "",
                temperature=0.3,
            )
            client = LLMClientFactory.create_client(llm_request, disable_stream=True)
            messages = [
                SystemMessage(content=write_rule),
                HumanMessage(content=input_text),
            ]
            response = client.invoke(messages)
            result_text = response.content if hasattr(response, "content") else str(response)
            return JsonResponse({"result": True, "data": {"result": result_text}})
        except Exception as e:
            logger.exception("记忆写入测试失败")
            return JsonResponse({"result": False, "message": f"LLM 调用失败: {str(e)}"}, status=500)


class MemoryViewSet(AuthViewSet):
    queryset = Memory.objects.all()
    serializer_class = MemorySerializer
    ordering = ("-id",)
    search_fields = ("title",)
    permission_key = "memory"
    filterset_fields = ("memory_space",)

    @HasPermission("memory_list-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        # 个人记忆仅创建者可见
        space_ids = MemorySpace.objects.filter(scope=MemorySpace.SCOPE_PERSONAL).values_list("id", flat=True)
        username = request.user.username
        domain = request.user.domain if hasattr(request.user, "domain") else ""
        queryset = queryset.exclude(memory_space_id__in=space_ids) | queryset.filter(
            memory_space_id__in=space_ids,
            owner_username=username,
            owner_domain=domain,
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return JsonResponse({"result": True, "data": serializer.data})

    @HasPermission("memory_list-View")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return JsonResponse({"result": True, "data": serializer.data})

    @HasPermission("memory_list-Add")
    def create(self, request, *args, **kwargs):
        request.data["owner_username"] = request.user.username
        request.data["owner_domain"] = getattr(request.user, "domain", "")
        response = super().create(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            memory_title = response.data.get("title") if isinstance(response.data, dict) else request.data.get("title", "")
            log_operation(request, "create", "opspilot", f"新增记忆: {memory_title}")
        return response

    @HasPermission("memory_list-Edit")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            memory_title = response.data.get("title") if isinstance(response.data, dict) else request.data.get("title", "")
            log_operation(request, "update", "opspilot", f"编辑记忆: {memory_title}")
        return response

    @HasPermission("memory_list-Edit")
    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            memory_title = response.data.get("title") if isinstance(response.data, dict) else request.data.get("title", "")
            log_operation(request, "update", "opspilot", f"编辑记忆: {memory_title}")
        return response

    @HasPermission("memory_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        response = super().destroy(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            log_operation(request, "delete", "opspilot", f"删除记忆: {obj.title}")
        return response
