import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.user_group import normalize_user_group_ids
from apps.operation_analysis.models.share_models import DashboardShareLink, DashboardShareSession
from apps.operation_analysis.services.canvas.registry import CANVAS_TYPE_REGISTRY
from apps.operation_analysis.services.share_token import InvalidShareToken, build_share_token, parse_share_token
from apps.system_mgmt.models.user import User

SHARE_PREPARE_PREFIX = "dashboard_share_prepare:"
SHARE_PREPARE_TTL = 300
SHARE_PREPARE_COOKIE = "bk_dashboard_share_prep"
SHARE_VISITOR_LINK_RATE_PREFIX = "dashboard_share_visitor_link_rate:"
SHARE_VISITOR_LINK_RATE_LIMIT = 300
SHARE_VISITOR_LINK_RATE_WINDOW = 60

SHARE_DATASOURCE_RESOURCE_TYPES = frozenset(
    {
        DashboardShareLink.ResourceType.DASHBOARD,
        DashboardShareLink.ResourceType.SCREEN,
        DashboardShareLink.ResourceType.TOPOLOGY,
    }
)

SHARE_DETAIL_ONLY_RESOURCE_TYPES = frozenset(
    {
        DashboardShareLink.ResourceType.ARCHITECTURE,
        DashboardShareLink.ResourceType.REPORT,
    }
)


class ShareLinkInvalid(Exception):
    def __init__(self, reason: str = "invalid"):
        super().__init__(reason)
        self.reason = reason


class SharePermissionDenied(Exception):
    pass


class ShareQueryParamsDenied(Exception):
    pass


class ShareRateLimited(Exception):
    pass


@dataclass(frozen=True)
class ShareLinkResult:
    link: DashboardShareLink
    token: str


@dataclass(frozen=True)
class SharePrincipal:
    user: User
    resource: object
    resource_type: str
    tenant_domain: str
    space_id: int
    link: DashboardShareLink

    @property
    def dashboard(self):
        """Backward-compatible alias for dashboard-only call sites."""
        return self.resource


