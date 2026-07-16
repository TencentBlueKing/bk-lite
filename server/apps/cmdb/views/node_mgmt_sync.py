from rest_framework.decorators import action

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class NodeMgmtSyncViewSet(AuthViewSet):
    queryset = None

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
        return WebUtils.response_success(NodeMgmtSyncService.get_latest_run_payload(run_type))

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="task/display")
    def display(self, request, *args, **kwargs):
        return WebUtils.response_success(NodeMgmtSyncService.get_display_payload())

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
