from apps.opspilot.metis.llm.chain.repair_report_identity import count_distinct_repair_targets


def test_same_name_in_different_namespaces_counts_as_distinct_targets():
    items = [
        {"namespace": "prod", "target_type": "Deployment", "target_name": "order-api"},
        {"namespace": "staging", "target_type": "Deployment", "target_name": "order-api"},
    ]

    assert count_distinct_repair_targets(items) == 2
