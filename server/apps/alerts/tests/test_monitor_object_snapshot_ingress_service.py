"""NATS 告警源接收监控对象身份快照的契约。"""

import logging
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.alerts.constants.constants import AlertsSourceTypes, LevelType
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.nats.nats import receive_alert_events
from apps.core.utils.internal_event_auth import sign_internal_event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _create_nats_source(source_id="nats"):
    for level_id in (0, 1, 2, 3):
        Level.objects.create(
            level_id=level_id,
            level_name=f"L{level_id}",
            level_display_name=f"等级{level_id}",
            level_type=LevelType.EVENT,
        )
    return AlertSource.objects.create(
        name=f"NATS Source {source_id}",
        source_id=source_id,
        source_type=AlertsSourceTypes.NATS,
        secret="nats-secret",
        is_active=True,
        is_effective=True,
        config={
            "event_fields_mapping": {
                "title": "title",
                "description": "description",
                "level": "level",
                "item": "item",
                "start_time": "start_time",
                "action": "action",
                "external_id": "external_id",
                "monitor_id": "monitor_id",
                "cmdb_id": "cmdb_id",
                "resource_id": "resource_id",
                "resource_name": "resource_name",
                "resource_type": "resource_type",
            }
        },
    )


def _receive(source, event, pusher="lite-monitor", signed=True):
    request_payload = {
        "source_id": source.source_id,
        "pusher": pusher,
        "events": [event],
    }
    kwargs = dict(request_payload)
    if signed:
        kwargs["internal_auth"] = sign_internal_event(
            "alerts.receive_alert_events",
            request_payload,
            caller=pusher,
        )
    return receive_alert_events(**kwargs)