def can_view_canvas(*, user, resource, resource_type, space_id):
    """与 AuthViewSet 详情一致：先校验空间成员，再校验实例/团队规则。"""
    if resource_type not in CANVAS_TYPE_REGISTRY:
        return False
    meta = CANVAS_TYPE_REGISTRY[resource_type]
    if getattr(user, "disabled", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    user_group_ids = set(normalize_user_group_ids(getattr(user, "group_list", [])))
    if space_id not in user_group_ids:
        return False
    if space_id not in (resource.groups or []):
        return False
    if getattr(resource, "is_build_in", False):
        return True

    permission_data = get_permission_rules(
        user,
        space_id,
        "ops-analysis",
        meta.permission_key,
        False,
    )
    instance_ids = {
        int(item["id"])
        for item in permission_data.get("instance", [])
        if "id" in item and "View" in (item.get("permission") or [])
    }
    team_ids = {int(item) for item in permission_data.get("team", [])}
    return resource.id in instance_ids or space_id in team_ids


def can_view_dashboard(*, user, dashboard, space_id):
    return can_view_canvas(
        user=user,
        resource=dashboard,
        resource_type=DashboardShareLink.ResourceType.DASHBOARD,
        space_id=space_id,
    )


def _assert_visitor_usable(visitor):
    if getattr(visitor, "disabled", False):
        raise ShareLinkInvalid


def _visitor_rate_ident(*, link_id: int, visitor) -> str:
    username = getattr(visitor, "username", "") or ""
    domain = getattr(visitor, "domain", "") or ""
    return f"{link_id}:{username}@{domain}"


def prepare_share_exchange(*, token: str) -> tuple[str, str]:
    """将原始 token 换成一次性 state + nonce；nonce 写入浏览器 Cookie 做发起方绑定。"""
    if not isinstance(token, str) or not token.strip():
        raise ShareLinkInvalid
    # 仅校验签名与链接可用，避免无效 token 进入登录回跳
    _resolve_link_from_token(token.strip())
    state = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    cache.set(
        f"{SHARE_PREPARE_PREFIX}{state}",
        {"token": token.strip(), "nonce": nonce},
        timeout=SHARE_PREPARE_TTL,
    )
    return state, nonce


def peek_prepare_state(*, state: str) -> tuple[str, str]:
    """读取 state 对应 token/nonce，不消费；供限流与校验先于销毁执行。"""
    if not isinstance(state, str) or not state.strip():
        raise ShareLinkInvalid
    payload = cache.get(f"{SHARE_PREPARE_PREFIX}{state.strip()}")
    if not isinstance(payload, dict):
        raise ShareLinkInvalid
    token = payload.get("token")
    nonce = payload.get("nonce")
    if not isinstance(token, str) or not token or not isinstance(nonce, str) or not nonce:
        raise ShareLinkInvalid
    return token, nonce


def consume_prepare_state(*, state: str, expected_token: str, expected_nonce: str) -> None:
    """校验通过后再销毁 state；值不匹配则视为无效（可能已被抢用）。"""
    if not isinstance(state, str) or not state.strip():
        raise ShareLinkInvalid
    key = f"{SHARE_PREPARE_PREFIX}{state.strip()}"
    payload = cache.get(key)
    if not isinstance(payload, dict):
        raise ShareLinkInvalid
    token = payload.get("token")
    nonce = payload.get("nonce")
    if token != expected_token or nonce != expected_nonce:
        raise ShareLinkInvalid
    cache.delete(key)


def enforce_share_visitor_link_rate_limit(*, link_id: int, visitor):
    """按「链接 + 访问者」限流，避免单访客打满整链导致他人 429。"""
    key = f"{SHARE_VISITOR_LINK_RATE_PREFIX}{_visitor_rate_ident(link_id=link_id, visitor=visitor)}"
    if cache.add(key, 1, timeout=SHARE_VISITOR_LINK_RATE_WINDOW):
        return
    try:
        current = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=SHARE_VISITOR_LINK_RATE_WINDOW)
        return
    if current > SHARE_VISITOR_LINK_RATE_LIMIT:
        raise ShareRateLimited


def _load_resource(resource_type, resource_instance_id):
    meta = CANVAS_TYPE_REGISTRY.get(resource_type)
    if meta is None:
        return None
    return meta.model.objects.filter(pk=resource_instance_id).first()


@transaction.atomic
def create_or_get_share(*, resource_type=None, resource=None, dashboard=None, sharer, tenant_domain, space_id):
    if resource is None and dashboard is not None:
        resource = dashboard
        resource_type = DashboardShareLink.ResourceType.DASHBOARD
    if resource_type is None or resource is None:
        raise SharePermissionDenied
    if resource_type not in CANVAS_TYPE_REGISTRY:
        raise SharePermissionDenied
    if not can_view_canvas(user=sharer, resource=resource, resource_type=resource_type, space_id=space_id):
        raise SharePermissionDenied
    link = (
        DashboardShareLink.objects.select_for_update()
        .filter(
            resource_type=resource_type,
            dashboard_instance_id=resource.pk,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            status=DashboardShareLink.Status.ACTIVE,
        )
        .first()
    )
    if link is None:
        create_kwargs = {
            "resource_type": resource_type,
            "dashboard_instance_id": resource.pk,
            "tenant_domain": tenant_domain,
            "space_id": space_id,
            "sharer_username": sharer.username,
            "sharer_domain": sharer.domain,
        }
        if resource_type == DashboardShareLink.ResourceType.DASHBOARD:
            create_kwargs["dashboard"] = resource
        try:
            with transaction.atomic():
                link = DashboardShareLink.objects.create(**create_kwargs)
        except IntegrityError:
            link = (
                DashboardShareLink.objects.select_for_update()
                .filter(
                    resource_type=resource_type,
                    dashboard_instance_id=resource.pk,
                    sharer_username=sharer.username,
                    sharer_domain=sharer.domain,
                    status=DashboardShareLink.Status.ACTIVE,
                )
                .get()
            )
    return ShareLinkResult(link=link, token=build_share_token(link.public_id))


