"""登录首页偏好：个人优先，全局次之，可见性与目录树一致。"""

from __future__ import annotations

from django.db import transaction

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.models.homepage import HomepagePreference
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.services.builtin_i18n import apply_canvas_representation
from apps.operation_analysis.services.user_messages import oa_message
from apps.system_mgmt.utils.operation_log_utils import log_operation

_FIRST_LOGIN_GROUP = "OpsPilotGuest"
_VIEW_PERMISSION = "view-View"
_OPS_ANALYSIS_APP = "ops-analysis"
_GLOBAL_LOG_APP = "system-manager"
_GLOBAL_SET_SUMMARY = "设置全局默认登录首页"
_GLOBAL_RESTORE_SUMMARY = "还原全局默认登录首页"

PERSONAL_FOLLOW = "follow"
FALLBACK_MISSING = "missing"
FALLBACK_ORG = "org"
FALLBACK_PERMISSION = "permission"
ACCESS_OK = "ok"

ACTION_SET = "set"
ACTION_CLEAR = "clear"
ACTION_PIN_WORKBENCH = "pin_workbench"
ACTION_RESTORE = "restore"


def is_platform_admin(user) -> bool:
    """与系统管理「超级管理员」页一致：仅 Role(app=\"\", name=\"admin\")。

    登录 token 把该角色写成裸名 ``admin``。``system-manager--admin`` 和
    ``{app}--admin`` 都不是平台超级管理员。
    """

    roles = getattr(user, "roles", None) or []
    if isinstance(roles, (list, tuple, set)):
        return "admin" in roles
    return False


def is_pending_org_init(user) -> bool:
    """与 ``_check_first_login`` 相同：恰好只属于 OpsPilotGuest。

    这种账号必须先停在应用工作台完成现有初始化，不能被首页配置带走。
    """

    group_list = getattr(user, "group_list", None) or []
    if len(group_list) != 1:
        return False
    first_group = group_list[0]
    group_name = first_group.get("name") if isinstance(first_group, dict) else str(first_group)
    return group_name == _FIRST_LOGIN_GROUP


def user_can_view_ops_analysis(user) -> bool:
    """运营分析「查看」功能权限。不放宽，也不把设置首页当成授权。"""

    if getattr(user, "is_superuser", False):
        return True
    permissions = getattr(user, "permission", None)
    if isinstance(permissions, dict):
        granted = permissions.get(_OPS_ANALYSIS_APP) or set()
        if isinstance(granted, str):
            granted = {granted}
        try:
            return _VIEW_PERMISSION in set(granted)
        except TypeError:
            return False
    if isinstance(permissions, (set, list, tuple)):
        return _VIEW_PERMISSION in set(permissions)
    return False


def account_key(user) -> tuple[str, str]:
    username = getattr(user, "username", "") or ""
    domain = getattr(user, "domain", None) or "domain.com"
    return username, domain


def _personal_row(user):
    username, domain = account_key(user)
    return HomepagePreference.objects.filter(
        scope=HomepagePreference.SCOPE_USER,
        username=username,
        domain=domain,
    ).first()


def _global_row():
    return HomepagePreference.objects.filter(
        scope=HomepagePreference.SCOPE_GLOBAL,
        username="",
        domain="",
    ).first()


def effective_dashboard_id(user) -> int | None:
    personal = _personal_row(user)
    if personal is not None:
        if personal.mode == HomepagePreference.MODE_WORKBENCH:
            return None
        if personal.mode == HomepagePreference.MODE_DASHBOARD and personal.dashboard_id:
            return int(personal.dashboard_id)
        return None
    global_row = _global_row()
    if global_row is not None and global_row.mode == HomepagePreference.MODE_DASHBOARD and global_row.dashboard_id:
        return int(global_row.dashboard_id)
    return None


def build_state(user) -> dict:
    personal = _personal_row(user)
    if personal is None:
        personal_mode = PERSONAL_FOLLOW
        personal_dashboard_id = None
    elif personal.mode == HomepagePreference.MODE_DASHBOARD and personal.dashboard_id:
        personal_mode = HomepagePreference.MODE_DASHBOARD
        personal_dashboard_id = int(personal.dashboard_id)
    else:
        personal_mode = HomepagePreference.MODE_WORKBENCH
        personal_dashboard_id = None

    global_row = _global_row()
    if global_row is not None and global_row.mode == HomepagePreference.MODE_DASHBOARD and global_row.dashboard_id:
        global_mode = HomepagePreference.MODE_DASHBOARD
        global_dashboard_id = int(global_row.dashboard_id)
    else:
        global_mode = HomepagePreference.MODE_WORKBENCH
        global_dashboard_id = None

    return {
        "is_platform_admin": is_platform_admin(user),
        "personal_mode": personal_mode,
        "personal_dashboard_id": personal_dashboard_id,
        "global_mode": global_mode,
        "global_dashboard_id": global_dashboard_id,
    }


