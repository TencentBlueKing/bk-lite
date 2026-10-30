"""推送事件聚合成告警后，工单编号和状态可以通过告警查询到。"""

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.alerts.aggregation.processor.instant_dispatcher import InstantAlertDispatcher, InstantStrategyCache
from apps.alerts.constants.constants import AlarmStrategyType, EventAction
from apps.alerts.itsm.config import BKLITE_RESPONSE_CONTRACT
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.models.outbox import AlertOutbox
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tasks.itsm_tasks import scan_itsm_tickets
from apps.alerts.tests.test_action_execution_views import superuser_client  # noqa: F401
from apps.alerts.tests.test_itsm_client import response
from apps.alerts.tests.test_itsm_service import rule

TICKET_ID = "9001001"
TICKET_NUMBER = "SN9001001"


@pytest.fixture
def contract_connection(monkeypatch):
    monkeypatch.setenv("TEST_ITSM_TOKEN", "SENSITIVE-SENTINEL")
    return {
        "url": "https://itsm.example/openapi/v1/itsm/openapi/v1",
        "token_env": "TEST_ITSM_TOKEN",
        "instance_id": "test-itsm",
        "teams": [1],
        **BKLITE_RESPONSE_CONTRACT,
    }


def _deliver_itsm(record_id):
    kind = AlertOutbox.objects.filter(pk=record_id).values_list("kind", flat=True).first()
    if kind in {"itsm_evaluate", "itsm_create", "itsm_sync"}:
        deliver_outbox_record(record_id)


def _remote(method, url, **kwargs):
    if url.rstrip("/").endswith("/ticket/create"):
        body = kwargs.get("json") or {}
        assert body["is_submit"] is True
        assert body["form_data"]["ticket__title"] == "完整性验证事件"
        return response({"code": "20000", "data": {"id": TICKET_ID}})
    if "/ticket/detail/" in url:
        return response(
            {
                "code": "20000",
                "data": {
                    "id": TICKET_ID,
                    "sn": TICKET_NUMBER,
                    "title": "完整性验证事件",
                    "status": "running",
                    "status_display": "处理中",
                    "end_at": None,
                },
            }
        )
    raise AssertionError(url)


@pytest.mark.django_db(transaction=True)
def test_pushed_event_aggregates_into_alert_with_queryable_ticket(settings, contract_connection, superuser_client):  # noqa: F811
    settings.ALERT_ITSM_CONNECTIONS = {"dev": contract_connection}
    InstantStrategyCache.cache_clear()
    AlarmStrategy.objects.create(
        name="完整性即时告警",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "contains", "value": "完整性"}]],
        params={"alert_template": {"title": "{title}", "description": "事件已聚合"}},
    )
    rule(
        name="完整性转工单",
        match_rules=[[{"key": "title", "operator": "contains", "value": "完整性"}]],
        action_config={
            "connection": "dev",
            "workflow_key": "20261012164700000901",
            "form_bindings": [{"name": "ticket__title", "from": "field", "value": "title"}],
            "close_alert_on_ticket_closed": False,
        },
    )
    source = AlertSource.objects.create(name="完整性源", source_id="itsm-flow", source_type="restful", secret="x")
    event = Event.objects.create(
        source=source,
        raw_data={},
        title="完整性验证事件",
        description="推送事件",
        level="1",
        service="api",
        location="lab",
        resource_id="host-1",
        resource_name="host-1",
        resource_type="host",
        item="cpu",
        event_id="EVENT-ITSM-FLOW-1",
        push_source_id="restful",
        start_time=timezone.now(),
        labels={},
        tags={},
        action=EventAction.CREATED,
    )
    with patch("apps.alerts.tasks.deliver_alert_outbox.delay", side_effect=_deliver_itsm), patch("requests.Session.request", side_effect=_remote):
        InstantAlertDispatcher.dispatch([[event]])
        scan_itsm_tickets()
    alert = Alert.objects.get(title="完整性验证事件")
    result = superuser_client.get(f"/api/v1/alerts/api/action_execution/itsm_ticket/?alert_id={alert.alert_id}")
    assert result.status_code == 200
    ticket = result.json()["data"]
    assert ticket["ticket_id"] == TICKET_ID
    assert ticket["ticket_number"] == TICKET_NUMBER
    assert ticket["status_label"] == "处理中"
    assert ticket["is_closed"] is False
