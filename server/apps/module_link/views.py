from rest_framework import status, viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.module_link.constants import BATCH_LIMIT
from apps.module_link.services.cmdb_monitor import CmdbMonitorTaskService, resolved_current_team, serialize_draft, serialize_task
from apps.module_link.services.monitor_cmdb import MonitorCmdbTaskService
from apps.module_link.services.monitor_cmdb import serialize_task as serialize_monitor_cmdb_task

CMDB_TASK_PERMISSION = "asset_info-Edit"
MONITOR_DRAFT_PERMISSION = "integration_configure-Add,integration_list-View"
MONITOR_TASK_PERMISSION = "integration_configure-Add,integration_list-View"


def _parse_uuid_list(value) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [str(item) for item in value if item not in (None, "")]


class CmdbMonitorTaskViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[0-9a-fA-F-]{36}"

    @HasPermission(CMDB_TASK_PERMISSION, app_name="cmdb")
    def create(self, request):
        inst_uuids = _parse_uuid_list(request.data.get("inst_uuids") if isinstance(request.data, dict) else None)
        if not inst_uuids:
            return WebUtils.response_error("inst_uuids 必须是非空数组", status_code=status.HTTP_400_BAD_REQUEST)
        if len(inst_uuids) > BATCH_LIMIT:
            return WebUtils.response_error("inst_uuids 数量超过上限", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            task = CmdbMonitorTaskService.create(inst_uuids, request=request)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return WebUtils.response_error("创建同步任务失败", status_code=status.HTTP_502_BAD_GATEWAY)
        return WebUtils.response_success(serialize_task(task))

    @HasPermission(CMDB_TASK_PERMISSION, app_name="cmdb")
    def retrieve(self, request, pk=None):
        task = CmdbMonitorTaskService.get_task(pk, request=request)
        if task is None:
            return WebUtils.response_error("任务不存在", status_code=status.HTTP_404_NOT_FOUND)
        return WebUtils.response_success(serialize_task(task))

    @HasPermission(CMDB_TASK_PERMISSION, app_name="cmdb")
    @action(methods=["post"], detail=True, url_path="cancel")
    def cancel(self, request, pk=None):
        task = CmdbMonitorTaskService.get_task(pk, request=request)
        if task is None:
            return WebUtils.response_error("任务不存在", status_code=status.HTTP_404_NOT_FOUND)
        task = CmdbMonitorTaskService.cancel(task)
        return WebUtils.response_success(serialize_task(task))

    @HasPermission(CMDB_TASK_PERMISSION, app_name="cmdb")
    @action(methods=["post"], detail=True, url_path="assign_object")
    def assign_object(self, request, pk=None):
        task = CmdbMonitorTaskService.get_task(pk, request=request)
        if task is None:
            return WebUtils.response_error("任务不存在", status_code=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        item_ids = _parse_uuid_list(payload.get("item_ids"))
        object_name = str(payload.get("object_name") or "").strip()
        remember = bool(payload.get("remember"))
        if not item_ids or not object_name:
            return WebUtils.response_error("item_ids 与 object_name 必填", status_code=status.HTTP_400_BAD_REQUEST)
        current_team = resolved_current_team(request)
        if remember and current_team is None:
            return WebUtils.response_error("current_team 不在授权范围内", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            task = CmdbMonitorTaskService.assign_object(
                task,
                item_ids=item_ids,
                object_name=object_name,
                remember=remember,
                request=request,
                current_team=current_team,
            )
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(serialize_task(task))


class MonitorCmdbTaskViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[0-9a-fA-F-]{36}"

    @HasPermission(MONITOR_TASK_PERMISSION, app_name="monitor")
    def create(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        monitor_ids = _parse_uuid_list(payload.get("monitor_ids"))
        object_name = str(payload.get("object_name") or "").strip()
        if not monitor_ids:
            return WebUtils.response_error("monitor_ids 必须是非空数组", status_code=status.HTTP_400_BAD_REQUEST)
        if len(monitor_ids) > BATCH_LIMIT:
            return WebUtils.response_error("monitor_ids 数量超过上限", status_code=status.HTTP_400_BAD_REQUEST)
        if not object_name:
            return WebUtils.response_error("object_name 必填", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            task = MonitorCmdbTaskService.create(monitor_ids, object_name, request=request)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return WebUtils.response_error("创建同步任务失败", status_code=status.HTTP_502_BAD_GATEWAY)
        return WebUtils.response_success(serialize_monitor_cmdb_task(task))

    @HasPermission(MONITOR_TASK_PERMISSION, app_name="monitor")
    def retrieve(self, request, pk=None):
        task = MonitorCmdbTaskService.get_task(pk, request=request)
        if task is None:
            return WebUtils.response_error("任务不存在", status_code=status.HTTP_404_NOT_FOUND)
        return WebUtils.response_success(serialize_monitor_cmdb_task(task))

    @HasPermission(MONITOR_TASK_PERMISSION, app_name="monitor")
    @action(methods=["post"], detail=True, url_path="cancel")
    def cancel(self, request, pk=None):
        task = MonitorCmdbTaskService.get_task(pk, request=request)
        if task is None:
            return WebUtils.response_error("任务不存在", status_code=status.HTTP_404_NOT_FOUND)
        task = MonitorCmdbTaskService.cancel(task)
        return WebUtils.response_success(serialize_monitor_cmdb_task(task))

    @HasPermission(MONITOR_TASK_PERMISSION, app_name="monitor")
    @action(methods=["post"], detail=True, url_path="create_missing")
    def create_missing(self, request, pk=None):
        task = MonitorCmdbTaskService.get_task(pk, request=request)
        if task is None:
            return WebUtils.response_error("任务不存在", status_code=status.HTTP_404_NOT_FOUND)
        payload = request.data if isinstance(request.data, dict) else {}
        item_ids = _parse_uuid_list(payload.get("item_ids"))
        if not item_ids:
            return WebUtils.response_error("item_ids 必须是非空数组", status_code=status.HTTP_400_BAD_REQUEST)
        if len(item_ids) > BATCH_LIMIT:
            return WebUtils.response_error("item_ids 数量超过上限", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            task = MonitorCmdbTaskService.create_missing(task, item_ids, request=request)
        except ValueError as exc:
            return WebUtils.response_error(str(exc), status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(serialize_monitor_cmdb_task(task))


class AccessDraftViewSet(viewsets.ViewSet):
    lookup_value_regex = r"[0-9a-fA-F-]{36}"

    @HasPermission(MONITOR_DRAFT_PERMISSION, app_name="monitor")
    def retrieve(self, request, pk=None):
        draft = CmdbMonitorTaskService.get_draft(pk, request=request)
        if draft is None:
            return WebUtils.response_error("草稿不存在", status_code=status.HTTP_404_NOT_FOUND)
        return WebUtils.response_success(serialize_draft(draft))
