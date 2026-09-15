"""阿里云指标缺少可选时间标签时仍能生成资产。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.cmdb.collection.plugins.community.cloud.aliyun import AliyunAccountCollectionPlugin


def _runner():
    return AliyunAccountCollectionPlugin(
        inst_name="测试云账号",
        inst_id=1,
        task_id="7",
        collect_inst=SimpleNamespace(model_id="aliyun_account"),
        round_ts=100,
        round_completed_at=101,
    )


def _vector(model_id, labels, task_id="7"):
    return {
        "result": [
            {
                "metric": {
                    "__name__": f"{model_id}_info_gauge",
                    "instance_id": f"cn-hangzhou_{task_id}",
                    "resource_name": "测试资源",
                    "resource_id": "resource-test",
                    **labels,
                },
                "value": [100, "1"],
            }
        ],
    }


def test_mongodb_without_expire_time_preserves_resource():
    runner = _runner()
    runner.format_data(_vector("aliyun_mongodb", {"storage_gb": "20"}))
    runner.format_metrics()
    resource = runner.result["aliyun_mongodb"][0]
    assert resource["resource_id"] == "resource-test"
    assert resource["expire_time"] == ""
    assert resource["storage_gb"] == 20


@pytest.mark.parametrize(
    "model_id,time_field,numbers",
    [
        ("aliyun_bucket", "creation_date", {}),
        ("aliyun_clb", "create_time", {}),
        ("aliyun_ecs", "create_time", {"vcpus": "2", "memory": "4096"}),
        ("aliyun_ecs", "expired_time", {"vcpus": "2", "memory": "4096"}),
        (
            "aliyun_kafka_inst",
            "create_time",
            {
                "storage_gb": "100",
                "msg_retain": "72",
                "topoc_num": "10",
                "io_max_read": "20",
                "io_max_write": "20",
            },
        ),
        ("aliyun_mongodb", "expire_time", {"storage_gb": "20"}),
        ("aliyun_mysql", "expire_time", {"cpu": "2", "memory_mb": "4096"}),
        ("aliyun_pgsql", "expire_time", {"cpu": "2", "memory_mb": "4096"}),
        ("aliyun_redis", "create_time", {"port": "6379", "bandwidth": "10", "qps": "1000"}),
        ("aliyun_redis", "end_time", {"port": "6379", "bandwidth": "10", "qps": "1000"}),
    ],
)
@pytest.mark.parametrize(
    "time_labels,expected",
    [
        ({}, ""),
        ({"time": ""}, ""),
        ({"time": None}, ""),
        ({"time": "2026-09-14 09:40:51"}, "2026-09-14T09:40:51+08:00"),
    ],
    ids=["missing", "empty", "null", "populated"],
)
def test_optional_times_preserve_asset_and_account(model_id, time_field, numbers, time_labels, expected):
    runner = _runner()
    labels = {**numbers, **{time_field: value for value in time_labels.values()}}
    runner.format_data(_vector(model_id, labels))
    runner.format_data(_vector(model_id, labels, task_id="other"))
    runner.format_metrics()

    assert len(runner.result[model_id]) == 1
    resource = runner.result[model_id][0]
    assert resource[time_field] == expected
    assert resource["inst_name"] == "测试资源(resource-test)"
    assert resource["assos"] == [
        {
            "model_id": "aliyun_account",
            "inst_name": "测试云账号",
            "asst_id": "belong",
            "model_asst_id": f"{model_id}_belong_aliyun_account",
        }
    ]
    for field, value in numbers.items():
        result_field = "memory_mb" if field == "memory" else field
        assert resource[result_field] == int(value)
        assert isinstance(resource[result_field], int)


def test_missing_time_does_not_interrupt_other_resources():
    runner = _runner()
    runner.format_data(_vector("aliyun_mysql", {"cpu": "2", "memory_mb": "4096"}))
    runner.format_data(
        _vector(
            "aliyun_pgsql",
            {
                "cpu": "4",
                "memory_mb": "8192",
                "expire_time": "2027-01-01 00:00:00",
            },
        )
    )
    runner.format_metrics()
    assert runner.result["aliyun_mysql"][0]["expire_time"] == ""
    assert runner.result["aliyun_pgsql"][0]["expire_time"] == "2027-01-01T00:00:00+08:00"


@pytest.mark.parametrize("storage_gb", ["", "invalid", None])
def test_invalid_number_still_fails(storage_gb):
    runner = _runner()
    runner.format_data(_vector("aliyun_mongodb", {"storage_gb": storage_gb}))
    with pytest.raises((TypeError, ValueError)):
        runner.format_metrics()


def test_real_django_task_id_consumes_matching_metric():
    from apps.cmdb.models import CollectModels

    task = CollectModels(id=7, model_id="aliyun_account")
    runner = AliyunAccountCollectionPlugin(inst_name="测试云账号", inst_id=1, task_id=task.id, collect_inst=task, round_ts=100, round_completed_at=101)
    runner.format_data(_vector("aliyun_mysql", {"cpu": "2", "memory_mb": "4096"}))
    runner.format_metrics()
    assert len(runner.result["aliyun_mysql"]) == 1


def test_aliyun_collector_local_timestamp_keeps_original_utc_instant():
    # utc_to_dts / ECS handle_time_str 将 00:00Z 转换为 08:00 北京时间。
    actual = AliyunAccountCollectionPlugin.convert_datetime_format("2024-01-01 08:00:00")
    assert datetime.fromisoformat(actual) == datetime(2024, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("failed_model", ["aliyun_bucket", "aliyun_mysql"])
def test_partial_snapshot_preserves_successes_and_prevents_deletion(monkeypatch, failed_model):
    from apps.cmdb.collection.common import Management
    from apps.cmdb.constants.constants import DataCleanupStrategy

    runner = _runner()
    runner.snapshot_complete = True
    vector = _vector("aliyun_mysql", {"cpu": "2", "memory_mb": "4096"})
    error = _vector(failed_model, {"cmdb_collect_error": "format failed", "collect_status": "failed"})["result"][0]
    vector["result"].append(error)
    monkeypatch.setattr(runner, "query_data", lambda: vector)
    result = runner.run()
    assert len(result["aliyun_mysql"]) == 1
    assert len(runner.raw_data) == 2
    assert runner.snapshot_complete is False

    management = Management.__new__(Management)
    management.model_id = failed_model
    management.collect_plugin = runner
    management.data_cleanup_strategy = DataCleanupStrategy.IMMEDIATELY
    _, _, _, deleted = management.contrast({("existing",): {"_id": 9}}, {})
    assert deleted == []


def test_complete_snapshot_still_allows_cleanup(monkeypatch):
    from apps.cmdb.collection.common import Management
    from apps.cmdb.constants.constants import DataCleanupStrategy

    runner = _runner()
    runner.snapshot_complete = True
    monkeypatch.setattr(runner, "query_data", lambda: {"result": []})
    runner.run()
    assert runner.snapshot_complete is True
    management = Management.__new__(Management)
    management.model_id = "aliyun_mysql"
    management.collect_plugin = runner
    management.data_cleanup_strategy = DataCleanupStrategy.IMMEDIATELY
    assert management.contrast({("existing",): {"_id": 9}}, {})[3] == [{"_id": 9, "model_id": "aliyun_mysql"}]
