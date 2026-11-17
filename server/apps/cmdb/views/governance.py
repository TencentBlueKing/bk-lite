"""数据治理工作台接口。视图放在 cmdb 应用下，权限应用名保持 cmdb。"""

from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.cmdb.utils.base import get_current_team_from_request
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils


class GovernanceViewSet(ViewSet):
    @HasPermission("asset_info-View")
    @action(detail=False, methods=["get"], url_path="overview")
    def overview(self, request):
        workbench = _workbench()
        try:
            result = workbench.get_workbench_overview(
                _user_info(request),
                model_id=request.query_params.get("model_id") or "",
                organization_id=request.query_params.get("organization_id") or "",
            )
        except workbench.GovernanceHealthPermissionError as exc:
            return WebUtils.response_403(str(exc))
        return WebUtils.response_success(result)

    @HasPermission("asset_info-View")
    @action(detail=False, methods=["post"], url_path="refresh")
    def refresh(self, request):
        return _call(lambda workbench: workbench.refresh_governance(_user_info(request), request.data.get("model_id") or ""))

    @HasPermission("asset_info-View")
    @action(detail=False, methods=["get"], url_path="problems")
    def problems(self, request):
        workbench = _workbench()
        try:
            result = workbench.list_problems(
                _user_info(request),
                path=request.query_params.get("path") or "all",
                model_id=request.query_params.get("model_id") or "",
                organization_id=request.query_params.get("organization_id") or "",
                rule_id=request.query_params.get("rule_id") or request.query_params.get("model_asst_id") or "",
                keyword=request.query_params.get("q") or "",
                page=request.query_params.get("page") or 1,
                page_size=request.query_params.get("page_size") or 20,
            )
        except workbench.GovernanceHealthPermissionError as exc:
            return WebUtils.response_403(str(exc))
        return WebUtils.response_success(result)

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="problems/(?P<problem_id>[0-9]+)/ignore")
    def ignore(self, request, problem_id: str):
        return _call(lambda workbench: workbench.ignore_problem(_user_info(request), int(problem_id), request.user.username))

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="problems/(?P<problem_id>[0-9]+)/confirm")
    def confirm(self, request, problem_id: str):
        return _call(lambda workbench: workbench.confirm_problem(_user_info(request), int(problem_id), request.user.username))

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="problems/(?P<problem_id>[0-9]+)/relation")
    def relation(self, request, problem_id: str):
        return _call(
            lambda workbench: workbench.create_island_relation(
                _user_info(request),
                int(problem_id),
                request.data.get("dst_inst_id"),
                request.user.username,
            )
        )

    @HasPermission("asset_info-Edit")
    @action(detail=False, methods=["post"], url_path="problems/batch_confirm")
    def batch_confirm(self, request):
        return _call(lambda workbench: workbench.batch_confirm(_user_info(request), request.data.get("problem_ids") or [], request.user.username))


def _user_info(request) -> dict:
    return {
        "is_superuser": bool(getattr(request.user, "is_superuser", False)),
        "team": get_current_team_from_request(request, required=False),
        "include_children": request.COOKIES.get("include_children", "0") == "1",
    }


def _workbench():
    from apps.cmdb_enterprise.governance import workbench
    from apps.cmdb_enterprise.governance.health_query import GovernanceHealthPermissionError

    workbench.GovernanceHealthPermissionError = GovernanceHealthPermissionError
    return workbench


def _call(func):
    from apps.cmdb_enterprise.governance.health_query import GovernanceHealthPermissionError
    from apps.core.exceptions.base_app_exception import BaseAppException

    try:
        return WebUtils.response_success(func(_workbench()))
    except GovernanceHealthPermissionError as exc:
        return WebUtils.response_403(str(exc))
    except BaseAppException as exc:
        return WebUtils.response_error(error_message=exc.message)
