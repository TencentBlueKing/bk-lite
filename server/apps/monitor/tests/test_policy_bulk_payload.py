import importlib.util
from pathlib import Path

import pytest

from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.policy_bulk import build_bulk_policy_payloads


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_bulk_policy_payloads_expands_templates_for_each_asset():
    module_path = Path(__file__).resolve().parents[1] / "services" / "policy_bulk.py"
    assert module_path.exists(), "bulk policy payload service should exist"
    module = _load_module("monitor_policy_bulk_payload_test_module", module_path)

    payloads = module.build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "CPU 使用率过高",
                "alert_name": "主机${instance_id} CPU使用率过高",
                "metric_name": "cpu_usage_total",
                "metric_id": 101,
                "metric_unit": "percent",
                "algorithm": "max",
                "threshold": [{"level": "critical", "method": ">", "value": 90}],
                "collect_type": 9,
            },
            {
                "name": "内存使用率过高",
                "alert_name": "主机${instance_id} 内存使用率过高",
                "metric_name": "mem_used_percent",
                "metric_id": 102,
                "metric_unit": "percent",
                "algorithm": "avg",
                "threshold": [{"level": "warning", "method": ">", "value": 80}],
                "collect_type": 9,
            },
        ],
        assets=[
            {"instance_id": "('host-a',)", "organizations": [7]},
            {"instance_id": "('host-b',)", "organizations": [8]},
        ],
        config={
            "name_prefix": "批量策略",
            "enable": False,
            "schedule": {"type": "min", "value": 5},
            "period": {"type": "min", "value": 10},
            "notice": True,
            "notice_type": "email",
            "notice_type_ids": [11, 12],
            "notice_users": ["alice", "bob"],
            "enable_alerts": ["threshold"],
            "group_by": ["instance_id"],
        },
    )

    assert len(payloads) == 4
    assert [item["name"] for item in payloads] == [
        "批量策略-CPU 使用率过高-host-a",
        "批量策略-CPU 使用率过高-host-b",
        "批量策略-内存使用率过高-host-a",
        "批量策略-内存使用率过高-host-b",
    ]
    assert {item["source"]["values"][0] for item in payloads} == {"('host-a',)", "('host-b',)"}
    assert {item["query_condition"]["metric_id"] for item in payloads} == {101, 102}
    assert all(item["monitor_object"] == 3 for item in payloads)
    assert all(item["source"]["type"] == "instance" for item in payloads)
    assert all(item["schedule"] == {"type": "min", "value": 5} for item in payloads)
    assert all(item["period"] == {"type": "min", "value": 10} for item in payloads)
    assert all(item["notice"] is True for item in payloads)
    assert all(item["notice_type"] == "email" for item in payloads)
    assert all(item["notice_type_ids"] == [11, 12] for item in payloads)
    assert all(item["notice_users"] == ["alice", "bob"] for item in payloads)
    assert all(item["enable"] is False for item in payloads)
    assert all(item["organizations"] in ([7], [8]) for item in payloads)
    assert all(item["trigger_count"] == 1 for item in payloads)
    assert all(item["threshold_unit"] == "percent" for item in payloads)
    assert all("no_data_level" not in item for item in payloads)
    assert all("no_data_alert_name" not in item for item in payloads)
    assert [(item["group_algorithm"], item["algorithm"]) for item in payloads] == [
        ("max", "max_over_time"),
        ("max", "max_over_time"),
        ("avg", "avg_over_time"),
        ("avg", "avg_over_time"),
    ]


def test_build_bulk_policy_payloads_includes_no_data_fields_only_when_enabled():
    module_path = Path(__file__).resolve().parents[1] / "services" / "policy_bulk.py"
    module = _load_module("monitor_policy_bulk_no_data_payload_test_module", module_path)

    payloads = module.build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "CPU 使用率过高",
                "metric_id": 101,
                "collect_type": 9,
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={
            "name_prefix": "批量策略",
            "enable_alerts": ["threshold", "no_data"],
            "no_data_level": "warning",
            "no_data_alert_name": "无数据告警",
            "notice": False,
        },
    )

    assert payloads[0]["no_data_level"] == "warning"
    assert payloads[0]["no_data_alert_name"] == "无数据告警"
    assert payloads[0]["group_algorithm"] == "avg"
    assert payloads[0]["algorithm"] == "avg_over_time"


def test_build_bulk_policy_payloads_prefers_explicit_threshold_unit():
    module_path = Path(__file__).resolve().parents[1] / "services" / "policy_bulk.py"
    module = _load_module("monitor_policy_bulk_threshold_unit_test_module", module_path)

    payload = module.build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "容量告警",
                "metric_id": 101,
                "metric_unit": "bytes",
                "calculation_unit": "mebibytes",
                "threshold_unit": "gibibytes",
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={},
    )[0]

    assert payload["threshold_unit"] == "gibibytes"


@pytest.mark.django_db
def test_build_bulk_policy_payloads_normalizes_legacy_percent_metric_unit():
    monitor_object = MonitorObject.objects.create(name="BulkLegacyPercentObj", level="base")
    payload = build_bulk_policy_payloads(
        monitor_object_id=monitor_object.id,
        templates=[
            {
                "name": "CPU 使用率过高",
                "metric_id": 101,
                "metric_unit": "%",
                "collect_type": "host",
                "threshold": [{"level": "warning", "method": ">", "value": 80}],
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={},
    )[0]

    assert payload["metric_unit"] == "%"
    assert payload["calculation_unit"] == "percent"
    assert payload["threshold_unit"] == "percent"
    serializer = MonitorPolicySerializer(data=payload)
    assert serializer.is_valid(), serializer.errors


def test_build_bulk_policy_payloads_does_not_promote_unknown_metric_unit():
    payload = build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "包速率过高",
                "metric_id": 101,
                "metric_unit": "pps",
                "threshold": [{"level": "warning", "method": ">", "value": 1000}],
            }
        ],
        assets=[{"instance_id": "('device-a',)", "organizations": [7]}],
        config={},
    )[0]

    assert payload["metric_unit"] == "pps"
    assert payload["calculation_unit"] == ""
    assert payload["threshold_unit"] == ""


def test_build_bulk_policy_payloads_prefers_config_trigger_count_then_template_default():
    module_path = Path(__file__).resolve().parents[1] / "services" / "policy_bulk.py"
    module = _load_module("monitor_policy_bulk_trigger_count_payload_test_module", module_path)

    config_payload = module.build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "CPU 使用率过高",
                "metric_id": 101,
                "collect_type": 9,
                "trigger_count": 2,
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={"trigger_count": 3},
    )
    assert config_payload[0]["trigger_count"] == 3

    template_payload = module.build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "CPU 使用率过高",
                "metric_id": 101,
                "collect_type": 9,
                "trigger_count": 2,
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={},
    )
    assert template_payload[0]["trigger_count"] == 2
