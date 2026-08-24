from apps.operation_analysis.services.table_query_list import apply_query_list_to_payload


def test_str_contains_filters_rows_in_list_payload():
    payload = [
        {"name": "bk-web", "ip": "10.0.0.1"},
        {"name": "ops-db", "ip": "10.0.0.2"},
        {"name": "bk-lite", "ip": "10.0.0.3"},
    ]

    filtered = apply_query_list_to_payload(
        payload,
        [{"field": "name", "type": "str*", "value": "bk"}],
    )

    assert filtered == [
        {"name": "bk-web", "ip": "10.0.0.1"},
        {"name": "bk-lite", "ip": "10.0.0.3"},
    ]


def test_empty_or_missing_query_list_keeps_payload():
    payload = [{"name": "bk-web"}]
    assert apply_query_list_to_payload(payload, []) == payload
    assert apply_query_list_to_payload(payload, None) == payload


def test_items_wrapper_updates_count_when_unpaged():
    payload = {
        "items": [
            {"title": "CPU 过高"},
            {"title": "磁盘告警"},
            {"title": "CPU 使用率"},
        ],
        "count": 3,
    }

    filtered = apply_query_list_to_payload(
        payload,
        [{"field": "title", "type": "str*", "value": "CPU"}],
    )

    assert filtered["items"] == [
        {"title": "CPU 过高"},
        {"title": "CPU 使用率"},
    ]
    assert filtered["count"] == 2


def test_paginated_items_keep_declared_total():
    payload = {
        "items": [
            {"title": "CPU 过高"},
            {"title": "磁盘告警"},
        ],
        "count": 40,
    }

    filtered = apply_query_list_to_payload(
        payload,
        [{"field": "title", "type": "str*", "value": "CPU"}],
    )

    assert filtered["items"] == [{"title": "CPU 过高"}]
    assert filtered["count"] == 40
