import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.share_models import DashboardShareLink
from apps.operation_analysis.services.share_service import (
    ShareDurationInvalid,
    ShareLinkInvalid,
    create_or_update_share,
    exchange_share,
    resolve_session,
    revoke_share,
)
from apps.system_mgmt.models.user import User
from apps.core.utils.permission_cache import clear_user_permission_cache


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
def test_create_returns_same_token_while_link_is_active(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)

    first = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=False,
        duration_seconds=3600,
    )
    second = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=True,
        duration_seconds=None,
    )

    assert first.link.pk == second.link.pk
    assert first.token == second.token
    assert second.link.expires_at is None


@pytest.mark.django_db
def test_expired_link_is_not_reactivated(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    first = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=False,
        duration_seconds=3600,
    )
    DashboardShareLink.objects.filter(pk=first.link.pk).update(expires_at=timezone.now() - timedelta(seconds=1))

    second = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=False,
        duration_seconds=3600,
    )

    assert first.link.pk != second.link.pk
    assert first.token != second.token


@pytest.mark.django_db
def test_duration_is_bounded(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)

    with pytest.raises(ShareDurationInvalid):
        create_or_update_share(
            dashboard=dashboard,
            sharer=sharer,
            tenant_domain="domain.com",
            space_id=1,
            permanent=False,
            duration_seconds=3599,
        )


@pytest.mark.django_db
def test_revocation_invalidates_existing_session(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=True,
        duration_seconds=None,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    revoke_share(link=result.link, actor="alice@domain.com")

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=visitor)


@pytest.mark.django_db
def test_share_session_is_bound_to_visitor(settings, dashboard, sharer, visitor, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=True,
        duration_seconds=None,
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
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=True,
        duration_seconds=None,
    )

    dashboard.delete()

    result.link.refresh_from_db()
    assert result.link.dashboard is None
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_dashboard_move_permanently_invalidates_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=True,
        duration_seconds=None,
    )

    dashboard.groups = [2]
    dashboard.save(update_fields=["groups"])

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.DASHBOARD_INVALID


@pytest.mark.django_db
def test_routine_permission_cache_clear_does_not_invalidate_link(settings, dashboard, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        tenant_domain="domain.com",
        space_id=1,
        permanent=True,
        duration_seconds=None,
    )

    clear_user_permission_cache(sharer.username, sharer.domain)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.ACTIVE


@pytest.mark.django_db
def test_actual_permission_loss_permanently_invalidates_link_and_session(
    settings, dashboard, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-key"
    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: True)
    result = create_or_update_share(
        dashboard=dashboard,
        sharer=sharer,
        space_id=1,
        tenant_domain="domain.com",
        permanent=True,
    )
    session = exchange_share(token=result.token, visitor=visitor)

    monkeypatch.setattr("apps.operation_analysis.services.share_service.can_view_dashboard", lambda **_: False)

    with pytest.raises(ShareLinkInvalid):
        resolve_session(session_id=session.session_id, visitor=visitor)

    result.link.refresh_from_db()
    assert result.link.status == DashboardShareLink.Status.SHARER_PERMISSION_LOST
