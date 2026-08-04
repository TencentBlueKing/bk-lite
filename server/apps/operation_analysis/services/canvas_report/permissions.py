from django.core.exceptions import ObjectDoesNotExist

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.services.canvas_report.registry import (
    get_canvas_report_adapter,
)
from apps.operation_analysis.services.canvas_report.types import (
    RESOURCE_TYPE_DASHBOARD,
    RESOURCE_TYPE_SCREEN,
)


def _resolve_user_and_team_context(
    request_or_user,
    *,
    team_id: int | None,
    include_children: bool | None,
) -> tuple[object, int | None, bool]:
    """从 request 或 user 解析查看上下文。"""
    if hasattr(request_or_user, "user"):
        request = request_or_user
        user = request.user
        if team_id is None:
            try:
                team_id = int(get_current_team(request))
            except (TypeError, ValueError):
                team_id = None
        if include_children is None:
            include_children = (
                request.COOKIES.get("include_children", "0") == "1"
            )
    else:
        user = request_or_user
        if include_children is None:
            include_children = False
    return user, team_id, bool(include_children)


def _instance_can_view(
    *,
    viewset_cls,
    user,
    resource,
    team_id: int,
    include_children: bool,
) -> bool:
    viewset = viewset_cls()
    return viewset.get_has_permission(
        user,
        resource,
        team_id,
        is_check=True,
        include_children=include_children,
    )


def can_view_canvas(
    request_or_user,
    resource_type: str,
    resource_id: int,
    *,
    team_id: int | None = None,
    include_children: bool | None = None,
) -> bool:
    """统一画布实例查看入口；仅封装实例 View，不含 DS/Channel/属主层。"""
    user, team_id, include_children = _resolve_user_and_team_context(
        request_or_user,
        team_id=team_id,
        include_children=include_children,
    )
    if getattr(user, "is_superuser", False):
        return True
    if team_id is None:
        return False

    adapter = get_canvas_report_adapter(resource_type)
    try:
        resource = adapter.load_resource(resource_id)
    except ObjectDoesNotExist:
        return False

    if resource_type == RESOURCE_TYPE_DASHBOARD:
        from apps.operation_analysis.views.view import DashboardModelViewSet

        return _instance_can_view(
            viewset_cls=DashboardModelViewSet,
            user=user,
            resource=resource,
            team_id=team_id,
            include_children=include_children,
        )
    if resource_type == RESOURCE_TYPE_SCREEN:
        from apps.operation_analysis.views.view import ScreenModelViewSet

        return _instance_can_view(
            viewset_cls=ScreenModelViewSet,
            user=user,
            resource=resource,
            team_id=team_id,
            include_children=include_children,
        )
    return False


def canvas_resource_exists(resource_type: str, resource_id: int) -> bool:
    """画布无关：经 Adapter 判断 resource_id 对应实体是否仍存在。"""
    from apps.operation_analysis.services.canvas_report.registry import (
        UnknownCanvasReportType,
    )

    try:
        adapter = get_canvas_report_adapter(resource_type)
        adapter.load_resource(resource_id)
    except (ObjectDoesNotExist, UnknownCanvasReportType, TypeError, ValueError):
        return False
    return True
