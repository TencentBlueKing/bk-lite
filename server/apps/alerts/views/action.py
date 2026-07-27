"""
告警处理动作回调视图

ActionCallbackView: 接收 job_mgmt 回调，校验 HMAC-SHA256 签名后更新 ActionExecution 状态。
ActionRuleViewSet: ActionRule 的 CRUD REST 视图集。
"""

import hashlib
import logging

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.action.handlers.registry import get_handler
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.models.action import ActionExecution, ActionRule
from apps.alerts.models.models import Alert
from apps.alerts.serializers.action import ActionExecutionSerializer, ActionRuleSerializer
from apps.alerts.utils.operator_log import record_operator_log
from apps.alerts.utils.permission_scope import (
    apply_team_scope_for_request,
    get_authorized_group_ids,
    get_current_team_from_request,
)
from apps.core.decorators.api_permission import HasPermission
from apps.job_mgmt.utils.callback_signer import verify_callback_signature
from apps.rpc.job_mgmt import JobMgmt
from config.drf.viewsets import ModelViewSet

logger = logging.getLogger(__name__)


def verify_job_signature(request) -> bool:
    """校验 job_mgmt 回调的 HMAC-SHA256 签名。

    算法与 job_mgmt 出站签名完全对称：
    - 密钥: settings.CALLBACK_SIGN_KEY 或 settings.SECRET_KEY (UTF-8 bytes)
    - 消息: f"{timestamp}{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
    - 算法: HMAC-SHA256 → hexdigest
    - 头部: X-BK-Lite-Timestamp / X-BK-Lite-Signature
    - 有效期: 签名时间戳与当前时间差不得超过 300 秒
    """
    # 读取签名头（Django META 中破折号→下划线，HTTP_ 前缀）
    timestamp_str = request.META.get("HTTP_X_BK_LITE_TIMESTAMP")
    signature = request.META.get("HTTP_X_BK_LITE_SIGNATURE")

    if not timestamp_str or not signature:
        logger.warning("[callback] 缺少签名头: timestamp=%s, signature=%s", timestamp_str, bool(signature))
        return False

    try:
        timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        logger.warning("[callback] 时间戳格式无效: %s", timestamp_str)
        return False

    # request.data 已解析为 dict；复用它作为 payload 参与签名验证
    # job_mgmt 签名时传入的就是 payload dict，verify_callback_signature 用 sort_keys=True 序列化
    payload = request.data if isinstance(request.data, dict) else {}

    result = verify_callback_signature(payload, timestamp, signature)
    if not result:
        logger.warning("[callback] 签名验证失败: timestamp=%s", timestamp_str)
    return result


class ActionCallbackView(APIView):
    """接收 job_mgmt 作业结果回调，更新 ActionExecution 状态。"""

    permission_classes = [AllowAny]

    def post(self, request):
        if not verify_job_signature(request):
            return Response({"result": False, "message": "invalid signature"}, status=403)

        data = request.data
        task_id = data.get("task_id")
        execution = ActionExecution.objects.filter(job_task_id=task_id).order_by("-id").first()
        if not execution:
            logger.info("[callback] 未找到对应的 ActionExecution: job_task_id=%s", task_id)
            return Response({"result": True})

        status_val = "success" if data.get("status") == "success" else "failed"
        execution.status = status_val
        execution.result = {
            "total_count": data.get("total_count"),
            "success_count": data.get("success_count"),
            "failed_count": data.get("failed_count"),
            "finished_at": data.get("finished_at"),
            "raw_status": data.get("status"),
        }
        execution.save(update_fields=["status", "result", "updated_at"])
        logger.info(
            "[callback] ActionExecution 状态已更新: id=%s, job_task_id=%s, status=%s",
            execution.id,
            task_id,
            status_val,
        )
        return Response({"result": True})


