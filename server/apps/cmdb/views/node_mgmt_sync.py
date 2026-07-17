from datetime import datetime

from rest_framework.decorators import action

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class NodeMgmtSyncViewSet(AuthViewSet):
    queryset = None
    MAX_SAFE_COUNT = 10_000_000
    COUNT_FIELDS = (
        "all",
        "add",
        "update",
        "delete",
        "association",
        "add_error",
        "add_success",
        "update_error",
        "update_success",
        "delete_error",
        "delete_success",
        "association_error",
        "association_success",
    )
    RUN_STATUSES = {
        "running",
        "waiting_sync",
        "submitted",
        "success",
        "partial_success",
        "blocked",
        "failed",
        "timeout",
        "unexecuted",
        "error",
        "writing",
        "force_stop",
        "unknown",
    }
    SCHEDULE_STATUSES = {
        "reconciling",
        "healthy",
        "degraded",
    }
    NODE_CONFIG_STATUSES = {
        "reconciling",
        "healthy",
        "degraded",
        "disabled",
        "waiting_sync",
        "unknown",
    }
    REASON_CODES = {
        "",
        "COLLECT_ALREADY_RUNNING",
        "COLLECT_CHILD_FAILED",
        "COLLECT_EXECUTION_ID_MISSING",
        "COLLECT_EXECUTION_SUPERSEDED",
        "COLLECT_SUBMISSION_BLOCKED",
        "COLLECT_SUBMIT_FAILED",
        "COLLECT_TASK_MISSING",
        "INVALID_REGION_CODE",
        "NODE_CONFIG_DELETE_FAILED",
        "NODE_CONFIG_PUSH_FAILED",
        "NODE_CONFIG_RECONCILE_FAILED",
        "NODE_PAGE_LIMIT_EXCEEDED",
        "NODE_QUERY_FAILED",
        "NODE_QUERY_TIMEOUT",
        "NODE_SOURCE_EMPTY",
        "NO_VALID_NODES",
        "NO_ACCESS_POINT",
        "RECONCILE_FAILED",
        "RECOVERY_FAILED",
        "RUN_ALREADY_ACTIVE",
        "RUN_FAILED",
        "RUN_NOT_ACTIVE",
        "RUN_TIMEOUT",
        "SYNC_REQUIRED",
    }
    TIME_FORMAT = "%Y-%m-%d %H:%M:%S%z"

    @classmethod
    def _safe_count(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value if 0 <= value <= cls.MAX_SAFE_COUNT else 0

    @classmethod
    def _safe_id(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 0 < value <= 2 ** 63 - 1 else None

    @classmethod
    def _safe_time(cls, value):
        if not isinstance(value, str):
            return ""
        try:
            parsed = datetime.strptime(value, cls.TIME_FORMAT)
        except ValueError:
            return ""
        return value if parsed.strftime(cls.TIME_FORMAT) == value else ""

    @staticmethod
    def _safe_choice(value, allowed, default=None):
        return value if isinstance(value, str) and value in allowed else default

    @classmethod
    def _safe_reason_code(cls, value):
        return value if isinstance(value, str) and value in cls.REASON_CODES else ""

    @classmethod
    def _safe_summary(cls, summary):
        source = summary if isinstance(summary, dict) else {}
        result = {field: cls._safe_count(source.get(field)) for field in cls.COUNT_FIELDS}
        result["message"] = ""
        result["last_time"] = cls._safe_time(source.get("last_time"))
        return result

    @classmethod
    def _safe_detail(cls, detail):
        source = detail if isinstance(detail, dict) else {}
        result = {}
        for name in ("add", "update", "delete", "relation", "raw_data"):
            bucket = source.get(name)
            count = cls._safe_count(bucket.get("count")) if isinstance(bucket, dict) else 0
            result[name] = {"data": [], "count": count}
        result["todo"] = []
        return result

    @classmethod
    def _safe_run(cls, payload):
        source = payload if isinstance(payload, dict) else {}
        return {
            "id": cls._safe_id(source.get("id")),
            "task_id": cls._safe_id(source.get("task_id")),
            "run_type": cls._safe_choice(source.get("run_type"), {"sync", "collect"}),
            "status": cls._safe_choice(source.get("status"), cls.RUN_STATUSES),
            "reason_code": cls._safe_reason_code(source.get("reason_code")),
            "started_at": cls._safe_time(source.get("started_at")),
            "submitted_at": cls._safe_time(source.get("submitted_at")),
            "finished_at": cls._safe_time(source.get("finished_at")),
            "deadline_at": cls._safe_time(source.get("deadline_at")),
            "message": cls._safe_summary(source.get("message")),
            "summary": cls._safe_summary(source.get("summary")),
            "detail": cls._safe_detail(source.get("detail")),
            "error_message": "",
        }

    @classmethod
    def _safe_task(cls, payload):
        source = payload if isinstance(payload, dict) else {}
        health = source.get("health") if isinstance(source.get("health"), dict) else {}
        return {
            "id": cls._safe_id(source.get("id")),
            "name": NodeMgmtSyncService.TASK_NAME,
            "is_builtin": source.get("is_builtin") if isinstance(source.get("is_builtin"), bool) else False,
            "auto_sync_enabled": source.get("auto_sync_enabled") if isinstance(source.get("auto_sync_enabled"), bool) else False,
            "auto_collect_enabled": source.get("auto_collect_enabled") if isinstance(source.get("auto_collect_enabled"), bool) else False,
            "sync_interval_minutes": source.get("sync_interval_minutes")
            if type(source.get("sync_interval_minutes")) is int and 1 <= source.get("sync_interval_minutes") <= 1440
            else 0,
            "collect_interval_minutes": source.get("collect_interval_minutes")
            if type(source.get("collect_interval_minutes")) is int and 1 <= source.get("collect_interval_minutes") <= 1440
            else 0,
            "version": cls._safe_count(source.get("version")),
            "schedule_status": cls._safe_choice(source.get("schedule_status"), cls.SCHEDULE_STATUSES, "degraded",),
            "node_config_status": cls._safe_choice(source.get("node_config_status"), cls.NODE_CONFIG_STATUSES, "unknown",),
            "last_reconciled_at": cls._safe_time(source.get("last_reconciled_at")),
            "reconcile_error_code": cls._safe_reason_code(source.get("reconcile_error_code")),
            "reconcile_error_message": "",
            "last_sync_at": cls._safe_time(source.get("last_sync_at")),
            "last_collect_at": cls._safe_time(source.get("last_collect_at")),
            "health": {
                "schedule_status": cls._safe_choice(health.get("schedule_status"), cls.SCHEDULE_STATUSES, "degraded",),
                "node_config_status": cls._safe_choice(health.get("node_config_status"), cls.NODE_CONFIG_STATUSES, "unknown",),
                "last_reconciled_at": cls._safe_time(health.get("last_reconciled_at")),
                "reason_code": cls._safe_reason_code(health.get("reason_code")),
                "message": "",
            },
        }

    @classmethod
    def _safe_display(cls, payload):
        source = payload if isinstance(payload, dict) else {}
        return {
            "display_source": cls._safe_choice(source.get("display_source"), {"sync", "collect", "sync_fallback", "none"}, "none",),
            "display_schema": "host_collect",
            "message": cls._safe_summary(source.get("message")),
            "summary": cls._safe_summary(source.get("summary")),
            "detail": cls._safe_detail(source.get("detail")),
            "run": cls._safe_run(source.get("run")),
            "task": cls._safe_task(source.get("task")),
        }

    @classmethod
    def _project_read_payload(cls, request, payload, *, display=False):
        if request.user.is_superuser:
            return payload
        return cls._safe_display(payload) if display else cls._safe_run(payload)

    @classmethod
    def _project_task_payload(cls, request, payload):
        if request.user.is_superuser:
            return payload
        return cls._safe_task(payload)

    @action(methods=["get", "put"], detail=False, url_path="task")
    def task(self, request, *args, **kwargs):
        if request.method.upper() == "PUT":
            return self._update_task(request)
        return self._get_task(request)

    @HasPermission("auto_collection-View")
    def _get_task(self, request):
        payload = NodeMgmtSyncService.get_task_payload(reconcile=True)
        return WebUtils.response_success(self._project_task_payload(request, payload))

    @HasPermission("auto_collection-Execute")
    def _update_task(self, request):
        try:
            task = NodeMgmtSyncService.update_task(request.data)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc))
        payload = NodeMgmtSyncService.serialize_task(task)
        return WebUtils.response_success(self._project_task_payload(request, payload))

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="task/latest_run")
    def latest_run(self, request, *args, **kwargs):
        run_type = request.GET.get("run_type", "sync")
        payload = NodeMgmtSyncService.get_latest_run_payload(run_type)
        return WebUtils.response_success(self._project_read_payload(request, payload))

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="task/display")
    def display(self, request, *args, **kwargs):
        payload = NodeMgmtSyncService.get_display_payload()
        return WebUtils.response_success(self._project_read_payload(request, payload, display=True))

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path="task/run_sync")
    def run_sync(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return WebUtils.response_403("仅平台管理员可执行全局节点同步")
        return WebUtils.response_success(NodeMgmtSyncService.trigger_sync())

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path="task/run_collect")
    def run_collect(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return WebUtils.response_403("仅平台管理员可执行全局节点同步")
        return WebUtils.response_success(NodeMgmtSyncService.trigger_collect())

    @action(methods=["get", "put"], detail=False, url_path="config")
    def config(self, request, *args, **kwargs):
        return self.task(request, *args, **kwargs)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="detail")
    def detail_compat(self, request, *args, **kwargs):
        return self.latest_run(request, *args, **kwargs)