def test_receive_monitor_event_persists_explicit_identity_snapshot():
    for level_id in (0, 1, 2, 3):
        Level.objects.create(
            level_id=level_id,
            level_name=f"L{level_id}",
            level_display_name=f"等级{level_id}",
            level_type=LevelType.EVENT,
        )
    source = AlertSource.objects.create(
        name="NATS Monitor Source",
        source_id="nats",
        source_type=AlertsSourceTypes.NATS,
        secret="nats-secret",
        is_active=True,
        is_effective=True,
        config={
            "event_fields_mapping": {
                "title": "title",
                "description": "description",
                "level": "level",
                "item": "item",
                "start_time": "start_time",
                "action": "action",
                "external_id": "external_id",
                "monitor_id": "monitor_id",
                "cmdb_id": "cmdb_id",
                "resource_id": "resource_id",
                "resource_name": "resource_name",
                "resource_type": "resource_type",
            }
        },
    )
    event_payload = {
        "title": "CPU usage exceeded 81%",
        "description": "CPU usage exceeded 81%",
        "level": "2",
        "item": "cpu_usage",
        "start_time": str(int(timezone.now().timestamp())),
        "action": "created",
        "external_id": "monitor-alert-1",
        "monitor_id": "0001",
        "cmdb_id": "550e8400-e29b-41d4-a716-446655440000",
        "resource_id": "0001",
        "resource_name": "ip1",
        "resource_type": "Host",
    }
    request_payload = {
        "source_id": source.source_id,
        "pusher": "lite-monitor",
        "events": [event_payload],
    }

    result = receive_alert_events(
        **request_payload,
        internal_auth=sign_internal_event(
            "alerts.receive_alert_events",
            request_payload,
            caller="lite-monitor",
        ),
    )

    assert result["result"] is True
    assert result["data"]["processed_events"] == 1
    event = Event.objects.get(source=source)
    assert {
        "monitor_id": event.monitor_id,
        "cmdb_id": event.cmdb_id,
        "resource_id": event.resource_id,
        "resource_name": event.resource_name,
        "resource_type": event.resource_type,
        "push_source_id": event.push_source_id,
    } == {
        "monitor_id": "0001",
        "cmdb_id": "550e8400-e29b-41d4-a716-446655440000",
        "resource_id": "0001",
        "resource_name": "ip1",
        "resource_type": "Host",
        "push_source_id": "lite-monitor",
    }
    assert event.raw_data["monitor_id"] == "0001"
    assert event.raw_data["cmdb_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_receive_legacy_monitor_event_keeps_identity_fields_null():
    source = _create_nats_source("nats-legacy-snapshot")

    result = _receive(
        source,
        {
            "title": "legacy event",
            "description": "legacy event",
            "level": "2",
            "item": "cpu_usage",
            "start_time": str(int(timezone.now().timestamp())),
            "action": "created",
            "external_id": "legacy-monitor-alert-1",
            "resource_id": "legacy-resource-1",
            "resource_name": "legacy-host",
            "resource_type": "Host",
        },
    )

    assert result["result"] is True
    event = Event.objects.get(source=source)
    assert (event.monitor_id, event.cmdb_id, event.resource_id) == (
        None,
        None,
        "legacy-resource-1",
    )


def test_third_party_resource_id_is_not_promoted_to_monitor_id():
    source = _create_nats_source("nats-third-party-snapshot")

    result = _receive(
        source,
        {
            "title": "third-party event",
            "description": "third-party event",
            "level": "2",
            "item": "availability",
            "start_time": str(int(timezone.now().timestamp())),
            "action": "created",
            "external_id": "third-party-alert-1",
            "resource_id": "vendor-resource-1",
            "resource_name": "vendor-host",
            "resource_type": "vendor-type",
        },
        pusher="third-party",
        signed=False,
    )

    assert result["result"] is True
    event = Event.objects.get(source=source)
    assert (event.monitor_id, event.cmdb_id, event.resource_id) == (
        None,
        None,
        "vendor-resource-1",
    )


def test_receive_monitor_event_accepts_null_cmdb_identity():
    source = _create_nats_source("nats-null-cmdb-snapshot")

    result = _receive(
        source,
        {
            "title": "unlinked monitor event",
            "description": "unlinked monitor event",
            "level": "2",
            "item": "availability",
            "start_time": str(int(timezone.now().timestamp())),
            "action": "created",
            "external_id": "unlinked-monitor-alert-1",
            "monitor_id": "monitor-without-cmdb",
            "cmdb_id": None,
            "resource_id": "monitor-without-cmdb",
            "resource_name": "unlinked-host",
            "resource_type": "Host",
        },
    )

    assert result["result"] is True
    event = Event.objects.get(source=source)
    assert (event.monitor_id, event.cmdb_id) == ("monitor-without-cmdb", None)


def test_monitor_identity_fields_do_not_change_existing_ingest_deduplication():
    source = _create_nats_source("nats-dedup-snapshot")
    event = {
        "title": "duplicate monitor event",
        "description": "duplicate monitor event",
        "level": "2",
        "item": "cpu_usage",
        "start_time": "1788400800",
        "action": "created",
        "external_id": "dedup-monitor-alert-1",
        "monitor_id": "dedup-monitor-1",
        "cmdb_id": "dedup-cmdb-1",
        "resource_id": "dedup-monitor-1",
        "resource_name": "dedup-host",
        "resource_type": "Host",
    }

    first = _receive(source, event)
    second = _receive(source, event)

    assert first["result"] is True
    assert second["result"] is False
    assert second["data"]["ingestion"]["duplicates"] == 1
    assert Event.objects.filter(source=source).count() == 1


def test_init_alert_sources_maps_monitor_identity_fields():
    call_command("init_alert_sources", stdout=StringIO())

    source = AlertSource.objects.get(source_id="nats")
    mapping = source.config["event_fields_mapping"]
    assert {
        "monitor_id": mapping.get("monitor_id"),
        "cmdb_id": mapping.get("cmdb_id"),
    } == {
        "monitor_id": "monitor_id",
        "cmdb_id": "cmdb_id",
    }
    restful_mapping = AlertSource.objects.get(source_id="restful").config["event_fields_mapping"]
    assert "monitor_id" not in restful_mapping
    assert "cmdb_id" not in restful_mapping


def test_new_monitor_payload_is_accepted_by_old_nats_mapping():
    source = _create_nats_source("nats-old-consumer")
    source.config["event_fields_mapping"].pop("monitor_id")
    source.config["event_fields_mapping"].pop("cmdb_id")
    source.save(update_fields=["config"])

    result = _receive(
        source,
        {
            "title": "new producer old consumer",
            "level": "2",
            "item": "cpu_usage",
            "start_time": "1788400800",
            "action": "created",
            "external_id": "new-producer-old-consumer-1",
            "monitor_id": "monitor-new-1",
            "cmdb_id": "cmdb-new-1",
            "resource_id": "monitor-new-1",
            "resource_name": "new-host",
            "resource_type": "Host",
        },
    )

    assert result["result"] is True
    event = Event.objects.get(source=source)
    assert (event.monitor_id, event.cmdb_id) == (None, None)
    assert event.raw_data["monitor_id"] == "monitor-new-1"
    assert event.raw_data["cmdb_id"] == "cmdb-new-1"


@pytest.mark.parametrize(
    ("field", "invalid_value", "sensitive_marker"),
    [
        (
            "monitor_id",
            {"unexpected": "SENSITIVE_MONITOR_ID_VALUE"},
            "SENSITIVE_MONITOR_ID_VALUE",
        ),
        (
            "cmdb_id",
            "SENSITIVE_CMDB_ID_VALUE" + "x" * 100,
            "SENSITIVE_CMDB_ID_VALUE",
        ),
    ],
)
def test_invalid_monitor_identity_is_rejected_without_database_error(
    field,
    invalid_value,
    sensitive_marker,
    caplog,
):
    source = _create_nats_source(f"nats-invalid-{field}")
    payload = {
        "title": "invalid monitor identity",
        "level": "2",
        "item": "cpu_usage",
        "start_time": "1788400800",
        "action": "created",
        "external_id": f"invalid-{field}-1",
        "monitor_id": "monitor-valid-1",
        "cmdb_id": "cmdb-valid-1",
        "resource_id": "monitor-valid-1",
        "resource_name": "invalid-host",
        "resource_type": "Host",
    }
    payload[field] = invalid_value

    with caplog.at_level(logging.INFO):
        result = _receive(source, payload)

    assert result["result"] is False
    assert result["data"]["ingestion"]["rejected"] == 1
    assert result["data"]["ingestion"]["errored"] == 0
    assert result["data"]["ingestion"]["accepted"] == 0
    assert not Event.objects.filter(source=source).exists()
    messages = [record.getMessage() for record in caplog.records]
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert not any("成功处理" in message for message in messages)
    assert any("部分接收" in message for message in messages)
    assert sensitive_marker not in "\n".join(messages)

    invalid_template = "[AlertSource] 事件身份字段校验失败: " "source_id=%s event_index=%s field=%s"
    summary_template = "[AlertSource] 接入丢弃统计: source_id=%s received=%s transformed=%s " "skipped_missing=%s rejected_invalid=%s errored=%s"
    partial_template = "[AlertEvent] 事件部分接收: source_id=%s pusher=%s received=%s " "accepted=%s rejected=%s errored=%s"
    contract_records = {record.msg: record for record in caplog.records if record.msg in {invalid_template, summary_template, partial_template}}
    assert set(contract_records) == {
        invalid_template,
        summary_template,
        partial_template,
    }
    assert contract_records[invalid_template].args == (source.source_id, 0, field)
    assert contract_records[summary_template].args == (
        source.source_id,
        1,
        0,
        0,
        1,
        0,
    )
    assert contract_records[partial_template].args == (
        source.source_id,
        "lite-monitor",
        1,
        0,
        1,
        0,
    )
    assert all(record.exc_info is None for record in contract_records.values())


def test_snapshot_schema_accepts_monitor_identity_and_object_name_lengths():
    assert Event._meta.get_field("monitor_id").max_length == 100
    assert Event._meta.get_field("cmdb_id").max_length == 100
    assert Event._meta.get_field("resource_id").max_length == 100
    assert Event._meta.get_field("resource_type").max_length == 100
    assert Alert._meta.get_field("resource_type").max_length == 100
