# -- coding: utf-8 --
# @File: source.py
# @Time: 2025/5/14 11:37
# @Author: windyzhao
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
from apps.alerts.models import AlertSource
from apps.core.utils.exempt import api_exempt


@csrf_exempt
@api_exempt
def receiver_data(request):
    """
    {
    source_type: "monitor",
    source_id: "monitor_id",
    secret: "your_secret",
    events: [
        {
            "title": "CPU Usage High",
            "description": "CPU usage exceeded 80%",
            "level": "critical",
            "start_time": "2025-05-14T10:00:00Z",
            "end_time": "2025-05-14T10:05:00Z",
            "labels": {"instance": "server1"},
            "annotations": {"alertname": "HighCPUUsage"},
            "event_id": "12345",
            "external_id": "67890",
            "status": "firing"
        }
    ]

    }

    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method."}, status=400)
    try:
        data = json.loads(request.body.decode("utf-8"))
        source_id = data.pop("source_id", None)
        events = data.pop("events", [])
        secret = request.META.get("HTTP_SECRET") or data.pop("secret", None)
        if not events:
            return JsonResponse({"status": "error", "message": "Missing events."}, status=400)

        event_source = AlertSource.objects.filter(source_id=source_id).first()
        if not event_source:
            return JsonResponse({"status": "error", "message": "Invalid source_id or source_type."}, status=400)

        if not secret:
            return JsonResponse({"status": "error", "message": "Missing secret."}, status=400)

        adapter_class = AlertSourceAdapterFactory.get_adapter(event_source)
        adapter = adapter_class(alert_source=event_source, secret=secret, events=events)

        # 验证密钥
        if not adapter.authenticate():
            return JsonResponse({"status": "error", "message": "Invalid secret."}, status=403)

        adapter.main()

        # TODO 若数据量大无法处理，及优化为异步处理 推送到队列
        # send_to_queue(events)
        return JsonResponse({"status": "success", "time": timezone.now().strftime("%Y-%m-%d %H:%M:%S"), "message": "Data received successfully."})
    except Exception as e:
        return JsonResponse({"status": "error", "time": timezone.now().strftime("%Y-%m-%d %H:%M:%S"), "message": str(e)}, status=500)
