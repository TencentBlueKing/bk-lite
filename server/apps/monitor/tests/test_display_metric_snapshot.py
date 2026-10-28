from apps.monitor.services.display_metric_snapshot import (
    display_metric_lookup_keys,
    localize_metric_column_names,
    metric_display_columns,
    metric_value_map,
    normalize_metric_cell,
)


def test_metric_columns_skip_field_columns_and_follow_sort_order():
    columns = metric_display_columns(
        [
            {
                "name": "内存使用率",
                "sort_order": 2,
                "metrics": [{"plugin": "os", "metric": "mem_used_percent"}],
            },
            {
                "name": "IP",
                "type": "field",
                "sort_order": 0,
                "metrics": [{"plugin": "os", "metric": "host", "field": "ip"}],
            },
            {
                "name": "CPU使用率",
                "sort_order": 1,
                "metrics": [{"plugin": "os", "metric": "cpu_usage_total"}],
            },
            {"name": "空列", "sort_order": 3, "metrics": []},
        ]
    )

    assert columns == [
        {"name": "CPU使用率", "keys": ["os::cpu_usage_total"]},
        {"name": "内存使用率", "keys": ["os::mem_used_percent"]},
    ]


def test_lookup_keys_cover_raw_id_and_storage_key():
    assert display_metric_lookup_keys("abc") == ["abc", "('abc',)"]
    assert display_metric_lookup_keys("('abc',)") == ["('abc',)"]
    assert display_metric_lookup_keys("  ") == []


def test_default_column_uses_translated_metric_name():
    columns = [{"name": "Active Connections", "keys": ["Nginx::nginx_active"]}]
    translations = {"monitor_object_metric.Nginx.nginx_active.name": "活跃连接数"}
    assert localize_metric_column_names(columns, "Nginx", translations) == [
        {"name": "活跃连接数", "keys": ["Nginx::nginx_active"]},
    ]
    assert localize_metric_column_names(columns, "Nginx", translations, customized=True) == columns
    assert localize_metric_column_names(columns, "Nginx", {}) == columns


def test_missing_metric_stays_empty():
    columns = [{"name": "CPU使用率", "keys": ["os::cpu_usage_total"]}]
    assert metric_value_map({"instance_id": "abc"}, columns) == {
        "os::cpu_usage_total": {"value": None, "unit": ""},
    }
    assert normalize_metric_cell({"value": "12.3", "unit": "%"}) == {"value": "12.3", "unit": "%"}
    assert normalize_metric_cell(None) == {"value": None, "unit": ""}
