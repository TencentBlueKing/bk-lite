import uuid

import pytest

from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.system_mgmt.models import IMNotificationChannel, IntegrationInstance


@pytest.fixture
def group(db):
    incident = Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}", level="warning", title="数据库连接异常", operator=["alice"], collaborators=["bob"],
    )
    instance = IntegrationInstance.objects.create(name=f"feishu-{uuid.uuid4().hex}", provider_key="feishu", enabled=True, status="ready",)
    channel = IMNotificationChannel.objects.create(name=f"channel-{uuid.uuid4().hex}", integration_instance=instance, enabled=True, status="ready",)
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="[Incident] 数据库连接异常",
        external_owner_id="ou_alice",
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


@pytest.fixture
def pending_members(group):
    return [
        IncidentIMMember.objects.create(
            group=group,
            username=username,
            role=role,
            external_id=external_id,
            external_id_type="open_id",
            mapping_status=IncidentIMMember.MappingStatus.MAPPED,
            sync_status=IncidentIMMember.SyncStatus.PENDING,
        )
        for username, role, external_id in (
            ("alice", IncidentIMMember.Role.OPERATOR, "ou_alice"),
            ("bob", IncidentIMMember.Role.COLLABORATOR, "ou_bob"),
        )
    ]
