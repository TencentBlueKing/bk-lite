"""独立业务矩阵逐入口测试：保存→回显→匹配→真实业务结果，不从生产目录生成期望值。"""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.cache.backends.locmem import LocMemCache
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.action.engine import ActionEngine
from apps.alerts.action.matcher import event_matches as action_matches
from apps.alerts.action.payload import build_rule_payload
from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.processor.instant_dispatcher import InstantAlertDispatcher, InstantStrategyCache
from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.common.assignment import AlertAssignmentOperator
from apps.alerts.common.shield import EventShieldOperator
from apps.alerts.constants.constants import EventStatus
from apps.alerts.enrichment.engine import EnrichmentEngine
from apps.alerts.enrichment.matcher import event_matches as enrichment_matches
from apps.alerts.models import AlarmStrategy, Alert, AlertSource, Event, Level
from apps.alerts.models.action import ActionExecution
from apps.alerts.tests.test_multivalue_completeness_service import SERIALIZERS
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher
from apps.alerts.utils.rule_catalog import FIELDS
from apps.alerts.views.action import ActionRuleViewSet
from apps.alerts.views.assignment_shield import AlertAssignmentModelViewSet, AlertShieldModelViewSet
from apps.alerts.views.enrichment import EnrichmentRuleModelViewSet
from apps.alerts.views.strategy import AlarmStrategyModelViewSet
from apps.system_mgmt.models.user import User

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
CONTRACT = json.loads((Path(__file__).resolve().parents[4] / "specs/changes/alert-rule-types/field-operator-test-matrix.json").read_text())
SCOPES = {"correlation": "event", "shield": "event", "enrichment": "event", "assignment": "alert", "action": "alert"}
CASES = [(scope, key, op) for scope, context in SCOPES.items() for key, ops in CONTRACT[context].items() for op in ops]
CASE_IDS = ["-".join(case) for case in CASES]
ALL_OPERATORS = {"eq", "ne", "contains", "not_contains", "re", "any_of", "all_of", "none_of", "gt", "gte", "lt", "lte", "in", "not_in"}
VIEWS = {
    "correlation": AlarmStrategyModelViewSet,
    "shield": AlertShieldModelViewSet,
    "enrichment": EnrichmentRuleModelViewSet,
    "assignment": AlertAssignmentModelViewSet,
    "action": ActionRuleViewSet,
}


@pytest.fixture(autouse=True)
def level_catalog():
    for context in ["event", "alert"]:
        for code in [1, 2, 3]:
            Level.objects.create(level_id=code, level_type=context, level_name=str(code), level_display_name=str(code))


@pytest.fixture
def api(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    User.objects.create(username=authenticated_user.username, domain="domain.com", group_list=[1])
    monkeypatch.setattr("apps.core.utils.viewset_utils.get_permission_rules", lambda *a, **k: {"instance": [], "team": [1]})
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **k: {"instance": [], "team": [1]})

    def invoke(scope, action, method="get", data=None, pk=None):
        request = getattr(APIRequestFactory(), method)("/rules/", data=data, format="json")
        request.COOKIES["current_team"] = "1"
        force_authenticate(request, user=authenticated_user)
        response = VIEWS[scope].as_view({method: action})(request, **({"pk": pk} if pk else {}))
        response.render()
        body = json.loads(response.content)
        return response.status_code, body.get("data", body)

    return invoke


def example(key, op):
    """每个字段独有哨兵；其他字段不复制被测值，避免取错字段仍然通过。"""
    a, b, c = f"{key}:Alpha", f"{key}:Beta", f"{key}:Gamma"
    if key == "level":
        return ["1", "2", "3", "01", "", " \t\n"], ["1", "2"], {"any_of": {0, 1}, "none_of": {2, 3}}[op]
    if key in {"push_source_ids", "source_names"}:
        return (
            [[a, b, c, a], [a], [b], [a + "-suffix"], [a.lower()], [c], [], [" \t\n"]],
            [a, b, a],
            {
                "any_of": {0, 1, 2},
                "all_of": {0},
                "none_of": {3, 4, 5},
            }[op],
        )
    if op in {"any_of", "none_of"}:
        return [a, b, a + "-suffix", a.lower(), c, "", " \t\n"], [a, b, a], {"any_of": {0, 1}, "none_of": {2, 3, 4}}[op]
    return (
        [a + " beta", a, a.lower() + " BETA", c, "", " \t\n"],
        {
            "eq": a + " beta",
            "ne": a + " beta",
            "contains": a,
            "not_contains": a,
            "re": "^" + a,
        }[op],
        {"eq": {0}, "ne": {1, 2, 3}, "contains": {0, 1, 2}, "not_contains": {3}, "re": {0, 1, 2}}[op],
    )


