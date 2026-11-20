from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.alerts.enrichment.engine import EnrichmentEngine

HOST = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
HOST_B = "c28e467a-501d-426f-a3c3-6e560c7b33cb"
HOST_C = "d44d4444-b6bb-43cc-9eae-8eb8a09f795e"
APP_SMALL = "a11a1111-b6bb-43cc-9eae-8eb8a09f795e"
APP_LARGE = "c33c3333-b6bb-43cc-9eae-8eb8a09f795e"
SYS = "b22b2222-b6bb-43cc-9eae-8eb8a09f795e"


@pytest.fixture(autouse=True)
def _clear_enrichment_cache():
    cache.clear()
    yield
    cache.clear()


def _rule(**overrides):
    data = {
        "id": 1,
        "is_active": True,
        "match_rules": [],
        "provider_type": "cmdb",
        "preset_key": "",
        "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
        "provider_config": {},
        "output_projection": [{"source": "ip_addr"}],
        "on_multiple": "list",
        "resolved_namespace": "cmdb",
        "namespace": "cmdb",
        "team": [1],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _event(resource_id=HOST, service="node-exporter"):
    event = {
        "team": [1],
        "resource_type": "host",
        "resource_id": resource_id,
        "enrichment": {},
    }
    if service is not None:
        event["service"] = service
    return event


def _install_cmdb(mock_cmdb_cls, mock_lookup, members, applications, systems=None):
    cmdb = MagicMock()
    mock_cmdb_cls.return_value = cmdb
    systems = systems or {}

    def search(params, _timeout=3):
        model_id = params.get("model_id")
        uuids = [str(item) for item in (params.get("inst_uuids") or [])]
        if model_id == "host":
            return {uid: {"inst_uuid": uid, "ip_addr": "10.0.0.8"} for uid in uuids}
        if model_id == "application":
            return {uid: applications[uid] for uid in uuids if uid in applications}
        if model_id == "system":
            return {uid: systems[uid] for uid in uuids if uid in systems}
        return {}

    cmdb.search_instances_batch.side_effect = search

    def lookup(organization_ids, inst_uuids=None, **kwargs):
        return {uid: members[uid] for uid in (inst_uuids or []) if uid in members}

    mock_lookup.side_effect = lookup
    return cmdb


def _member(root_uuid, system_uuid=None):
    return {"root_uuid": root_uuid, "system_uuid": system_uuid, "ci_uuid": HOST}


def _app(inst_uuid, inst_name, app_id="ADV-TEST"):
    return {"inst_uuid": inst_uuid, "inst_name": inst_name, "app_id": app_id}


def _system(inst_name):
    return {"inst_uuid": SYS, "inst_name": inst_name, "operator": 4}


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_application_name_replaces_reported_service(mock_cmdb_cls, mock_lookup):
    _install_cmdb(
        mock_cmdb_cls,
        mock_lookup,
        members={HOST: [_member(APP_SMALL, SYS)]},
        applications={APP_SMALL: _app(APP_SMALL, "adv-app-test")},
        systems={SYS: _system("交易系统")},
    )
    event = _event()

    EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert event["service"] == "adv-app-test"
    assert event["enrichment"]["cmdb"]["service"] == "adv-app-test"
    assert event["service"] != "ADV-TEST"
    assert event["enrichment"]["cmdb"]["ip_addr"] == "10.0.0.8"
    assert "application.inst_name" not in event["enrichment"]["cmdb"]


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_missing_application_keeps_reported_service(mock_cmdb_cls, mock_lookup):
    _install_cmdb(mock_cmdb_cls, mock_lookup, members={}, applications={})
    event = _event()
    empty = _event(service=None)

    EnrichmentEngine(rules=[_rule()]).enrich_batch([event, empty])

    assert event["service"] == "node-exporter"
    assert "service" not in empty
    assert "service" not in event["enrichment"].get("cmdb", {})


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_blank_application_name_uses_that_application_system_name(mock_cmdb_cls, mock_lookup):
    _install_cmdb(
        mock_cmdb_cls,
        mock_lookup,
        members={HOST: [_member(APP_LARGE, SYS), _member(APP_SMALL, SYS)]},
        applications={
            APP_LARGE: _app(APP_LARGE, "adv-app-prod"),
            APP_SMALL: _app(APP_SMALL, "   "),
        },
        systems={SYS: _system("交易系统")},
    )
    event = _event()

    EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert event["service"] == "交易系统"
    assert event["enrichment"]["cmdb"]["service"] == "交易系统"


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_multiple_applications_use_smallest_root_uuid_name(mock_cmdb_cls, mock_lookup):
    _install_cmdb(
        mock_cmdb_cls,
        mock_lookup,
        members={HOST: [_member(APP_LARGE), _member(APP_SMALL)]},
        applications={
            APP_LARGE: {"inst_name": "adv-app-prod"},
            APP_SMALL: {"inst_name": "adv-app-test"},
        },
    )
    event = _event()

    EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert event["service"] == "adv-app-test"
    assert event["enrichment"]["cmdb"]["ip_addr"] == "10.0.0.8"


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_application_name_is_stripped_without_changing_case(mock_cmdb_cls, mock_lookup):
    _install_cmdb(
        mock_cmdb_cls,
        mock_lookup,
        members={HOST: [_member(APP_SMALL)]},
        applications={APP_SMALL: _app(APP_SMALL, " API ")},
    )
    event = _event()

    EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert event["service"] == "API"


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_cmdb_lookup_failure_keeps_reported_service(mock_cmdb_cls, mock_lookup):
    cmdb = MagicMock()
    mock_cmdb_cls.return_value = cmdb
    cmdb.search_instances_batch.return_value = {HOST: {"inst_uuid": HOST, "ip_addr": "10.0.0.8"}}
    mock_lookup.side_effect = TimeoutError("rpc timeout")
    event = _event()

    result = EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert result.events == [event]
    assert event["service"] == "node-exporter"
    assert "service" not in event["enrichment"].get("cmdb", {})


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_service_name_longer_than_column_keeps_reported_service(mock_cmdb_cls, mock_lookup):
    _install_cmdb(
        mock_cmdb_cls,
        mock_lookup,
        members={HOST: [_member(APP_SMALL, SYS)]},
        applications={APP_SMALL: _app(APP_SMALL, "n" * 201)},
        systems={SYS: _system("交易系统")},
    )
    event = _event()

    EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert event["service"] == "node-exporter"


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
def test_later_cmdb_rule_does_not_replace_the_first_service_name(mock_cmdb_cls, mock_lookup):
    names = iter(["adv-app-test", "adv-app-prod"])
    cmdb = MagicMock()
    mock_cmdb_cls.return_value = cmdb

    def search(params, _timeout=3):
        model_id = params.get("model_id")
        uuids = [str(item) for item in (params.get("inst_uuids") or [])]
        if model_id == "host":
            return {uid: {"inst_uuid": uid, "ip_addr": "10.0.0.8"} for uid in uuids}
        if model_id == "application":
            return {APP_SMALL: _app(APP_SMALL, next(names))}
        return {}

    cmdb.search_instances_batch.side_effect = search
    mock_lookup.side_effect = lambda organization_ids, inst_uuids=None, **kwargs: {uid: [_member(APP_SMALL)] for uid in (inst_uuids or [])}
    event = _event()
    rules = [
        _rule(id=1, provider_config={"query_timeout_seconds": 3}),
        _rule(id=2, provider_config={"query_timeout_seconds": 4}),
    ]

    EnrichmentEngine(rules=rules).enrich_batch([event])

    assert event["service"] == "adv-app-test"


@patch("apps.alerts.enrichment.providers.cmdb.lookup_ci_context")
@patch("apps.alerts.enrichment.providers.cmdb.CMDB")
@pytest.mark.django_db
def test_same_application_events_aggregate_by_service(mock_cmdb_cls, mock_lookup):
    from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
    from apps.alerts.common.source_adapter.restful import RestFulAdapter
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.alert_operator import AlarmStrategy
    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.enrichment import EnrichmentRule
    from apps.alerts.models.models import Alert, Event, Level

    for level_type in (LevelType.EVENT, LevelType.ALERT):
        for level_id in (0, 1, 2, 3):
            Level.objects.create(
                level_id=level_id,
                level_name=f"{level_type}-{level_id}",
                level_display_name=f"{level_type}-{level_id}",
                level_type=level_type,
            )
    source = AlertSource.objects.create(
        name="应用归属源",
        source_id="app-service-flow",
        source_type="restful",
        secret="src-secret",
        config={
            "event_fields_mapping": {
                "title": "title",
                "level": "level",
                "resource_id": "resource_id",
                "resource_type": "resource_type",
                "resource_name": "resource_name",
                "service": "service",
                "item": "item",
                "external_id": "external_id",
            }
        },
    )
    EnrichmentRule.objects.create(
        name="应用名写入 service",
        is_active=True,
        match_rules=[],
        provider_type="cmdb",
        input_binding={"model_id": "resource_type", "inst_uuid": "resource_id"},
        provider_config={},
        output_projection=[{"source": "ip_addr"}],
        on_multiple="first",
        namespace="cmdb",
        team=[1],
    )
    AlarmStrategy.objects.create(
        name="只按 service",
        strategy_type="smart_denoise",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "主机告警"}]],
        params={"window_size": 60, "group_by": ["service"]},
    )
    _install_cmdb(
        mock_cmdb_cls,
        mock_lookup,
        members={
            HOST: [_member(APP_SMALL, SYS)],
            HOST_B: [_member(APP_SMALL, SYS)],
        },
        applications={APP_SMALL: _app(APP_SMALL, "adv-app-test")},
        systems={SYS: _system("交易系统")},
    )
    adapter = RestFulAdapter(alert_source=source)
    adapter.resolved_team = [1]
    adapter.create_events(
        [
            {
                "title": "主机告警",
                "level": "1",
                "resource_type": "host",
                "resource_id": HOST,
                "resource_name": "host-a",
                "service": "job-a",
                "item": "cpu",
                "external_id": "ext-a",
            },
            {
                "title": "主机告警",
                "level": "1",
                "resource_type": "host",
                "resource_id": HOST_B,
                "resource_name": "host-b",
                "service": "job-b",
                "item": "mem",
                "external_id": "ext-b",
            },
            {
                "title": "主机告警",
                "level": "1",
                "resource_type": "host",
                "resource_id": HOST_C,
                "resource_name": "host-c",
                "service": "node-exporter",
                "item": "cpu",
                "external_id": "ext-c",
            },
        ]
    )

    by_name = {event.resource_name: event for event in Event.objects.all()}
    assert by_name["host-a"].service == "adv-app-test"
    assert by_name["host-b"].service == "adv-app-test"
    assert by_name["host-a"].enrichment["cmdb"]["service"] == "adv-app-test"
    assert by_name["host-a"].raw_data["service"] == "job-a"
    assert by_name["host-c"].service == "node-exporter"

    AggregationProcessor().process_aggregation()

    alerts = {alert.dimensions.get("service"): alert for alert in Alert.objects.all()}
    assert set(alerts) == {"adv-app-test", "node-exporter"}
    grouped = alerts["adv-app-test"]
    assert sorted(grouped.events.values_list("resource_name", flat=True)) == ["host-a", "host-b"]
    assert alerts["node-exporter"].events.get().resource_name == "host-c"
