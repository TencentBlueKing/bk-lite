from apps.log.serializers.log_group import LogGroupSerializer


def test_serializer_rejects_unknown_rule_mode():
    serializer = LogGroupSerializer(
        data={
            "id": "invalid-mode",
            "name": "invalid rule",
            "rule": {
                "mode": "ADN",
                "conditions": [
                    {"field": "cluster", "op": "==", "value": "a"},
                    {"field": "namespace", "op": "==", "value": "b"},
                ],
            },
        }
    )

    assert serializer.is_valid() is False
    assert "Unsupported mode" in str(serializer.errors["rule"])


def test_serializer_accepts_supported_rule_mode_case_insensitively():
    serializer = LogGroupSerializer(
        data={
            "id": "valid-mode",
            "name": "valid rule",
            "rule": {
                "mode": "and",
                "conditions": [
                    {"field": "cluster", "op": "==", "value": "a"},
                    {"field": "namespace", "op": "==", "value": "b"},
                ],
            },
        }
    )

    assert serializer.is_valid(), serializer.errors
