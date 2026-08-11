import pytest

from apps.log.serializers.log_group import LogGroupSerializer


pytestmark = pytest.mark.unit


def _payload(rule):
    return {
        "id": "rule-validation",
        "name": "rule validation",
        "organizations": [1],
        "rule": rule,
    }


@pytest.mark.parametrize("mode", ["ADN", "", None, 1])
def test_serializer_rejects_unknown_rule_mode(mode):
    serializer = LogGroupSerializer(data=_payload({"mode": mode, "conditions": []}))

    assert serializer.is_valid() is False
    assert "AND or OR" in str(serializer.errors["rule"])


def test_serializer_rejects_non_object_rule():
    serializer = LogGroupSerializer(data=_payload([]))

    assert serializer.is_valid() is False
    assert "object" in str(serializer.errors["rule"])


@pytest.mark.parametrize(
    "conditions",
    [
        "not-a-list",
        [1],
        [{"field": "cluster"}],
        [{"field": "", "op": "==", "value": "prod"}],
        [{"field": "cluster", "op": "xor", "value": "prod"}],
        [{"field": "cluster", "op": [], "value": "prod"}],
        [{"field": "cluster", "op": "==", "value": None}],
        [{"field": "cluster", "op": "==", "value": ["prod"]}],
        [{"field": 'cluster") OR (*)', "op": "==", "value": "prod"}],
        [{"field": "cluster", "op": "==", "value": 'prod") OR (*)'}],
    ],
)
def test_serializer_rejects_malformed_rule_conditions(conditions):
    serializer = LogGroupSerializer(data=_payload({"mode": "AND", "conditions": conditions}))

    assert serializer.is_valid() is False
    assert serializer.errors["rule"]


@pytest.mark.parametrize(
    "value",
    [
        "prod* OR (*)",
        "prod*) OR (*) OR (cluster:prod",
        "/var/log",
        "ops@example.com",
        "GET /api",
        "-prod",
        "!prod",
        "prod | stats",
        "prod OR staging",
    ],
)
def test_serializer_legacy_mode_rejects_wildcard_query_structure(settings, value):
    settings.LOG_GROUP_RULE_MODE_ENFORCEMENT = "legacy"
    serializer = LogGroupSerializer(
        data=_payload({"mode": "AND", "conditions": [{"field": "cluster", "op": "startswith", "value": value}]})
    )

    assert serializer.is_valid() is False
    assert "unsafe for legacy" in str(serializer.errors["rule"])


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "@timestamp", "op": "==", "value": "prod"},
        {"field": "http/request", "op": "==", "value": "ok"},
        {"field": "message", "op": "contains", "value": "a.b"},
    ],
)
def test_serializer_legacy_mode_rejects_strict_only_rule_shapes(settings, condition):
    settings.LOG_GROUP_RULE_MODE_ENFORCEMENT = "legacy"
    serializer = LogGroupSerializer(data=_payload({"mode": "AND", "conditions": [condition]}))

    assert serializer.is_valid() is False
    assert "unsafe for legacy" in str(serializer.errors["rule"])


@pytest.mark.parametrize(
    "rule",
    [
        {"conditions": []},
        {"mode": "and", "conditions": [{"field": "count", "op": "==", "value": 1}]},
        {"mode": "OR", "conditions": [{"field": "enabled", "op": "!=", "value": False}]},
        {"mode": "AND", "conditions": [{"field": "@timestamp", "op": "==", "value": "2026-08-11"}]},
        {"mode": "AND", "conditions": [{"field": "http/request", "op": "==", "value": "ok"}]},
        {"mode": "AND", "conditions": [{"field": "log.file.path", "op": "startswith", "value": "/var/log"}]},
        {"mode": "AND", "conditions": [{"field": "user.email", "op": "endswith", "value": "@example.com"}]},
        {"mode": "AND", "conditions": [{"field": "request", "op": "startswith", "value": "GET /api"}]},
        {"mode": "AND", "conditions": [{"field": "cluster", "op": "startswith", "value": "prod* OR (*)"}]},
    ],
)
def test_serializer_accepts_supported_or_default_rule_mode(rule):
    serializer = LogGroupSerializer(data=_payload(rule))

    assert serializer.is_valid(), serializer.errors
