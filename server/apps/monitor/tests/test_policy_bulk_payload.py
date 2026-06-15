import importlib.util
from pathlib import Path


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
    assert all(item["notice_type_ids"] == [11, 12] for item in payloads)
    assert all(item["notice_users"] == ["alice", "bob"] for item in payloads)
    assert all(item["enable"] is False for item in payloads)
    assert all(item["organizations"] in ([7], [8]) for item in payloads)