class ActionRuleViewSet(ModelViewSet):
    """告警处理动作规则 CRUD 视图集。"""

    queryset = ActionRule.objects.all().order_by("-id")
    serializer_class = ActionRuleSerializer

    def get_queryset(self):
        qs = apply_team_scope_for_request(super().get_queryset(), self.request)
        name = self.request.query_params.get("name")
        action_type = self.request.query_params.get("action_type")
        is_active = self.request.query_params.get("is_active")
        if name:
            qs = qs.filter(name__icontains=name)
        if action_type:
            qs = qs.filter(action_type=action_type)
        if is_active is not None:
            qs = qs.filter(is_active=(is_active in ("true", "1", "True")))
        return qs

    @HasPermission("action_rule-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("action_rule-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("action_rule-Add")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        log_data = {
            "action": LogAction.ADD,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警处理动作规则-创建",
            "target_id": serializer.data["id"],
            "overview": f"创建告警处理动作规则[{serializer.data['name']}]",
        }
        record_operator_log(**log_data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @HasPermission("action_rule-Edit")
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        log_data = {
            "action": LogAction.MODIFY,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警处理动作规则-修改",
            "target_id": instance.id,
            "overview": f"修改告警处理动作规则[{instance.name}]",
        }
        record_operator_log(**log_data)
        return super().update(request, *args, **kwargs)

    @HasPermission("action_rule-Edit")
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("action_rule-Delete")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        log_data = {
            "action": LogAction.DELETE,
            "target_type": LogTargetType.SYSTEM,
            "operator": request.user.username,
            "operator_object": "告警处理动作规则-删除",
            "target_id": instance.id,
            "overview": f"删除告警处理动作规则[{instance.name}]",
        }
        record_operator_log(**log_data)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActionExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """告警执行记录只读视图集，支持手动触发。"""

    queryset = ActionExecution.objects.all().order_by("-created_at")
    serializer_class = ActionExecutionSerializer

    def get_queryset(self):
        scoped_alerts = apply_team_scope_for_request(Alert.objects.all(), self.request)
        qs = super().get_queryset().filter(alert__in=scoped_alerts)
        alert_id = self.request.query_params.get("alert_id")
        rule_id = self.request.query_params.get("rule_id")
        status_val = self.request.query_params.get("status")
        if alert_id:
            qs = qs.filter(alert__alert_id=alert_id)
        if rule_id:
            qs = qs.filter(rule_id=rule_id)
        if status_val:
            qs = qs.filter(status=status_val)
        return qs

    @HasPermission("action_exec-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("action_exec-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    @HasPermission("action_exec-Manual")
    def manual_trigger(self, request):
        client_key = request.headers.get("Idempotency-Key", "").strip()
        if not client_key or len(client_key) > 128:
            return Response(
                {"detail": "Idempotency-Key 必填且长度不能超过 128"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alert = apply_team_scope_for_request(Alert.objects.all(), request).filter(
            alert_id=request.data.get("alert_id")
        ).first()
        rule = apply_team_scope_for_request(ActionRule.objects.all(), request).filter(
            id=request.data.get("rule_id")
        ).first()
        if not alert or not rule:
            return Response({"detail": "alert/rule 不存在或无权访问"}, status=status.HTTP_400_BAD_REQUEST)

        operator = getattr(request.user, "username", None) or "anonymous"
        key_digest = hashlib.sha256(client_key.encode("utf-8")).hexdigest()
        idempotency_key = f"manual:{operator}:{rule.id}:{alert.alert_id}:{key_digest}"
        execution, created = ActionExecution.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "rule": rule,
                "alert": alert,
                "trigger_event": "manual",
                "trigger_type": "manual",
                "status": "pending",
                "action_type": rule.action_type,
                "operator": operator,
            },
        )
        if not created:
            return Response({"execution_id": execution.id, "status": execution.status, "deduplicated": True})

        # 与自动触发同源：写 OperatorLog，让"变更记录" Tab 也能展示手动触发。
        # 仅在首次创建 execution 时记录，幂等重放不会产生重复审计日志。
        try:
            record_operator_log(
                action=LogAction.EXECUTE,
                target_type=LogTargetType.ALERT,
                operator=operator,
                operator_object="告警处理-动作",
                target_id=alert.alert_id,
                overview=f"手动执行规则[{rule.name}]触发动作",
            )
        except Exception:
            # 与自动路径（action/engine.py:51-59）的容忍策略一致：审计日志写失败不阻塞主流程，
            # 但要把异常记录下来以便排障——而不是静默吞掉。
            logger.exception(
                "[ActionView] manual_trigger 写 OperatorLog 失败 alert_id=%s rule_id=%s",
                alert.alert_id, rule.id,
            )
        get_handler(rule.action_type).execute(rule, alert, execution)
        execution.refresh_from_db(fields=["status", "result"])
        response_data = {"execution_id": execution.id, "status": execution.status, "deduplicated": False}
        if execution.status in {"failed", "config_error"}:
            return Response(
                {"detail": execution.result.get("message", "动作执行失败"), "data": response_data},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(response_data)


class ActionJobScriptListView(APIView):
    """代理 job_mgmt 脚本列表，供告警动作规则编辑器使用。"""

    @HasPermission("action_rule-View")
    def get(self, request):
        group_id = get_current_team_from_request(request, required=True)
        if not group_id:
            return Response({"result": False, "message": "缺少团队上下文"}, status=status.HTTP_400_BAD_REQUEST)

        data = JobMgmt().list_scripts(group_id=group_id, team=get_authorized_group_ids(request))
        return Response(data)


class ActionJobScriptDetailView(APIView):
    """代理 job_mgmt 单个脚本详情（含 params），供告警动作字段绑定表使用。"""

    @HasPermission("action_rule-View")
    def get(self, request, script_id):
        group_id = get_current_team_from_request(request, required=True)
        if not group_id:
            return Response({"result": False, "message": "缺少团队上下文"}, status=status.HTTP_400_BAD_REQUEST)
        data = JobMgmt().get_script(script_id, team=get_authorized_group_ids(request))
        if not data:
            return Response({"result": False, "message": "脚本不存在或无权访问"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)
