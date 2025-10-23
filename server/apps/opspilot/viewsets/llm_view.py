from django.http import JsonResponse, StreamingHttpResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.core.utils.async_utils import create_async_compatible_generator
from apps.core.utils.viewset_utils import AuthViewSet, LanguageViewSet
from apps.opspilot.models import KnowledgeBase, LLMModel, LLMSkill, SkillRequestLog, SkillTools
from apps.opspilot.serializers.llm_serializer import LLMModelSerializer, LLMSerializer, SkillRequestLogSerializer, SkillToolsSerializer
from apps.opspilot.utils.quota_utils import get_quota_client
from apps.opspilot.utils.sse_chat import stream_chat


class LLMFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    is_template = filters.NumberFilter(field_name="is_template", lookup_expr="exact")
    skill_type = filters.CharFilter(method="filter_skill_type")

    @staticmethod
    def filter_skill_type(qs, field_name, value):
        """查询类型"""
        if not value:
            return qs
        return qs.filter(skill_type__in=[int(i.strip()) for i in value.split(",") if i.strip()])


class LLMViewSet(AuthViewSet):
    serializer_class = LLMSerializer
    queryset = LLMSkill.objects.all()
    filterset_class = LLMFilter
    permission_key = "skill"

    @action(methods=["GET"], detail=False)
    @HasPermission("skill_list-View")
    def get_template_list(self, request):
        skill_list = LLMSkill.objects.filter(is_template=True)
        serializer = self.get_serializer(skill_list, many=True)
        return Response(serializer.data)

    @HasPermission("skill_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("skill_list-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("skill_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data
        if not request.user.is_superuser:
            client = get_quota_client(request)
            skill_count, used_skill_count, __ = client.get_skill_quota()
            if skill_count != -1 and skill_count <= used_skill_count:
                message = self.loader.get("skill_quota_exceeded") if self.loader else "Skill count exceeds quota limit."
                return JsonResponse({"result": False, "message": message})
        validate_msg = self._validate_name(params["name"], request.user.group_list, params["team"])
        if validate_msg:
            message = self.loader.get("skill_name_exists") if self.loader else f"A skill with the same name already exists in group {validate_msg}."
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        params["team"] = params.get("team", []) or [int(request.COOKIES.get("current_team"))]
        params["enable_conversation_history"] = True
        params[
            "skill_prompt"
        ] = """你是关于专业机器人，请按照以下要求进行回复
1、请根据用户的问题，从知识库检索关联的知识进行总结回复
2、请根据用户需求，从工具中选取适当的工具进行执行
3、回复的语句请保证准确，不要杜撰
4、请按照要点有条理的梳理答案"""
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("skill_setting-Edit")
    def update(self, request, *args, **kwargs):
        instance: LLMSkill = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            has_permission = self.get_has_permission(request.user, instance, current_team)
            if not has_permission:
                return JsonResponse(
                    {
                        "result": False,
                        "message": self.loader.get("permission_update_denied")
                        if self.loader
                        else "You do not have permission to update this instance",
                    }
                )

        params = request.data
        validate_msg = self._validate_name(
            params["name"],
            request.user.group_list,
            params["team"],
            exclude_id=instance.id,
        )
        if validate_msg:
            message = (
                self.loader.get("skill_name_exists_update") if self.loader else f"A skill with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        if (not request.user.is_superuser) and (instance.created_by != request.user.username):
            params.pop("team", [])
        if "team" in params:
            delete_team = [i for i in instance.team if i not in params["team"]]
            self.delete_rules(instance.id, delete_team)
        if "llm_model" in params:
            params["llm_model_id"] = params.pop("llm_model")
        if "km_llm_model" in params:
            params["km_llm_model_id"] = params.pop("km_llm_model")
        for tool in params.get("tools", []):
            for i in tool.get("kwargs", []):
                if i["type"] == "password":
                    EncryptMixin.decrypt_field("value", i)
                    EncryptMixin.encrypt_field("value", i)
        for key in params.keys():
            if hasattr(instance, key):
                setattr(instance, key, params[key])
        instance.updated_by = request.user.username
        if "rag_score_threshold" in params:
            score_threshold_map = {i["knowledge_base"]: i["score"] for i in params["rag_score_threshold"]}
            instance.rag_score_threshold_map = score_threshold_map
            knowledge_base_list = KnowledgeBase.objects.filter(id__in=list(score_threshold_map.keys()))
            instance.knowledge_base.set(knowledge_base_list)
        instance.save()
        return JsonResponse({"result": True})

    @staticmethod
    def _create_error_stream_response(error_message):
        """
        创建错误的流式响应
        用于在流式模式下返回错误信息
        """
        import json

        def error_generator():
            error_data = {"result": False, "message": error_message, "error": True}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        # 使用异步兼容的生成器包装器

        async_generator = create_async_compatible_generator(error_generator())

        response = StreamingHttpResponse(async_generator, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["X-Accel-Buffering"] = "no"  # Nginx
        # response["Pragma"] = "no-cache"
        # response["Expires"] = "0"
        # response["X-Buffering"] = "no"  # Apache
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "Cache-Control"
        return response

    @action(methods=["POST"], detail=False)
    @HasPermission("skill_setting-View")
    def execute(self, request):
        """
        {
            "user_message": "你好", # 用户消息
            "llm_model": 1, # 大模型ID
            "skill_prompt": "abc", # Prompt
            "enable_rag": True, # 是否启用RAG
            "enable_rag_knowledge_source": True, # 是否显示RAG知识来源
            "rag_score_threshold": [{"knowledge_base": 1, "score": 0.7}], # RAG分数阈值
            "chat_history": "abc", # 对话历史
            "conversation_window_size": 10, # 对话窗口大小
            "show_think": True, # 是否展示think的内容
            "group": 1,
            "enable_rag_strict_mode": False,
            "skill_name": "test"
        }
        """
        params = request.data
        params["username"] = request.user.username
        params["user_id"] = request.user.id
        try:
            # 获取客户端IP
            skill_obj = LLMSkill.objects.get(id=int(params["skill_id"]))
            if not request.user.is_superuser:
                current_team = request.COOKIES.get("current_team", "0")
                has_permission = self.get_has_permission(request.user, skill_obj, current_team, is_check=True)
                if not has_permission:
                    message = self.loader.get("no_agent_update_permission") if self.loader else "You do not have permission to update this agent."
                    return self._create_error_stream_response(message)

            current_ip = request.META.get("HTTP_X_FORWARDED_FOR")
            if current_ip:
                current_ip = current_ip.split(",")[0].strip()
            else:
                current_ip = request.META.get("REMOTE_ADDR", "")
                # 这里可以添加具体的配额检查逻辑
            params["skill_type"] = skill_obj.skill_type
            params["tools"] = params.get("tools", [])
            params["group"] = params["group"] if params.get("group") else skill_obj.team[0]
            params["enable_km_route"] = params["enable_km_route"] if params.get("enable_km_route") else skill_obj.enable_km_route
            params["km_llm_model"] = params["km_llm_model"] if params.get("km_llm_model") else skill_obj.km_llm_model
            params["enable_suggest"] = params["enable_suggest"] if params.get("enable_suggest") else skill_obj.enable_suggest
            params["enable_query_rewrite"] = params["enable_query_rewrite"] if params.get("enable_query_rewrite") else skill_obj.enable_query_rewrite
            # 调用stream_chat函数返回流式响应
            return stream_chat(params, skill_obj.name, {}, current_ip, params["user_message"])
        except LLMSkill.DoesNotExist:
            message = self.loader.get("skill_not_found_detail") if self.loader else "Skill not found."
            return self._create_error_stream_response(message)
        except Exception as e:
            logger.exception(e)
            return self._create_error_stream_response(str(e))


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    enabled = filters.CharFilter(method="filter_enabled")

    @staticmethod
    def filter_enabled(qs, field_name, value):
        """查询类型"""
        if not value:
            return qs
        enabled = value == "1"
        return qs.filter(enabled=enabled)


class LLMModelViewSet(AuthViewSet):
    serializer_class = LLMModelSerializer
    queryset = LLMModel.objects.all()
    permission_key = "provider.llm_model"
    filterset_class = ObjFilter

    @HasPermission("provide_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(methods=["POST"], detail=False)
    @HasPermission("provide_list-View")
    def search_by_groups(self, request):
        model_list = LLMModel.objects.all().values_list("name", flat=True)
        return JsonResponse({"result": True, "data": list(model_list)})

    @HasPermission("provide_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data
        if not params.get("team"):
            message = self.loader.get("team_empty") if self.loader else "The team is empty."
            return JsonResponse({"result": False, "message": message})
        validate_msg = self._validate_name(params["name"], request.user.group_list, params["team"])
        if validate_msg:
            message = (
                self.loader.get("llm_model_name_exists") if self.loader else f"A LLM Model with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        LLMModel.objects.create(
            name=params["name"],
            model_type_id=params["model_type"],
            llm_config=params["llm_config"],
            enabled=params.get("enabled", True),
            team=params.get("team"),
            label=params.get("label"),
            is_build_in=False,
        )
        return JsonResponse({"result": True})

    @HasPermission("provide_list-Setting")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        params = request.data
        validate_msg = self._validate_name(
            params["name"],
            request.user.group_list,
            params["team"],
            exclude_id=instance.id,
        )
        if validate_msg:
            message = (
                self.loader.get("llm_model_name_exists") if self.loader else f"A LLM Model with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        return super().update(request, *args, **kwargs)

    @HasPermission("provide_list-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_build_in:
            return JsonResponse(
                {
                    "result": False,
                    "message": self.loader.get("builtin_model_delete_denied") if self.loader else "Built-in model is not allowed to be deleted",
                }
            )
        return super().destroy(request, *args, **kwargs)


class LogFilter(FilterSet):
    skill_id = filters.NumberFilter(field_name="skill_id", lookup_expr="exact")
    current_ip = filters.CharFilter(field_name="current_ip", lookup_expr="icontains")
    start_time = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    end_time = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")


class SkillRequestLogViewSet(LanguageViewSet):
    serializer_class = SkillRequestLogSerializer
    queryset = SkillRequestLog.objects.all()
    filterset_class = LogFilter
    ordering = ("-created_at",)

    @HasPermission("skill_invocation_logs-View")
    def list(self, request, *args, **kwargs):
        if not request.GET.get("skill_id"):
            message = self.loader.get("skill_not_found") if self.loader else "Skill id not found"
            return JsonResponse({"result": False, "message": message})
        return super().list(request, *args, **kwargs)


class ToolsFilter(FilterSet):
    display_name = filters.CharFilter(field_name="display_name", lookup_expr="icontains")


class SkillToolsViewSet(AuthViewSet):
    serializer_class = SkillToolsSerializer
    queryset = SkillTools.objects.all()
    filterset_class = ToolsFilter
    permission_key = "tools"

    @HasPermission("tool_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("tool_list-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("tool_list-Setting")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @HasPermission("tool_list-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