def make_event(name, index, **fields):
    source = AlertSource.objects.create(name=name, source_id=f"source-{index}", source_type="restful", secret="test")
    defaults = {key: f"unrelated:{key}" for key in CONTRACT["event"] if key != "source_name"}
    defaults.update(level="3", team=[1], status=EventStatus.RECEIVED, external_id=f"external-{index}")
    defaults.update(fields)
    return Event.objects.create(source=source, event_id=f"event-{index}", start_time=timezone.now(), raw_data={}, **defaults)


def records(scope, key, actuals):
    models, payloads = [], []
    for index, actual in enumerate(actuals):
        if SCOPES[scope] == "event":
            row = make_event(actual if key == "source_name" else "unrelated:source", str(index), **({key: actual} if key != "source_name" else {}))
            payload = {field: getattr(row, field) for field in CONTRACT["event"] if field != "source_name"}
            payload.update(source_name=row.source.name, team=[1])
        else:
            fields = {field: f"unrelated:{field}" for field in CONTRACT["alert"] if field not in {"source_names", "push_source_ids"}}
            fields.update(level="3", source_name="wrong-snapshot", push_source_ids=["unrelated:monitor"], team=[1], labels={"ip_addr": "192.0.2.10"})
            if key != "source_names":
                fields[key] = actual
            row = Alert.objects.create(alert_id=f"alert-{index}", fingerprint=f"fp-{index}", **fields)
            if key == "source_names":
                for ordinal, name in enumerate(actual):
                    row.events.add(make_event(name, f"{index}-{ordinal}", action="closed" if ordinal == 2 else "created"))
                # 每条告警都追加候选恢复事件，不能把它们算进正向或反向来源集合。
                for ordinal, name in enumerate([f"{key}:Alpha", f"{key}:Beta"]):
                    row.events.add(make_event(name, f"{index}-recovery-{ordinal}", action="recovery"))
            payload = build_rule_payload(row)
        models.append(row)
        payloads.append(payload)
    return models, payloads


def matched_indexes(scope, rows, payloads, rules):
    if scope == "correlation":
        pks = set(StrategyMatcher.match_events_to_strategy(Event.objects.filter(pk__in=[row.pk for row in rows]), rules).values_list("pk", flat=True))
        result = {i for i, row in enumerate(rows) if row.pk in pks}
        assert {i for i, row in enumerate(rows) if InstantMatcher.match_in_memory(row, rules)} == result
        return result
    if scope in {"shield", "assignment"}:
        model = Event if scope == "shield" else Alert
        matcher = MonitorSourceRuleMatcher({}, source_field="push_source_id" if scope == "shield" else "push_source_ids")
        pks = set(matcher.filter_queryset(model.objects.filter(pk__in=[row.pk for row in rows]), rules))
        return {i for i, row in enumerate(rows) if row.pk in pks}
    match = enrichment_matches if scope == "enrichment" else action_matches
    return {i for i, payload in enumerate(payloads) if match(payload, rules)}


def rule_request(scope, key, rules, username):
    common = {"name": "字段条件交叉测试", "match_rules": rules, "team": [1]}
    extras = {
        "correlation": {"strategy_type": "smart_denoise", "dispatch_team": [1], "params": {"window_size": 10, "group_by": ["resource_name"]}},
        "shield": {"match_type": "filter", "suppression_time": {}},
        "assignment": {"match_type": "filter", "config": {}, "personnel": [username], "notify_channels": [], "notification_scenario": []},
        "enrichment": {
            "provider_type": "cmdb",
            "namespace": "cross",
            "input_binding": {
                "model_id": "location" if key != "location" else "service",
                "inst_name": "resource_id" if key != "resource_id" else "resource_type",
            },
            "output_projection": [{"source": "owner"}],
        },
        "action": {"trigger_events": ["created"], "action_type": "job", "action_config": {"script_id": 1}},
    }
    return {**common, **extras[scope]}


