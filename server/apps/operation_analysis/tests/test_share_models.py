import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.share_models import DashboardShareLink, DashboardShareSession


@pytest.fixture
def dashboard():
    directory = Directory.objects.create(name=f"share-dir-{uuid.uuid4()}", groups=[1], created_by="alice")
    return Dashboard.objects.create(
        name=f"share-dashboard-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )


def make_link(dashboard, **overrides):
    values = {
        "dashboard": dashboard,
        "dashboard_instance_id": dashboard.pk,
        "tenant_domain": "domain.com",
        "space_id": 1,
        "sharer_username": "alice",
        "sharer_domain": "domain.com",
        "public_id": uuid.uuid4(),
    }
    values.update(overrides)
    return DashboardShareLink.objects.create(**values)


@pytest.mark.django_db
def test_active_share_is_unique_per_dashboard_and_sharer(dashboard):
    make_link(dashboard)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_link(dashboard)


@pytest.mark.django_db
def test_invalidated_share_allows_new_active_link(dashboard):
    old_link = make_link(dashboard)
    old_link.mark_invalid(DashboardShareLink.Status.SHARER_PERMISSION_LOST, actor="alice")

    new_link = make_link(dashboard)

    assert new_link.pk != old_link.pk
    assert new_link.is_usable() is True


@pytest.mark.django_db
def test_share_link_contains_no_expiry_revocation_or_version_fields(dashboard):
    link = make_link(dashboard)
    fields = {field.name for field in link._meta.fields}
    assert "expires_at" not in fields
    assert "token_version" not in fields
    assert "authorization_version" not in fields
    assert set(DashboardShareLink.Status.values) == {
        "active",
        "sharer_permission_lost",
        "dashboard_invalid",
    }


@pytest.mark.django_db
def test_session_is_unique_for_link_and_visitor(dashboard):
    share_link = make_link(dashboard)
    values = {
        "share_link": share_link,
        "visitor_username": "bob",
        "visitor_domain": "other.com",
        "expires_at": timezone.now() + timedelta(hours=8),
    }
    DashboardShareSession.objects.create(**values)
    with pytest.raises(IntegrityError), transaction.atomic():
        DashboardShareSession.objects.create(**values)
