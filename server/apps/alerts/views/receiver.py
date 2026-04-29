# -- coding: utf-8 --
"""
告警接收器

处理外部告警源发送过来的告警数据
"""
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.alerts.common.source_adapter.base import AlertSourceAdapterFactory
from apps.alerts.models.alert_source import AlertSource
from apps.core.logger import alert_logger as logger
from apps.core.utils.exempt import api_exempt
from apps.core.utils.web_utils import WebUtils


def _receive_events(request, path_source_id=None, expected_source_type=None):
    source_id = path_source_id
    try:
        data = json.loads(request.body.decode("utf-8"))
        if not isinstance(data, dict):
            return JsonResponse({"status": "error", "message": "Invalid request payload."}, status=400)

        payload_source_id = data.get("source_id")
        source_id = source_id or payload_source_id
        secret = request.META.get("HTTP_SECRET") or data.get("secret")

        if source_id and payload_source_id and payload_source_id != source_id:
            return JsonResponse({"status": "error", "message": "source_id mismatch."}, status=400)

        if not source_id:
            return JsonResponse({"status": "error", "message": "Missing source_id."}, status=400)

        event_source = AlertSource.objects.filter(source_id=source_id).first()
        if not event_source:
            return JsonResponse({"status": "error", "message": "Invalid source_id or source_type."}, status=400)

        if expected_source_type and event_source.source_type != expected_source_type:
            return JsonResponse({"status": "error", "message": "Invalid source type for endpoint."}, status=400)

        adapter_class = AlertSourceAdapterFactory.get_adapter(event_source)
        adapter = adapter_class(alert_source=event_source, secret=secret)

        events = adapter.normalize_payload(data)

        data.pop("source_id", None)
        data.pop("secret", None)

        if not isinstance(events, list) or not events:
            return JsonResponse({"status": "error", "message": "Missing events."}, status=400)

        if not secret:
            return JsonResponse({"status": "error", "message": "Missing secret."}, status=400)

        adapter = adapter_class(alert_source=event_source, secret=secret, events=events)

        if not adapter.authenticate():
            return JsonResponse({"status": "error", "message": "Invalid secret."}, status=403)

        adapter.main()
        return JsonResponse({"status": "success", "time": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                             "message": "Data received successfully."})
    except ValueError as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
    except Exception as e:
        logger.error(
            "receiver failed: source_id=%s, expected_source_type=%s, error=%s",
            source_id,
            expected_source_type,
            str(e),
            exc_info=True,
        )
        return JsonResponse({"status": "error", "time": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
                             "message": "Internal server error."}, status=500)


@csrf_exempt
@api_exempt
def receiver_source_data(request, source_id):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method."}, status=400)
    return _receive_events(request, path_source_id=source_id)


@csrf_exempt
@api_exempt
def receiver_data(request):
    """
    接收告警数据的函数视图
    
    :param request: 请求对象
    :return: JSON响应
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method."}, status=400)
    return _receive_events(request)


def request_test(requests):
    """
    Test function to handle requests.

    :param requests: The request data.
    :return: A response indicating success or failure.
    """
    logger.info("Processing request test: request=%s", requests)
    return WebUtils.response_success([])

