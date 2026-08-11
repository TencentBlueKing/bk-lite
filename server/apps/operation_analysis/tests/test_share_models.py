import uuid
from datetime import timedelta
from types import SimpleNamespace

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
        "resource_type": DashboardShareLink.ResourceType.DASHBOARD,
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
def test_active_share_is_unique_per_resource_type_and_sharer(dashboard):
    make_link(dashboard)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_link(dashboard)


@pytest.mark.django_db
def test_active_share_guard_cannot_be_bypassed_by_bulk_writes(dashboard):
    active = make_link(dashboard)
    inactive = make_link(dashboard, status=DashboardShareLink.Status.DASHBOARD_INVALID)
    inactive.status = DashboardShareLink.Status.ACTIVE

    with pytest.raises(IntegrityError), transaction.atomic():
        DashboardShareLink.objects.bulk_update([inactive], ["status"])

    duplicate = DashboardShareLink(
        dashboard=dashboard,
        dashboard_instance_id=active.dashboard_instance_id,
        tenant_domain=active.tenant_domain,
        space_id=active.space_id,
        sharer_username=active.sharer_username,
        sharer_domain=active.sharer_domain,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        DashboardShareLink.objects.bulk_create([duplicate])

    with pytest.raises(IntegrityError), transaction.atomic():
        DashboardShareLink.objects.filter(pk=inactive.pk).update(
            status=DashboardShareLink.Status.ACTIVE,
            active_guard=None,
        )
    with pytest.raises(ValueError, match="派生保护字段"):
        DashboardShareLink.objects.filter(pk=active.pk).update(active_guard=None)


@pytest.mark.django_db
def test_mysql_guard_migration_rejects_duplicate_without_invalidating_links(dashboard):
    from importlib import import_module

    from django.apps import apps
    from django.db import connection, models

    if connection.vendor != "mysql":
        pytest.skip("MySQL 5.7 legacy data migration contract")

    oldest = make_link(dashboard)
    duplicate = make_link(dashboard, status=DashboardShareLink.Status.DASHBOARD_INVALID)
    models.QuerySet(model=DashboardShareLink, using="default").filter(pk=duplicate.pk).update(
        status=DashboardShareLink.Status.ACTIVE,
        active_guard=None,
    )

    migration = import_module("apps.operation_analysis.migrations.0023_cross_database_active_share_guard")
    schema_editor = SimpleNamespace(connection=connection)
    with pytest.raises(RuntimeError, match="重复的有效画布分享链接"):
        migration.ensure_active_links_unique(apps, schema_editor)

    oldest.refresh_from_db()
    duplicate.refresh_from_db()
    assert oldest.status == DashboardShareLink.Status.ACTIVE
    assert duplicate.status == DashboardShareLink.Status.ACTIVE
    assert duplicate.active_guard is None


@pytest.mark.django_db
def test_same_instance_id_allows_different_resource_types(dashboard):
    make_link(dashboard, resource_type=DashboardShareLink.ResourceType.DASHBOARD)
    screen_link = DashboardShareLink.objects.create(
        resource_type=DashboardShareLink.ResourceType.SCREEN,
        dashboard_instance_id=dashboard.pk,
        tenant_domain="domain.com",
        space_id=1,
        sharer_username="alice",
        sharer_domain="domain.com",
        public_id=uuid.uuid4(),
    )
    assert screen_link.resource_type == DashboardShareLink.ResourceType.SCREEN


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
