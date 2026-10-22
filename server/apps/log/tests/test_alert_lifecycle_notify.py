import logging
from datetime import datetime, timezone

import pytest

from apps.core.logger import SafeLogException
from apps.log.models.policy import Alert, Event, Policy, PolicyOrganization
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.system_mgmt.models.channel import Channel

_RESPONSE_BODY_SENTINEL = "SYNTHETIC_RESPONSE_BODY_SENTINEL\nsecond_line"
_LIFECYCLE_FAILURE_LOG = (
    "event=lifecycle_notify_failed policy_id=%s alert_id=%s action=%s "
    "attempt=%s failed_stage=send error_type=%s"
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_policy(channel, **overrides):
    data = {
        "name": overrides.pop("name", "日志告警策略"),
        "alert_type": "keyword",
        "alert_name": "日志错误告警",
        "alert_level": "error",
        "alert_condition": {"query": "error"},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "notice": True,
        "notice_type": channel.channel_type,
        "notice_type_id": channel.id,
        "notice_users": [],
    }
    data.update(overrides)
    return Policy.objects.create(**data)


def _make_alert_event(policy):
    occurred_at = datetime(2026, 7, 17, 1, 2, 3, tzinfo=timezone.utc)
    alert = Alert.objects.create(
        id="log-alert-1",
        policy=policy,
        source_id="host-1",
        level="error",
        value=7.5,
        content="日志出现 error",
        status="new",
        start_event_time=occurred_at,
        end_event_time=occurred_at,
        notice=False,
    )
    event = Event.objects.create(
        id="log-event-1",
        policy=policy,
        alert=alert,
        source_id="host-1",
        event_time=occurred_at,
        value=7.5,
        level="error",
        content="日志出现 error",
    )
    return alert, event


@pytest.fixture
def alert_center_channel():
    return Channel.objects.create(
        name="告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events", "namespace": "default"},
        description="",
    )


def test_only_receive_alert_events_nats_channel_is_alert_center(alert_center_channel):
    policy = _make_policy(alert_center_channel)
    assert LogAlertLifecycleNotifier(policy).is_alert_center_channel() is True

    mail = Channel.objects.create(name="邮件", channel_type="email", config={}, description="")
    policy.notice_type_id = mail.id
    assert LogAlertLifecycleNotifier(policy).is_alert_center_channel() is False

    other_nats = Channel.objects.create(
        name="其他 NATS",
        channel_type="nats",
        config={"method_name": "other_method"},
        description="",
    )
    policy.notice_type_id = other_nats.id
    assert LogAlertLifecycleNotifier(policy).is_alert_center_channel() is False


def test_build_created_event_uses_current_policy_and_log_event(alert_center_channel):
    policy = _make_policy(alert_center_channel)
    PolicyOrganization.objects.create(policy=policy, organization=7)
    PolicyOrganization.objects.create(policy=policy, organization=2)
    alert, event = _make_alert_event(policy)

    payload = LogAlertLifecycleNotifier(policy).build_created_event(event)

    assert payload == {
        "external_id": alert.id,
        "rule_id": str(policy.id),
        "title": "日志出现 error",
        "description": "日志出现 error",
        "level": "1",
        "value": None,
        "action": "created",
        "start_time": str(int(event.event_time.timestamp())),
        "end_time": None,
        "item": "",
        "resource_id": "host-1",
        "resource_type": "",
        "resource_name": policy.name,
        "organizations": [2, 7],
        "tags": {},
        "labels": {
            "policy_name": policy.name,
            "alert_type": policy.alert_type,
            "collect_type_id": "",
            "log_alert_id": alert.id,
            "status": "new",
        },
    }


def test_created_and_closed_events_use_same_alert_resource_identity(alert_center_channel):
    policy = _make_policy(alert_center_channel)
    alert, event = _make_alert_event(policy)
    alert.source_id = "policy_1_host=h1"
    event.source_id = "policy_1_g2_abc"

    notifier = LogAlertLifecycleNotifier(policy)
    created = notifier.build_created_event(event)
    closed = notifier.build_closed_event(alert)

    assert created["resource_id"] == "policy_1_host=h1"
    assert closed["resource_id"] == created["resource_id"]


def test_build_closed_event_uses_stable_close_time_and_operator(alert_center_channel):
    policy = _make_policy(alert_center_channel)
    alert, _ = _make_alert_event(policy)
    closed_at = datetime(2026, 7, 17, 2, 3, 4, tzinfo=timezone.utc)
    alert.status = "closed"
    alert.end_event_time = closed_at
    alert.operator = "admin"
    alert.save(update_fields=["status", "end_event_time", "operator"])

    payload = LogAlertLifecycleNotifier(policy).build_closed_event(alert)

    expected_time = str(int(closed_at.timestamp()))
    assert payload["external_id"] == alert.id
    assert payload["action"] == "closed"
    assert payload["title"] == "日志出现 error"
    assert payload["value"] is None
    assert payload["item"] == ""
    assert payload["resource_type"] == ""
    assert payload["resource_name"] == policy.name
    assert payload["start_time"] == expected_time
    assert payload["end_time"] == expected_time
    assert payload["labels"]["status"] == "closed"
    assert payload["labels"]["operator"] == "admin"


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("critical", "0"),
        ("error", "1"),
        ("warning", "2"),
        ("info", "3"),
        ("no_data", "2"),
        ("unknown", "3"),
    ],
)
def test_level_mapping_matches_monitor_center(alert_center_channel, level, expected):
    policy = _make_policy(alert_center_channel, name=f"policy-{level}")
    alert, event = _make_alert_event(policy)
    event.level = level
    assert LogAlertLifecycleNotifier(policy).build_created_event(event)["level"] == expected


