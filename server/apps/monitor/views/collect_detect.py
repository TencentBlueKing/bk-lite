import json

from rest_framework import viewsets

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import CollectDetectTask
from apps.monitor.services.collect_detect import CollectDetectService
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.views.node_mgmt import _build_actor_context


def _ensure_monitor_object_access(request, monitor_object_id, actor_context):
    if actor_context["is_superuser"]:
        return

    permission = get_permission_rules(
        request.user,
        actor_context["current_team"],
        "monitor",
        f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
        include_children=actor_context.get("include_children", False),
    )
    if actor_context["current_team"] in permission.get("team", []):
        return
    if permission.get("instance"):
        return
    raise UnauthorizedException("无权限访问指定监控对象")


def _ensure_collect_detect_access(request, payload):
    actor_context = _build_actor_context(request)
    node_id = str(payload.get("node_id") or "").strip()
    if not node_id:
        raise BaseAppException("node_id 必填")

    monitor_object_id = int(payload.get("monitor_object_id") or 0)
    if not monitor_object_id:
        raise BaseAppException("monitor_object_id 必填")

    _ensure_monitor_object_access(request, monitor_object_id, actor_context)
    instance = {
        **(payload.get("instance") or {}),
        "node_ids": [node_id],
    }
    sanitized_instances = InstanceConfigService._sanitize_instances_for_onboarding([instance], actor_context)
    InstanceConfigService._validate_instances_with_plugin_selector(
        sanitized_instances,
        payload.get("monitor_plugin_id"),
        actor_context,
    )
    return actor_context


class CollectDetectViewSet(viewsets.ViewSet):
    def create(self, request):
        payload = getattr(request, "data", None)
        if payload is None:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        actor_context = _ensure_collect_detect_access(request, payload)
        organization = actor_context["current_team"]
        task = CollectDetectService.create_task(payload, request.user, organization)
        return WebUtils.response_success({"task_id": task.id, "status": task.status})

    def retrieve(self, request, pk=None):
        actor_context = _build_actor_context(request)
        task = CollectDetectTask.objects.filter(
            id=pk,
            created_by=actor_context["username"],
            organization=actor_context["current_team"],
        ).first()
        if not task:
            return WebUtils.response_error("任务不存在或无权访问", status_code=404)
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
