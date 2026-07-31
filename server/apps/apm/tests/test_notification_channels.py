import pytest

from apps.apm.services.notifications import NotificationChannelDirectory


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def search_channel_list_scoped(
        self,
        actor_context,
        channel_type,
        teams,
        include_children,
        channel_method,
    ):
        self.calls.append((actor_context, channel_type, teams, include_children, channel_method))
        return self.response


def test_directory_exposes_only_alert_event_nats_channels():
    client = FakeClient(
        {
            "result": True,
            "data": [{"id": 1, "name": "告警中心", "channel_type": "nats"}],
        }
    )
    actor_context = {"username": "alice", "current_team": 10}

    channels = NotificationChannelDirectory(client=client).list_alert_event_channels(
        actor_context=actor_context,
        organization_id=10,
        include_children=False,
    )

    assert [channel["id"] for channel in channels] == [1]
    assert client.calls == [(actor_context, "nats", [10], False, "receive_alert_events")]


def test_directory_failure_does_not_disguise_channel_outage_as_empty():
    directory = NotificationChannelDirectory(
        client=FakeClient({"result": False, "message": "system management unavailable"})
    )

    with pytest.raises(RuntimeError, match="system management unavailable"):
        directory.list_alert_event_channels(
            actor_context={"username": "alice", "current_team": 10},
            organization_id=10,
            include_children=False,
        )
