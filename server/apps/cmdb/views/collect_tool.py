# -- coding: utf-8 --
# @File: collect_tool.py
# @Time: 2026/05/08
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from apps.cmdb.serializers.collect_tool import CollectToolExecuteSerializer, CollectToolPrefillRequestSerializer, CollectToolResultRequestSerializer
from apps.cmdb.services.collect_tool_service import MASKED_PASSWORD, CollectToolService
from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class CollectToolViewSet(AuthViewSet):
    """
    采集工具 ViewSet，独立于 CollectModelViewSet，不操作采集任务模型。
    """

    @action(methods=["POST"], detail=False, url_path="execute")
    @HasPermission("collection_tool-Execute")
    def execute(self, request):
        """
        执行一次同步协议诊断。
        1. 校验并标准化请求参数
        2. 解析接入点，确定目标 Stargazer service_name
        3. 按 action 写死 timeout
        4. 若密码字段为 '••••••' 且 task_id 存在，从原任务解密注入
        5. 创建调试任务并异步投递执行
        6. 立即返回 debug_id，前端轮询结果
        """
        serializer = CollectToolExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)

        # Resolve access point to Stargazer service_name
        try:
            service_name = CollectToolService.resolve_access_point(request, payload["access_point_id"])
        except (ValidationError, Exception) as e:
            debug_id = CollectToolService.create_debug_id()
            result = CollectToolService.build_error_result(
                debug_id=debug_id,
                payload=payload,
                stage="param",
                summary=f"接入点解析失败: {e}",
            )
            CollectToolService.save_debug_state(debug_id, "error", result)
            return WebUtils.response_success(CollectToolService.build_submit_response(debug_id, "error", result))

        # Inject credentials if masked
        task_id = payload.get("task_id")
        credential = payload.get("credential", {})
        protocol = payload.get("protocol")

        if protocol == "snmp":
            masked_fields = {"community", "authkey", "privkey"}
        else:
            masked_fields = {"password"}

        has_masked = any(credential.get(f) == MASKED_PASSWORD for f in masked_fields)
        if has_masked:
            if not task_id:
                debug_id = CollectToolService.create_debug_id()
                result = CollectToolService.build_error_result(
                    debug_id=debug_id,
                    payload=payload,
                    stage="param",
                    summary="密码字段为脱敏占位，需要传入 task_id 以恢复原始凭据",
                )
                CollectToolService.save_debug_state(debug_id, "error", result)
                return WebUtils.response_success(CollectToolService.build_submit_response(debug_id, "error", result))
            try:
                instance = CollectToolService.get_accessible_task(request, task_id, operator="Operator")
                payload = CollectToolService.inject_credentials(payload, instance)
            except ValidationError as e:
                logger.warning(
                    "collect tool credential restore blocked, task_id=%s, user=%s, error=%s",
                    task_id,
                    getattr(request.user, "username", ""),
                    e,
                )
                debug_id = CollectToolService.create_debug_id()
                result = CollectToolService.build_error_result(
                    debug_id=debug_id,
                    payload=payload,
                    stage="param",
                    summary="无法恢复原始凭据，请确认原任务可访问，或手动重新输入凭据",
                )
                CollectToolService.save_debug_state(debug_id, "error", result)
                return WebUtils.response_success(CollectToolService.build_submit_response(debug_id, "error", result))
            except Exception:
                logger.exception(
                    "collect tool credential restore failed unexpectedly, task_id=%s, user=%s",
                    task_id,
                    getattr(request.user, "username", ""),
                )
                debug_id = CollectToolService.create_debug_id()
                result = CollectToolService.build_error_result(
                    debug_id=debug_id,
                    payload=payload,
                    stage="param",
                    summary="无法恢复原始凭据，请确认原任务可访问，或手动重新输入凭据",
                )
                CollectToolService.save_debug_state(debug_id, "error", result)
                return WebUtils.response_success(CollectToolService.build_submit_response(debug_id, "error", result))

        action_name = payload["action"]
        timeout = CollectToolService.get_timeout(action_name)
        debug_id = CollectToolService.create_debug_id()
        owner = CollectToolService.build_debug_owner(request)
        CollectToolService.enqueue_debug_task(debug_id, payload, service_name, timeout, owner)
        return WebUtils.response_success(CollectToolService.build_submit_response(debug_id, "pending"))

    @action(methods=["GET"], detail=False, url_path="result")
    @HasPermission("collection_tool-View")
    def result(self, request):
        serializer = CollectToolResultRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        debug_id = serializer.validated_data["debug_id"]
        result = CollectToolService.get_debug_state(debug_id)
        if not result:
            return WebUtils.response_success(CollectToolService.build_submit_response(debug_id, "not_found"))
        if not CollectToolService.can_access_debug_state(result, request):
            return WebUtils.response_403("抱歉！您没有访问该调试结果的权限")
        return WebUtils.response_success(result)

    @action(methods=["GET"], detail=False, url_path="prefill")
    @HasPermission("collection_tool-View")
    def prefill(self, request):
        """
        根据失败任务 ID 返回预填上下文。
        1. 读取 CollectModels(id=task_id)
        2. 提取可解析字段：target, port, access_point, credential
        3. 密码字段脱敏为 '••••••'
        4. 仅当任务不存在或没有任何可用预填字段时返回 can_prefill=false
        """
        serializer = CollectToolPrefillRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        task_id = serializer.validated_data["task_id"]
        protocol = serializer.validated_data["protocol"]

        try:
            instance = CollectToolService.get_accessible_task(request, task_id, operator="View")
        except ValidationError:
            return WebUtils.response_error(
                error_message="抱歉！您没有访问该采集任务的权限",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        result = CollectToolService.build_prefill(instance, task_id, protocol)
        return WebUtils.response_success(result)
