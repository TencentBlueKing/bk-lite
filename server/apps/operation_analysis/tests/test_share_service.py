import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.core.utils.permission_cache import clear_user_permission_cache
from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.share_models import DashboardShareLink, DashboardShareSession
from apps.operation_analysis.services.share_service import (
    ShareLinkInvalid,
    create_or_get_share,
    exchange_share,
    resolve_link,
    resolve_session,
)
from apps.system_mgmt.models.user import User


@pytest.fixture
def sharer(db):
    return User.objects.create(
        username="alice",
        domain="domain.com",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 1}],
    )


@pytest.fixture
def visitor(db):
    return User.objects.create(
        username="bob",
        domain="other.com",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[{"id": 99}],
    )


@pytest.fixture
def dashboard(db):
    directory = Directory.objects.create(name=f"share-dir-{uuid.uuid4()}", groups=[1], created_by="alice")
    return Dashboard.objects.create(
        name=f"share-dashboard-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )


@pytest.mark.django_db
def test_create_or_get_share_is_idempotent(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    first = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    second = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    assert second.link.pk == first.link.pk
    assert second.token == first.token
    assert (
        DashboardShareLink.objects.filter(
            dashboard_instance_id=dashboard.pk,
            sharer_username=sharer.username,
            sharer_domain=sharer.domain,
            status=DashboardShareLink.Status.ACTIVE,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_exchange_reuses_unexpired_session_and_resets_eight_hours(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    settings.DASHBOARD_SHARE_SESSION_AGE = 28800
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first = exchange_share(token=result.token, visitor=visitor)
    exchange_time = first.expires_at - timedelta(hours=1)

    with mock.patch(
        "apps.operation_analysis.services.share_service.timezone.now",
        return_value=exchange_time,
    ):
        second = exchange_share(token=result.token, visitor=visitor)

    assert second.session_id == first.session_id
    assert second.expires_at == exchange_time + timedelta(hours=8)


@pytest.mark.django_db
def test_exchange_replaces_expired_session(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    settings.DASHBOARD_SHARE_SESSION_AGE = 28800
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first = exchange_share(token=result.token, visitor=visitor)
    DashboardShareSession.objects.filter(pk=first.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    second = exchange_share(token=result.token, visitor=visitor)
    assert second.session_id != first.session_id
    assert not DashboardShareSession.objects.filter(pk=first.pk).exists()


@pytest.mark.django_db
def test_resolve_session_does_not_extend_expiry(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    original_expiry = session.expires_at

    resolve_session(session_id=session.session_id, visitor=visitor)

    session.refresh_from_db()
    assert session.expires_at == original_expiry


@pytest.mark.django_db
def test_share_sessions_cannot_be_used_across_visitors(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    visitor_c = User.objects.create(
        username="carol",
        domain="third.com",
        display_name="Carol",
        email="carol@example.com",
        password="x",
    )
    session_b = exchange_share(token=result.token, visitor=visitor)
    session_c = exchange_share(token=result.token, visitor=visitor_c)

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session_b.session_id, visitor=visitor_c)
    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session_c.session_id, visitor=visitor)


@pytest.mark.django_db
def test_permission_loss_becomes_permanent_only_when_observed(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: False,
    )
    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.SHARER_PERMISSION_LOST
    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)


@pytest.mark.django_db
def test_share_session_is_bound_to_visitor(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    other = User.objects.create(
        username="mallory",
        domain="third.com",
        display_name="Mallory",
        email="mallory@example.com",
        password="x",
    )

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=other)


@pytest.mark.django_db
def test_dashboard_delete_permanently_invalidates_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    dashboard.delete()

    result.link.refresh_from_db()
    assert result.link.dashboard is None
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_dashboard_move_permanently_invalidates_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    dashboard.groups = [2]
    dashboard.save(update_fields=["groups"])

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_same_space_directory_move_does_not_invalidate_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    other_directory = Directory.objects.create(
        name=f"share-dir-moved-{uuid.uuid4()}",
        groups=[1],
        created_by="alice",
    )

    dashboard.directory = other_directory
    dashboard.save(update_fields=["directory"])

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_routine_permission_cache_clear_does_not_invalidate_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    clear_user_permission_cache(sharer.username, sharer.domain)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_actual_permission_loss_permanently_invalidates_link_and_session(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        space_id=1,
        tenant_domain=dashboard.domain,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: False,
    )

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=visitor)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.SHARER_PERMISSION_LOST


@pytest.mark.django_db
def test_new_share_after_permanent_invalidation_uses_new_token(
    settings, dashboard, sharer, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    first = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    first.link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="system")

    second = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    assert second.link.pk != first.link.pk
    assert second.token != first.token
    with pytest.raises(ShareLinkInvalid):
        resolve_link(first.link)


@pytest.mark.django_db
def test_disabled_visitor_cannot_exchange_or_resolve_session(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    visitor.disabled = True
    visitor.save(update_fields=["disabled"])

    with pytest.raises(ShareLinkInvalid):
        exchange_share(token=result.token, visitor=visitor)
    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=visitor)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_space_mismatch_marks_dashboard_invalid_not_permission_lost(
    settings, dashboard, sharer, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_dashboard",
        lambda **_: True,
    )
    result = create_or_get_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )

    # 绕过 pre_save signal，模拟归属已被改但链接仍为 active
    Dashboard.objects.filter(pk=dashboard.pk).update(groups=[2])
    dashboard.refresh_from_db()

    with pytest.raises(ShareLinkInvalid):
        resolve_link(result.link)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID
