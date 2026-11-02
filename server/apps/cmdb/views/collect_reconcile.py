from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.cmdb.models.collect_reconcile import CollectReconcile
from apps.cmdb.services.collect_reconcile import (
    candidate_tasks,
    create_reconcile,
    delete_reconcile,
    detail_payload,
    list_payload,
    update_reconcile,
    write_stale_days,
)
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils


class CollectReconcileViewSet(ViewSet):
    @HasPermission("auto_collection-View")
    def list(self, request):
        model_id = (request.query_params.get("model_id") or "").strip() or None
        return WebUtils.response_success(list_payload(request, model_id))

    @HasPermission("auto_collection-View")
    def retrieve(self, request, pk=None):
        reconcile = CollectReconcile.objects.filter(id=pk).first()
        if reconcile is None:
            return WebUtils.response_error(error_message="数据调和不存在", status_code=404)
        return WebUtils.response_success(detail_payload(request, reconcile))

    @HasPermission("auto_collection-Add")
    def create(self, request):
        try:
            data = create_reconcile(
                request,
                name=(request.data.get("name") or "").strip(),
                model_id=(request.data.get("model_id") or "").strip(),
                task_ids=[int(item) for item in request.data.get("task_ids") or []],
                field_orders=request.data.get("field_orders"),
            )
        except (BaseAppException, TypeError, ValueError) as exc:
            return WebUtils.response_error(error_message=getattr(exc, "message", str(exc)), status_code=400)
        return WebUtils.response_success(data)

    @HasPermission("auto_collection-Edit")
    def update(self, request, pk=None):
        try:
            data = update_reconcile(
                request,
                int(pk),
                version=int(request.data.get("version")),
                task_ids=request.data.get("task_ids") or [],
                field_orders=request.data.get("field_orders"),
                added_task_ids=request.data.get("added_task_ids") or [],
                removed_task_ids=request.data.get("removed_task_ids") or [],
            )
        except (BaseAppException, TypeError, ValueError) as exc:
            return WebUtils.response_error(error_message=getattr(exc, "message", str(exc)), status_code=400)
        return WebUtils.response_success(data)

    @HasPermission("auto_collection-Delete")
    def destroy(self, request, pk=None):
        try:
            delete_reconcile(request, int(pk))
        except (BaseAppException, TypeError, ValueError) as exc:
            return WebUtils.response_error(error_message=getattr(exc, "message", str(exc)), status_code=400)
        return WebUtils.response_success()

    @HasPermission("auto_collection-View")
    @action(methods=["get"], detail=False)
    def candidates(self, request):
        model_id = request.query_params.get("model_id") or ""
        return WebUtils.response_success(candidate_tasks(request, model_id))

    @HasPermission("auto_collection-Edit")
    @action(methods=["post"], detail=False, url_path="stale_days")
    def stale_days(self, request):
        try:
            days = write_stale_days(request.data.get("days"))
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message, status_code=400)
        return WebUtils.response_success({"days": days})
