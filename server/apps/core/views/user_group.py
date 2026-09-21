from apps.core.logger import logger, safe_exception_info
from apps.core.services.user_group import USER_LIST_MAX_PAGE_SIZE, UserGroup
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.rpc.system_mgmt import SystemMgmt
from rest_framework import viewsets
from rest_framework.decorators import action


def _build_actor_context(request):
    current_team = get_current_team(request)
    if current_team not in (None, ""):
        try:
            current_team = int(current_team)
        except (TypeError, ValueError):
            current_team = None
    else:
        current_team = None

    user = getattr(request, "user", None)
    return {
        "username": getattr(user, "username", None),
        "domain": getattr(user, "domain", "domain.com"),
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": bool(getattr(user, "is_superuser", False)),
        "group_list": normalize_user_group_ids(getattr(user, "group_list", [])),
    }


class UserGroupViewSet(viewsets.ViewSet):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.system_mgmt_client = SystemMgmt()

    def get_pagination_params(self, params):
        """获取分页参数"""
        try:
            page = int(params.get("page", 1))
            page_size = int(params.get("page_size", 20))
            page_size = min(max(page_size, 1), USER_LIST_MAX_PAGE_SIZE)
            first = (page - 1) * page_size
            return first, page_size
        except (ValueError, TypeError):
            return 0, 20

    @action(methods=["get"], detail=False)
    def user_list(self, request):
        try:
            search = request.query_params.get("search", "") or ""
            _, page_size = self.get_pagination_params(request.query_params)
            try:
                page = int(request.query_params.get("page", 1))
            except (ValueError, TypeError):
                page = 1
            page = max(page, 1)

            data = UserGroup.user_list(
                self.system_mgmt_client,
                actor_context=_build_actor_context(request),
                query_params={
                    "page": page,
                    "page_size": page_size,
                    "search": search,
                },
            )
            return WebUtils.response_success(data)
        except Exception as exc:
            logger.error(
                "event=user_list_query_failed failed_stage=user_list error_type=%s",
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return WebUtils.response_error("获取用户列表失败")
