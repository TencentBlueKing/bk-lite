from urllib.parse import urlparse

import yaml
from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.core.utils.viewset_utils import AuthViewSet, LanguageViewSet
from apps.opspilot.metis.llm.tools.elasticsearch.connection import normalize_es_instance, test_es_instance
from apps.opspilot.metis.llm.tools.jenkins.connection import normalize_jenkins_instance, test_jenkins_instance
from apps.opspilot.metis.llm.tools.kubernetes.connection import normalize_kubernetes_instance, test_kubernetes_instance
from apps.opspilot.metis.llm.tools.mysql.connection import normalize_mysql_instance, test_mysql_instance
from apps.opspilot.metis.llm.tools.oracle.connection import normalize_oracle_instance, test_oracle_instance
from apps.opspilot.metis.llm.tools.postgres.connection import normalize_postgres_instance, test_postgres_instance
from apps.opspilot.metis.llm.tools.redis.connection import normalize_redis_instance, test_redis_instance
from apps.opspilot.models import KnowledgeBase, LLMModel, LLMSkill, SkillRequestLog, SkillTools, UserPin
from apps.opspilot.serializers.llm_serializer import LLMModelSerializer, LLMSerializer, SkillRequestLogSerializer, SkillToolsSerializer
from apps.opspilot.services.builtin_tools import (
    BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
    BUILTIN_MONITOR_TOOL_NAME,
    BUILTIN_MSSQL_TOOL_NAME,
    BUILTIN_MYSQL_TOOL_NAME,
    BUILTIN_ORACLE_TOOL_NAME,
    BUILTIN_REDIS_TOOL_NAME,
    build_builtin_attachment_file_tool,
    build_builtin_monitor_tool,
    build_builtin_mssql_tool,
    build_builtin_mysql_tool,
    build_builtin_oracle_tool,
    build_builtin_redis_tool,
)
from apps.opspilot.services.mcp_client import MCPClient
from apps.opspilot.utils.agui_chat import stream_agui_chat
from apps.opspilot.utils.mcp_cache import get_cached_mcp_tools, set_cached_mcp_tools
from apps.opspilot.utils.pin_mixin import PinMixin
from apps.opspilot.utils.skill_execution_params import resolve_request_tools
from apps.opspilot.utils.sse_chat import stream_chat
from apps.opspilot.utils.vendor_model_mixin import VendorModelMixin
from apps.system_mgmt.utils.operation_log_utils import log_operation


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


