from datetime import datetime, timezone

from apps.apm.adapters import SystemMgmtNatsAlertPublisher
from apps.apm.constants import APM_ALERT_PUSHER
from apps.apm.services.contracts import ApmAlertEvent


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def send_msg_with_channel(self, channel_id, title, content, receivers):
        self.calls.append((channel_id, title, content, receivers))
        return self.response


def _event():
    return ApmAlertEvent(
        event_key="event-1:channel:23",
        external_id="alert-1",
        status="created",
        severity="error",
        title="APM 告警",
        occurred_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        channel_id=23,
        payload={"title": "APM 告警", "action": "created"},
    )


def test_nats_publisher_uses_selected_system_management_channel():
    client = FakeClient(
        {
            "result": True,
            "data": {"ingestion": {"accepted": 1, "skipped": 0, "errored": 0}},
        }
    )

    result = SystemMgmtNatsAlertPublisher(client=client).publish([_event()])

    assert result.accepted == 1
    assert client.calls == [
        (
            23,
            "",
            {
                "source_id": "nats",
                "pusher": APM_ALERT_PUSHER,
                "events": [{"title": "APM 告警", "action": "created"}],
            },
            [],
        )
    ]


def test_nats_publisher_treats_clean_ingress_skip_as_idempotent_duplicate():
    client = FakeClient(
        {
            "result": False,
            "data": {"ingestion": {"accepted": 0, "skipped": 1, "errored": 0}},
        }
    )

    result = SystemMgmtNatsAlertPublisher(client=client).publish([_event()])

    assert result.duplicates == 1
    assert result.failed == 0