def test_notify_created_sends_standard_envelope_without_notice_users(alert_center_channel, mocker):
    policy = _make_policy(alert_center_channel, notice_users=[])
    _, event = _make_alert_event(policy)
    send = mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )

    success, result = LogAlertLifecycleNotifier(policy).notify_created(event, max_attempts=1)

    assert success is True
    assert result == {"result": True}
    send.assert_called_once()
    channel_id, title, envelope, users = send.call_args.args
    assert channel_id == alert_center_channel.id
    assert title == ""
    assert envelope["source_id"] == "nats"
    assert envelope["pusher"] == "lite-log"
    assert envelope["events"][0]["action"] == "created"
    assert users == []
    assert send.call_args.kwargs == {"internal_caller": "lite-log"}


@pytest.mark.parametrize(
    ("response", "expected_success"),
    [
        ({"result": False, "message": "down"}, False),
        ({"errcode": 1, "errmsg": "bad"}, False),
        ({"code": 2, "msg": "bad"}, False),
        ({"errcode": 0}, True),
        ({"data": {}}, True),
        (None, False),
    ],
)
def test_channel_result_parsing_matches_monitor_center(response, expected_success):
    success, _ = LogAlertLifecycleNotifier._parse_channel_result(response)
    assert success is expected_success


def test_notify_created_retries_exception_without_leaking_payload(alert_center_channel, mocker):
    policy = _make_policy(alert_center_channel)
    _, event = _make_alert_event(policy)
    send = mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        side_effect=[RuntimeError("channel down"), {"result": True}],
    )
    sleep = mocker.patch("apps.log.services.alert_lifecycle_notify.time.sleep")

    success, _ = LogAlertLifecycleNotifier(policy).notify_created(event, max_attempts=2)

    assert success is True
    assert send.call_count == 2
    sleep.assert_called_once()


def _failure_records(caplog):
    return [
        record
        for record in caplog.records
        if record.name == "log" and record.msg == _LIFECYCLE_FAILURE_LOG
    ]


def _capture_notify_logs(caplog):
    caplog.set_level(logging.WARNING, logger="log")
    caplog.set_level(logging.WARNING, logger="celery")


def test_channel_failure_log_omits_response_body(alert_center_channel, mocker, caplog):
    policy = _make_policy(alert_center_channel)
    alert, event = _make_alert_event(policy)
    response = {"result": False, "message": _RESPONSE_BODY_SENTINEL}
    mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value=response,
    )
    _capture_notify_logs(caplog)

    success, result = LogAlertLifecycleNotifier(policy).notify_created(event, max_attempts=1)

    assert success is False
    assert result == response
    records = _failure_records(caplog)
    assert len(records) == 1
    record = records[0]
    rendered = record.getMessage()
    formatted = logging.Formatter().format(record)
    assert record.levelno == logging.ERROR
    assert record.exc_info is None
    assert record.args == (policy.id, alert.id, "created", 1, "channel_result")
    assert "policy" in rendered
    assert "alert" in rendered
    assert "action" in rendered
    assert "failed_stage" in rendered
    assert "error_type" in rendered
    assert "SYNTHETIC_RESPONSE_BODY_SENTINEL" not in rendered
    assert "SYNTHETIC_RESPONSE_BODY_SENTINEL" not in formatted
    assert "second_line" not in formatted
    assert "SYNTHETIC_RESPONSE_BODY_SENTINEL" not in caplog.text


def test_exception_retry_logs_one_traceback_on_final_attempt(alert_center_channel, mocker, caplog):
    policy = _make_policy(alert_center_channel)
    alert, event = _make_alert_event(policy)
    error = RuntimeError(_RESPONSE_BODY_SENTINEL)
    send = mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        side_effect=error,
    )
    sleep = mocker.patch("apps.log.services.alert_lifecycle_notify.time.sleep")
    _capture_notify_logs(caplog)

    success, result = LogAlertLifecycleNotifier(policy).notify_created(event, max_attempts=2)

    assert success is False
    assert result == {"result": False, "message": _RESPONSE_BODY_SENTINEL}
    assert send.call_count == 2
    sleep.assert_called_once()
    records = _failure_records(caplog)
    assert len(records) == 2
    retry, final = records
    assert retry.levelno == logging.WARNING
    assert retry.exc_info is None
    assert retry.args == (policy.id, alert.id, "created", 1, "RuntimeError")
    assert "Traceback" not in logging.Formatter().format(retry)
    assert final.levelno == logging.ERROR
    assert final.args == (policy.id, alert.id, "created", 2, "RuntimeError")
    assert final.exc_info[0] is SafeLogException
    assert final.exc_info[1].args == ("RuntimeError",)
    assert final.exc_info[2] is error.__traceback__
    formatted_logs = "\n".join(logging.Formatter().format(record) for record in caplog.records)
    assert formatted_logs.count("Traceback (most recent call last)") == 1
    assert "SYNTHETIC_RESPONSE_BODY_SENTINEL" not in formatted_logs
    assert "second_line" not in formatted_logs
    assert "SYNTHETIC_RESPONSE_BODY_SENTINEL" not in caplog.text
