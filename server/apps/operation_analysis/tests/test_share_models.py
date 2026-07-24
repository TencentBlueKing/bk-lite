import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.share_models import DashboardShareLink


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
        "authorization_version": 1,
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
    old_link.mark_invalid(DashboardShareLink.Status.REVOKED, actor="alice")

    new_link = make_link(dashboard)

    assert new_link.pk != old_link.pk
    assert new_link.is_usable(timezone.now()) is True


@pytest.mark.django_db
def test_expired_share_is_not_usable(dashboard):
    link = make_link(dashboard, expires_at=timezone.now())

    assert link.is_usable(timezone.now()) is False

