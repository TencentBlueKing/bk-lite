from rest_framework.views import APIView

from apps.cmdb.services.owner_handover import OwnerHandoverRejected, OwnerHandoverService, UserDirectory
from apps.cmdb.utils.base import get_current_team_from_request
from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils


def _service(request):
    team_id = get_current_team_from_request(request)
    include_children = request.COOKIES.get("include_children") == "1"
    return OwnerHandoverService.for_actor(request.user, team_id, include_children)


def _rejected(exc: OwnerHandoverRejected):
    return WebUtils.response_error(error_message=exc.message, status_code=exc.status)


class OwnerHandoverModelView(APIView):
    @HasPermission("owner_handover-View,owner_handover-Execute,model_management-View")
    def get(self, request):
        try:
            return WebUtils.response_success(_service(request).list_models())
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)


class OwnerHandoverUserView(APIView):
    @HasPermission("owner_handover-View,owner_handover-Execute,model_management-View")
    def get(self, request):
        role = request.GET.get("role") or "from"
        if role not in {"from", "to"}:
            return WebUtils.response_error(error_message="role 只能是 from 或 to")
        directory = UserDirectory(getattr(request.user, "domain", "domain.com") or "domain.com")
        return WebUtils.response_success(directory.search(role, request.GET.get("search", "")))


class OwnerHandoverPreviewView(APIView):
    @HasPermission("owner_handover-Execute,model_management-Edit Model")
    def post(self, request):
        try:
            payload = _service(request).preview(
                request.data.get("from_user_id"),
                request.data.get("to_user_id"),
                request.data.get("model_ids") or None,
                page=request.data.get("page") or 1,
                page_size=request.data.get("page_size") or 20,
                attr_id=request.data.get("attr_id"),
                attr_name=request.data.get("attr_name"),
            )
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)


class OwnerHandoverTaskCreateView(APIView):
    @HasPermission("owner_handover-View,owner_handover-Execute,model_management-View")
    def get(self, request):
        try:
            payload = _service(request).list_tasks(
                request.GET.get("user_id") or None,
                page=request.GET.get("page") or 1,
                page_size=request.GET.get("page_size") or 20,
            )
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)

    @HasPermission("owner_handover-Execute,model_management-Edit Model")
    def post(self, request):
        try:
            payload, _created = _service(request).submit(
                request.data.get("preview_token"),
                request.headers.get("Idempotency-Key"),
            )
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)


class OwnerHandoverTaskDeleteView(APIView):
    @HasPermission("owner_handover-Execute,model_management-Edit Model")
    def post(self, request):
        try:
            payload = _service(request).delete_tasks(request.data.get("ids") or [])
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)


class OwnerHandoverTaskDetailView(APIView):
    @HasPermission("owner_handover-View,owner_handover-Execute,model_management-View")
    def get(self, request, task_id):
        try:
            return WebUtils.response_success(_service(request).get_task(task_id))
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)


class OwnerHandoverFailureView(APIView):
    @HasPermission("owner_handover-View,owner_handover-Execute,model_management-View")
    def get(self, request, task_id):
        try:
            payload = _service(request).list_failures(
                task_id,
                page=request.GET.get("page") or 1,
                page_size=request.GET.get("page_size") or 20,
            )
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)


class OwnerHandoverOutcomeView(APIView):
    @HasPermission("owner_handover-View,owner_handover-Execute,model_management-View")
    def get(self, request, task_id):
        try:
            payload = _service(request).list_outcome_statuses(task_id, request.GET.getlist("inst_uuid"))
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)


class OwnerHandoverCleanupView(APIView):
    @HasPermission("owner_handover-Execute,model_management-Edit Model")
    def post(self, request):
        try:
            payload = _service(request).cleanup_history(request.data.get("user_id"), request.data.get("days"))
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
        return WebUtils.response_success(payload)


class OwnerHandoverCancelView(APIView):
    @HasPermission("owner_handover-Execute,model_management-Edit Model")
    def post(self, request, task_id):
        try:
            return WebUtils.response_success(_service(request).cancel(task_id))
        except OwnerHandoverRejected as exc:
            return _rejected(exc)
        except BaseAppException as exc:
            return WebUtils.response_error(error_message=exc.message)
