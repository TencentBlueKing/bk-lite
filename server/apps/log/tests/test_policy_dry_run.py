"""日志策略试算：授权、零副作用、缺对照与失败日志。"""

import json
import logging
from datetime import datetime, timezone

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.models.policy import Alert, AlertSnapshot, Event, EventRawData, Policy, PolicyOrganization
from apps.log.services.policy_dry_run import DRY_RUN_FAIL_TEMPLATE
from apps.log.views.policy import PolicyViewSet

FIXED_NOW = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
SENTINEL_QUERY = "SENTINEL_DRY_RUN_QUERY level:error AND service:=order"


def _allow_policy_operations(mocker, policy_id=None):
    instance_permissions = []
    if policy_id is not None:
        instance_permissions.append({"id": str(policy_id), "permission": ["View", "Operate"]})
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": {"None": {"instance": instance_permissions}}, "team": [1]},
    )


def _timing():
    return {"type": "min", "value": 5}


def _aggregate_payload(name, organizations, **overrides):
    payload = {
        "name": name,
        "alert_type": "aggregate",
        "alert_name": "${service} ${count_rate} ${count_delta}",
        "alert_level": "warning",
        "schedule": _timing(),
        "period": _timing(),
        "organizations": organizations,
        "alert_condition": {
            "query": "level:error",
            "group_by": ["service"],
            "rule": {
                "mode": "and",
                "conditions": [
                    {"func": "count_rate", "field": "_msg", "op": ">", "value": 0.5},
                    {"func": "count_delta", "field": "_msg", "op": ">", "value": 100},
                ],
            },
        },
    }
    payload.update(overrides)
    return payload


def _create_policy(name, organization, **overrides):
    data = {
        "name": name,
        "alert_type": "aggregate",
        "alert_name": name,
        "alert_level": "warning",
        "alert_condition": {"query": "level:error", "group_by": ["service"], "rule": {"mode": "and", "conditions": []}},
        "schedule": _timing(),
        "period": _timing(),
        "last_run_time": FIXED_NOW,
    }
    data.update(overrides)
    policy = Policy.objects.create(**data)
    PolicyOrganization.objects.create(policy=policy, organization=organization)
    return policy


