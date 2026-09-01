import datetime
import json

from django.db.models import Q
from django.http import JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models import WorkFlowTaskResult
from apps.opspilot.serializers.request_serializers import (
    InterruptChatFlowRequestSerializer,
    SubmitApprovalRequestSerializer,
    SubmitChoiceRequestSerializer,
)
from apps.opspilot.utils.execution_interrupt import request_interrupt

from apps.opspilot.views.chat_flow import extract_api_token, get_loader, parse_json_body, validate_openai_token

LOCAL_SKILL_HITL_NODES = frozenset({"skill_test", "deep_agent"})

def submit_approval(request):  # pragma: no cover
    """提交审批决策 — 用户对 Agent 危险操作的批准/拒绝。

    要求有效的 API Token（与 interrupt_chat_flow_execution 保持一致），并校验
    execution_id 归属于 Token 所属团队的 Bot，防止跨租户伪造审批决策。
    """
    loader = get_loader(request)
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)

    # 认证：要求有效 Token
    token = extract_api_token(request)
    is_valid, msg = validate_openai_token(token, get_current_team(request) or None)
    if not is_valid:
        return JsonResponse(msg, status=401)
    user = msg

    serializer = SubmitApprovalRequestSerializer(data=kwargs)
    if not serializer.is_valid():
        errors = serializer.errors
        if "decision" in errors and all(k not in errors for k in ("execution_id", "node_id", "tool_call_id")):
            message = "decision must be 'approve' or 'reject'"
        else:
            message = "execution_id, node_id, tool_call_id, decision are all required"
        return JsonResponse({"result": False, "message": message}, status=400)

    validated = serializer.validated_data
    execution_id = validated["execution_id"]
    node_id = validated["node_id"]
    tool_call_id = validated["tool_call_id"]
    decision = validated["decision"]

    # 归属校验：execution_id 必须属于调用者所在团队的 Bot
    task_result = (
        WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            bot_work_flow__bot__team__contains=int(user.team),
        )
        .order_by("-id")
        .first()
    )
    if not task_result:
        if node_id not in LOCAL_SKILL_HITL_NODES or WorkFlowTaskResult.objects.filter(execution_id=execution_id).exists():
            return JsonResponse(
                {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
                status=404,
            )
        logger.warning(
            "Local skill/AGUI approval submitted without workflow task result: execution_id=%s, node_id=%s, tool_call_id=%s",
            execution_id,
            node_id,
            tool_call_id,
        )

    from apps.opspilot.services.approval import submit_approval_decision

    submit_approval_decision(
        execution_id=execution_id,
        node_id=node_id,
        tool_call_id=tool_call_id,
        decision=decision,
        reason=validated["reason"],
        decided_by=kwargs.get("decided_by", getattr(user, "username", "")),
    )

    return JsonResponse({"result": True, "data": {"execution_id": execution_id, "node_id": node_id, "decision": decision}})


def submit_choice(request):  # pragma: no cover
    """提交用户选择 — 用户从多个选项中选择的结果。

    要求有效的 API Token，并校验 execution_id 归属于 Token 所属团队的 Bot，
    防止攻击者劫持他人工作流的选项决策。
    """
    loader = get_loader(request)
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)

    # 认证：要求有效 Token
    token = extract_api_token(request)
    is_valid, msg = validate_openai_token(token, get_current_team(request) or None)
    if not is_valid:
        return JsonResponse(msg, status=401)
    user = msg

    serializer = SubmitChoiceRequestSerializer(data=kwargs)
    if not serializer.is_valid():
        errors = serializer.errors
        if "selected" in errors and all(k not in errors for k in ("execution_id", "node_id", "choice_id")):
            message = "selected must be a non-empty list"
        else:
            message = "execution_id, node_id, choice_id are all required"
        return JsonResponse({"result": False, "message": message}, status=400)

    validated = serializer.validated_data
    execution_id = validated["execution_id"]
    node_id = validated["node_id"]
    choice_id = validated["choice_id"]
    selected = validated["selected"]

    # 归属校验：execution_id 必须属于调用者所在团队的 Bot
    task_result = (
        WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            bot_work_flow__bot__team__contains=int(user.team),
        )
        .order_by("-id")
        .first()
    )
    if not task_result:
        # 技能调试 / AGUI DeepAgent 本地会话没有 WorkFlowTaskResult；
        # 与 request_user_choice、ask_limit_continue 默认 node_id 对齐后放行。
        if node_id not in LOCAL_SKILL_HITL_NODES:
            return JsonResponse(
                {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
                status=404,
            )
        logger.warning(
            "Local skill/AGUI choice submitted without workflow task result: execution_id=%s, node_id=%s, choice_id=%s",
            execution_id,
            node_id,
            choice_id,
        )

    from apps.opspilot.utils.user_choice import submit_user_choice

    submit_user_choice(
        execution_id=execution_id,
        node_id=node_id,
        choice_id=choice_id,
        selected=selected,
    )

    return JsonResponse({"result": True, "data": {"execution_id": execution_id, "node_id": node_id, "selected": selected}})
