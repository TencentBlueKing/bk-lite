"""作业管理辅助视图"""

import json
import logging
from datetime import datetime

from django.http import JsonResponse

from apps.core.utils.exempt import api_exempt

logger = logging.getLogger("job")


@api_exempt
def callback_test(request):
    """
    回调测试端点

    用于本地测试 callback_url 功能，模拟第三方 App 接收回调。
    接收回调 payload 并打印到日志，方便调试确认回调内容。

    使用方式：
        在调用 job_script_execute / job_file_distribute 时设置：
        "callback_url": "http://localhost:8001/api/v1/job_mgmt/callback_test/"
    """
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        f"[callback_test] 收到回调 @ {now}\n"
        f"  task_id: {payload.get('task_id')}\n"
        f"  status: {payload.get('status')}\n"
        f"  total_count: {payload.get('total_count')}\n"
        f"  success_count: {payload.get('success_count')}\n"
        f"  failed_count: {payload.get('failed_count')}\n"
        f"  finished_at: {payload.get('finished_at')}"
    )

    return JsonResponse(
        {
            "result": True,
            "message": "callback received",
            "received_at": now,
            "payload": payload,
        }
    )
