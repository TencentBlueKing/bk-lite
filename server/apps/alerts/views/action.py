"""
告警处理动作回调视图

ActionCallbackView: 接收 job_mgmt 回调，校验 HMAC-SHA256 签名后更新 ActionExecution 状态。
"""

import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models.action import ActionExecution
from apps.job_mgmt.utils.callback_signer import verify_callback_signature

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
