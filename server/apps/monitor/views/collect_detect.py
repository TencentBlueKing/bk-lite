import json

from rest_framework import viewsets

from apps.core.utils.web_utils import WebUtils
from apps.monitor.models import CollectDetectTask
from apps.monitor.services.collect_detect import CollectDetectService


class CollectDetectViewSet(viewsets.ViewSet):
    def create(self, request):
        organization = int(request.COOKIES.get("current_team") or 0)
        payload = getattr(request, "data", None)
        if payload is None:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        task = CollectDetectService.create_task(payload, request.user, organization)
        return WebUtils.response_success({"task_id": task.id, "status": task.status})

    def retrieve(self, request, pk=None):
        task = CollectDetectTask.objects.get(id=pk)
        return WebUtils.response_success(
            {
                "id": task.id,
                "status": task.status,
                "phase": task.phase,
                "result": task.result,
                "error_message": task.error_message,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            }
        )