def _resolve_link_from_token(token):
    try:
        public_id = parse_share_token(token)
        link = DashboardShareLink.objects.get(public_id=public_id)
    except (InvalidShareToken, DashboardShareLink.DoesNotExist) as exc:
        raise ShareLinkInvalid from exc
    if not link.is_usable():
        raise ShareLinkInvalid
    return link


def resolve_link(link):
    if not link.is_usable():
        raise ShareLinkInvalid("inactive")

    resource = _load_resource(link.resource_type, link.dashboard_instance_id)
    if resource is None:
        link.mark_invalid(DashboardShareLink.Status.DASHBOARD_INVALID, actor="system")
        raise ShareLinkInvalid("dashboard_invalid")

    if (
        resource.pk != link.dashboard_instance_id
        or resource.domain != link.tenant_domain
        or link.space_id not in (resource.groups or [])
    ):
        link.mark_invalid(DashboardShareLink.Status.DASHBOARD_INVALID, actor="system")
        raise ShareLinkInvalid("dashboard_invalid")

    try:
        sharer = User.objects.get(username=link.sharer_username, domain=link.sharer_domain)
    except User.DoesNotExist as exc:
        link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")
        raise ShareLinkInvalid("sharer_permission_lost") from exc
    if not can_view_canvas(
        user=sharer,
        resource=resource,
        resource_type=link.resource_type,
        space_id=link.space_id,
    ):
        link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")
        raise ShareLinkInvalid("sharer_permission_lost")
    return SharePrincipal(
        user=sharer,
        resource=resource,
        resource_type=link.resource_type,
        tenant_domain=link.tenant_domain,
        space_id=link.space_id,
        link=link,
    )


@transaction.atomic
def exchange_share(*, token=None, state=None, visitor, prepare_nonce=None):
    _assert_visitor_usable(visitor)
    prepared_state = None
    expected_nonce = None
    if state:
        token, expected_nonce = peek_prepare_state(state=state)
        if not prepare_nonce or prepare_nonce != expected_nonce:
            raise ShareLinkInvalid("prepare_nonce_mismatch")
        prepared_state = state
    if not token:
        raise ShareLinkInvalid
    link = _resolve_link_from_token(token)
    resolve_link(link)
    enforce_share_visitor_link_rate_limit(link_id=link.id, visitor=visitor)
    now = timezone.now()
    expires_at = now + timedelta(seconds=settings.DASHBOARD_SHARE_SESSION_AGE)
    session = (
        DashboardShareSession.objects.select_for_update()
        .filter(
            share_link=link,
            visitor_username=visitor.username,
            visitor_domain=visitor.domain,
        )
        .first()
    )
    if session is not None and session.expires_at <= now:
        session.delete()
        session = None
    if session is None:
        try:
            with transaction.atomic():
                session = DashboardShareSession.objects.create(
                    share_link=link,
                    visitor_username=visitor.username,
                    visitor_domain=visitor.domain,
                    expires_at=expires_at,
                )
        except IntegrityError:
            session = (
                DashboardShareSession.objects.select_for_update()
                .filter(
                    share_link=link,
                    visitor_username=visitor.username,
                    visitor_domain=visitor.domain,
                )
                .get()
            )
            session.expires_at = expires_at
            session.save(update_fields=["expires_at", "refreshed_at"])
    else:
        session.expires_at = expires_at
        session.save(update_fields=["expires_at", "refreshed_at"])

    # 会话就绪后再消费 state，避免限流/校验失败烧掉登录续接凭证。
    # 同访客并发重复兑换时，同伴请求可能已消费 state，此时忽略即可。
    if prepared_state is not None:
        try:
            consume_prepare_state(
                state=prepared_state,
                expected_token=token,
                expected_nonce=expected_nonce,
            )
        except ShareLinkInvalid:
            pass
    return session


