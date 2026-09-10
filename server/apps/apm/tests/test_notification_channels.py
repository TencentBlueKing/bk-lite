import pytest

from apps.apm.services.notifications import NotificationChannelDirectory


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def list_notification_channels_scoped(
        self,
        actor_context,
        teams,
        include_children,
    ):
        self.calls.append((actor_context, teams, include_children))
        return self.response

    def search_notification_recipients_scoped(
        self,
        actor_context,
        teams,
        include_children,
        search,
        limit,
        recipient_ids=None,
    ):
        if recipient_ids is not None:
            self.calls.append(("validate", actor_context, teams, include_children, recipient_ids))
            return self.response
        self.calls.append(("recipients", actor_context, teams, include_children, search, limit))
        return self.response


def test_directory_exposes_all_public_channel_capabilities():
    client = FakeClient(
        {
            "result": True,
            "data": [
                {
                    "id": 1,
                    "name": "邮件",
                    "channel_type": "email",
                    "description": "值班邮件",
                    "delivery_mode": "message",
                    "recipient_mode": "system_user",
                    "availability": "available",
                },
                {
                    "id": 2,
                    "name": "告警中心",
                    "channel_type": "nats",
                    "description": "事件副本",
                    "delivery_mode": "alert_event_copy",
                    "recipient_mode": "none",
                    "availability": "available",
                },
            ],
        }
    )
    actor_context = {"username": "alice", "current_team": 10}

    channels = NotificationChannelDirectory(client=client).list_available(
        actor_context=actor_context,
        organization_id=10,
        include_children=False,
    )

    assert [channel.id for channel in channels] == [1, 2]
    assert channels[0].recipient_mode == "system_user"
    assert channels[1].delivery_mode == "alert_event_copy"
    assert client.calls == [(actor_context, [10], False)]


def test_directory_failure_does_not_disguise_channel_outage_as_empty():
    directory = NotificationChannelDirectory(client=FakeClient({"result": False, "message": "system management unavailable"}))

    with pytest.raises(RuntimeError, match="system management unavailable"):
        directory.list_available(
            actor_context={"username": "alice", "current_team": 10},
            organization_id=10,
            include_children=False,
        )


def test_recipient_directory_maps_only_public_identity_fields():
    client = FakeClient(
        {
            "result": True,
            "data": [{"id": 42, "username": "alice", "display_name": "Alice"}],
        }
    )
    actor_context = {"username": "operator", "current_team": 10}

    recipients = NotificationChannelDirectory(client=client).search_recipients(
        actor_context=actor_context,
        organization_id=10,
        include_children=False,
        search="ali",
        limit=20,
    )

    assert recipients[0].id == 42
    assert recipients[0].username == "alice"
    assert client.calls == [("recipients", actor_context, [10], False, "ali", 20)]


def test_recipient_validation_uses_bounded_id_lookup():
    client = FakeClient(
        {
            "result": True,
            "data": [{"id": 42, "username": "alice", "display_name": "Alice"}],
        }
    )
    actor_context = {"username": "operator", "current_team": 10}

    valid_ids = NotificationChannelDirectory(client=client).validate_recipient_ids(
        actor_context=actor_context,
        organization_id=10,
        include_children=False,
        recipient_ids={42, 99},
    )

    assert valid_ids == {42}
    assert client.calls == [("validate", actor_context, [10], False, [42, 99])]


def test_recipient_validation_fails_closed_during_rolling_upgrade():
    class RollingUpgradeClient:
        def __init__(self):
            self.calls = []

        def search_notification_recipients_scoped(self, actual_actor_context, **kwargs):
            self.calls.append(("new", actual_actor_context, kwargs))
            return {"result": False, "message": "unexpected keyword argument recipient_ids"}

    client = RollingUpgradeClient()
    actor_context = {"username": "operator", "current_team": 10}

    with pytest.raises(RuntimeError, match="unexpected keyword argument recipient_ids"):
        NotificationChannelDirectory(client=client).validate_recipient_ids(
            actor_context=actor_context,
            organization_id=10,
            include_children=False,
            recipient_ids={42},
        )

    assert client.calls == [
        (
            "new",
            actor_context,
            {
                "teams": [10],
                "include_children": False,
                "search": "",
                "limit": 1,
                "recipient_ids": [42],
            },
        )
    ]