def _post_dry_run(data, user):
    request = APIRequestFactory().post("/api/v1/log/policy/dry_run/", data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return PolicyViewSet.as_view({"post": "dry_run"})(request)


def _body(response):
    return json.loads(response.content.decode("utf-8"))


def _row_counts():
    return {
        "policy": Policy.objects.count(),
        "organization": PolicyOrganization.objects.count(),
        "alert": Alert.objects.count(),
        "event": Event.objects.count(),
        "raw": EventRawData.objects.count(),
        "snapshot": AlertSnapshot.objects.count(),
    }


def _window_bounds():
    window_end = int(FIXED_NOW.timestamp())
    window_start = window_end - 300
    return window_start, window_end, window_start - 300


@pytest.mark.django_db
def test_foreign_organization_is_forbidden(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    before = _row_counts()

    response = _post_dry_run(_aggregate_payload("foreign-org", [2]), authenticated_user)

    assert response.status_code == 403
    assert _body(response)["result"] is False
    assert _row_counts() == before


@pytest.mark.django_db
def test_foreign_log_group_is_rejected(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    LogGroup.objects.create(id="lg-foreign", name="foreign", rule={})
    LogGroupOrganization.objects.create(log_group_id="lg-foreign", organization=2)
    before = _row_counts()

    payload = _aggregate_payload("foreign-group", [1], log_groups=["lg-foreign"])
    response = _post_dry_run(payload, authenticated_user)

    assert response.status_code == 400
    body = _body(response)
    assert body["result"] is False
    assert "lg-foreign" in body["message"]
    assert "试算失败" not in body["message"]
    assert _row_counts() == before


@pytest.mark.django_db
def test_foreign_policy_id_is_forbidden(authenticated_user, mocker):
    foreign = _create_policy("foreign-policy", 2)
    _allow_policy_operations(mocker)
    before = _row_counts()

    payload = _aggregate_payload("foreign-policy", [1], id=foreign.id)
    response = _post_dry_run(payload, authenticated_user)

    assert response.status_code == 403
    assert _row_counts() == before
    foreign.refresh_from_db()
    assert foreign.last_run_time == FIXED_NOW


@pytest.mark.django_db
def test_same_name_dry_run_skips_uniqueness(authenticated_user, mocker):
    existing = _create_policy("taken-name", 1)
    _allow_policy_operations(mocker, existing.id)
    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", return_value=[])

    with_id = _post_dry_run(_aggregate_payload("taken-name", [1], id=existing.id), authenticated_user)
    without_id = _post_dry_run(_aggregate_payload("taken-name", [1]), authenticated_user)

    assert with_id.status_code == 200
    assert _body(with_id)["result"] is True
    assert without_id.status_code == 200
    assert _body(without_id)["result"] is True
    assert Policy.objects.filter(name="taken-name").count() == 1


@pytest.mark.django_db
def test_dry_run_returns_group_verdicts_without_side_effects(authenticated_user, mocker):
    policy = _create_policy("rate-policy", 1)
    _allow_policy_operations(mocker, policy.id)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    notice = mocker.patch("apps.log.tasks.services.policy_scan.SystemMgmtUtils.send_msg_with_channel")
    lifecycle = mocker.patch("apps.log.services.alert_lifecycle_notify.LogAlertLifecycleNotifier.notify_created")
    window_start, window_end, prev_start = _window_bounds()
    queries = []

    def fake_query(self, query, start, end, limit=10):
        queries.append((query, start, end, limit))
        if start == prev_start:
            return [
                {"service": "order", "count__msg": "50"},
                {"service": "pay", "count__msg": "90"},
            ]
        if "stats" in query:
            return [
                {"service": "order", "count__msg": "180"},
                {"service": "pay", "count__msg": "100"},
            ]
        return [{"_time": "2026-10-27T07:55:00Z", "_msg": "order exploded"}]

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    before = _row_counts()

    response = _post_dry_run(_aggregate_payload("rate-policy", [1], id=policy.id), authenticated_user)

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["alert_type"] == "aggregate"
    assert data["window"] == {"start": window_start, "end": window_end}
    assert data["previous_window"] == {"start": prev_start, "end": window_start}
    assert data["baseline_status"] == "ok"
    assert data["truncated"] is False
    order, pay = data["items"]
    assert order["group"] == {"service": "order"}
    assert order["count"] == 180
    assert order["previous_count"] == 50
    assert order["count_rate"] == pytest.approx(0.6)
    assert order["count_delta"] == 130
    assert order["verdict"] == "would_trigger"
    assert order["reason"] == ""
    assert pay["group"] == {"service": "pay"}
    assert pay["count"] == 100
    assert pay["previous_count"] == 90
    assert pay["count_rate"] == pytest.approx(100 / 300)
    assert pay["count_delta"] == 10
    assert pay["verdict"] == "no_trigger"
    assert data["sample_preview"] == [{"_time": "2026-10-27T07:55:00Z", "_msg": "order exploded"}]
    aggregate_queries = [query for query, start, _, _ in queries if start == window_start and "stats" in query]
    assert len(aggregate_queries) == 1
    assert aggregate_queries[0].count("count() as count__msg") == 1
    sample_queries = [query for query, start, _, _ in queries if start == window_start and "stats" not in query]
    assert sample_queries and 'service:="order"' in sample_queries[0]
    assert any(start == prev_start for _, start, _, _ in queries)
    assert _row_counts() == before
    policy.refresh_from_db()
    assert policy.last_run_time == FIXED_NOW
    notice.assert_not_called()
    lifecycle.assert_not_called()


@pytest.mark.django_db
def test_dry_run_truncates_items_and_skips_previous_window_without_delta(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    window_start, window_end, prev_start = _window_bounds()
    starts = []

    def fake_query(self, query, start, end, limit=10):
        starts.append(start)
        if "stats" in query:
            return [{"service": f"s{index}", "count__msg": "1"} for index in range(201)]
        return [{"_msg": "sample"}]

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    payload = _aggregate_payload(
        "many-groups",
        [1],
        alert_condition={
            "query": "level:error",
            "group_by": ["service"],
            "rule": {"mode": "and", "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 0}]},
        },
    )

    response = _post_dry_run(payload, authenticated_user)

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["baseline_status"] == "not_required"
    assert data["truncated"] is True
    assert len(data["items"]) == 200
    assert data["items"][0]["verdict"] == "would_trigger"
    assert data["previous_window"] == {"start": prev_start, "end": window_start}
    assert prev_start not in starts
    assert window_end == window_start + 300


@pytest.mark.django_db
def test_previous_window_failure_is_missing_baseline(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    _, _, prev_start = _window_bounds()

    def fake_query(self, query, start, end, limit=10):
        if start == prev_start:
            raise RuntimeError("baseline down")
        if "stats" in query:
            return [{"service": "order", "count__msg": "180"}]
        return [{"_msg": "still sampled"}]

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    response = _post_dry_run(_aggregate_payload("missing-baseline", [1]), authenticated_user)

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["baseline_status"] == "unavailable"
    assert data["items"][0]["verdict"] == "missing_baseline"
    assert data["items"][0]["count_delta"] is None
    assert data["items"][0]["previous_count"] is None
    assert data["items"][0]["count"] == 180
    assert data["sample_preview"] == [{"_msg": "still sampled"}]


@pytest.mark.django_db
def test_sample_failure_keeps_verdict(authenticated_user, mocker, caplog):
    _allow_policy_operations(mocker)
    secret = SENTINEL_QUERY

    def fake_query(self, query, start, end, limit=10):
        if "stats" in query:
            return [{"service": "order", "count__msg": "3"}]
        raise RuntimeError(secret)

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    payload = _aggregate_payload(
        "sample-fails",
        [1],
        alert_condition={
            "query": "level:error",
            "group_by": ["service"],
            "rule": {"mode": "and", "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 0}]},
        },
    )

    with caplog.at_level(logging.WARNING, logger="log"):
        response = _post_dry_run(payload, authenticated_user)

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["items"][0]["verdict"] == "would_trigger"
    assert data["sample_preview"] == []
    warnings = [record for record in caplog.records if record.name == "log" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].msg == "event=log_policy_dry_run_sample_failed policy_id=%s failed_stage=%s error_type=%s"
    assert warnings[0].args[1:] == ("sample", "RuntimeError")
    assert secret not in warnings[0].getMessage()


@pytest.mark.django_db
def test_unexpected_failure_logs_once_without_query(authenticated_user, mocker, caplog):
    policy = _create_policy("boom-policy", 1)
    _allow_policy_operations(mocker, policy.id)
    secret = SENTINEL_QUERY

    def explode(*args, **kwargs):
        raise RuntimeError(secret)

    mocker.patch("apps.log.tasks.services.policy_scan.LogPolicyScan.evaluate_aggregate", side_effect=explode)

    with caplog.at_level(logging.ERROR, logger="log"):
        response = _post_dry_run(_aggregate_payload("boom-policy", [1], id=policy.id), authenticated_user)

    assert response.status_code == 400
    assert _body(response)["message"] == "试算失败"
    errors = [record for record in caplog.records if record.name == "log" and record.levelno == logging.ERROR]
    assert len(errors) == 1
    record = errors[0]
    assert record.msg == DRY_RUN_FAIL_TEMPLATE
    assert record.args == (str(policy.id), "evaluate", "RuntimeError")
    assert record.exc_info is not None
    formatted = logging.Formatter().format(record)
    assert secret not in formatted
    assert formatted.count("Traceback") == 1
    policy.refresh_from_db()
    assert policy.last_run_time == FIXED_NOW


@pytest.mark.django_db
def test_dry_run_returns_conditions_and_baselines(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    window_start, window_end, prev_start = _window_bounds()
    offset_start = window_start - 86400
    starts = []

    def fake_query(self, query, start, end, limit=10):
        starts.append(start)
        if start == offset_start:
            return [{"service": "order", "count__msg": "120"}]
        if start == prev_start:
            return [{"service": "order", "count_uniq_client_ip": "40", "count__msg": "10"}]
        if "stats" in query:
            return [{"service": "order", "count__msg": "180", "count_uniq_client_ip": "63"}]
        return [{"_msg": "sample"}]

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    payload = _aggregate_payload(
        "catalog-dry-run",
        [1],
        alert_condition={
            "query": "level:error",
            "group_by": ["service"],
            "rule": {
                "mode": "and",
                "conditions": [
                    {
                        "func": "count",
                        "field": "_msg",
                        "op": ">",
                        "value": "49",
                        "compare": {"kind": "percent", "to": "offset_24h"},
                    },
                    {
                        "func": "count_uniq",
                        "field": "client_ip",
                        "op": ">",
                        "value": "10",
                        "compare": {"kind": "delta", "to": "previous_window"},
                    },
                ],
            },
        },
    )

    response = _post_dry_run(payload, authenticated_user)

    assert response.status_code == 200
    data = _body(response)["data"]
    assert data["baseline_status"] == "ok"
    assert set(data["baselines"]) == {"offset_hours:24", "previous_window"}
    assert data["baselines"]["offset_hours:24"]["status"] == "ok"
    assert data["baselines"]["offset_hours:24"]["window"] == {"start": offset_start, "end": window_end - 86400}
    assert data["baselines"]["previous_window"]["window"]["start"] == prev_start
    assert starts.count(offset_start) == 1
    assert starts.count(prev_start) == 1
    item = data["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["conditions"][0]["value"] == pytest.approx(50.0)
    assert item["conditions"][0]["matched"] is True
    assert item["conditions"][1]["value"] == 23
    assert item["conditions"][1]["matched"] is True
    assert item["count"] == 180
    assert item["no_data"] is False


@pytest.mark.django_db
def test_dry_run_ratio_denominator_zero_and_hit_ratio(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)

    def fake_query(self, query, start, end, limit=10):
        if "stats" in query:
            return [{"count__msg": "180", "ratio_0_hit": "13"}]
        return []

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    payload = _aggregate_payload(
        "ratio-hit",
        [1],
        alert_condition={
            "query": "*",
            "group_by": [],
            "rule": {
                "mode": "and",
                "conditions": [
                    {
                        "func": "ratio",
                        "field": "_msg",
                        "op": ">",
                        "value": "5",
                        "params": {"filter": "status:500"},
                    }
                ],
            },
        },
    )
    response = _post_dry_run(payload, authenticated_user)
    assert response.status_code == 200
    item = _body(response)["data"]["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["no_data"] is False
    assert item["conditions"][0]["matched"] is True
    assert item["conditions"][0]["value"] == pytest.approx(13 / 180 * 100)
    assert item["reason"] == ""

    def zero_query(self, query, start, end, limit=10):
        if "stats" in query:
            return [{"count__msg": "0", "ratio_0_hit": "0"}]
        return []

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", zero_query)
    zero_payload = _aggregate_payload(
        "ratio-zero",
        [1],
        alert_condition=payload["alert_condition"],
    )
    zero = _post_dry_run(zero_payload, authenticated_user)
    assert zero.status_code == 200
    zero_item = _body(zero)["data"]["items"][0]
    assert zero_item["verdict"] == "no_trigger"
    assert zero_item["no_data"] is False
    assert zero_item["reason"] == "denominator_zero"
    assert zero_item["conditions"][0]["reason"] == "denominator_zero"
    assert zero_item["conditions"][0]["matched"] is False


@pytest.mark.django_db
def test_dry_run_ignores_stored_no_data_and_uses_count_below_one(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    window_start, _, prev_start = _window_bounds()

    def fake_query(self, query, start, end, limit=10):
        if start == prev_start:
            return [{"count__msg": "4"}]
        if start == window_start and "stats" in query:
            return [{"count__msg": "0"}]
        return []

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    silent = _aggregate_payload(
        "no-data-dry-run",
        [1],
        alert_condition={
            "query": "*",
            "group_by": [],
            "no_data": {"enabled": True, "level": "warning"},
            "rule": {
                "mode": "and",
                "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": "1"}],
            },
        },
    )
    silent_response = _post_dry_run(silent, authenticated_user)
    assert silent_response.status_code == 200
    silent_items = _body(silent_response)["data"]["items"]
    assert silent_items
    assert all(item["verdict"] != "would_trigger_no_data" for item in silent_items)
    assert all(item["no_data"] is False for item in silent_items)
    assert silent_items[0]["verdict"] == "no_trigger"

    below = _aggregate_payload(
        "count-below-one",
        [1],
        alert_condition={
            "query": "*",
            "group_by": [],
            "no_data": {"enabled": True, "level": "error"},
            "rule": {
                "mode": "and",
                "conditions": [{"func": "count", "field": "_msg", "op": "<", "value": "1"}],
            },
        },
    )
    below_response = _post_dry_run(below, authenticated_user)
    assert below_response.status_code == 200
    item = _body(below_response)["data"]["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["no_data"] is False
    assert item["count"] == 0


@pytest.mark.django_db
def test_dry_run_reports_streak_without_extra_side_effects(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    window_start, _window_end, prev_start = _window_bounds()
    oldest = window_start - 600
    before = _row_counts()

    def post(name, rows_for_start, trigger_count=3, compare=None):
        calls = []

        def fake_query(self, query, start, end, limit=10):
            calls.append(query)
            if "stats" not in query:
                return [{"_msg": "sample"}]
            count = rows_for_start(start)
            if isinstance(count, Exception):
                raise count
            return [{"service": "order", "count__msg": str(count)}]

        mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
        condition = {"func": "count", "field": "_msg", "op": ">", "value": "1"}
        if compare is not None:
            condition["compare"] = compare
            condition["value"] = "-1"
        payload = _aggregate_payload(
            name,
            [1],
            alert_condition={
                "query": "level:error",
                "group_by": ["service"],
                "rule": {"mode": "and", "trigger_count": trigger_count, "conditions": [condition]},
            },
        )
        response = _post_dry_run(payload, authenticated_user)
        assert response.status_code == 200
        return _body(response)["data"], calls

    short, short_calls = post("streak-two", lambda start: 1 if start == oldest else 10)
    assert short["items"][0]["streak"] == 2
    assert short["items"][0]["verdict"] == "no_trigger"
    assert short["items"][0]["reason"] == ""
    assert len([query for query in short_calls if "stats" in query]) == 3

    full, full_calls = post(
        "streak-baseline",
        lambda start: 10,
        compare={"kind": "percent", "to": "previous_window"},
    )
    assert full["items"][0]["streak"] == 3
    assert full["items"][0]["verdict"] == "would_trigger"
    stats_calls = [query for query in full_calls if "stats" in query]
    assert len(stats_calls) == 3 * (1 + 1)
    assert len(full_calls) == len(stats_calls) + 1

    sentinel = RuntimeError("SENTINEL_DRY_RUN_STREAK_QUERY")

    def failing(start):
        if start == oldest:
            return sentinel
        return 10

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture(level=logging.WARNING)
    logger = logging.getLogger("celery")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        failed, _failed_calls = post("streak-failed", failing)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert failed["items"][0]["streak"] == 0
    assert failed["items"][0]["verdict"] == "no_trigger"
    assert failed["items"][0]["reason"] == "window_failed"
    template = "event=log_policy_streak_failed policy_id=%s failed_stage=%s window_index=%s error_type=%s"
    matched = [record for record in records if record.msg == template]
    assert len(matched) == 1
    assert matched[0].args[1:] == ("streak", 2, "RuntimeError")
    assert "SENTINEL_DRY_RUN_STREAK_QUERY" not in matched[0].getMessage()
    assert _row_counts() == before

    untouched, untouched_calls = post("streak-default", lambda start: 10, trigger_count=1)
    assert "streak" not in untouched["items"][0]
    assert untouched["items"][0]["verdict"] == "would_trigger"
    assert len([query for query in untouched_calls if "stats" in query]) == 1


@pytest.mark.django_db
def test_dry_run_no_data_ignores_trigger_count(authenticated_user, mocker):
    _allow_policy_operations(mocker)
    mocker.patch("apps.log.services.policy_dry_run._safe_now", return_value=FIXED_NOW)
    window_start, _window_end, prev_start = _window_bounds()

    def fake_query(self, query, start, end, limit=10):
        if start == prev_start:
            return [{"count__msg": "4"}]
        if start == window_start and "stats" in query:
            return []
        return [{"count__msg": "1"}]

    mocker.patch("apps.log.tasks.services.policy_scan.VictoriaMetricsAPI.query", fake_query)
    payload = _aggregate_payload(
        "no-data-streak",
        [1],
        alert_condition={
            "query": "*",
            "group_by": [],
            "no_data": {"enabled": True, "level": "warning"},
            "rule": {
                "mode": "and",
                "trigger_count": 3,
                "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": "1"}],
            },
        },
    )
    response = _post_dry_run(payload, authenticated_user)
    assert response.status_code == 200
    items = _body(response)["data"]["items"]
    assert all(item["verdict"] != "would_trigger_no_data" for item in items)
    assert all(item.get("no_data") is not True for item in items)


def test_aggregate_dry_run_item_includes_level():
    from apps.log.services.policy_dry_run import LogPolicyDryRunService

    item = LogPolicyDryRunService._aggregate_item(
        {
            "triggered": True,
            "group_values": {"service": "order"},
            "aggregate_data": {
                "count": 60,
                "level": "error",
                "conditions": [{"func": "count", "level": "error", "matched": True}],
            },
        }
    )
    assert item["level"] == "error"
    assert item["verdict"] == "would_trigger"
    assert item["conditions"][0]["level"] == "error"
