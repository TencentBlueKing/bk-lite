import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.system_mgmt.models import IMNotificationChannel, IntegrationInstance

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def incident(db):
    return Incident.objects.create(incident_id=f"INC-{uuid.uuid4().hex}", level="warning", title="Incident IM 模型测试",)


@pytest.fixture
def channel(db):
    instance = IntegrationInstance.objects.create(name=f"feishu-{uuid.uuid4().hex}", provider_key="feishu", enabled=True, status="ready",)
    return IMNotificationChannel.objects.create(name=f"channel-{uuid.uuid4().hex}", integration_instance=instance, enabled=True, status="ready",)


@pytest.fixture
def group(incident, channel):
    return make_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE)


def make_group(incident, channel, status):
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name=f"[INC-{incident.id}] test-{uuid.uuid4().hex[:8]}",
        status=status,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


@pytest.mark.django_db
def test_incident_has_only_one_non_unlinked_im_group(incident, channel):
    current = make_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE)
    assert current.active_slot == 1
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_group(incident, channel, status=IncidentIMGroup.Status.PENDING_CREATE)


@pytest.mark.django_db
def test_unlinked_history_allows_new_binding(incident, channel):
    first = make_group(incident, channel, status=IncidentIMGroup.Status.UNLINKED)
    second = make_group(incident, channel, status=IncidentIMGroup.Status.UNLINKED)
    current = make_group(incident, channel, status=IncidentIMGroup.Status.PENDING_CREATE)
    assert first.active_slot is None
    assert second.active_slot is None
    assert current.status == IncidentIMGroup.Status.PENDING_CREATE
    assert current.active_slot == 1


@pytest.mark.django_db
def test_status_save_derives_active_slot(incident, channel):
    group = make_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE)
    group.status = IncidentIMGroup.Status.UNLINKED
    group.save()

    group.refresh_from_db()
    assert group.active_slot is None


def test_group_unique_constraint_uses_cross_database_active_slot():
    constraint = next(item for item in IncidentIMGroup._meta.constraints if item.name == "unique_active_incident_im_group")
    assert constraint.fields == ("incident", "active_slot")
    assert constraint.condition is None


def test_group_has_independent_nullable_reconcile_attempt_cursor():
    field = IncidentIMGroup._meta.get_field("last_reconcile_attempt_at")
    assert field.null is True
    assert field.blank is True


def test_group_actor_audit_fields_accept_authenticated_username_limit():
    assert IncidentIMGroup._meta.get_field("created_by").max_length == 150
    assert IncidentIMGroup._meta.get_field("updated_by").max_length == 150
    assert IncidentIMGroup._meta.get_field("unlinked_by").max_length == 150


@pytest.mark.django_db
def test_member_identity_is_snapshot_not_mapping_foreign_key(group):
    field_names = {field.name for field in IncidentIMMember._meta.fields}
    assert "mapping" not in field_names
    assert {"username", "external_id", "external_id_type"} <= field_names
