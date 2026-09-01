import logging
from types import SimpleNamespace

import plugins.inputs.aliyun.aliyun_info as aliyun_module
from plugins.inputs.aliyun.aliyun_info import Aliyun

SENTINEL_AK = "SENTINEL_ALIYUN_AK_MUST_NOT_LOG"


def test_list_buckets_failure_logs_exception_not_ak(monkeypatch, caplog, capsys):
    original = RuntimeError("oss boom")

    plugin = Aliyun.__new__(Aliyun)
    plugin.RegionId = "cn-hangzhou"
    plugin.custom_endpoint = "oss.example.com"
    plugin.collection_task_id = "collect-task-9"
    plugin.AccessKey = SENTINEL_AK
    plugin.AccessSecret = SENTINEL_AK

    def boom(*_args, **_kwargs):
        raise original

    plugin.oss_client = SimpleNamespace(list_buckets_with_options=boom)

    monkeypatch.setattr(
        aliyun_module.oss_20190517_models,
        "ListBucketsRequest",
        lambda: SimpleNamespace(max_keys=None),
    )
    monkeypatch.setattr(
        aliyun_module.oss_20190517_models,
        "ListBucketsHeaders",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        aliyun_module.util_models, "RuntimeOptions", lambda: SimpleNamespace()
    )

    test_logger = logging.getLogger("test.stargazer.aliyun_list_buckets")
    monkeypatch.setattr(aliyun_module, "logger", test_logger)

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        result = plugin.list_buckets()

    assert result == {"result": False, "message": repr(original)}
    captured = capsys.readouterr()
    assert "list_buckets error" not in captured.out
    assert SENTINEL_AK not in captured.out
    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=aliyun_list_buckets_failed" in message
    assert "region=cn-hangzhou" in message
    assert "task_id=collect-task-9" in message
    assert "error_type=RuntimeError" in message
    assert SENTINEL_AK not in message
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[1] is original
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_AK not in joined
