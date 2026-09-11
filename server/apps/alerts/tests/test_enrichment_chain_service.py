from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.common.source_adapter.base import AlertSourceAdapter
from apps.alerts.enrichment.engine import EnrichmentEngine


def _cmdb_rule(**overrides):
    data = {
        "name": "CMDB chain",
        "provider_type": "cmdb",
        "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
        "provider_config": {"query_timeout_seconds": 3},
        "output_projection": [{"source": "owner"}, {"source": "business_system"}],
        "on_multiple": "first",
        "resolved_namespace": "cmdb",
        "namespace": "cmdb",
        "match_rules": [[{"key": "source_name", "operator": "any_of", "value": ["Prometheus"]}]],
        "team": [7],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_event_context_to_cmdb_to_alert_to_notification_chain(mock_cmdb_cls, monkeypatch):
    cmdb = MagicMock()
    mock_cmdb_cls.return_value = cmdb
    cmdb.search_instances_batch.return_value = {
        "63e4a531-b6bb-43cc-9eae-8eb8a09f795e": {
            "owner": "alice",
            "business_system": "payment",
            "credential": "must-not-leak",
        }
    }
    event = {
        "source_id": "prometheus",
        "source_name": "Prometheus",
        "resource_type": "host",
        "resource_id": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
        "team": [7],
        "enrichment": {},
    }

    EnrichmentEngine(rules=[_cmdb_rule()]).enrich_batch([event])
    merged = AlertBuilder._merge_enrichment([SimpleNamespace(enrichment=event["enrichment"])])

    assert merged == {"cmdb": {"owner": "alice", "business_system": "payment"}}
    assert "credential" not in str(merged)

    alert = SimpleNamespace(
        title="CPU high",
        content="usage > 90%",
        enrichment=merged,
        format_created_at=lambda timezone: "2026-09-03 09:00:00",
    )
    monkeypatch.setattr(NotifyParamsFormat, "get_user_timezone", lambda self: None)
    content = NotifyParamsFormat(["ops"], [alert]).format_content()
    assert "enrichment.cmdb.owner: alice" in content
    assert "enrichment.cmdb.business_system: payment" in content

    cmdb.search_instances_batch.assert_called_once_with(
        params={
            "protocol_version": "2",
            "model_id": "host",
            "inst_uuids": ["63e4a531-b6bb-43cc-9eae-8eb8a09f795e"],
            "organization_ids": [7],
        },
        _timeout=3,
    )


def test_enrichment_dimension_resolves_from_event_payload():
    event = SimpleNamespace(enrichment={"cmdb": {"owner": "alice"}})
    assert AlertBuilder._resolve_dimensions([event], "enrichment.cmdb.owner") == {"enrichment.cmdb.owner": "alice"}


def test_ingestion_adds_source_context_before_enrichment(monkeypatch):
    class _Adapter(AlertSourceAdapter):
        def fetch_alerts(self):
            return []

    adapter = object.__new__(_Adapter)
    adapter.alert_source = SimpleNamespace(source_id="prometheus", name="Prometheus", pk=7)
    adapter.mapping_fields_to_event = MagicMock(
        return_value={
            "title": "CPU high",
            "resource_type": "host",
            "resource_id": "uuid-1",
            "start_time": "2026-09-03T09:00:00Z",
        }
    )
    adapter._resolve_event_team = MagicMock(return_value=[7])
    adapter.add_base_fields = MagicMock()
    adapter.bulk_save_events = MagicMock(return_value=[])
    captured = []
    monkeypatch.setattr(
        "apps.alerts.common.source_adapter.base.EnrichmentEngine.enrich_batch",
        lambda self, events: captured.extend(dict(event) for event in events),
    )

    adapter.create_events([{"title": "CPU high"}])

    assert captured[0]["source_id"] == "prometheus"
    assert captured[0]["source_name"] == "Prometheus"
    assert "_rule_source_id" not in captured[0]
    constructed_data = adapter.add_base_fields.call_args.args[0]
    assert getattr(constructed_data, "source_id", None) is None


@pytest.mark.django_db
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_persisted_ingestion_to_alert_full_chain(mock_cmdb_cls):
    from apps.alerts.common.source_adapter.restful import RestFulAdapter
    from apps.alerts.constants.constants import AlertsSourceTypes, LevelType
    from apps.alerts.models.alert_operator import AlarmStrategy
    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.enrichment import EnrichmentRule
    from apps.alerts.models.models import Level

    for level_type, level_ids in ((LevelType.EVENT, range(4)), (LevelType.ALERT, range(3))):
        for level_id in level_ids:
            Level.objects.create(
                level_type=level_type,
                level_id=level_id,
                level_name=str(level_id),
                level_display_name=str(level_id),
            )
    source = AlertSource.objects.create(
        name="Prometheus",
        source_id="prometheus-chain",
        source_type=AlertsSourceTypes.RESTFUL,
        config={
            "event_fields_mapping": {
                "title": "title",
                "description": "description",
                "level": "level",
                "resource_type": "resource_type",
                "resource_id": "resource_id",
                "resource_name": "resource_name",
                "item": "item",
                "start_time": "start_time",
            }
        },
    )
    EnrichmentRule.objects.create(
        name="chain-rule",
        provider_type="cmdb",
        input_binding={"model_id": "resource_type", "inst_uuid": "resource_id"},
        output_projection=[{"source": "owner"}, {"source": "business_system"}],
        namespace="cmdb",
        team=[7],
    )
    cmdb = MagicMock()
    mock_cmdb_cls.return_value = cmdb
    resource_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    cmdb.search_instances_batch.return_value = {resource_uuid: {"owner": "alice", "business_system": "payment"}}
    adapter = RestFulAdapter(alert_source=source, trusted_internal=True)

    batches = adapter.create_events(
        [
            {
                "title": "CPU high",
                "description": "usage > 90%",
                "level": "1",
                "resource_type": "host",
                "resource_id": resource_uuid,
                "resource_name": "host-a",
                "item": "cpu",
                "start_time": "1788400800",
                "organizations": [7],
            }
        ]
    )
    event = batches[0][0]
    strategy = AlarmStrategy.objects.create(
        name="chain-strategy",
        dispatch_team=[7],
        team=[7],
        params={"window_size": 10, "group_by": ["enrichment.cmdb.owner"]},
    )
    now = timezone.now()
    alert = AlertBuilder._create_new_alert(
        {
            "fingerprint": "chain-fingerprint",
            "event_ids": [event.event_id],
            "alert_level": "1",
            "alert_title": "CPU high",
            "alert_description": "host-a",
            "first_event_time": now,
            "last_event_time": now,
        },
        strategy,
        [event.event_id],
        "enrichment.cmdb.owner",
    )

    event.refresh_from_db()
    alert.refresh_from_db()
    assert event.enrichment == {"cmdb": {"owner": "alice", "business_system": "payment"}}
    assert event.enrichment_meta["status"] == "success"
    assert alert.enrichment == event.enrichment
    assert alert.enrichment_meta == {
        "schema_version": 1,
        "event_count": 1,
        "status_counts": {"success": 1},
    }
    assert alert.dimensions == {"enrichment.cmdb.owner": "alice"}
    assert list(alert.events.values_list("event_id", flat=True)) == [event.event_id]


def test_rule_foreign_key_context_does_not_change_provider_binding(monkeypatch):
    provider = MagicMock()
    provider.fetch_batch.side_effect = lambda keys, config: {key: [{"owner": "ops"}] for key in keys}
    monkeypatch.setattr("apps.alerts.enrichment.engine.get_provider", lambda kind: provider)
    event = {"source_id": "business-code", "source_name": "Prometheus", "resource_type": "host", "team": [7], "enrichment": {}}
    rule = _cmdb_rule(input_binding={"model_id": "resource_type", "inst_uuid": "source_id"})
    EnrichmentEngine(rules=[rule]).enrich_batch([event])
    provider.fetch_batch.assert_called_once()
    assert "business-code" in str(provider.fetch_batch.call_args.args[0])
    assert event["source_id"] == "business-code"
    assert event["enrichment"] == {"cmdb": {"owner": "ops"}}
