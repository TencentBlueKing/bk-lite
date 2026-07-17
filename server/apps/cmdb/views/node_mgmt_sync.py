import copy

from rest_framework.decorators import action

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class NodeMgmtSyncViewSet(AuthViewSet):
    queryset = None

    @staticmethod
    def _safe_count_only_payload(payload):
        """普通用户仅可查看全局运行健康和计数，不外显跨组织主机明细。"""
        projected = copy.deepcopy(payload)

        def count_only_detail(detail):
            if not isinstance(detail, dict):
                return detail
            safe_detail = {}
            for bucket_name in ("add", "update", "delete", "relation", "raw_data"):
                bucket = detail.get(bucket_name)
                if isinstance(bucket, dict):
                    safe_detail[bucket_name] = {
                        "data": [],
                        "count": bucket.get("count", 0),
                    }
            safe_detail["todo"] = []
            return safe_detail

        def strip_free_text(run_payload):
            if not isinstance(run_payload, dict):
                return
            for key in ("message", "summary"):
                summary = run_payload.get(key)
                if isinstance(summary, dict):
                    run_payload[key] = {
                        item_key: ("" if item_key == "message" else value)
                        for item_key, value in summary.items()
                        if item_key
                        in {
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
                            "message",
                            "last_time",
                        }
                    }
            if "error_message" in run_payload:
                run_payload["error_message"] = ""

        if isinstance(projected, dict):
            projected["detail"] = count_only_detail(projected.get("detail"))
            strip_free_text(projected)
            run = projected.get("run")
            if isinstance(run, dict):
                run["detail"] = count_only_detail(run.get("detail"))
                strip_free_text(run)
        return projected

    @classmethod
    def _project_read_payload(cls, request, payload):
        if request.user.is_superuser:
            return payload
        return cls._safe_count_only_payload(payload)

    @action(methods=["get", "put"], detail=False, url_path="task")
    def task(self, request, *args, **kwargs):
        if request.method.upper() == "PUT":
            return self._update_task(request)
        return self._get_task(request)

    @HasPermission("auto_collection-View")
    def _get_task(self, request):
        payload = NodeMgmtSyncService.get_task_payload(reconcile=True)
        return WebUtils.response_success(payload)

    @HasPermission("auto_collection-Execute")
    def _update_task(self, request):
        try:
            task = NodeMgmtSyncService.update_task(request.data)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc))
        return WebUtils.response_success(NodeMgmtSyncService.serialize_task(task))

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
        return WebUtils.response_success(self._project_read_payload(request, payload))

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
