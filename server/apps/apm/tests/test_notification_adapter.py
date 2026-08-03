from apps.apm.adapters import SystemMgmtNotificationDispatcher
from apps.apm.services.contracts import NotificationDelivery


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def dispatch_notification(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _event():
    return NotificationDelivery(
        delivery_key="event-1:channel:23",
        channel_id=23,
        organization_ids=(10,),
        recipients=("42",),
        title="APM 告警",
        body="checkout 错误率过高",
        event_payload={"title": "APM 告警", "action": "created"},
    )


def test_dispatcher_uses_public_system_management_contract():
    client = FakeClient(
        {
            "result": True,
            "code": "delivered",
            "retryable": False,
            "message": "success",
        }
    )

    result = SystemMgmtNotificationDispatcher(client=client).dispatch(_event())

    assert result.delivered is True
    assert result.retryable is False
    assert client.calls == [{
        "delivery_key": "event-1:channel:23",
        "channel_id": 23,
        "organization_ids": [10],
        "recipients": ["42"],
        "title": "APM 告警",
        "body": "checkout 错误率过高",
        "event_payload": {"title": "APM 告警", "action": "created"},
    }]


def test_dispatcher_preserves_retryability_and_stable_error_code():
    client = FakeClient(
        {
            "result": False,
            "code": "provider_unavailable",
            "retryable": True,
            "message": "temporarily unavailable",
        }
    )

    result = SystemMgmtNotificationDispatcher(client=client).dispatch(_event())

    assert result.delivered is False
    assert result.code == "provider_unavailable"
    assert result.retryable is True