def user_may_use_current_team(request) -> bool:
    """当前组织是否属于登录用户。超管豁免，与 GenericViewSetFun 一致。"""

    if getattr(request.user, "is_superuser", False):
        return True
    from apps.core.utils.viewset_utils import user_group_id_set

    team = get_current_team(request)
    try:
        team_id = int(team)
    except (TypeError, ValueError):
        return False
    return team_id in user_group_id_set(request.user)


class _TeamUnresolved(Exception):
    """current_team 缺失或非法，目录树无法判定。"""


def dashboard_in_directory_tree(request, dashboard_id: int) -> Dashboard | None:
    """这张盘现在是否出现在当前组织的目录树里。"""

    from rest_framework.exceptions import ValidationError

    from apps.operation_analysis.services.directory_service import visible_canvas_queryset

    try:
        return visible_canvas_queryset(request, "dashboard").filter(pk=dashboard_id).first()
    except ValidationError as exc:
        raise _TeamUnresolved from exc


def build_landing(request) -> dict:
    """登录落地。目录树能判定时，不在树上的盘按当前组织回工作台。

    current_team 缺失或不属于当前账号时无法对照目录树，先返回目标，由 access 在 cookie 就绪后再判定。
    """

    user = request.user
    empty = {"dashboard_id": None, "fallback": None}
    if is_pending_org_init(user):
        return empty
    target_id = effective_dashboard_id(user)
    if target_id is None:
        return empty
    if not user_can_view_ops_analysis(user):
        return empty
    if not Dashboard.objects.filter(pk=target_id).exists():
        return {"dashboard_id": None, "fallback": FALLBACK_MISSING}
    if not user_may_use_current_team(request):
        # 浏览器里残留的是别的账号的组织，登录后才会改正，交给 access 判定。
        return {"dashboard_id": target_id, "fallback": None}
    try:
        visible = dashboard_in_directory_tree(request, target_id)
    except _TeamUnresolved:
        return {"dashboard_id": target_id, "fallback": None}
    if visible is None:
        return {"dashboard_id": None, "fallback": FALLBACK_ORG}
    return {"dashboard_id": target_id, "fallback": None}


def build_shortcut(request) -> dict:
    """顶栏 Logo 的有效首页。解析顺序与 landing 相同，并要求当前组织目录树可见。"""

    empty = {"dashboard_id": None}
    if not user_may_use_current_team(request):
        return empty
    landing = build_landing(request)
    target_id = landing.get("dashboard_id")
    if not target_id:
        return empty
    try:
        visible = dashboard_in_directory_tree(request, int(target_id))
    except _TeamUnresolved:
        return empty
    if visible is None:
        return empty
    return {"dashboard_id": int(target_id)}


def build_access(request) -> dict:
    raw_id = request.query_params.get("dashboard_id")
    try:
        dashboard_id = int(raw_id)
    except (TypeError, ValueError):
        return {"status": FALLBACK_MISSING, "name": "", "desc": "", "is_build_in": False}
    if dashboard_id <= 0:
        return {"status": FALLBACK_MISSING, "name": "", "desc": "", "is_build_in": False}

    if not user_can_view_ops_analysis(request.user):
        return {"status": FALLBACK_PERMISSION, "name": "", "desc": "", "is_build_in": False}

    if not user_may_use_current_team(request):
        # 伪造/残留的组织 cookie 不能用来读元信息或绕过目录树。
        return {"status": FALLBACK_ORG, "name": "", "desc": "", "is_build_in": False}

    dashboard = Dashboard.objects.filter(pk=dashboard_id).first()
    if dashboard is None:
        return {"status": FALLBACK_MISSING, "name": "", "desc": "", "is_build_in": False}

    try:
        visible = dashboard_in_directory_tree(request, dashboard.id)
    except _TeamUnresolved:
        visible = None
    if visible is None:
        return {"status": FALLBACK_ORG, "name": "", "desc": "", "is_build_in": False}

    represented = apply_canvas_representation(
        {"name": visible.name, "desc": visible.desc or ""},
        visible,
        {"request": request},
    )
    return {
        "status": ACCESS_OK,
        "name": represented.get("name") or "",
        "desc": represented.get("desc") or "",
        "is_build_in": bool(visible.is_build_in),
    }


