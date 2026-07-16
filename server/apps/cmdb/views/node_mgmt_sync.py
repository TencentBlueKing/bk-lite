from rest_framework.decorators import action

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.core.utils.web_utils import WebUtils


class NodeMgmtSyncViewSet(AuthViewSet):
    queryset = None

    @HasPermission("auto_collection-View")
    @action(methods=["get", "put"], detail=False, url_path="task")
    def task(self, request, *args, **kwargs):
        if request.method.upper() == "PUT":
            task = NodeMgmtSyncService.update_task(request.data)
            payload = NodeMgmtSyncService.serialize_task(task)
        else:
            payload = NodeMgmtSyncService.get_task_payload(reconcile=True)
        return WebUtils.response_success(payload)

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
        return WebUtils.response_success(NodeMgmtSyncService.trigger_sync())

    @HasPermission("auto_collection-Execute")
    @action(methods=["post"], detail=False, url_path="task/run_collect")
    def run_collect(self, request, *args, **kwargs):
        return WebUtils.response_success(NodeMgmtSyncService.trigger_collect())

    @HasPermission("auto_collection-View")
    @action(methods=["get", "put"], detail=False, url_path="config")
    def config(self, request, *args, **kwargs):
        return self.task(request, *args, **kwargs)

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False, url_path="detail")
    def detail_compat(self, request, *args, **kwargs):
        return self.latest_run(request, *args, **kwargs)
