"""NATS 事件组织优先、组织密钥兜底的真实接入回归。"""

import json

import pytest

from apps.alerts.common.source_adapter.constants import build_nats_source_config
from apps.alerts.constants.constants import LevelType
from apps.alerts.models import AlertSource, Event, Level
from apps.alerts.nats import nats as handlers
from apps.alerts.utils.util import encode_team_secret
from apps.alerts.views.receiver import receiver_data
from apps.core.utils.internal_event_auth import sign_internal_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv("ALERTS_ALLOW_LEGACY_INTERNAL_EVENT_AUTH", "false")
    monkeypatch.setenv("ALERTS_INTERNAL_EVENT_AUTH_LITE_MONITOR_KEY", "test-monitor-signing-key")
    for level_id in range(4):
        Level.objects.create(level_id=level_id, level_name=str(level_id), level_type=LevelType.EVENT)
    return AlertSource.objects.create(
        name="NATS 组织测试",
        source_id="nats",
        source_type="nats",
        secret="test-source-key",
        team_secrets={"1": encode_team_secret("test-source-key", "1")},
        config=build_nats_source_config(),
    )


def _event(external_id="monitor-1", **extra):
    return {"title": "内存告警", "level": "2", "action": "created", "start_time": "1790649420", "external_id": external_id, **extra}


def _receive(source, events, *, secret=None, ack=False):
    payload = {"source_id": source.source_id, "pusher": "lite-monitor", "events": events}
    if secret is not None:
        payload["secret"] = secret
    if ack:
        payload.update(ack_mode="per_event_v1", ack_token="test-ack-key")
    auth = sign_internal_event("alerts.receive_alert_events", payload, caller="lite-monitor")
    return handlers.receive_alert_events(**payload, internal_auth=auth)


@pytest.mark.parametrize("organizations", [{}, {"organizations": None}, {"organizations": []}])
@pytest.mark.parametrize("ack", [False, True])
def test_missing_event_organizations_use_validated_team_secret(source, monkeypatch, organizations, ack, caplog):
    monkeypatch.setattr(handlers, "PER_EVENT_ACK_TOKEN", "test-ack-key")
    secret = source.team_secrets["1"]
    result = _receive(source, [_event(delivery_id="delivery-1", **organizations)], secret=secret, ack=ack)
    assert result["result"] is True
    event = Event.objects.get(source=source)
    assert event.team == [1]
    assert event.push_source_id == "lite-monitor"
    assert "secret" not in event.raw_data
    assert secret not in caplog.text
    assert secret not in json.dumps(result)
    if ack:
        assert result["data"]["event_results"][0]["status"] == "accepted"


def test_signed_event_organizations_override_secret_organization(source):
    result = _receive(source, [_event(organizations=[2, 3])], secret=source.team_secrets["1"])
    assert result["result"] is True
    assert Event.objects.get(source=source).team == [2, 3]


def test_signed_event_organizations_do_not_require_team_secret(source):
    result = _receive(source, [_event(organizations=[2])])
    assert result["result"] is True
    assert Event.objects.get(source=source).team == [2]


def test_mixed_batch_resolves_each_event_independently(source):
    result = _receive(source, [_event("explicit", organizations=[2]), _event("fallback")], secret=source.team_secrets["1"])
    assert result["result"] is True
    assert dict(Event.objects.values_list("external_id", "team")) == {"explicit": [2], "fallback": [1]}


@pytest.mark.parametrize("kind", ["invalid", "foreign", "stale"])
def test_invalid_or_foreign_secret_is_rejected_without_leaking(source, kind, caplog):
    secret = "invalid-team-secret" if kind == "invalid" else encode_team_secret("another-source-key", "1")
    if kind == "stale":
        source.team_secrets = {"1": secret}
        source.save(update_fields=["team_secrets"])
    result = _receive(source, [_event()], secret=secret)
    assert result["result"] is False
    assert not Event.objects.exists()
    assert secret not in caplog.text
    assert secret not in json.dumps(result)


def test_fallback_secret_does_not_bypass_internal_signature_validation(source):
    payload = {"source_id": source.source_id, "pusher": "lite-monitor", "secret": source.team_secrets["1"], "events": [_event(organizations=[2])]}
    auth = sign_internal_event("alerts.receive_alert_events", payload, caller="lite-monitor")
    payload["events"][0]["organizations"] = [3]
    result = handlers.receive_alert_events(**payload, internal_auth=auth)
    assert result["result"] is False
    assert result["code"] == "internal_auth_required"
    assert not Event.objects.exists()


def test_invalid_signature_cannot_fall_back_to_team_secret_without_event_organizations(source):
    payload = {"source_id": source.source_id, "pusher": "lite-monitor", "secret": source.team_secrets["1"], "events": [_event()]}
    auth = sign_internal_event("alerts.receive_alert_events", payload, caller="lite-monitor")
    payload["events"][0]["title"] = "tampered-event"
    result = handlers.receive_alert_events(**payload, internal_auth=auth)
    assert result["result"] is False
    assert result["code"] == "internal_auth_required"
    assert not Event.objects.exists()


@pytest.mark.parametrize("secret", [{"invalid": "shape"}, ["invalid"], 123])
def test_non_string_secret_is_rejected(source, secret):
    result = _receive(source, [_event()], secret=secret)
    assert result["result"] is False
    assert not Event.objects.exists()


def test_external_nats_caller_uses_secret_even_when_event_names_another_team(source):
    result = handlers.receive_alert_events(
        source_id=source.source_id,
        pusher="external-monitor",
        secret=source.team_secrets["1"],
        events=[_event(organizations=[2])],
    )
    assert result["result"] is True
    assert Event.objects.get(source=source).team == [1]


def test_internal_nats_without_event_organization_can_authenticate_by_team_secret(source):
    result = handlers.receive_alert_events(
        source_id=source.source_id,
        pusher="lite-monitor",
        secret=source.team_secrets["1"],
        events=[_event()],
    )
    assert result["result"] is True
    assert Event.objects.get(source=source).team == [1]


def test_invalid_event_organization_is_not_silently_replaced_by_secret_team(source):
    result = _receive(source, [_event(organizations=["invalid-id"])], secret=source.team_secrets["1"])
    assert result["result"] is False
    assert not Event.objects.exists()


@pytest.mark.parametrize("source_type", ["nats", "restful", "zabbix", "prometheus"])
def test_other_sources_keep_secret_based_organization(source, request_factory, source_type):
    source.source_type = source_type
    source.save(update_fields=["source_type"])
    request = request_factory.post(
        "/api/v1/alerts/api/receiver_data/",
        data=json.dumps({"source_id": source.source_id, "events": [_event(organizations=[2])]}),
        content_type="application/json",
        HTTP_SECRET=source.team_secrets["1"],
    )
    response = receiver_data(request)
    assert response.status_code == 200
    assert Event.objects.get(source=source).team == [1]
