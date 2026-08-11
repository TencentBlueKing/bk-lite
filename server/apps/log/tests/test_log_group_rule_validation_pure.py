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
        [{"field": "cluster", "op": "startswith", "value": "prod* OR (*)"}],
        [{"field": "cluster", "op": "startswith", "value": "-prod"}],
        [{"field": "cluster", "op": "endswith", "value": "-prod"}],
        [{"field": "cluster", "op": "startswith", "value": "@prod"}],
    ],
)
def test_serializer_rejects_malformed_rule_conditions(conditions):
    serializer = LogGroupSerializer(data=_payload({"mode": "AND", "conditions": conditions}))

    assert serializer.is_valid() is False
    assert serializer.errors["rule"]


@pytest.mark.parametrize(
    "rule",
    [
        {"conditions": []},
        {"mode": "and", "conditions": [{"field": "count", "op": "==", "value": 1}]},
        {"mode": "OR", "conditions": [{"field": "enabled", "op": "!=", "value": False}]},
        {"mode": "AND", "conditions": [{"field": "@timestamp", "op": "==", "value": "2026-08-11"}]},
        {"mode": "AND", "conditions": [{"field": "http/request", "op": "==", "value": "ok"}]},
    ],
)
def test_serializer_accepts_supported_or_default_rule_mode(rule):
    serializer = LogGroupSerializer(data=_payload(rule))

    assert serializer.is_valid(), serializer.errors