def execute_workflow(scope, rows, payloads, expected, rule_id, monkeypatch):
    """不 mock 匹配器/流程/Provider/Handler，仅替代外部 RPC。"""
    if scope == "correlation":
        AggregationProcessor().process_aggregation()
        assert set(Alert.objects.filter(rule_id=str(rule_id)).values_list("events__pk", flat=True)) == {rows[i].pk for i in expected}
        periodic = AlarmStrategy.objects.get(pk=rule_id)
        instant = AlarmStrategy.objects.create(
            name="即时字段条件交叉测试", strategy_type="instant", match_rules=periodic.match_rules, team=[1], dispatch_team=[1]
        )
        InstantStrategyCache.cache_clear()
        try:
            InstantAlertDispatcher.dispatch([rows])
            assert set(Alert.objects.filter(rule_id=str(instant.pk)).values_list("events__pk", flat=True)) == {rows[i].pk for i in expected}
            assert Alert.objects.filter(rule_id=str(instant.pk)).count() == len(expected)
        finally:
            InstantStrategyCache.cache_clear()
    elif scope == "shield":
        result = EventShieldOperator([row.event_id for row in rows]).execute_shield_check()
        assert {item["event_id"] for item in result["shield_results"] if item["success"]} == {rows[i].pk for i in expected}
        assert result["shielded_events"] == len(expected)
    elif scope == "assignment":
        result = AlertAssignmentOperator([row.alert_id for row in rows]).execute_auto_assignment()
        assert {item["alert_id"] for item in result["assignment_results"] if item["success"]} == {rows[i].alert_id for i in expected}
        assert result["assigned_alerts"] == len(expected)
        assert result["failed_alerts"] == 0
    elif scope == "enrichment":
        monkeypatch.setattr(
            "apps.rpc.cmdb.CMDB.search_instances_batch", lambda self, params, **kw: {name: {"owner": "cross-owner"} for name in params["inst_names"]}
        )
        cache = LocMemCache(f"cross-{uuid4().hex}", {})
        try:
            result = EnrichmentEngine(cache_backend=cache).enrich_batch(payloads)
        finally:
            cache.clear()
        assert {i for i, item in enumerate(result.events) if item.get("enrichment") == {"cross": {"owner": "cross-owner"}}} == expected
        assert result.summary.enriched == len(expected)
        assert result.summary.failed == 0
    elif scope == "action":
        monkeypatch.setattr("apps.rpc.job_mgmt.JobMgmt.get_script", lambda *a, **kw: {"script_type": "shell", "content": "true", "params": []})
        monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt.node_list", lambda *a, **kw: {"nodes": [{"id": "test-node", "ip": "192.0.2.10"}]})
        monkeypatch.setattr("apps.rpc.job_mgmt.JobMgmt.job_script_execute", lambda *a, **kw: {"result": True, "data": {"task_id": 123}})
        for row in rows:
            ActionEngine().evaluate(row, "created")
        executions = list(ActionExecution.objects.filter(rule_id=rule_id))
        assert {item.alert_id for item in executions} == {rows[i].pk for i in expected}
        assert all(item.status == "running" for item in executions)


@pytest.mark.parametrize("scope,key,op", CASES, ids=CASE_IDS)
def test_every_combination_roundtrips_and_drives_its_real_entry(api, authenticated_user, monkeypatch, scope, key, op):
    actuals, wanted, expected = example(key, op)
    rows, payloads = records(scope, key, actuals)
    condition = {"key": key, "operator": op, "value": wanted}
    rules = [[condition]]
    status, created = api(scope, "create", "post", rule_request(scope, key, rules, authenticated_user.username))
    assert status == 201, created
    status, saved = api(scope, "retrieve", pk=created["id"])
    assert status == 200 and saved["match_rules"] == rules, saved
    assert matched_indexes(scope, rows, payloads, saved["match_rules"]) == expected
    execute_workflow(scope, rows, payloads, expected, created["id"], monkeypatch)

    if key == "level":
        updated_value, updated_expected = ["3"], ({2} if op == "any_of" else {0, 1, 3})
    elif key in {"push_source_ids", "source_names"}:
        updated_value = [f"{key}:Beta"]
        updated_expected = {1, 3, 4, 5} if op == "none_of" else {0, 2}
    elif isinstance(wanted, list):
        updated_value, updated_expected = [f"{key}:Gamma"], ({4} if op == "any_of" else {0, 1, 2, 3})
    else:
        updated_value = ("^" if op == "re" else "") + f"{key}:Gamma"
        updated_expected = {0, 1, 2} if op in {"ne", "not_contains"} else {3}
    rules = [[{**condition, "value": updated_value}]]
    status, changed = api(scope, "partial_update", "patch", {"match_rules": rules}, created["id"])
    assert status == 200 and changed["match_rules"] == rules, changed
    status, saved = api(scope, "retrieve", pk=created["id"])
    assert status == 200 and saved["match_rules"] == rules, saved
    assert matched_indexes(scope, rows, payloads, saved["match_rules"]) == updated_expected

    # 每个合法组合都覆盖非法修改及保存后不变，不能接受类型强转。
    invalid = deepcopy(condition)
    invalid["value"] = "not-an-array" if isinstance(wanted, list) else [wanted]
    status, error = api(scope, "partial_update", "patch", {"match_rules": [[invalid]]}, created["id"])
    assert status == 400, error
    status, saved = api(scope, "retrieve", pk=created["id"])
    assert status == 200 and saved["match_rules"] == rules


