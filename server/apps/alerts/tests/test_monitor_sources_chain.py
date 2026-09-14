"""监控源从策略 API、事件接入到真实分派和详情响应的链路契约。"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.processor.instant_dispatcher import InstantStrategyCache
from apps.alerts.common.source_adapter.restful import RestFulAdapter
from apps.alerts.constants.constants import AlarmStrategyType, AlertStatus, EventStatus, LevelType
from apps.alerts.models import AlarmStrategy, Alert, AlertOutbox, AlertSource, Event, Incident, Level
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tasks.tasks import beat_retry_unassigned_assignment, build_instant_alerts
from apps.alerts.views.action import ActionRuleViewSet
from apps.alerts.views.alert import AlertModelViewSet
from apps.alerts.views.assignment_shield import AlertAssignmentModelViewSet, AlertShieldModelViewSet
from apps.alerts.views.enrichment import EnrichmentRuleModelViewSet
from apps.alerts.views.incident import IncidentModelViewSet
from apps.alerts.views.strategy import AlarmStrategyModelViewSet
from apps.system_mgmt.models.user import User

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def api(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    User.objects.create(username=authenticated_user.username, domain="domain.com", group_list=[1])
    monkeypatch.setattr("apps.core.utils.viewset_utils.get_permission_rules", lambda *a, **k: {"instance": [], "team": [1]})
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **k: {"instance": [], "team": [1]})

    def invoke(view, action, *, method="get", data=None, pk=None, query=""):
        request = getattr(APIRequestFactory(), method)(f"/api/{action}/{query}", data=data, format="json")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=authenticated_user)
        response = view.as_view({method: action})(request, **({"pk": str(pk)} if pk is not None else {}))
        if hasattr(response, "render"):
            response.render()
        return response.status_code, json.loads(response.content)

    return invoke


@pytest.fixture
def ingress():
    for kind in (LevelType.EVENT, LevelType.ALERT):
        Level.objects.create(level_id=1, level_name=f"{kind}-error", level_display_name="错误", level_type=kind)
    source = AlertSource.objects.create(
        name="链路源",
        source_id="monitor-source-chain",
        source_type="restful",
        secret="test",
        config={
            "event_fields_mapping": {
                key: key for key in ("title", "description", "level", "action", "item", "resource_name", "external_id", "start_time")
            },
        },
    )
    strategy = AlarmStrategy.objects.create(
        name="来源即时告警",
        strategy_type=AlarmStrategyType.INSTANT,
        dispatch_team=[1],
        team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU high"}]],
    )
    InstantStrategyCache.cache_clear()
    yield source, strategy
    InstantStrategyCache.cache_clear()


def payload(source, external_id, **extra):
    result = dict(
        title="CPU high",
        description="CPU",
        level="1",
        action="created",
        item="cpu",
        resource_name="host1",
        start_time=str(int(timezone.now().timestamp())),
        external_id=external_id,
        push_source_id=source,
    )
    result.update(extra)
    return result


def create_assignment(api, username, value="prod", operator="any_of"):
    rules = [[{"key": "push_source_ids", "operator": operator, "value": [value] if isinstance(value, str) else value}]]
    status, response = api(
        AlertAssignmentModelViewSet,
        "create",
        method="post",
        data={
            "name": f"分派-{value}",
            "match_type": "filter",
            "match_rules": rules,
            "personnel": [username],
            "config": {},
            "notify_channels": [],
            "notification_scenario": [],
            "notification_frequency": {},
        },
    )
    assert status == 201, response
    assert response["data"]["match_rules"] == rules
    return response["data"]["id"]


def create_rule_via_api(api, view, **payload):
    status, response = api(view, "create", method="post", data=payload)
    assert status == 201, response
    result = response.get("data", response)
    status, detail = api(view, "retrieve", pk=result["id"])
    assert status == 200, detail
    assert detail.get("data", detail)["match_rules"] == payload["match_rules"]
    return result


@pytest.mark.parametrize(
    "view,extra",
    [
        (AlertAssignmentModelViewSet, {"match_type": "filter", "config": {}, "notify_channels": []}),
        (AlertShieldModelViewSet, {"match_type": "filter", "suppression_time": {}}),
        (
            AlarmStrategyModelViewSet,
            {"strategy_type": "smart_denoise", "team": [1], "dispatch_team": [1], "params": {"window_size": 10, "group_by": ["resource_name"]}},
        ),
        (
            EnrichmentRuleModelViewSet,
            {
                "provider_type": "cmdb",
                "team": [1],
                "namespace": "api_multi",
                "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
                "output_projection": [{"source": "owner"}],
            },
        ),
        (ActionRuleViewSet, {"team": [1], "trigger_events": ["created"], "action_type": "job", "action_config": {}}),
    ],
)
def test_five_rule_apis_create_read_update_and_reject_invalid_changes(api, authenticated_user, view, extra):
    key = "source_names" if view in (AlertAssignmentModelViewSet, ActionRuleViewSet) else "source_name"
    rules = [[{"key": key, "operator": "any_of", "value": ["平台A", "平台B"]}]]
    created = create_rule_via_api(api, view, name="多值 API", match_rules=rules, personnel=[authenticated_user.username], **extra)
    updated = [[{"key": key, "operator": "none_of", "value": ["平台C"]}]]
    status, response = api(view, "partial_update", method="patch", pk=created["id"], data={"match_rules": updated})
    assert status == 200, response
    status, response = api(view, "retrieve", pk=created["id"])
    assert status == 200
    assert response.get("data", response)["match_rules"] == updated
    status, response = api(
        view,
        "partial_update",
        method="patch",
        pk=created["id"],
        data={"match_rules": [[{"key": "resource_name", "operator": "any_of", "value": []}]]},
    )
    assert status == 400, response
    status, response = api(view, "retrieve", pk=created["id"])
    assert status == 200
    assert response.get("data", response)["match_rules"] == updated


def deliver_assignments():
    for record in AlertOutbox.objects.filter(kind="auto_assignment", status=AlertOutbox.Status.PENDING):
        assert deliver_outbox_record(record.pk)


@pytest.mark.parametrize("strategy_type", [AlarmStrategyType.INSTANT, AlarmStrategyType.SMART_DENOISE])
def test_multivalue_ingress_enrichment_shield_detection_assignment_and_action(api, ingress, authenticated_user, monkeypatch, strategy_type):
    from unittest.mock import MagicMock

    from apps.alerts.action.engine import ActionEngine
    from apps.alerts.models.action import ActionExecution

    source, strategy = ingress
    strategy.strategy_type = strategy_type
    strategy.params = {"window_size": 10, "group_by": ["resource_name"], "alert_template": {"title": "CPU high", "description": "CPU busy"}}
    strategy.match_rules = [
        [
            {"key": "source_name", "operator": "any_of", "value": [source.name]},
            {"key": "item", "operator": "re", "value": "^(cpu|disk)$"},
            {"key": "title", "operator": "contains", "value": "CPU"},
        ]
    ]
    status, response = api(
        AlarmStrategyModelViewSet,
        "partial_update",
        method="patch",
        pk=strategy.pk,
        data={"strategy_type": strategy_type, "params": strategy.params, "match_rules": strategy.match_rules},
    )
    assert status == 200, response
    provider = MagicMock()
    provider.fetch_batch.side_effect = lambda keys, config: {key: [{"owner": "ops"}] for key in keys}
    monkeypatch.setattr("apps.alerts.enrichment.engine.get_provider", lambda kind: provider)
    create_rule_via_api(
        api,
        EnrichmentRuleModelViewSet,
        name="多值丰富",
        team=[1],
        provider_type="cmdb",
        namespace="multi",
        input_binding={"model_id": "resource_name", "inst_name": "resource_name"},
        output_projection=[{"source": "owner"}],
        match_rules=[
            [
                {"key": "source_name", "operator": "any_of", "value": [source.name]},
                {"key": "push_source_id", "operator": "any_of", "value": ["prod-a", "prod-b"]},
                {"key": "description", "operator": "contains", "value": "CPU busy"},
            ]
        ],
    )
    create_assignment(api, authenticated_user.username, ["prod-a", "prod-b"], "any_of")
    status, response = api(
        AlertShieldModelViewSet,
        "create",
        method="post",
        data={
            "name": "多资源屏蔽",
            "match_type": "filter",
            "suppression_time": {},
            "match_rules": [[{"key": "resource_name", "operator": "re", "value": "^blocked-(a|b)$"}]],
        },
    )
    assert status == 201, response
    payloads = [
        payload(value, value, resource_name=host, item=metric, description="CPU busy")
        for value, host, metric in [
            ("prod-a", "host-a", "cpu"),
            ("prod-b", "host-b", "disk"),
            ("blocked", "blocked-a", "cpu"),
            ("outside", "host-c", "memory"),
        ]
    ]
    from apps.alerts.utils.util import encode_team_secret

    secret = encode_team_secret(source.secret, "1")
    source.team_secrets = {"1": secret}
    source.save(update_fields=["team_secrets"])
    adapter = RestFulAdapter(alert_source=source, secret=secret, events=payloads)
    assert adapter.authenticate()
    adapter.main()
    if strategy_type == AlarmStrategyType.SMART_DENOISE:
        AggregationProcessor().process_aggregation()
    assert Event.objects.get(push_source_id="blocked").status == EventStatus.SHIELD
    assert Event.objects.get(push_source_id="prod-a").enrichment == {"multi": {"owner": "ops"}}
    assert Event.objects.get(push_source_id="outside").enrichment == {}
    assert provider.fetch_batch.call_count == 1
    assert len(provider.fetch_batch.call_args.args[0]) == 2
    deliver_assignments()
    alerts = list(Alert.objects.all())
    assert {alert.resource_name for alert in alerts} == {"host-a", "host-b"}
    assert all(alert.operator == [authenticated_user.username] for alert in alerts)
    action = create_rule_via_api(
        api,
        ActionRuleViewSet,
        name="多值处理",
        team=[1],
        trigger_events=["assigned"],
        action_type="job",
        action_config={},
        match_rules=[
            [
                {"key": "item", "operator": "re", "value": "^(cpu|disk)$"},
                {"key": "push_source_ids", "operator": "any_of", "value": ["prod-a", "prod-b"]},
            ]
        ],
    )
    handler = MagicMock()
    monkeypatch.setattr("apps.alerts.action.engine.get_handler", lambda kind: handler)
    for alert in alerts:
        ActionEngine().evaluate(alert, "assigned")
        ActionEngine().evaluate(alert, "assigned")
    assert ActionExecution.objects.filter(rule_id=action["id"]).count() == 2
    assert handler.execute.call_count == 2


def items(response):
    data = response.get("data", response)
    assert not isinstance(data, dict) or "items" in data, response
    return data["items"] if isinstance(data, dict) else data


def test_saved_source_rules_control_ingress_assignment_and_detail(api, ingress, authenticated_user):
    source, _ = ingress
    create_assignment(api, authenticated_user.username)
    status, response = api(
        AlertShieldModelViewSet,
        "create",
        method="post",
        data={
            "name": "来源屏蔽",
            "match_type": "filter",
            "suppression_time": {},
            "match_rules": [[{"key": "push_source_id", "operator": "any_of", "value": ["blocked"]}]],
        },
    )
    assert status == 201, response
    events = [payload("prod", "prod-1"), payload("test", "test-1"), payload("blocked", "blocked-1")]
    RestFulAdapter(alert_source=source, secret="test", events=events).main()

    assert Event.objects.get(push_source_id="blocked").status == EventStatus.SHIELD
    assert Alert.objects.count() == 2
    assert AlertOutbox.objects.filter(kind="auto_assignment").exists()
    deliver_assignments()

    status, response = api(AlertModelViewSet, "list")
    assert status == 200, response
    rows = items(response)
    actual = {tuple(row["push_source_ids"]): (row["status"], row["operator"]) for row in rows}
    assert actual == {("prod",): (AlertStatus.PENDING, [authenticated_user.username]), ("test",): (AlertStatus.UNASSIGNED, [])}
    prod = next(row for row in rows if row["push_source_ids"] == ["prod"])
    status, detail = api(AlertModelViewSet, "retrieve", pk=prod["id"])
    assert status == 200
    assert detail["data"]["push_source_ids"] == ["prod"]
    status, associated = api(AlertModelViewSet, "events", pk=prod["id"])
    assert status == 200
    assert [event["push_source_id"] for event in items(associated)] == ["prod"]

    # 同一上报和已投递 outbox 重放，来源、告警数量与责任人保持一致。
    RestFulAdapter(alert_source=source, secret="test", events=events).main()
    for record in AlertOutbox.objects.filter(kind="auto_assignment"):
        deliver_outbox_record(record.pk)
    assert Event.objects.count() == 3
    assert Alert.objects.count() == 2
    _, detail = api(AlertModelViewSet, "retrieve", pk=prod["id"])
    assert (detail["data"]["push_source_ids"], detail["data"]["operator"]) == (["prod"], [authenticated_user.username])


@pytest.mark.parametrize("operator,value", [("any_of", ["prod"]), ("all_of", ["001", "prod"])])
def test_aggregation_append_retries_assignment_with_complete_source_set(api, ingress, authenticated_user, operator, value):
    source, strategy = ingress
    strategy.strategy_type = AlarmStrategyType.SMART_DENOISE
    strategy.params = {"window_size": 10, "group_by": ["resource_name"]}
    strategy.save()
    create_assignment(api, authenticated_user.username, value, operator)
    RestFulAdapter(alert_source=source, secret="test", events=[payload("001", "first")]).main()
    AggregationProcessor().process_aggregation()
    deliver_assignments()
    alert = Alert.objects.get()
    _, before = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert (before["data"]["push_source_ids"], before["data"]["status"]) == (["001"], AlertStatus.UNASSIGNED)

    RestFulAdapter(alert_source=source, secret="test", events=[payload("prod", "second"), payload("prod", "third")]).main()
    AggregationProcessor().process_aggregation()
    beat_retry_unassigned_assignment()
    deliver_assignments()
    assert Alert.objects.count() == 1
    _, after = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert (after["data"]["push_source_ids"], after["data"]["status"], after["data"]["operator"]) == (
        ["001", "prod"],
        AlertStatus.PENDING,
        [authenticated_user.username],
    )
    # 新来源继续归并，但已分派告警不被后来创建的规则重新分派。
    User.objects.create(username="second-op", domain="domain.com", group_list=[1])
    create_assignment(api, "second-op", "test")
    RestFulAdapter(alert_source=source, secret="test", events=[payload("test", "fourth")]).main()
    AggregationProcessor().process_aggregation()
    beat_retry_unassigned_assignment()
    deliver_assignments()
    _, final = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert (final["data"]["push_source_ids"], final["data"]["operator"]) == (["001", "prod", "test"], [authenticated_user.username])


def test_source_name_all_of_from_ingress_append_to_assignment_and_detail(api, ingress, authenticated_user):
    source, strategy = ingress
    strategy.strategy_type = AlarmStrategyType.SMART_DENOISE
    strategy.params = {"window_size": 10, "group_by": ["resource_name"]}
    strategy.save()
    second = AlertSource.objects.create(name="第二平台", source_id="second-platform", source_type="restful", secret="test", config=source.config)
    rules = [[{"key": "source_names", "operator": "all_of", "value": [source.name, second.name]}]]
    create_rule_via_api(
        api,
        AlertAssignmentModelViewSet,
        name="跨来源分派",
        match_type="filter",
        match_rules=rules,
        personnel=[authenticated_user.username],
        config={},
        notify_channels=[],
    )

    RestFulAdapter(alert_source=source, secret="test", events=[payload("a", "first-platform")]).main()
    AggregationProcessor().process_aggregation()
    deliver_assignments()
    alert = Alert.objects.get()
    assert alert.status == AlertStatus.UNASSIGNED
    assert api(AlertModelViewSet, "retrieve", pk=alert.pk)[1]["data"]["source_names"] == [source.name]

    RestFulAdapter(alert_source=second, secret="test", events=[payload("b", "second-platform")]).main()
    AggregationProcessor().process_aggregation()
    beat_retry_unassigned_assignment()
    deliver_assignments()
    assert Alert.objects.count() == 1
    detail = api(AlertModelViewSet, "retrieve", pk=alert.pk)[1]["data"]
    assert detail["source_names"] == sorted([source.name, second.name])
    assert detail["operator"] == [authenticated_user.username]
    assert detail["status"] == AlertStatus.PENDING


@pytest.mark.parametrize("broker_available", [True, False], ids=["worker-replay", "broker-fallback"])
def test_large_ingress_batch_keeps_sources_through_async_build(api, ingress, authenticated_user, monkeypatch, broker_available):
    source, _ = ingress
    create_assignment(api, authenticated_user.username, "001")
    queued = []

    def send_task(name, args):
        assert name == build_instant_alerts.name
        if not broker_available:
            raise ConnectionError("test broker unavailable")
        # 模拟消息传输的序列化边界，worker 下方直接执行真实任务。
        queued.append(json.loads(json.dumps(args[0])))

    monkeypatch.setattr("apps.alerts.aggregation.processor.instant_dispatcher.current_app.send_task", send_task)
    RestFulAdapter(alert_source=source, secret="test", events=[payload("001" if index % 2 else "1", f"batch-{index}") for index in range(51)]).main()
    if broker_available:
        assert Alert.objects.count() == 0
        assert len(queued) == 1
        assert build_instant_alerts(queued[0]) == {"created": 51}
        assert build_instant_alerts(queued[0]) == {"created": 0}
    else:
        assert queued == []
    deliver_assignments()
    status, response = api(AlertModelViewSet, "list", query="?page=1&page_size=100")
    assert status == 200
    rows = items(response)
    assert len(rows) == 51
    assert sum(row["push_source_ids"] == ["001"] and row["operator"] == [authenticated_user.username] for row in rows) == 25
    assert sum(row["push_source_ids"] == ["1"] and row["status"] == AlertStatus.UNASSIGNED for row in rows) == 26


@pytest.mark.parametrize("action", ["recovery", "closed"])
@pytest.mark.parametrize("recovery_source,expected", [("prod", ["prod"]), ("bridge", ["bridge", "prod"])])
def test_ingress_recovery_and_close_keep_complete_sources(api, ingress, action, recovery_source, expected):
    source, _ = ingress
    RestFulAdapter(alert_source=source, secret="test", events=[payload("prod", "lifecycle")]).main()
    alert = Alert.objects.get()
    recovery = payload(recovery_source, "lifecycle", action=action)
    RestFulAdapter(alert_source=source, secret="test", events=[recovery]).main()
    RestFulAdapter(alert_source=source, secret="test", events=[recovery]).main()
    _, detail = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert detail["data"]["push_source_ids"] == expected
    _, associated = api(AlertModelViewSet, "events", pk=alert.pk)
    assert sorted(event["action"] for event in items(associated)) == sorted(["created", action])
    assert Alert.objects.count() == 1


def test_backfilled_history_can_be_assigned_and_cannot_be_overwritten_from_api(api, ingress, authenticated_user):
    source, _ = ingress
    RestFulAdapter(alert_source=source, secret="test", events=[payload("prod", "historical")]).main()
    alert = Alert.objects.get()
    # 升级后的历史记录只有事件关联，新列仍为默认空列表。
    Alert.objects.filter(pk=alert.pk).update(push_source_ids=[])
    create_assignment(api, authenticated_user.username)
    deliver_assignments()
    _, before = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert (before["data"]["push_source_ids"], before["data"]["status"]) == ([], AlertStatus.UNASSIGNED)
    call_command("backfill_alert_monitor_sources", stdout=StringIO())
    beat_retry_unassigned_assignment()
    deliver_assignments()
    status, response = api(AlertModelViewSet, "partial_update", method="patch", pk=alert.pk, data={"push_source_ids": ["forged"]})
    assert status == 200, response
    _, after = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert (after["data"]["push_source_ids"], after["data"]["operator"]) == (["prod"], [authenticated_user.username])


def test_sources_are_complete_in_pagination_incident_and_related_responses_without_tenant_leaks(api, ingress, authenticated_user):
    source, strategy = ingress
    strategy.strategy_type = AlarmStrategyType.SMART_DENOISE
    strategy.params = {"window_size": 10, "group_by": ["resource_name"], "alert_template": {"title": "CPU high", "description": "CPU busy"}}
    strategy.save()
    RestFulAdapter(
        alert_source=source, secret="test", events=[payload(value, f"page-{index}") for index, value in enumerate(["001", "1", "prod"])]
    ).main()
    AggregationProcessor().process_aggregation()
    alert = Alert.objects.get()
    other = Alert.objects.create(
        alert_id="visible-related",
        title="related",
        content="",
        level="1",
        fingerprint="related",
        team=[1],
        push_source_ids=["test"],
        dimensions=alert.dimensions,
    )
    private = Alert.objects.create(
        alert_id="private",
        title="private",
        content="",
        level="1",
        fingerprint="private",
        team=[2],
        push_source_ids=["private-monitor-sentinel"],
        dimensions=alert.dimensions,
    )
    incident = Incident.objects.create(incident_id="sources-incident", title="事故", level="1", team=[1])
    incident.alert.add(alert, other, private)
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"alarm": {"Alarms-View", "Incidents-View"}}
    for view, action, pk in [(AlertModelViewSet, "list", None), (IncidentModelViewSet, "alerts", incident.pk)]:
        status, response = api(view, action, pk=pk, query="?page=1&page_size=100")
        assert status == 200, response
        assert {row["alert_id"]: row["push_source_ids"] for row in items(response)} == {
            alert.alert_id: ["001", "1", "prod"],
            other.alert_id: ["test"],
        }
    status, related = api(AlertModelViewSet, "related", pk=alert.pk)
    assert status == 200, related
    assert [(row["id"], row["push_source_ids"]) for row in items(related)] == [(other.pk, ["test"])]
    _, events = api(AlertModelViewSet, "events", pk=alert.pk, query="?page=1&page_size=1")
    assert len(items(events)) == 1
    _, detail = api(AlertModelViewSet, "retrieve", pk=alert.pk)
    assert detail["data"]["push_source_ids"] == ["001", "1", "prod"]
    for action in ("retrieve", "events", "related"):
        status, denied = api(AlertModelViewSet, action, pk=private.pk)
        if action == "retrieve":
            # 详情 CRUD 沿用旧接口的 HTTP 200 + result=false 拒绝契约。
            assert status == 200 and denied["result"] is False, denied
        else:
            assert status == 404, denied
        assert "private-monitor-sentinel" not in json.dumps(denied)


@pytest.mark.parametrize("view,key", [(AlertAssignmentModelViewSet, "push_source_ids"), (AlertShieldModelViewSet, "push_source_id")])
@pytest.mark.parametrize(
    "bad_rule",
    [
        {"operator": "eq", "value": []},
        {"operator": "eq", "value": 1},
        {"operator": "eq", "value": "  "},
        {"operator": "re", "value": "["},
        {"operator": "unknown", "value": "prod"},
        {"operator": "eq", "value": "x" * 257},
        {"operator": "eq", "value": "prod", "key": "wrong-domain"},
    ],
)
def test_invalid_rule_update_is_rejected_and_keeps_saved_source_condition(api, view, key, bad_rule):
    saved_rules = [[{"key": key, "operator": "any_of", "value": ["001"]}]]
    status, created = api(view, "create", method="post", data={"name": "校验规则", "match_type": "filter", "match_rules": saved_rules})
    assert status == 201, created
    rule = {"key": key, **bad_rule}
    if rule["key"] == "wrong-domain":
        rule["key"] = "push_source_id" if key == "push_source_ids" else "push_source_ids"
    status, rejected = api(view, "partial_update", method="patch", pk=created["data"]["id"], data={"match_rules": [[rule]]})
    assert status == 400, rejected
    status, persisted = api(view, "retrieve", pk=created["data"]["id"])
    assert status == 200, persisted
    assert persisted["data"]["match_rules"] == saved_rules