def resolve_session(*, session_id, visitor):
    _assert_visitor_usable(visitor)
    try:
        session = DashboardShareSession.objects.select_related("share_link").get(session_id=session_id)
    except (DashboardShareSession.DoesNotExist, ValueError) as exc:
        raise ShareLinkInvalid from exc
    if (
        session.expires_at <= timezone.now()
        or session.visitor_username != visitor.username
        or session.visitor_domain != visitor.domain
    ):
        raise ShareLinkInvalid
    principal = resolve_link(session.share_link)
    enforce_share_visitor_link_rate_limit(link_id=principal.link.id, visitor=visitor)
    return principal


def _iter_view_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_view_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_view_nodes(child)


def _normalize_filter_definitions(filters):
    if isinstance(filters, list):
        return [item for item in filters if isinstance(item, dict)]
    if isinstance(filters, dict):
        raw = filters.get("definitions") or filters.get("unifiedFilters") or []
        return [item for item in raw if isinstance(item, dict)]
    return []


def _param_names_from_specs(params) -> set[str]:
    names: set[str] = set()
    if not isinstance(params, list):
        return names
    for param in params:
        if not isinstance(param, dict):
            continue
        name = param.get("name")
        if isinstance(name, str) and name.strip():
            # 含 fixed：前端仍会把固定参数放进请求体，底层再按 fixed 取值
            names.add(name.strip())
    return names


def _widget_chart_type(value_config: dict) -> str:
    chart_type = value_config.get("chartType")
    return chart_type.strip() if isinstance(chart_type, str) else ""


def _matching_value_configs(*, dashboard, data_source_id: int):
    for node in _iter_view_nodes(dashboard.view_sets):
        value_config = node.get("valueConfig") if isinstance(node.get("valueConfig"), dict) else node
        if not isinstance(value_config, dict):
            continue
        raw_source = value_config.get("dataSource")
        try:
            if int(raw_source) != int(data_source_id):
                continue
        except (TypeError, ValueError):
            continue
        yield value_config


def _merge_effective_param_specs(*, schema_params, widget_params) -> dict:
    """对齐前端 effectiveComponentParams：schema 为底，widget dataSourceParams 按 name 覆盖。"""
    merged: dict = {}
    if isinstance(schema_params, list):
        for item in schema_params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                merged[name.strip()] = dict(item)
    if isinstance(widget_params, list):
        for item in widget_params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                key = name.strip()
                merged[key] = {**merged.get(key, {}), **item}
    return merged


def _datasource_param_specs(data_source_id: int) -> list:
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    datasource = DataSourceAPIModel.objects.filter(id=data_source_id).only("params").first()
    if datasource is None or not isinstance(datasource.params, list):
        return []
    return datasource.params


_SHARE_FIXED_CONFLICT = object()


def _freeze_param_value(value):
    """将可能不可 hash 的参数值转为可放入 set 的形式。"""
    if isinstance(value, (dict, list)):
        return ("__json__", repr(value))
    return value


def allowed_share_query_keys(*, dashboard, data_source_id: int) -> set[str]:
    """对齐前端实际发参：数据源 schema ∪ 组件声明 ∪ 表格运行时键 ∪ 分页。

    前端会把 table 的 query_list、topN 运行时切换键等放进 extraParams；
    即使组件 dataSourceParams 只覆盖了部分字段，这些键仍可能出现在请求中。
    fixed 取值由 filter_share_query_params 按 effective specs 强制覆盖。
    """
    allowed = {"page", "page_size", "namespace_id"}
    filter_defs = {
        item.get("id"): item
        for item in _normalize_filter_definitions(getattr(dashboard, "filters", None))
        if item.get("id")
    }
    matched_widget = False
    allow_query_list = False
    schema_params = _datasource_param_specs(data_source_id)

    for value_config in _matching_value_configs(dashboard=dashboard, data_source_id=data_source_id):
        matched_widget = True
        allowed.update(_param_names_from_specs(value_config.get("dataSourceParams") or []))

        chart_type = _widget_chart_type(value_config)
        if chart_type in {"table", "eventTable"}:
            allow_query_list = True

        # 组件级运行时覆盖（如 topN group_by 切换）保存在 valueConfig.params
        runtime_params = value_config.get("params")
        if isinstance(runtime_params, dict):
            for key in runtime_params:
                if isinstance(key, str) and key.strip():
                    allowed.add(key.strip())

        bindings = value_config.get("filterBindings") or {}
        if isinstance(bindings, dict):
            for filter_id, enabled in bindings.items():
                if not enabled:
                    continue
                definition = filter_defs.get(filter_id)
                key = definition.get("key") if definition else None
                if isinstance(key, str) and key.strip():
                    allowed.add(key.strip())

    if matched_widget:
        # 始终并入数据源 schema：与普通查询 _resolve_request_params 的允许键对齐，
        # 覆盖「组件只存了部分覆盖、运行时仍带 schema 键」的情况。
        allowed.update(_param_names_from_specs(schema_params))
        if allow_query_list:
            allowed.add("query_list")

    return allowed


