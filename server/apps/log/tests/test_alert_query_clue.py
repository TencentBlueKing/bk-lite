from types import SimpleNamespace

from apps.log.services.alert_query_clue import freeze_log_alert_query_clue


def test_freeze_log_alert_query_clue_copies_hit_time_fields():
    condition = {"query": "error", "rule": {"mode": "and", "conditions": [{"field": "level", "op": "=", "value": "error"}]}}
    period = {"type": "min", "value": 5}
    collect_type = SimpleNamespace(name="host")
    policy = SimpleNamespace(
        id=42,
        name="keyword-host",
        collect_type=collect_type,
        collect_type_id=7,
        log_groups=["g-a", "g-b"],
        alert_type="keyword",
        alert_name="${host} error",
        alert_level="warning",
        alert_condition=condition,
        period=period,
        schedule={"type": "min", "value": 1},
        show_fields=["_msg", "host"],
    )

    clue = freeze_log_alert_query_clue(policy, window_start=100, window_end=400)

    assert clue == {
        "policy_id": 42,
        "policy_name": "keyword-host",
        "collect_type_id": 7,
        "collect_type_name": "host",
        "log_groups": ["g-a", "g-b"],
        "alert_type": "keyword",
        "alert_name": "${host} error",
        "alert_level": "warning",
        "alert_condition": {
            "query": "error",
            "rule": {"mode": "and", "conditions": [{"field": "level", "op": "=", "value": "error"}]},
        },
        "period": {"type": "min", "value": 5},
        "schedule": {"type": "min", "value": 1},
        "show_fields": ["_msg", "host"],
        "window_start": 100,
        "window_end": 400,
    }
    clue["alert_condition"]["query"] = "mutated"
    clue["log_groups"].append("g-c")
    assert condition["query"] == "error"
    assert policy.log_groups == ["g-a", "g-b"]


def test_freeze_log_alert_query_clue_defaults_missing_collect_type():
    policy = SimpleNamespace(
        id=1,
        name="p",
        collect_type=None,
        collect_type_id=None,
        log_groups=None,
        alert_type="aggregate",
        alert_name="agg",
        alert_level="error",
        alert_condition=None,
        period=None,
        schedule=None,
        show_fields=None,
    )

    clue = freeze_log_alert_query_clue(policy)

    assert clue["collect_type_name"] is None
    assert clue["log_groups"] == []
    assert clue["alert_condition"] == {}
    assert clue["period"] == {}
    assert clue["schedule"] == {}
    assert clue["show_fields"] == []
    assert clue["window_start"] is None
    assert clue["window_end"] is None