@pytest.mark.parametrize("scope", SCOPES)
def test_independent_contract_has_exactly_the_fields_and_operators_offered(scope):
    actual = {key: field["operators"] for key, field in FIELDS.items() if SCOPES[scope] in field["contexts"]}
    assert actual == CONTRACT[SCOPES[scope]]


def validate_submission(scope, rules):
    serializer = SERIALIZERS[scope](
        data={
            "name": "cross-validation",
            "strategy_type": "smart_denoise",
            "match_rules": rules,
            "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
        },
        partial=True,
    )
    return serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("scope,key,op", CASES, ids=CASE_IDS)
def test_every_combination_rejects_bad_values_without_widening_an_or_rule(scope, key, op):
    actuals, wanted, expected = example(key, op)
    rows, payloads = records(scope, key, actuals)
    valid = {"key": key, "operator": op, "value": wanted}
    accepted, errors = validate_submission(scope, [[valid]])
    assert accepted, errors
    assert matched_indexes(scope, rows, payloads, [[valid]]) == expected
    invalid_values = [None, True, 1, {}, [], "", " \t\n"]
    if isinstance(wanted, list):
        invalid_values += ["Alpha", [None], [1], [True], [{}], [["Alpha"]], [""], [" \t\n"], ["x" * 257], ["x"] * 51]
    else:
        invalid_values += [[wanted], "x" * 257]
        if op == "re":
            invalid_values += ["["]
    for value in invalid_values:
        bad = {**valid, "value": value}
        # 即使另一个 OR 分支有效并能命中，非法条件也必须使整条规则失败。
        rules = [[valid], [bad]]
        accepted, errors = validate_submission(scope, rules)
        assert not accepted and "match_rules" in errors, (scope, key, op, value, errors)
        assert matched_indexes(scope, rows, payloads, rules) == set(), (scope, key, op, value)


FIELD_CASES = [(scope, key) for scope, context in SCOPES.items() for key in CONTRACT[context]]


@pytest.mark.parametrize("scope,key", FIELD_CASES, ids=["-".join(case) for case in FIELD_CASES])
def test_every_field_rejects_every_unsupported_operator(scope, key):
    legal_op = CONTRACT[SCOPES[scope]][key][0]
    actuals, wanted, expected = example(key, legal_op)
    rows, payloads = records(scope, key, actuals)
    valid = {"key": key, "operator": legal_op, "value": wanted}
    accepted, errors = validate_submission(scope, [[valid]])
    assert accepted, errors
    assert matched_indexes(scope, rows, payloads, [[valid]]) == expected
    for op in sorted(ALL_OPERATORS - set(CONTRACT[SCOPES[scope]][key])):
        bad = {"key": key, "operator": op, "value": ["x"] if op in {"any_of", "all_of", "none_of", "in", "not_in"} else "x"}
        accepted, errors = validate_submission(scope, [[valid], [bad]])
        assert not accepted and "match_rules" in errors, (scope, key, op, errors)
        assert matched_indexes(scope, rows, payloads, [[valid], [bad]]) == set(), (scope, key, op)


@pytest.mark.parametrize("scope,key,op", CASES, ids=CASE_IDS)
def test_every_combination_obeys_and_or_with_independent_fields(scope, key, op):
    actuals, wanted, expected = example(key, op)
    rows, payloads = records(scope, key, actuals)
    condition = {"key": key, "operator": op, "value": wanted}
    gate = "title" if key != "title" else "resource_id"
    # 只放行一个已知命中和一个空值反例：可辨别 AND 错写成 OR、空值错误否定。
    first = min(expected)
    for index, row in enumerate(rows):
        setattr(row, gate, "gate-open" if index in {first, len(rows) - 1} else "gate-closed")
        row.save(update_fields=[gate])
        payloads[index][gate] = getattr(row, gate)
    gate_condition = {"key": gate, "operator": "eq" if gate == "title" else "any_of", "value": "gate-open" if gate == "title" else ["gate-open"]}
    assert matched_indexes(scope, rows, payloads, [[condition, gate_condition]]) == {first}
    assert matched_indexes(scope, rows, payloads, [[condition], [gate_condition]]) == expected | {len(rows) - 1}
    assert matched_indexes(scope, rows, payloads, [[gate_condition, condition]]) == {first}


