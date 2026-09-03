import logging

import pytest

from apps.cmdb.nats import nats as cmdb_nats

pytestmark = pytest.mark.unit


def test_config_file_callback_business_failure_has_correlated_terminal_summary(monkeypatch, caplog):
    monkeypatch.setattr(
        cmdb_nats.ConfigFileService,
        "process_collect_result",
        lambda _data: {
            "version_obj": None,
            "changed": False,
            "task_updated": True,
            "stale": False,
            "error": "配置文件采集回调缺少目标实例标识\ninternal detail",
        },
    )
    payload = {
        "collect_task_id": 42,
        "instance_uuid": "123e4567-e89b-42d3-a456-426614174001",
        "status": "error",
    }
    caplog.set_level(logging.INFO, logger="cmdb")

    response = cmdb_nats.receive_config_file_result(payload)

    assert response == {
        "result": True,
        "processed": False,
        "error": "配置文件采集回调缺少目标实例标识",
        "changed": False,
        "task_updated": True,
    }
    summaries = [record for record in caplog.records if "event=config_file_callback_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING
    assert "task_id=42" in summaries[0].getMessage()
    assert "instance_uuid=123e4567-e89b-42d3-a456-426614174001" in summaries[0].getMessage()
    assert "callback_status=error" in summaries[0].getMessage()
    assert "processed=False" in summaries[0].getMessage()
    assert "changed=False" in summaries[0].getMessage()
    assert "task_updated=True" in summaries[0].getMessage()
    assert "stale=False" in summaries[0].getMessage()
    assert "internal detail" not in summaries[0].getMessage()


def test_config_file_callback_success_preserves_ack_and_uses_info(monkeypatch, caplog):
    monkeypatch.setattr(
        cmdb_nats.ConfigFileService,
        "process_collect_result",
        lambda _data: {
            "version_obj": object(),
            "changed": True,
            "task_updated": True,
        },
    )
    payload = {
        "collect_task_id": 43,
        "instance_uuid": "123e4567-e89b-42d3-a456-426614174002",
        "status": "success",
    }
    caplog.set_level(logging.INFO, logger="cmdb")

    response = cmdb_nats.receive_config_file_result(payload)

    assert response == {
        "result": True,
        "processed": True,
        "error": "",
        "changed": True,
        "task_updated": True,
    }
    summaries = [record for record in caplog.records if "event=config_file_callback_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.INFO
    assert "task_id=43" in summaries[0].getMessage()
    assert "instance_uuid=123e4567-e89b-42d3-a456-426614174002" in summaries[0].getMessage()
    assert "callback_status=success" in summaries[0].getMessage()
    assert "processed=True" in summaries[0].getMessage()
    assert "changed=True" in summaries[0].getMessage()
    assert "task_updated=True" in summaries[0].getMessage()


def test_config_file_callback_reported_failure_uses_warning_when_processing_completed(monkeypatch, caplog):
    monkeypatch.setattr(
        cmdb_nats.ConfigFileService,
        "process_collect_result",
        lambda _data: {
            "version_obj": None,
            "changed": False,
            "task_updated": True,
        },
    )
    payload = {
        "collect_task_id": 44,
        "instance_uuid": "123e4567-e89b-42d3-a456-426614174003",
        "status": "permission_denied",
    }
    caplog.set_level(logging.INFO, logger="cmdb")

    response = cmdb_nats.receive_config_file_result(payload)

    assert response["processed"] is True
    summaries = [record for record in caplog.records if "event=config_file_callback_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING
    assert "callback_status=permission_denied" in summaries[0].getMessage()


def test_config_file_callback_noncanonical_status_uses_warning(monkeypatch, caplog):
    monkeypatch.setattr(
        cmdb_nats.ConfigFileService,
        "process_collect_result",
        lambda _data: {
            "version_obj": None,
            "changed": False,
            "task_updated": True,
        },
    )
    payload = {
        "collect_task_id": 45,
        "instance_uuid": "123e4567-e89b-42d3-a456-426614174004",
        "status": " success ",
    }
    caplog.set_level(logging.INFO, logger="cmdb")

    cmdb_nats.receive_config_file_result(payload)

    summaries = [record for record in caplog.records if "event=config_file_callback_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING
    assert "callback_status=unknown" in summaries[0].getMessage()


def test_config_file_callback_log_uses_normalized_nested_payload(monkeypatch, caplog):
    monkeypatch.setattr(
        cmdb_nats.ConfigFileService,
        "process_collect_result",
        lambda _data: {
            "version_obj": None,
            "changed": False,
            "task_updated": True,
        },
    )
    payload = {
        "collect_task_id": 47,
        "instance_uuid": "123e4567-e89b-42d3-a456-426614174005",
        "status": "success",
        "collect_result": {
            "collect_task_id": 48,
            "instance_uuid": "123e4567-e89b-42d3-a456-426614174006",
            "status": "error",
        },
    }
    caplog.set_level(logging.INFO, logger="cmdb")

    cmdb_nats.receive_config_file_result(payload)

    summaries = [record for record in caplog.records if "event=config_file_callback_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING
    assert "task_id=48" in summaries[0].getMessage()
    assert "instance_uuid=123e4567-e89b-42d3-a456-426614174006" in summaries[0].getMessage()
    assert "callback_status=error" in summaries[0].getMessage()


def test_config_file_callback_bounds_and_escapes_instance_uuid(monkeypatch, caplog):
    monkeypatch.setattr(
        cmdb_nats.ConfigFileService,
        "process_collect_result",
        lambda _data: {
            "version_obj": None,
            "changed": False,
            "task_updated": False,
            "stale": True,
            "error": "非当前执行",
        },
    )
    payload = {
        "collect_task_id": 46,
        "instance_uuid": "instance\n" + "x" * 100,
        "status": "success",
    }
    caplog.set_level(logging.INFO, logger="cmdb")

    cmdb_nats.receive_config_file_result(payload)

    summaries = [record for record in caplog.records if "event=config_file_callback_finished" in record.getMessage()]
    assert len(summaries) == 1
    instance_uuid = summaries[0].args[1]
    assert len(instance_uuid) == 64
    assert "\n" not in instance_uuid
    assert "\\n" in instance_uuid
