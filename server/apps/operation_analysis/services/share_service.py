from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.utils.permission_utils import get_permission_rules
from apps.operation_analysis.models.share_models import DashboardShareLink, DashboardShareSession
from apps.operation_analysis.services.share_token import InvalidShareToken, build_share_token, parse_share_token
from apps.system_mgmt.models.user import User


class ShareLinkInvalid(Exception):
    pass


class SharePermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class ShareLinkResult:
    link: DashboardShareLink
    token: str


@dataclass(frozen=True)
class SharePrincipal:
    user: User
    dashboard: object
    tenant_domain: str
    space_id: int
    link: DashboardShareLink


def can_view_dashboard(*, user, dashboard, space_id):
    if getattr(user, "disabled", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if space_id not in (dashboard.groups or []):
        return False
    permission_data = get_permission_rules(
        user,
        space_id,
        "ops-analysis",
        "directory.dashboard",
        False,
    )
    instance_ids = {int(item["id"]) for item in permission_data.get("instance", []) if "id" in item}
    team_ids = {int(item) for item in permission_data.get("team", [])}
    return dashboard.id in instance_ids or space_id in team_ids or bool(getattr(dashboard, "is_build_in", False))


def _assert_visitor_usable(visitor):
    if getattr(visitor, "disabled", False):
        raise ShareLinkInvalid


@transaction.atomic
def create_or_get_share(*, dashboard, sharer, tenant_domain, space_id):
    if not can_view_dashboard(user=sharer, dashboard=dashboard, space_id=space_id):
        raise SharePermissionDenied
    link = (
        DashboardShareLink.objects.select_for_update()
        .filter(
            dashboard_instance_id=dashboard.pk,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            status=DashboardShareLink.Status.ACTIVE,
        )
        .first()
    )
    if link is None:
        link = DashboardShareLink.objects.create(
            dashboard=dashboard,
            dashboard_instance_id=dashboard.pk,
            tenant_domain=tenant_domain,
            space_id=space_id,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
        )
    return ShareLinkResult(link=link, token=build_share_token(link.public_id))


def _resolve_link_from_token(token):
    try:
        public_id = parse_share_token(token)
        link = DashboardShareLink.objects.select_related("dashboard").get(public_id=public_id)
    except (InvalidShareToken, DashboardShareLink.DoesNotExist) as exc:
        raise ShareLinkInvalid from exc
    if not link.is_usable():
        raise ShareLinkInvalid
    return link


def resolve_link(link):
    if not link.is_usable():
        raise ShareLinkInvalid
    if link.dashboard is None:
        link.mark_invalid(DashboardShareLink.Status.DASHBOARD_INVALID, actor="system")
        raise ShareLinkInvalid

    dashboard = link.dashboard
    # 归属校验必须先于分享者权限：空间/租户/实例不一致属于画布失效，不能记成失权
    if (
        dashboard.pk != link.dashboard_instance_id
        or dashboard.domain != link.tenant_domain
        or link.space_id not in (dashboard.groups or [])
    ):
        link.mark_invalid(DashboardShareLink.Status.DASHBOARD_INVALID, actor="system")
        raise ShareLinkInvalid

    try:
        sharer = User.objects.get(username=link.sharer_username, domain=link.sharer_domain)
    except User.DoesNotExist as exc:
        link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")
        raise ShareLinkInvalid from exc
    if not can_view_dashboard(user=sharer, dashboard=dashboard, space_id=link.space_id):
        link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")
        raise ShareLinkInvalid
    return SharePrincipal(
        user=sharer,
        dashboard=dashboard,
        tenant_domain=link.tenant_domain,
        space_id=link.space_id,
        link=link,
    )


@transaction.atomic
def exchange_share(*, token, visitor):
    _assert_visitor_usable(visitor)
    link = _resolve_link_from_token(token)
    resolve_link(link)
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
        return DashboardShareSession.objects.create(
            share_link=link,
            visitor_username=visitor.username,
            visitor_domain=visitor.domain,
            expires_at=expires_at,
        )
    session.expires_at = expires_at
    session.save(update_fields=["expires_at", "refreshed_at"])
    return session


def resolve_session(*, session_id, visitor):
    _assert_visitor_usable(visitor)
    try:
        session = DashboardShareSession.objects.select_related("share_link__dashboard").get(session_id=session_id)
    except (DashboardShareSession.DoesNotExist, ValueError) as exc:
        raise ShareLinkInvalid from exc
    if (
        session.expires_at <= timezone.now()
        or session.visitor_username != visitor.username
        or session.visitor_domain != visitor.domain
    ):
        raise ShareLinkInvalid
    return resolve_link(session.share_link)
