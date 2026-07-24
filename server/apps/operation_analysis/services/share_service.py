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


class ShareDurationInvalid(ValueError):
    pass


class SharePermissionDenied(Exception):
    pass


MIN_DURATION_SECONDS = 60 * 60
DEFAULT_DURATION_SECONDS = 7 * 24 * 60 * 60
MAX_DURATION_SECONDS = 90 * 24 * 60 * 60


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


def _resolve_expiry(*, permanent, duration_seconds, now):
    if permanent:
        if duration_seconds is not None:
            raise ShareDurationInvalid("永久链接不能设置有效时长")
        return None
    duration_seconds = DEFAULT_DURATION_SECONDS if duration_seconds is None else int(duration_seconds)
    if not MIN_DURATION_SECONDS <= duration_seconds <= MAX_DURATION_SECONDS:
        raise ShareDurationInvalid("有效期必须在 1 小时至 90 天之间")
    return now + timedelta(seconds=duration_seconds)


@transaction.atomic
def create_or_update_share(
    *,
    dashboard,
    sharer,
    tenant_domain,
    space_id,
    permanent=False,
    duration_seconds=None,
):
    if not can_view_dashboard(user=sharer, dashboard=dashboard, space_id=space_id):
        raise SharePermissionDenied
    now = timezone.now()
    expires_at = _resolve_expiry(permanent=permanent, duration_seconds=duration_seconds, now=now)
    active = (
        DashboardShareLink.objects.select_for_update()
        .filter(
            dashboard_instance_id=dashboard.pk,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            status=DashboardShareLink.Status.ACTIVE,
        )
        .first()
    )
    if active and not active.is_usable(now):
        active.mark_invalid(DashboardShareLink.Status.EXPIRED, actor="system")
        active = None
    if active is None:
        active = DashboardShareLink.objects.create(
            dashboard=dashboard,
            dashboard_instance_id=dashboard.pk,
            tenant_domain=tenant_domain,
            space_id=space_id,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            expires_at=expires_at,
        )
    elif active.expires_at != expires_at:
        active.expires_at = expires_at
        active.save(update_fields=["expires_at", "updated_at"])
    return ShareLinkResult(
        link=active,
        token=build_share_token(active.public_id, active.token_version),
    )


@transaction.atomic
def revoke_share(*, link, actor):
    locked = DashboardShareLink.objects.select_for_update().get(pk=link.pk)
    locked.mark_invalid(DashboardShareLink.Status.REVOKED, actor=actor)
    locked.sessions.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


def _resolve_link_from_token(token):
    try:
        public_id, token_version = parse_share_token(token)
    except InvalidShareToken as exc:
        raise ShareLinkInvalid from exc
    try:
        link = DashboardShareLink.objects.select_related("dashboard").get(
            public_id=public_id,
            token_version=token_version,
        )
    except DashboardShareLink.DoesNotExist as exc:
        raise ShareLinkInvalid from exc
    if not link.is_usable():
        if link.status == DashboardShareLink.Status.ACTIVE:
            link.mark_invalid(DashboardShareLink.Status.EXPIRED, actor="system")
        raise ShareLinkInvalid
    return link


def resolve_link(link):
    if not link.is_usable() or link.dashboard is None:
        raise ShareLinkInvalid
    try:
        sharer = User.objects.get(username=link.sharer_username, domain=link.sharer_domain)
    except User.DoesNotExist as exc:
        link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")
        raise ShareLinkInvalid from exc
    if not can_view_dashboard(user=sharer, dashboard=link.dashboard, space_id=link.space_id):
        link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")
        raise ShareLinkInvalid
    if link.dashboard.pk != link.dashboard_instance_id or link.dashboard.domain != link.tenant_domain:
        link.mark_invalid(DashboardShareLink.Status.DASHBOARD_INVALID, actor="system")
        raise ShareLinkInvalid
    return SharePrincipal(
        user=sharer,
        dashboard=link.dashboard,
        tenant_domain=link.tenant_domain,
        space_id=link.space_id,
        link=link,
    )


@transaction.atomic
def exchange_share(*, token, visitor):
    link = _resolve_link_from_token(token)
    resolve_link(link)
    return DashboardShareSession.objects.create(
        share_link=link,
        visitor_username=visitor.username,
        visitor_domain=visitor.domain,
        expires_at=timezone.now() + timedelta(seconds=settings.DASHBOARD_SHARE_SESSION_AGE),
    )


def resolve_session(*, session_id, visitor):
    try:
        session = DashboardShareSession.objects.select_related("share_link__dashboard").get(session_id=session_id)
    except (DashboardShareSession.DoesNotExist, ValueError) as exc:
        raise ShareLinkInvalid from exc
    if (
        session.revoked_at is not None
        or session.expires_at <= timezone.now()
        or session.visitor_username != visitor.username
        or session.visitor_domain != visitor.domain
    ):
        raise ShareLinkInvalid
    return resolve_link(session.share_link)