PUNCTUATION_CASES = [case for case in CASES if case[1] != "level"]


@pytest.mark.parametrize("scope,key,op", PUNCTUATION_CASES, ids=["-".join(case) for case in PUNCTUATION_CASES])
def test_every_string_or_set_combination_handles_single_values_and_literal_punctuation(scope, key, op):
    value = f"{key}:源,100%_*\\cpu"
    if key in {"push_source_ids", "source_names"}:
        actuals = [[value, "extra"], ["prefix" + value], ["other"], [], [" \t\n"]]
        wanted = [value]
        expected = {"any_of": {0}, "all_of": {0}, "none_of": {1, 2}}[op]
    else:
        actuals = [value, "prefix" + value + "suffix", "other", "", " \t\n"]
        wanted = [value] if op in {"any_of", "none_of"} else value
        if op == "re":
            # 预先写出的转义模式，不调用生产代码计算期望。
            wanted = f"{key}:源,100%_\\*\\\\cpu"
        expected = {"eq": {0}, "ne": {1, 2}, "any_of": {0}, "none_of": {1, 2}, "contains": {0, 1}, "not_contains": {2}, "re": {0, 1}}[op]
    rows, payloads = records(scope, key, actuals)
    assert matched_indexes(scope, rows, payloads, [[{"key": key, "operator": op, "value": wanted}]]) == expected


@pytest.mark.parametrize("scope,key,op", CASES, ids=CASE_IDS)
def test_every_combination_excludes_null_and_missing_actual_values(scope, key, op):
    actuals, wanted, _ = example(key, op)
    rules = [[{"key": key, "operator": op, "value": wanted}]]
    model = Event if SCOPES[scope] == "event" else Alert
    if key not in {"source_name", "source_names"} and model._meta.get_field(key).null:
        rows, payloads = records(scope, key, [None])
        assert matched_indexes(scope, rows, payloads, rules) == set()
    else:
        rows, payloads = records(scope, key, [actuals[-1]])
        assert matched_indexes(scope, rows, payloads, rules) == set()
    for value in [None, "", " \t\n", [], {}, 1, True]:
        payloads[0][key] = value
        matcher = enrichment_matches if SCOPES[scope] == "event" else action_matches
        assert matcher(payloads[0], rules) is False, (scope, key, op, value)
    del payloads[0][key]
    assert matcher(payloads[0], rules) is False


def test_builtin_enrichment_provider_is_available_in_a_fresh_worker_process():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); "
            "from apps.alerts.enrichment.providers.base import get_provider; "
            "assert get_provider('cmdb').provider_type == 'cmdb'",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("scope,key,op", CASES, ids=CASE_IDS)
def test_every_combination_accepts_its_exact_size_boundary(scope, key, op):
    if op in {"any_of", "all_of", "none_of"}:
        values = [["1"], ["1"] * 50]
        if key != "level":
            values.append(["x" * 256])
    else:
        values = ["x", "x" * 256]
    for value in values:
        accepted, errors = validate_submission(scope, [[{"key": key, "operator": op, "value": value}]])
        assert accepted, (scope, key, op, errors)


@pytest.mark.parametrize("scope", SCOPES)
def test_each_entry_rejects_foreign_context_and_retired_fields(scope):
    own = CONTRACT[SCOPES[scope]]
    other = CONTRACT["alert" if SCOPES[scope] == "event" else "event"]
    forbidden = (set(other) - set(own)) | {"source_id", "source_pk", "level_id", "monitor_objects", "source.name", "unknown_field"}
    rows, payloads = records(scope, "title", ["control"])
    valid = {"key": "title", "operator": "eq", "value": "control"}
    assert matched_indexes(scope, rows, payloads, [[valid]]) == {0}
    for key in sorted(forbidden):
        rules = [[valid], [{"key": key, "operator": "any_of", "value": ["control"]}]]
        accepted, errors = validate_submission(scope, rules)
        assert not accepted and "match_rules" in errors, (scope, key, errors)
        assert matched_indexes(scope, rows, payloads, rules) == set()
