"""
告警处理动作回调视图

ActionCallbackView: 接收 job_mgmt 回调，校验 HMAC-SHA256 签名后更新 ActionExecution 状态。
ActionRuleViewSet: ActionRule 的 CRUD REST 视图集。
"""

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
from apps.core.decorators.api_permission import HasPermission
from apps.job_mgmt.utils.callback_signer import verify_callback_signature
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
        qs = super().get_queryset()
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
        qs = super().get_queryset()
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
        alert = Alert.objects.filter(alert_id=request.data.get("alert_id")).first()
        rule = ActionRule.objects.filter(id=request.data.get("rule_id")).first()
        if not alert or not rule:
            return Response({"result": False, "message": "alert/rule 不存在"}, status=400)
        execution = ActionExecution.objects.create(
            rule=rule,
            alert=alert,
            trigger_event="manual",
            trigger_type="manual",
            idempotency_key=None,
            status="pending",
            action_type=rule.action_type,
            operator=getattr(request.user, "username", None),
        )
        get_handler(rule.action_type).execute(rule, alert, execution)
        return Response({"result": True, "data": {"execution_id": execution.id}})
