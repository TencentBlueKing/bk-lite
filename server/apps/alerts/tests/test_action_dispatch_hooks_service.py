from unittest.mock import patch
import pytest
from apps.alerts.action.engine import ActionEngine


@pytest.mark.django_db(transaction=True)
@patch("apps.alerts.tasks.deliver_alert_outbox.delay")
def test_dispatch_async_persists_outbox_before_enqueuing(mock_delivery):
    from apps.alerts.models import AlertOutbox

    ActionEngine.dispatch_async("A1", "created")
    record = AlertOutbox.objects.get()
    assert record.kind == "action"
    assert record.payload == {"alert_id": "A1", "event_name": "created"}
    mock_delivery.assert_called_once_with(record.pk)


@pytest.mark.django_db(transaction=True)
@patch("apps.alerts.tasks.deliver_alert_outbox.delay", side_effect=RuntimeError("broker down"))
def test_dispatch_async_broker_error_keeps_pending_outbox(_mock_delivery):
    from apps.alerts.models import AlertOutbox

    ActionEngine.dispatch_async("A1", "created")
    assert AlertOutbox.objects.get().status == AlertOutbox.Status.PENDING


@pytest.mark.django_db
def test_process_alert_actions_propagates_business_failure():
    from apps.alerts.models.models import Alert
    from apps.alerts.tasks.action_tasks import process_alert_actions

    Alert.objects.create(
        alert_id="A-task-failure",
        fingerprint="fp-task-failure",
        title="t",
        content="c",
        level="1",
        team=[1],
    )
    with patch.object(ActionEngine, "evaluate", side_effect=RuntimeError("handler failed")):
        with pytest.raises(RuntimeError, match="handler failed"):
            process_alert_actions("A-task-failure", "created")
