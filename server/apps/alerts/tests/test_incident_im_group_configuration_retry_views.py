from unittest.mock import patch

import pytest

from apps.alerts.models import AlertOutbox, IncidentIMGroup
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tests.incident_im_group_fixtures import create_active_group, group_url
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_group_fixtures"]


@pytest.mark.parametrize("configuration_error", ["IM_WEB_BASE_URL_MISSING", "IM_WEB_BASE_URL_INVALID"])
def test_retry_degraded_summary_configuration_requeues_summary_without_recreating_group(
    api_client, operator, incident, channel, configuration_error, settings,
):
    settings.WEB_BASE_URL = "https://bklite.example.com"
    group = create_active_group(
        incident, channel, status=IncidentIMGroup.Status.DEGRADED, current_stage=IncidentIMGroup.Stage.COMPLETED, last_error_code=configuration_error,
    )
    delivered = AlertOutbox.objects.create(
        kind="incident_im_group.send_summary",
        payload={"group_id": str(group.id)},
        idempotency_key=f"incident-im-group:{group.id}:send-summary",
        status=AlertOutbox.Status.DELIVERED,
    )
    api_client.force_authenticate(operator)

    exists = CapabilityExecutionResult.success_result("exists", payload={"chat_id": group.external_chat_id})
    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute", return_value=exists,) as execute:
        first = api_client.post(f"{group_url(incident)}retry/")

    assert first.status_code == 200
    assert [call.kwargs["operation"] for call in execute.call_args_list] == ["get_group"]
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL
    assert group.current_stage == IncidentIMGroup.Stage.SENDING_SUMMARY
    summaries = AlertOutbox.objects.filter(
        kind="incident_im_group.send_summary", payload={"group_id": str(group.id)}, status=AlertOutbox.Status.PENDING,
    )
    assert summaries.count() == 1
    assert summaries.get().idempotency_key == f"incident-im-group:{group.id}:send-summary:resume:{delivered.id}"
    assert not AlertOutbox.objects.filter(kind="incident_im_group.create", payload={"group_id": str(group.id)},).exists()

    group.status = IncidentIMGroup.Status.DEGRADED
    group.last_error_code = configuration_error
    group.save(update_fields=["status", "last_error_code"])
    with patch(
        "apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute", return_value=exists,
    ):
        second = api_client.post(f"{group_url(incident)}retry/")

    assert second.status_code == 200
    assert summaries.count() == 1
    assert not AlertOutbox.objects.filter(kind="incident_im_group.create", payload={"group_id": str(group.id)},).exists()

    with patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=CapabilityExecutionResult.success_result("sent"),
    ) as send:
        assert deliver_outbox_record(summaries.get().id) is True

    assert send.call_args.kwargs["operation"] == "send_group_message"
    assert send.call_args.kwargs["idempotency_key"] == f"bklite-summary-{group.id.hex}"
