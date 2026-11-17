import hmac
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.operation_analysis.models.models import Screen
from apps.operation_analysis.models.share_models import DashboardShareLink, ScreenDisplayGrant, ScreenDisplaySession
from apps.operation_analysis.services.display_token import InvalidDisplayToken, build_display_token, parse_display_token
from apps.operation_analysis.services.share_service import ShareLinkInvalid, SharePermissionDenied, SharePrincipal
from apps.system_mgmt.models.user import User

DISPLAY_COOKIE = "bk_screen_display"
DISPLAY_DURATIONS = (1, 7, 30, 90)
DEFAULT_DISPLAY_DAYS = 30
_LAST_ACCESS_INTERVAL = timedelta(seconds=60)


class DisplayDurationInvalid(SharePermissionDenied):
    pass


class DisplayGrantExists(Exception):
    pass


def display_path(token):
    return f"/ops-analysis/display/t/{token}"


def _require_signing_key():
    """签名失败必须发生在写库之前，避免留下一条无法展示的授权。"""
    build_display_token(uuid.uuid4())


def _duration_days(value):
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise DisplayDurationInvalid from exc
    if days not in DISPLAY_DURATIONS:
        raise DisplayDurationInvalid
    return days


def _load_sharer(grant):
    try:
        return User.objects.get(username=grant.sharer_username, domain=grant.sharer_domain)
    except User.DoesNotExist as exc:
        raise ShareLinkInvalid("sharer_missing") from exc


def _assert_screen_grant(grant, screen, sharer):
    from apps.operation_analysis.services.share_service import can_view_canvas

    if getattr(sharer, "disabled", False):
        raise ShareLinkInvalid("sharer_disabled")
    if screen is None or screen.domain != grant.tenant_domain or grant.space_id not in (screen.groups or []):
        raise ShareLinkInvalid("screen_invalid")
    if not can_view_canvas(
        user=sharer,
        resource=screen,
        resource_type=DashboardShareLink.ResourceType.SCREEN,
        space_id=grant.space_id,
    ):
        raise ShareLinkInvalid("sharer_permission_lost")


def _principal(grant, screen, sharer):
    return SharePrincipal(
        user=sharer,
        resource=screen,
        resource_type=DashboardShareLink.ResourceType.SCREEN,
        tenant_domain=grant.tenant_domain,
        space_id=grant.space_id,
        link=grant,
    )


def serialize_grant(grant):
    now = timezone.now()
    token = build_display_token(grant.public_id)
    expired = grant.is_expired(now)
    if grant.status == ScreenDisplayGrant.Status.PAUSED:
        state = "paused"
    elif expired:
        state = "expired"
    else:
        state = "active"
    return {
        "configured": True,
        "state": state,
        "duration_days": grant.duration_days,
        "expires_at": grant.expires_at,
        "last_access_at": grant.last_access_at,
        "url": display_path(token),
    }


def empty_grant():
    return {"configured": False, "state": "absent", "duration_days": DEFAULT_DISPLAY_DAYS, "url": ""}


@transaction.atomic
def create_grant(*, screen, sharer, space_id, duration_days):
    from apps.operation_analysis.services.share_service import can_view_canvas

    _require_signing_key()
    days = _duration_days(duration_days)
    if not can_view_canvas(
        user=sharer,
        resource=screen,
        resource_type=DashboardShareLink.ResourceType.SCREEN,
        space_id=space_id,
    ):
        raise SharePermissionDenied
    if ScreenDisplayGrant.objects.filter(screen=screen).exists():
        raise DisplayGrantExists
    now = timezone.now()
    return ScreenDisplayGrant.objects.create(
        screen=screen,
        duration_days=days,
        expires_at=now + timedelta(days=days),
        status=ScreenDisplayGrant.Status.ACTIVE,
        tenant_domain=screen.domain,
        space_id=space_id,
        sharer_username=sharer.username,
        sharer_domain=sharer.domain,
    )


def _replace_secret(grant, *, sharer, space_id, duration_days):
    _require_signing_key()
    days = _duration_days(duration_days)
    now = timezone.now()
    grant.public_id = uuid.uuid4()
    grant.duration_days = days
    grant.expires_at = now + timedelta(days=days)
    grant.status = ScreenDisplayGrant.Status.ACTIVE
    grant.space_id = space_id
    grant.tenant_domain = grant.screen.domain
    grant.sharer_username = sharer.username
    grant.sharer_domain = sharer.domain
    grant.save(
        update_fields=[
            "public_id",
            "duration_days",
            "expires_at",
            "status",
            "space_id",
            "tenant_domain",
            "sharer_username",
            "sharer_domain",
            "updated_at",
        ]
    )
    grant.sessions.all().delete()
    return grant


