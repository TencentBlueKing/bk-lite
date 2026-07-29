import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import Incident, IncidentIMGroup
from apps.alerts.serializers.incident import IncidentModelSerializer
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationUserMapping, IntegrationInstance, User


@pytest.fixture
def incident(db):
    return Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}", level="warning", title="持续同步测试", status=IncidentStatus.PROCESSING, operator=["alice"],
    )


@pytest.fixture
def channel(db):
    instance = IntegrationInstance.objects.create(name=f"feishu-{uuid.uuid4().hex}", provider_key="feishu", enabled=True, status="ready",)
    return IMNotificationChannel.objects.create(
        name=f"channel-{uuid.uuid4().hex}", integration_instance=instance, enabled=True, status="ready", external_receive_field="open_id",
    )


@pytest.fixture
def group(incident, channel):
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="[Incident] 持续同步测试",
        external_chat_id="oc_test",
        status=IncidentIMGroup.Status.ACTIVE,
        current_stage=IncidentIMGroup.Stage.COMPLETED,
        continuous_sync_enabled=True,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


def map_user(channel, username):
    user = User.objects.create(username=username, display_name=username.title(), email=f"{username}@example.com", password="test-password",)
    return IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="open_id",
        external_identity_value=f"identity-{username}",
        external_receive_key="open_id",
        external_snapshot={"open_id": f"ou_{username}"},
    )


def incident_serializer(incident, data):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    with mock.patch(
        "apps.core.utils.serializers.get_permission_rules", return_value={"team": [], "instance": []},
    ):
        return IncidentModelSerializer(incident, data=data, partial=True, context={"request": request},)
