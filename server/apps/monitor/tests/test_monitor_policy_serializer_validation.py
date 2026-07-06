from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer


def test_serializer_accepts_valid_formula_query_condition():
    serializer = MonitorPolicySerializer()
    value = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "a / b * 100",
        "queries": [
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    }

    assert serializer.validate_query_condition(value) == value
