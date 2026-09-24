from types import SimpleNamespace

import pytest

from apps.system_mgmt.models.channel import Channel
from apps.system_mgmt.nats.channels import (
    delete_workflow_orchestration_nats_channels,
    search_workflow_orchestration_nats_channels,
    sync_workflow_orchestration_nats_channels,
)
from apps.system_mgmt.utils.channel_utils import send_nats_message


@pytest.mark.django_db
def test_workflow_orchestration_managed_channels_reconcile_and_keep_inactive_record():
    created = sync_workflow_orchestration_nats_channels(
        workflow_id=12,
        workflow_name="主机巡检",
        team=[7],
        active=True,
        nodes=[
            {
                "trigger_id": "00000000-0000-0000-0000-000000000012",
                "node_key": "alert_entry",
                "name": "告警入口",
                "subject": "bklite.workflow.12.alert_entry",
            }
        ],
    )

    assert created == {"result": True, "data": {"created": 1, "updated": 0, "deleted": 0}}
    channel = Channel.objects.get(config__source="workflow_orchestration", config__workflow_id=12)
    assert channel.name == "主机巡检 - 告警入口"
    assert channel.config["source"] == "workflow_orchestration"
    assert channel.config["active"] is True
    assert search_workflow_orchestration_nats_channels(teams=[7])["data"][0]["id"] == channel.id

    updated = sync_workflow_orchestration_nats_channels(
        workflow_id=12,
        workflow_name="主机巡检",
        team=[7],
        active=False,
        nodes=[
            {
                "trigger_id": "00000000-0000-0000-0000-000000000012",
                "node_key": "alert_entry",
                "name": "新告警入口",
                "subject": "bklite.workflow.12.alert_entry",
            }
        ],
    )

    channel.refresh_from_db()
    assert updated == {"result": True, "data": {"created": 0, "updated": 1, "deleted": 0}}
    assert channel.config["active"] is False
    assert search_workflow_orchestration_nats_channels(teams=[7])["data"] == []
    assert search_workflow_orchestration_nats_channels(teams=[7], active_only=False)["data"][0]["id"] == channel.id

    assert delete_workflow_orchestration_nats_channels(12) == {"result": True, "data": {"deleted": 1}}
    assert not Channel.objects.filter(config__source="workflow_orchestration", config__workflow_id=12).exists()


def test_send_nats_message_adapts_managed_channel_to_standard_event(monkeypatch):
    captured = {}

    def fake_request_sync(namespace, method_name, _timeout=None, **kwargs):
        captured.update({"namespace": namespace, "method_name": method_name, "timeout": _timeout, "kwargs": kwargs})
        return {"result": True}

    monkeypatch.setattr("apps.system_mgmt.utils.channel_utils.nats_client.request_sync", fake_request_sync)
    channel = SimpleNamespace(
        team=[7],
        config={
            "namespace": "bklite",
            "method_name": "trigger_orchestration_workflow_by_nats",
            "trigger_id": "00000000-0000-0000-0000-000000000012",
            "subject": "bklite.workflow.12.alert_entry",
            "active": True,
            "timeout": 30,
        },
    )

    result = send_nats_message(
        channel,
        {
            "message": "disk full",
            "team": 7,
            "user_ids": ["alice"],
            "event_id": "alert-notification:1",
            "occurred_at": "2026-09-20T10:00:00+00:00",
            "producer": "alerts",
            "object_id": "ALERT-1",
            "scene": "assignment",
        },
    )

    assert result == {"result": True}
    assert captured["method_name"] == "trigger_orchestration_workflow_by_nats"
    assert captured["kwargs"]["data"] == {
        "trigger_id": "00000000-0000-0000-0000-000000000012",
        "team": 7,
        "subject": "bklite.workflow.12.alert_entry",
        "event": {
            "event_id": "alert-notification:1",
            "occurred_at": "2026-09-20T10:00:00+00:00",
            "producer": "alerts",
            "payload": {
                "message": "disk full",
                "team": 7,
                "user_ids": ["alice"],
                "object_id": "ALERT-1",
                "scene": "assignment",
            },
        },
    }
    assert captured["kwargs"]["actor_context"]["authorized_team_ids"] == [7]


def test_send_nats_message_rejects_inactive_or_cross_team_managed_channel(monkeypatch):
    monkeypatch.setattr(
        "apps.system_mgmt.utils.channel_utils.nats_client.request_sync",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not send")),
    )
    base_config = {
        "namespace": "bklite",
        "method_name": "trigger_orchestration_workflow_by_nats",
        "trigger_id": "00000000-0000-0000-0000-000000000012",
        "subject": "bklite.workflow.12.alert_entry",
    }

    inactive = send_nats_message(SimpleNamespace(team=[7], config={**base_config, "active": False}), {"team": 7})
    cross_team = send_nats_message(SimpleNamespace(team=[7], config={**base_config, "active": True}), {"team": 8})

    assert inactive == {"result": False, "message": "编排流程已停用"}
    assert cross_team["result"] is False
    assert "organization scope" in cross_team["message"]