class LLMViewSet(PinMixin, AuthViewSet):
    pin_content_type = UserPin.CONTENT_TYPE_SKILL
    pin_permission_error_key = "error.permission_update_denied"
    serializer_class = LLMSerializer
    queryset = LLMSkill.objects.all()
    filterset_class = LLMFilter
    permission_key = "skill"

    # F017: 明确允许通过 update 直接写入的标量模型字段白名单。
    # 排除主键 / 审计 / 域 / 内建标记等受保护字段，避免任意 request.data
    # 键被盲目 setattr 到模型上（mass-assignment）。team / knowledge_base /
    # rag_score_threshold 等关系字段及派生字段由下方专门逻辑处理，不在此列。
    UPDATABLE_SKILL_FIELDS = frozenset(
        {
            "name",
            "llm_model_id",
            "skill_prompt",
            "enable_conversation_history",
            "conversation_window_size",
            "enable_rag",
            "enable_rag_knowledge_source",
            "rag_score_threshold_map",
            "introduction",
            "team",
            "show_think",
            "tools",
            "skill_params",
            "temperature",
            "skill_type",
            "enable_rag_strict_mode",
            "is_template",
            "enable_km_route",
            "km_llm_model_id",
            "guide",
            "enable_suggest",
            "enable_query_rewrite",
            "instance_id",
            "skill_id",
        }
    )

    def query_by_groups(self, request, queryset):
        """重写排序逻辑：当前用户置顶优先，再按 ID 倒序"""
        return self.query_by_groups_with_pinned(request, queryset)

    @action(methods=["POST"], detail=True)
    @HasPermission("skill_setting-Edit")
    def toggle_pin(self, request, pk=None):
        return super().toggle_pin(request, pk)

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
        instance = self.get_object()
        skill_name = instance.name
        response = super().destroy(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            log_operation(request, "delete", "opspilot", f"删除智能体: {skill_name}")
        return response

    @HasPermission("skill_list-Add")
    def create(self, request, *args, **kwargs):
        params = request.data
        params["team"] = params.get("team", []) or [int(request.COOKIES.get("current_team"))]
        # 校验用户是否有目标组织的权限
        self._validate_org_field_permission(request, params["team"])
        validate_msg = self._validate_name(params["name"], request.user.group_list, params["team"])
        if validate_msg:
            message = (
                self.loader.get("error.skill_name_exists") if self.loader else f"A skill with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        params["enable_conversation_history"] = True
        params[
            "skill_prompt"
        ] = """你是关于专业机器人，请按照以下要求进行回复
1、请根据用户的问题，从知识库检索关联的知识进行总结回复
2、请根据用户需求，从工具中选取适当的工具进行执行
3、回复的语句请保证准确，不要杜撰
4、请按照要点有条理的梳理答案"""
        for item in params.get("skill_params", []):
            if item.get("type") == "password":
                EncryptMixin.encrypt_field("value", item)
        serializer = self.get_serializer(data=params)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        response = Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        skill_name = response.data.get("name") if isinstance(response.data, dict) else None
        if not skill_name:
            skill_name = request.data.get("name", "")
        log_operation(request, "create", "opspilot", f"新增智能体: {skill_name}")
        return response

    @HasPermission("skill_setting-Edit")
    def update(self, request, *args, **kwargs):
        instance: LLMSkill = self.get_object()
        if not request.user.is_superuser:
            current_team = request.COOKIES.get("current_team", "0")
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, instance, current_team, include_children=include_children)
            if not has_permission:
                return JsonResponse(
                    {
                        "result": False,
                        "message": (
                            self.loader.get("error.permission_update_denied") if self.loader else "You do not have permission to update this instance"
                        ),
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
                self.loader.get("error.skill_name_exists_update")
                if self.loader
                else f"A skill with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        if "team" in params:
            delete_team = [i for i in instance.team if i not in params["team"]]
            self.delete_rules(instance.id, delete_team)
        if "llm_model" in params:
            params["llm_model_id"] = params.pop("llm_model")
        if "km_llm_model" in params:
            params["km_llm_model_id"] = params.pop("km_llm_model")
        for tool in params.get("tools", []):
            for i in tool.get("kwargs", []):
                if i.get("type") == "password":
                    EncryptMixin.decrypt_field("value", i)
                    EncryptMixin.encrypt_field("value", i)
        # 处理 skill_params 中 password 类型的加密/保留
        old_skill_params = {p.get("key"): p for p in (instance.skill_params or [])}
        for item in params.get("skill_params", []):
            if item.get("type") == "password":
                if item.get("value") == "******":
                    old_param = old_skill_params.get(item.get("key"))
                    if old_param:
                        item["value"] = old_param["value"]
                else:
                    EncryptMixin.encrypt_field("value", item)
        # F017: 仅允许写入显式白名单内的字段，杜绝把任意 request.data 键
        # 盲目 setattr 到模型（mass-assignment）。受保护字段（id/created_by/
        # domain/is_builtin 等）即便随请求传入也被忽略。
        for key in self.UPDATABLE_SKILL_FIELDS:
            if key in params and hasattr(instance, key):
                setattr(instance, key, params[key])
        instance.updated_by = request.user.username
        if "rag_score_threshold" in params:
            score_threshold_map = {i["knowledge_base"]: i["score"] for i in params["rag_score_threshold"]}
            instance.rag_score_threshold_map = score_threshold_map
            knowledge_base_list = KnowledgeBase.objects.filter(id__in=list(score_threshold_map.keys()))
            instance.knowledge_base.set(knowledge_base_list)
        # 当 enable_rag=False 时，清空知识库和阈值配置
        if "enable_rag" in params and not params["enable_rag"]:
            instance.knowledge_base.clear()
            instance.rag_score_threshold_map = {}
        instance.save()
        log_operation(request, "update", "opspilot", f"编辑智能体: {instance.name}")
        return JsonResponse({"result": True})

    @staticmethod
    def create_error_stream_response(error_message):
        """
        创建错误的流式响应，用于在流式模式下返回错误信息。

        实际实现位于 utils.sse_chat.create_error_stream_response，此处保留
        静态方法仅为兼容既有调用方。
        """
        from apps.opspilot.utils.sse_chat import create_error_stream_response

        return create_error_stream_response(error_message)

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
                include_children = request.COOKIES.get("include_children", "0") == "1"
                has_permission = self.get_has_permission(
                    request.user,
                    skill_obj,
                    current_team,
                    is_check=True,
                    include_children=include_children,
                )
                if not has_permission:
                    message = (
                        self.loader.get("error.no_agent_update_permission") if self.loader else "You do not have permission to update this agent."
                    )
                    return self.create_error_stream_response(message)

            current_ip = request.META.get("HTTP_X_FORWARDED_FOR")
            if current_ip:
                current_ip = current_ip.split(",")[0].strip()
            else:
                current_ip = request.META.get("REMOTE_ADDR", "")
                # 这里可以添加具体的配额检查逻辑
            params["skill_type"] = skill_obj.skill_type
            params["tools"] = resolve_request_tools(params.get("tools"), skill_obj.tools)
            params["group"] = params["group"] if params.get("group") else skill_obj.team[0]
            params["enable_km_route"] = params["enable_km_route"] if params.get("enable_km_route") else skill_obj.enable_km_route
            params["km_llm_model"] = params["km_llm_model"] if params.get("km_llm_model") else skill_obj.km_llm_model
            params["enable_suggest"] = params["enable_suggest"] if params.get("enable_suggest") else skill_obj.enable_suggest
            params["enable_query_rewrite"] = params["enable_query_rewrite"] if params.get("enable_query_rewrite") else skill_obj.enable_query_rewrite
            params["show_think"] = params["show_think"] if params.get("show_think") is not None else skill_obj.show_think
            params["locale"] = getattr(request.user, "locale", "en")  # 用户语言设置
            # 合并前端传入的 skill_params 和 DB 中的值（处理 ****** 掩码）
            from apps.opspilot.utils.prompt_utils import merge_skill_params

            params["skill_params"] = merge_skill_params(params.get("skill_params", []), skill_obj.skill_params or [])
            # 调用stream_chat函数返回流式响应
            return stream_chat(params, skill_obj.name, {}, current_ip, params["user_message"])
        except LLMSkill.DoesNotExist:
            message = self.loader.get("error.skill_not_found_detail") if self.loader else "Skill not found."
            return self.create_error_stream_response(message)
        except Exception as e:
            logger.exception("Skill execute failed: skill_id=%s", params.get("skill_id"))
            return self.create_error_stream_response(str(e))

    @action(methods=["POST"], detail=False)
    @HasPermission("skill_setting-View")
    def execute_agui(self, request):
        """
        AGUI协议的execute接口

        遵循AGUI协议规范，调用metis的/api/agent/invoke_chatbot_workflow_agui接口

        请求参数与execute相同:
        {
            "user_message": "你好",
            "llm_model": 1,
            "skill_prompt": "abc",
            "enable_rag": True,
            "enable_rag_knowledge_source": True,
            "rag_score_threshold": [{"knowledge_base": 1, "score": 0.7}],
            "chat_history": "abc",
            "conversation_window_size": 10,
            "show_think": True,
            "group": 1,
            "enable_rag_strict_mode": False,
            "skill_name": "test"
        }

        返回AGUI协议格式的流式响应
        """
        params = request.data
        params["username"] = request.user.username
        params["user_id"] = request.user.id
        try:
            skill_obj = LLMSkill.objects.get(id=int(params["skill_id"]))
            if not request.user.is_superuser:
                current_team = request.COOKIES.get("current_team", "0")
                include_children = request.COOKIES.get("include_children", "0") == "1"
                has_permission = self.get_has_permission(
                    request.user,
                    skill_obj,
                    current_team,
                    is_check=True,
                    include_children=include_children,
                )
                if not has_permission:
                    message = (
                        self.loader.get("error.no_agent_update_permission") if self.loader else "You do not have permission to update this agent."
                    )
                    return self.create_error_stream_response(message)

            current_ip = request.META.get("HTTP_X_FORWARDED_FOR")
            if current_ip:
                current_ip = current_ip.split(",")[0].strip()
            else:
                current_ip = request.META.get("REMOTE_ADDR", "")

            params["skill_type"] = skill_obj.skill_type
            params["tools"] = resolve_request_tools(params.get("tools"), skill_obj.tools)
            params["group"] = params["group"] if params.get("group") else skill_obj.team[0]
            params["enable_km_route"] = params["enable_km_route"] if params.get("enable_km_route") else skill_obj.enable_km_route
            params["km_llm_model"] = params["km_llm_model"] if params.get("km_llm_model") else skill_obj.km_llm_model
            params["enable_suggest"] = params["enable_suggest"] if params.get("enable_suggest") else skill_obj.enable_suggest
            params["enable_query_rewrite"] = params["enable_query_rewrite"] if params.get("enable_query_rewrite") else skill_obj.enable_query_rewrite
            params["show_think"] = params["show_think"] if params.get("show_think") is not None else skill_obj.show_think
            params["locale"] = getattr(request.user, "locale", "en")  # 用户语言设置
            params["browser_use_force_task"] = True
            # 合并前端传入的 skill_params 和 DB 中的值（处理 ****** 掩码）
            from apps.opspilot.utils.prompt_utils import merge_skill_params

            params["skill_params"] = merge_skill_params(params.get("skill_params", []), skill_obj.skill_params or [])

            # 调用AGUI协议的流式响应
            return stream_agui_chat(params, skill_obj.name, {}, current_ip, params["user_message"])
        except LLMSkill.DoesNotExist:
            message = self.loader.get("error.skill_not_found_detail") if self.loader else "Skill not found."
            return self.create_error_stream_response(message)
        except Exception as e:
            logger.exception("AGUI skill execute failed: skill_id=%s", params.get("skill_id"))
            return self.create_error_stream_response(str(e))


class ObjFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    enabled = filters.CharFilter(method="filter_enabled")
    vendor = filters.NumberFilter(field_name="vendor_id", lookup_expr="exact")

    @staticmethod
    def filter_enabled(qs, field_name, value):
        """查询类型"""
        if not value:
            return qs
        enabled = value == "1"
        return qs.filter(enabled=enabled)


class LLMModelViewSet(VendorModelMixin, AuthViewSet):
    serializer_class = LLMModelSerializer
    queryset = LLMModel.objects.all()
    permission_key = "provider.llm_model"
    filterset_class = ObjFilter

    def _validate_llm_model_name(self, name, group_list, org_value, vendor_id, exclude_id=None):
        """验证 LLM 模型名称在同一供应商和团队中的唯一性"""
        try:
            if not name or not isinstance(name, str):
                return ""

            if not isinstance(group_list, list) or not isinstance(org_value, list):
                return ""

            if not vendor_id:
                return ""

            org_field = self.ORGANIZATION_FIELD
            # 添加 vendor_id 过滤条件
            queryset = self.queryset.filter(name=name, vendor_id=vendor_id)
            if exclude_id:
                queryset = queryset.exclude(id=exclude_id)

            team_list = list(queryset.values_list(org_field, flat=True))
            existing_teams = []

            for team_data in team_list:
                if isinstance(team_data, list):
                    existing_teams.extend(team_data)

            team_name_map = {}
            for group in group_list:
                if isinstance(group, dict) and "id" in group and "name" in group:
                    team_name_map[group["id"]] = group["name"]

            for team_id in org_value:
                if team_id in existing_teams:
                    conflict_team_name = team_name_map.get(team_id, f"Team-{team_id}")
                    return conflict_team_name

            return ""

        except Exception:
            logger.exception("Error in _validate_llm_model_name")
            return ""

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
            message = self.loader.get("error.team_empty") if self.loader else "The team is empty."
            return JsonResponse({"result": False, "message": message})
        # 校验用户是否有目标组织的权限
        self._validate_org_field_permission(request, params["team"])
        validate_msg = self._validate_llm_model_name(
            params["name"],
            request.user.group_list,
            params["team"],
            params.get("vendor"),
        )
        if validate_msg:
            message = (
                self.loader.get("error.llm_model_name_exists")
                if self.loader
                else f"A LLM Model with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        LLMModel.objects.create(
            name=params["name"],
            vendor_id=params["vendor"],
            model=params["model"],
            enabled=params.get("enabled", True),
            team=params.get("team"),
            label=params.get("label"),
            is_build_in=False,
        )
        response = JsonResponse({"result": True})
        log_operation(request, "create", "opspilot", f"新增模型: {params['name']}")
        return response

    @HasPermission("provide_list-Setting")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        params = request.data
        # 更新时使用请求中的 vendor，如果没有则使用实例原有的 vendor
        vendor_id = params.get("vendor") or instance.vendor_id
        validate_msg = self._validate_llm_model_name(
            params["name"],
            request.user.group_list,
            params["team"],
            vendor_id,
            exclude_id=instance.id,
        )
        if validate_msg:
            message = (
                self.loader.get("error.llm_model_name_exists")
                if self.loader
                else f"A LLM Model with the same name already exists in group {validate_msg}."
            )
            if self.loader:
                message = message.format(validate_msg=validate_msg)
            return JsonResponse({"result": False, "message": message})
        response = super().update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            model_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not model_name:
                model_name = params.get("name", instance.name)
            log_operation(request, "update", "opspilot", f"编辑模型: {model_name}")
        return response

    @HasPermission("provide_list-Delete")
    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            model_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not model_name:
                model_name = request.data.get("name", "")
            log_operation(request, "delete", "opspilot", f"删除模型: {model_name}")
        return response


class LogFilter(FilterSet):
    skill_id = filters.NumberFilter(field_name="skill_id", lookup_expr="exact")
    current_ip = filters.CharFilter(field_name="current_ip", lookup_expr="icontains")
    start_time = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    end_time = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")


class SkillRequestLogViewSet(LanguageViewSet):
    """技能调用日志 ViewSet - 仅暴露 list 接口，验证 skill 的 team 权限"""

    serializer_class = SkillRequestLogSerializer
    queryset = SkillRequestLog.objects.all()
    filterset_class = LogFilter
    ordering = ("-created_at",)
    # 仅允许 GET (list)，禁用其他内置接口
    http_method_names = ["get", "head", "options"]

    @HasPermission("skill_invocation_logs-View")
    def list(self, request, *args, **kwargs):
        skill_id = request.GET.get("skill_id")
        if not skill_id:
            message = self.loader.get("error.skill_not_found") if self.loader else "Skill id not found"
            return JsonResponse({"result": False, "message": message})

        # 验证 skill 存在且用户有权限访问
        skill = LLMSkill.objects.filter(id=skill_id).first()
        if not skill:
            message = self.loader.get("error.skill_not_found") if self.loader else "Skill not found"
            return JsonResponse({"result": False, "message": message})

        # 验证 current_team 权限
        if not request.user.is_superuser:
            current_team = self._parse_current_team_cookie(request)
            user_group_ids = {g["id"] for g in getattr(request.user, "group_list", [])}
            if current_team not in user_group_ids:
                raise PermissionDenied(self.loader.get("error.no_permission_access_team") if self.loader else "无权访问该团队数据")
            if current_team not in (skill.team or []):
                raise PermissionDenied(self.loader.get("error.no_permission_access_skill") if self.loader else "无权访问该技能的日志")

        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        """禁用 retrieve 接口"""
        return JsonResponse({"result": False, "message": "接口未启用"}, status=405)


class ToolsFilter(FilterSet):
    # display_name 是基于 language yaml 在序列化阶段动态翻译出来的派生字段，
    # 数据库中并不存在该列，无法直接做 ORM 过滤；这里退化为按 name(即工具 ID)
    # 进行模糊匹配，避免传入 display_name 参数时抛 FieldError。前端工具列表的
    # 展示名搜索走客户端过滤，不依赖该后端过滤器。
    display_name = filters.CharFilter(field_name="name", lookup_expr="icontains")


class SkillToolsViewSet(AuthViewSet):
    serializer_class = SkillToolsSerializer
    queryset = SkillTools.objects.all().order_by("-id")
    filterset_class = ToolsFilter
    permission_key = "tools"

    def _ssrf_error_response(self, error):
        """统一的 SSRF 拦截响应（保持 {result, message} 形状）。"""
        message = self.loader.get("error.connection_target_forbidden") if self.loader else "Connection target is not allowed"
        return JsonResponse({"result": False, "message": f"{message}: {error}"}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _guard_connection_host(host, port=None):
        """对 host(:port) 形式的连接目标做 SSRF 校验。

        复用统一的 ``SSRFValidator``：把 host/port 拼成 http(s) URL 后走与
        fetch/browser 工具同款的私网 / 链路本地 / 回环 / 云元数据阻断逻辑，
        防止被诱导对内网做端口扫描 / SSRF。

        Raises:
            SSRFError: 目标解析到被禁止的地址。
        """
        if host is None or str(host).strip() == "":
            return
        host = str(host).strip()
        # 去除可能误带的协议前缀，仅取主机名用于校验。
        netloc = host
        if "://" in netloc:
            netloc = urlparse(host).hostname or host
        target = f"http://{netloc}"
        if port not in (None, ""):
            target = f"http://{netloc}:{port}"
        SSRFValidator.validate(target)

    @classmethod
    def _guard_connection_url(cls, url):
        """对完整 URL 形式的连接目标做 SSRF 校验。"""
        if not url or not str(url).strip():
            return
        SSRFValidator.validate(str(url).strip())

    @classmethod
    def _guard_kubeconfig(cls, kubeconfig_data):
        """对 kubeconfig 中所有 cluster.server 地址做 SSRF 校验。

        防止通过上传任意 kubeconfig 诱导服务端连接内网 API server。
        非 http(s) 的 server 地址（理论上 k8s 仅用 https）会被校验器拒绝。
        """
        if not kubeconfig_data or not str(kubeconfig_data).strip():
            return

        try:
            kubeconfig = yaml.safe_load(kubeconfig_data)
        except Exception:
            # 无法解析的 kubeconfig 交由后续 normalize/连接逻辑报错，
            # 这里不替它产生误导性的 SSRF 错误。
            return
        if not isinstance(kubeconfig, dict):
            return
        for cluster in kubeconfig.get("clusters", []) or []:
            if not isinstance(cluster, dict):
                continue
            server = (cluster.get("cluster") or {}).get("server")
            if server:
                SSRFValidator.validate(str(server).strip())

    @HasPermission("tool_list-View")
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, list):
            loader = LanguageLoader(app="opspilot", default_lang=getattr(request.user, "locale", "en") or "en")
            if not any(item.get("name") == BUILTIN_ATTACHMENT_FILE_TOOL_NAME for item in response.data):
                response.data.append(build_builtin_attachment_file_tool(loader))
            if not any(item.get("name") == BUILTIN_MONITOR_TOOL_NAME for item in response.data):
                response.data.append(build_builtin_monitor_tool(loader))
            if not any(item.get("name") == BUILTIN_REDIS_TOOL_NAME for item in response.data):
                response.data.append(build_builtin_redis_tool(loader))
            if not any(item.get("name") == BUILTIN_MYSQL_TOOL_NAME for item in response.data):
                response.data.append(build_builtin_mysql_tool(loader))
            if not any(item.get("name") == BUILTIN_ORACLE_TOOL_NAME for item in response.data):
                response.data.append(build_builtin_oracle_tool(loader))
            if not any(item.get("name") == BUILTIN_MSSQL_TOOL_NAME for item in response.data):
                response.data.append(build_builtin_mssql_tool(loader))
        return response

    @HasPermission("tool_list-Add")
    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            tool_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not tool_name:
                tool_name = request.data.get("name", "")
            log_operation(request, "create", "opspilot", f"新增工具: {tool_name}")
        return response

    @HasPermission("tool_list-Setting")
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            tool_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not tool_name:
                tool_name = request.data.get("name", "")
            log_operation(request, "update", "opspilot", f"编辑工具: {tool_name}")
        return response

    @HasPermission("tool_list-Delete")
    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        if response.status_code >= 200 and response.status_code < 300:
            tool_name = response.data.get("name") if isinstance(response.data, dict) else None
            if not tool_name:
                tool_name = request.data.get("name", "")
            log_operation(request, "delete", "opspilot", f"删除工具: {tool_name}")
        return response

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def get_mcp_tools(self, request):
        """
        根据 MCP server 地址获取子工具列表

        MCP (Model Context Protocol) 标准握手流程:
        1. initialize - 建立连接并获取 session ID
        2. notifications/initialized - 通知服务器初始化完成
        3. tools/list - 请求工具列表

        请求参数:
            server_url: MCP server 地址
            enable_auth: 是否启用基本认证
            auth_token: 基本认证的 token
            force_refresh: 是否强制刷新缓存（可选，默认 False）
        返回格式:
            {
                "result": True,
                "data": [
                    {
                        "name": "tool_name",
                        "description": "tool description",
                        "input_schema": {...}
                    }
                ],
                "cached": True/False  # 是否来自缓存
            }
        """
        server_url = request.data.get("server_url")
        transport = request.data.get("transport", "")
        enable_auth = request.data.get("enable_auth", False)
        auth_token = request.data.get("auth_token", "")
        force_refresh = request.data.get("force_refresh", False)

        if not server_url:
            message = self.loader.get("error.server_url_required") if self.loader else "MCP server URL is required"
            return JsonResponse({"result": False, "message": message})

        # SSRF 防护：复用统一校验器（与 fetch/browser 工具同款），阻断私网 /
        # 链路本地 / 回环 / 云元数据地址以及非 http(s) 协议，避免服务端被诱导
        # 访问内网 MCP 服务。
        try:
            SSRFValidator.validate(server_url)
        except SSRFError as error:
            logger.warning("Blocked MCP server URL by SSRF guard: server_url=%s, reason=%s", server_url, error)
            message = self.loader.get("error.mcp_server_url_forbidden") if self.loader else "MCP server URL is not allowed"
            return JsonResponse({"result": False, "message": f"{message}: {error}"})

        # 先查缓存（非强制刷新时）
        if not force_refresh:
            cached_tools = get_cached_mcp_tools(server_url, auth_token, transport)
            if cached_tools is not None:
                return JsonResponse({"result": True, "data": cached_tools, "cached": True})

        # 构建 MCP 客户端配置
        mcp_config = {"server_url": server_url, "transport": transport}

        # 如果启用认证，添加认证信息
        if enable_auth:
            if not auth_token:
                message = self.loader.get("error.auth_token_required") if self.loader else "Auth token is required when authentication is enabled"
                return JsonResponse({"result": False, "message": message})

            mcp_config["enable_auth"] = True
            mcp_config["auth_token"] = auth_token

        try:
            with MCPClient(**mcp_config) as mcp_client:
                tools = mcp_client.get_tools()
                # 缓存结果
                set_cached_mcp_tools(server_url, tools, auth_token, transport)
                return JsonResponse({"result": True, "data": tools, "cached": False})
        except Exception as e:
            logger.exception("Failed to fetch MCP tools: server_url=%s", server_url)
            message = self.loader.get("error.mcp_server_error") if self.loader else "Error occurred while fetching MCP tools"
            return JsonResponse({"result": False, "message": f"{message}: {str(e)}"})

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_redis_connection(self, request):
        try:
            self._guard_connection_url(request.data.get("url"))
            if not request.data.get("url"):
                self._guard_connection_host(request.data.get("host"), request.data.get("port"))
            instance = normalize_redis_instance(request.data)
            if test_redis_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except RedisError as error:
            return JsonResponse({"result": False, "message": f"Redis connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        except TypeError as error:
            return JsonResponse({"result": False, "message": f"Redis connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "Redis connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_mysql_connection(self, request):
        try:
            self._guard_connection_host(request.data.get("host"), request.data.get("port"))
            instance = normalize_mysql_instance(request.data)
            if test_mysql_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"MySQL connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "MySQL connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_oracle_connection(self, request):
        try:
            self._guard_connection_host(request.data.get("host"), request.data.get("port"))
            instance = normalize_oracle_instance(request.data)
            if test_oracle_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"Oracle connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "Oracle connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_mssql_connection(self, request):
        from apps.opspilot.metis.llm.tools.mssql.connection import normalize_mssql_instance, test_mssql_instance

        try:
            self._guard_connection_host(request.data.get("host"), request.data.get("port"))
            instance = normalize_mssql_instance(request.data)
            if test_mssql_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"MSSQL connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "MSSQL connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_postgres_connection(self, request):
        try:
            self._guard_connection_host(request.data.get("host"), request.data.get("port"))
            instance = normalize_postgres_instance(request.data)
            if test_postgres_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"PostgreSQL connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "PostgreSQL connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_es_connection(self, request):
        try:
            self._guard_connection_url(request.data.get("url"))
            instance = normalize_es_instance(request.data)
            if test_es_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"Elasticsearch connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "Elasticsearch connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_jenkins_connection(self, request):
        try:
            self._guard_connection_url(request.data.get("jenkins_url"))
            instance = normalize_jenkins_instance(request.data)
            if test_jenkins_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"Jenkins connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "Jenkins connection test failed"}, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=["POST"], detail=False)
    @HasPermission("tool_list-View")
    def test_kubernetes_connection(self, request):
        try:
            self._guard_kubeconfig(request.data.get("kubeconfig_data"))
            instance = normalize_kubernetes_instance(request.data)
            if test_kubernetes_instance(instance):
                return JsonResponse({"result": True, "data": {"success": True}})
        except SSRFError as error:
            return self._ssrf_error_response(error)
        except ValueError as error:
            return JsonResponse({"result": False, "message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return JsonResponse({"result": False, "message": f"Kubernetes connection test failed: {error}"}, status=status.HTTP_400_BAD_REQUEST)
        return JsonResponse({"result": False, "message": "Kubernetes connection test failed"}, status=status.HTTP_400_BAD_REQUEST)
