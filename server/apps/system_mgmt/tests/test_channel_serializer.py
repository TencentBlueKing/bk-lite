import pytest

from apps.system_mgmt.models import Channel, ChannelChoices
from apps.system_mgmt.serializers import ChannelSerializer


@pytest.mark.django_db
def test_event_publish_channel_rejects_duplicate_subject_key():
    Channel.objects.create(
        name="existing-event-publish",
        channel_type=ChannelChoices.NATS,
        description="Existing event publish channel",
        team=[],
        config={"nats_mode": "event_publish", "subject_key": "customer-alerts"},
    )

    serializer = ChannelSerializer(
        data={
            "name": "duplicate-event-publish",
            "channel_type": ChannelChoices.NATS,
            "description": "Duplicate event publish channel",
            "team": [],
            "config": {"nats_mode": "event_publish", "subject_key": "customer-alerts"},
        }
    )

    assert serializer.is_valid() is False
    assert serializer.errors["config"]["subject_key"] == "notification topic identifier is already in use"


@pytest.mark.django_db
def test_event_publish_channel_allows_its_own_subject_key_when_editing():
    channel = Channel.objects.create(
        name="existing-event-publish",
        channel_type=ChannelChoices.NATS,
        description="Existing event publish channel",
        team=[],
        config={"nats_mode": "event_publish", "subject_key": "customer-alerts"},
    )

    serializer = ChannelSerializer(
        channel,
        data={
            "name": channel.name,
            "channel_type": ChannelChoices.NATS,
            "description": channel.description,
            "team": channel.team,
            "config": {"nats_mode": "event_publish", "subject_key": "customer-alerts"},
        },
    )

    assert serializer.is_valid() is True

@pytest.mark.django_db
def test_nats_channel_rejects_non_boolean_notify_person_flag():
    serializer = ChannelSerializer(data={
        "name": "invalid-notify-person",
        "channel_type": ChannelChoices.NATS,
        "description": "Invalid config",
        "team": [],
        "config": {"supports_notify_person": "true"},
    })

    assert serializer.is_valid() is False
    assert "supports_notify_person" in str(serializer.errors)