def _require_org_visible_dashboard(request, dashboard_id: int) -> Dashboard:
    from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

    from apps.core.utils.viewset_utils import team_access_denied_message

    dashboard = Dashboard.objects.filter(pk=dashboard_id).first()
    if dashboard is None:
        raise NotFound(oa_message("messages.homepage_not_found", "仪表盘不存在"))
    team_raw = get_current_team(request)
    try:
        int(team_raw)
    except (TypeError, ValueError):
        raise ValidationError({"detail": oa_message("messages.homepage_team_missing", "current_team cookie 缺失或格式错误")})
    if not user_may_use_current_team(request):
        raise PermissionDenied(team_access_denied_message(request))
    try:
        visible = dashboard_in_directory_tree(request, dashboard.id)
    except _TeamUnresolved:
        raise ValidationError({"detail": oa_message("messages.homepage_team_missing", "current_team cookie 缺失或格式错误")})
    if visible is None:
        raise PermissionDenied(oa_message("messages.homepage_org_denied", "当前组织无法查看该仪表盘"))
    return visible


def _require_visible_dashboard(request, dashboard_id: int) -> Dashboard:
    from rest_framework.exceptions import PermissionDenied

    if not user_can_view_ops_analysis(request.user):
        raise PermissionDenied(oa_message("messages.homepage_view_denied", "没有运营分析查看权限"))
    return _require_org_visible_dashboard(request, dashboard_id)


def _parse_dashboard_id(raw) -> int:
    from rest_framework.exceptions import ValidationError

    try:
        dashboard_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"dashboard_id": oa_message("messages.homepage_not_found", "仪表盘不存在")}) from exc
    if dashboard_id <= 0:
        raise ValidationError({"dashboard_id": oa_message("messages.homepage_not_found", "仪表盘不存在")})
    return dashboard_id


def _upsert_user(user, *, mode: str, dashboard_id: int | None):
    username, domain = account_key(user)
    HomepagePreference.objects.update_or_create(
        scope=HomepagePreference.SCOPE_USER,
        username=username,
        domain=domain,
        defaults={"mode": mode, "dashboard_id": dashboard_id},
    )


def _upsert_global(*, mode: str, dashboard_id: int | None):
    HomepagePreference.objects.update_or_create(
        scope=HomepagePreference.SCOPE_GLOBAL,
        username="",
        domain="",
        defaults={"mode": mode, "dashboard_id": dashboard_id},
    )


def _log_global(request, summary: str, dashboard_id: int | None):
    log_operation(
        request,
        "update",
        _GLOBAL_LOG_APP,
        summary,
        target_type="ops_homepage",
        target_id="" if dashboard_id is None else str(dashboard_id),
        detail={},
    )


@transaction.atomic
def apply_personal(request) -> dict:
    from rest_framework.exceptions import ValidationError

    action = request.data.get("action")
    if action == ACTION_CLEAR:
        username, domain = account_key(request.user)
        HomepagePreference.objects.filter(
            scope=HomepagePreference.SCOPE_USER,
            username=username,
            domain=domain,
        ).delete()
        return build_state(request.user)
    if action == ACTION_PIN_WORKBENCH:
        _upsert_user(request.user, mode=HomepagePreference.MODE_WORKBENCH, dashboard_id=None)
        return build_state(request.user)
    if action == ACTION_SET:
        _require_visible_dashboard(request, _parse_dashboard_id(request.data.get("dashboard_id")))
        _upsert_user(
            request.user,
            mode=HomepagePreference.MODE_DASHBOARD,
            dashboard_id=_parse_dashboard_id(request.data.get("dashboard_id")),
        )
        return build_state(request.user)
    raise ValidationError({"action": oa_message("messages.homepage_action_invalid", "不支持的首页操作")})


@transaction.atomic
def apply_global(request) -> dict:
    from rest_framework.exceptions import PermissionDenied, ValidationError

    if not is_platform_admin(request.user):
        raise PermissionDenied(oa_message("messages.homepage_admin_required", "仅超级管理员可以修改全局默认首页"))

    action = request.data.get("action")
    if action == ACTION_RESTORE:
        _upsert_global(mode=HomepagePreference.MODE_WORKBENCH, dashboard_id=None)
        _log_global(request, _GLOBAL_RESTORE_SUMMARY, None)
        return build_state(request.user)
    if action == ACTION_SET:
        dashboard = _require_org_visible_dashboard(request, _parse_dashboard_id(request.data.get("dashboard_id")))
        _upsert_global(mode=HomepagePreference.MODE_DASHBOARD, dashboard_id=dashboard.id)
        _log_global(request, _GLOBAL_SET_SUMMARY, dashboard.id)
        return build_state(request.user)
    raise ValidationError({"action": oa_message("messages.homepage_action_invalid", "不支持的首页操作")})


def clear_homepage_pointers(dashboard_id: int):
    """仪表盘删除（含目录级联）后清掉指向它的个人和全局首页。"""

    HomepagePreference.objects.filter(
        scope=HomepagePreference.SCOPE_GLOBAL,
        dashboard_id=dashboard_id,
    ).update(mode=HomepagePreference.MODE_WORKBENCH, dashboard_id=None)
    HomepagePreference.objects.filter(
        scope=HomepagePreference.SCOPE_USER,
        dashboard_id=dashboard_id,
    ).delete()