@transaction.atomic
def regenerate_grant(*, screen, sharer, space_id, duration_days):
    from apps.operation_analysis.services.share_service import can_view_canvas

    if not can_view_canvas(
        user=sharer,
        resource=screen,
        resource_type=DashboardShareLink.ResourceType.SCREEN,
        space_id=space_id,
    ):
        raise SharePermissionDenied
    grant = ScreenDisplayGrant.objects.select_for_update().filter(screen=screen).first()
    if grant is None:
        raise ShareLinkInvalid
    return _replace_secret(grant, sharer=sharer, space_id=space_id, duration_days=duration_days)


@transaction.atomic
def pause_grant(*, screen):
    grant = ScreenDisplayGrant.objects.select_for_update().filter(screen=screen).first()
    if grant is None:
        raise ShareLinkInvalid
    grant.status = ScreenDisplayGrant.Status.PAUSED
    grant.save(update_fields=["status", "updated_at"])
    grant.sessions.all().delete()
    return grant


@transaction.atomic
def resume_grant(*, screen):
    grant = ScreenDisplayGrant.objects.select_for_update().filter(screen=screen).first()
    if grant is None:
        raise ShareLinkInvalid
    if grant.is_expired():
        raise ShareLinkInvalid("expired")
    grant.status = ScreenDisplayGrant.Status.ACTIVE
    grant.save(update_fields=["status", "updated_at"])
    return grant


def _touch_access(grant):
    now = timezone.now()
    if grant.last_access_at and now - grant.last_access_at < _LAST_ACCESS_INTERVAL:
        return
    ScreenDisplayGrant.objects.filter(pk=grant.pk).update(last_access_at=now)


@transaction.atomic
def activate_display(*, token):
    try:
        public_id = parse_display_token(token)
    except InvalidDisplayToken as exc:
        raise ShareLinkInvalid from exc
    grant = ScreenDisplayGrant.objects.select_for_update().filter(public_id=public_id).first()
    if grant is None:
        raise ShareLinkInvalid
    screen = Screen.objects.filter(pk=grant.screen_id).first()
    sharer = _load_sharer(grant)
    _assert_screen_grant(grant, screen, sharer)
    now = timezone.now()
    if grant.status != ScreenDisplayGrant.Status.ACTIVE:
        raise ShareLinkInvalid("paused" if grant.status == ScreenDisplayGrant.Status.PAUSED else "inactive")
    if grant.is_expired(now):
        raise ShareLinkInvalid("expired")
    session = ScreenDisplaySession.objects.create(grant=grant, expires_at=grant.expires_at)
    _touch_access(grant)
    return session


def resolve_display_request(request):
    supplied = request.COOKIES.get(DISPLAY_COOKIE) or ""
    if not supplied:
        raise ShareLinkInvalid
    try:
        session = ScreenDisplaySession.objects.select_related("grant").get(session_id=supplied)
    except (ScreenDisplaySession.DoesNotExist, ValueError, ValidationError) as exc:
        raise ShareLinkInvalid from exc
    if not hmac.compare_digest(supplied, str(session.session_id)):
        raise ShareLinkInvalid
    now = timezone.now()
    if session.expires_at <= now:
        raise ShareLinkInvalid("expired")
    grant = session.grant
    screen = Screen.objects.filter(pk=grant.screen_id).first()
    sharer = _load_sharer(grant)
    _assert_screen_grant(grant, screen, sharer)
    if grant.status != ScreenDisplayGrant.Status.ACTIVE:
        raise ShareLinkInvalid("paused")
    if grant.is_expired(now) or session.expires_at > grant.expires_at:
        raise ShareLinkInvalid("expired")
    _touch_access(grant)
    return _principal(grant, screen, sharer)


def set_display_cookie(response, request, session):
    remaining = int((session.expires_at - timezone.now()).total_seconds())
    response.set_cookie(
        DISPLAY_COOKIE,
        str(session.session_id),
        max_age=max(1, remaining),
        httponly=True,
        secure=request.is_secure(),
        samesite="Lax",
        path="/",
    )
    return response