def allowed_share_namespace_ids(*, data_source_id: int) -> set[int]:
    from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

    datasource = (
        DataSourceAPIModel.objects.filter(id=data_source_id)
        .prefetch_related("namespaces")
        .first()
    )
    if datasource is None:
        return set()
    return {int(namespace_id) for namespace_id in datasource.namespaces.values_list("id", flat=True)}


def _enforce_share_fixed_params(*, dashboard, data_source_id: int, safe: dict) -> dict:
    """fixed 可出现在请求中，但访问者不可改：单值覆盖，多组件冲突则校验落在允许集合。"""
    schema_params = _datasource_param_specs(data_source_id)
    # name -> 原始 fixed value（单组件路径直接写入，避免 json 解冻问题）
    forced: dict[str, object] = {}
    allowed_sets: dict[str, set] = {}

    for value_config in _matching_value_configs(dashboard=dashboard, data_source_id=data_source_id):
        effective = _merge_effective_param_specs(
            schema_params=schema_params,
            widget_params=value_config.get("dataSourceParams") or [],
        )
        for name, spec in effective.items():
            if spec.get("filterType") != "fixed":
                continue
            value = spec.get("value")
            allowed_sets.setdefault(name, set()).add(_freeze_param_value(value))
            if name not in forced:
                forced[name] = value
            elif forced[name] != value:
                forced[name] = _SHARE_FIXED_CONFLICT

    result = dict(safe)
    for name, allowed in allowed_sets.items():
        if forced.get(name) is _SHARE_FIXED_CONFLICT:
            frozen_request = _freeze_param_value(result.get(name))
            if name not in result or frozen_request not in allowed:
                raise ShareQueryParamsDenied(f"参数 {name} 为固定值，不允许修改")
            continue
        result[name] = forced[name]
    return result


def filter_share_query_params(*, dashboard, data_source_id: int, request_data: dict) -> dict:
    if not isinstance(request_data, dict):
        raise ShareQueryParamsDenied
    data_source_id = int(data_source_id)
    allowed = allowed_share_query_keys(dashboard=dashboard, data_source_id=data_source_id)
    unknown = sorted(str(key) for key in request_data.keys() if key not in allowed)
    if unknown:
        raise ShareQueryParamsDenied(f"存在未声明参数: {', '.join(unknown)}")

    safe = {key: value for key, value in request_data.items() if key in allowed}
    if "namespace_id" in safe:
        try:
            namespace_id = int(safe["namespace_id"])
        except (TypeError, ValueError) as exc:
            raise ShareQueryParamsDenied("namespace_id 无效") from exc
        allowed_namespaces = allowed_share_namespace_ids(data_source_id=data_source_id)
        if not allowed_namespaces or namespace_id not in allowed_namespaces:
            raise ShareQueryParamsDenied("namespace_id 不在允许范围")
        safe["namespace_id"] = namespace_id
    return _enforce_share_fixed_params(dashboard=dashboard, data_source_id=data_source_id, safe=safe)
