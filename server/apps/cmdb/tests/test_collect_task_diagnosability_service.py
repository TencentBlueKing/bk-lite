import logging

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tasks import celery_tasks as collect_tasks

pytestmark = pytest.mark.integration


def _create_protocol_task(name: str) -> CollectModels:
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.PROTOCOL,
        model_id="mysql",
        driver_type="protocol",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": "instance-1", "model_id": "mysql", "inst_name": "db-1"}],
    )


def _create_config_file_task(name: str) -> CollectModels:
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.CONFIG_FILE,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential={"credential_id": "credential-1"},
        instances=[{"_id": "host-1", "model_id": "host", "inst_name": "host-1"}],
    )


@pytest.mark.django_db
def test_collect_execution_failure_has_owned_error_and_correlated_terminal_summary(monkeypatch, caplog):
    task = _create_protocol_task("diagnosability-execution-failure")
    monkeypatch.setattr(
        collect_tasks.CollectDispatchService,
        "should_dispatch",
        staticmethod(lambda _task: False),
    )

    class FailingProtocolCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            raise RuntimeError("collector unavailable")

    monkeypatch.setattr(collect_tasks, "ProtocolCollect", FailingProtocolCollect)
    caplog.set_level(logging.INFO, logger="cmdb")

    collect_tasks.sync_collect_task(task.id, execution_id="execution-log-1")

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert "collector unavailable" in task.collect_digest["message"]

    owned_errors = [record for record in caplog.records if "event=collect_task_stage_failed" in record.getMessage()]
    assert len(owned_errors) == 1
    assert owned_errors[0].levelno == logging.ERROR
    assert owned_errors[0].exc_info is not None
    assert owned_errors[0].exc_info[0] is RuntimeError
    assert f"task_id={task.id}" in owned_errors[0].getMessage()
    assert "execution_id=execution-log-1" in owned_errors[0].getMessage()
    assert "failed_stage=collection" in owned_errors[0].getMessage()
    assert "error_type=RuntimeError" in owned_errors[0].getMessage()

    summaries = [record for record in caplog.records if "event=collect_task_execution_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING
    assert f"task_id={task.id}" in summaries[0].getMessage()
    assert "execution_id=execution-log-1" in summaries[0].getMessage()
    assert "status=ERROR" in summaries[0].getMessage()
    assert "failed_stage=collection" in summaries[0].getMessage()


@pytest.mark.django_db
def test_collect_result_persistence_failure_identifies_stage_and_preserves_error_state(monkeypatch, caplog):
    task = _create_protocol_task("diagnosability-persistence-failure")
    monkeypatch.setattr(
        collect_tasks.CollectDispatchService,
        "should_dispatch",
        staticmethod(lambda _task: False),
    )

    class MalformedProtocolCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            return {}, {
                "add": [],
                "update": [],
                "delete": [],
                "association": [],
                "__raw_data__": [None],
            }

    monkeypatch.setattr(collect_tasks, "ProtocolCollect", MalformedProtocolCollect)
    caplog.set_level(logging.INFO, logger="cmdb")

    collect_tasks.sync_collect_task(task.id, execution_id="execution-log-2")

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert "采集结果写入失败" in task.collect_digest["message"]

    owned_errors = [record for record in caplog.records if "event=collect_task_stage_failed" in record.getMessage()]
    assert len(owned_errors) == 1
    assert owned_errors[0].levelno == logging.ERROR
    assert owned_errors[0].exc_info is not None
    assert owned_errors[0].exc_info[0] is AttributeError
    assert f"task_id={task.id}" in owned_errors[0].getMessage()
    assert "execution_id=execution-log-2" in owned_errors[0].getMessage()
    assert "failed_stage=result_persistence" in owned_errors[0].getMessage()
    assert "error_type=AttributeError" in owned_errors[0].getMessage()

    summaries = [record for record in caplog.records if "event=collect_task_execution_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.WARNING
    assert "status=ERROR" in summaries[0].getMessage()
    assert "failed_stage=result_persistence" in summaries[0].getMessage()
    assert "result_persisted=True" in summaries[0].getMessage()


@pytest.mark.django_db
def test_collect_config_callback_pending_is_an_info_outcome(monkeypatch, caplog):
    task = _create_config_file_task("diagnosability-callback-pending")
    monkeypatch.setattr(
        collect_tasks.CollectDispatchService,
        "should_dispatch",
        staticmethod(lambda _task: False),
    )

    class PendingConfigFileCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            return {"config_file": {"status": "pending"}}, {}

    monkeypatch.setattr(collect_tasks, "JobCollect", PendingConfigFileCollect)
    caplog.set_level(logging.INFO, logger="cmdb")

    collect_tasks.sync_collect_task(task.id, execution_id="execution-log-3")

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    summaries = [record for record in caplog.records if "event=collect_task_execution_finished" in record.getMessage()]
    assert len(summaries) == 1
    assert summaries[0].levelno == logging.INFO
    assert "status=RUNNING" in summaries[0].getMessage()
    assert "callback_pending=True" in summaries[0].getMessage()
