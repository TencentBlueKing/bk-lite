"""CMDB 采集任务单任务互斥测试。"""

import pydantic.root_model  # noqa: F401

import pytest
from django.utils.timezone import now

from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.tasks import celery_tasks as ct


def create_collect_task(**overrides):
    defaults = {
        "name": "single-flight",
        "task_type": CollectPluginTypes.PROTOCOL,
        "model_id": "mysql",
        "driver_type": "protocol",
        "cycle_value_type": "cycle",
        "team": [1],
        "instances": [{"_id": "i1", "model_id": "mysql", "inst_name": "db1"}],
    }
    defaults.update(overrides)
    return CollectModels.objects.create(**defaults)


@pytest.mark.django_db
def test_periodic_collect_skips_running_task_without_mutation(monkeypatch):
    started_at = now()
    task = create_collect_task(
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=started_at,
        collect_data={"kept": True},
        format_data={"kept": True},
        collect_digest={"kept": True},
    )

    class ForbiddenCollect:
        def __init__(self, task):
            raise AssertionError("重复周期任务不应创建采集器")

    monkeypatch.setattr(ct, "ProtocolCollect", ForbiddenCollect)
    ct.sync_collect_task(task.id)

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.exec_time == started_at
    assert task.collect_data == {"kept": True}
    assert task.format_data == {"kept": True}
    assert task.collect_digest == {"kept": True}


@pytest.mark.django_db
def test_claim_execution_only_first_claim_succeeds():
    task = create_collect_task(exec_status=CollectRunStatusType.SUCCESS)

    first_claim = CollectModelService.claim_execution(task.id)
    second_claim = CollectModelService.claim_execution(task.id)

    assert first_claim is not None
    assert second_claim is None
    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.exec_time == first_claim


@pytest.mark.django_db
def test_preclaimed_collect_runs_without_claiming_again(monkeypatch):
    task = create_collect_task(exec_status=CollectRunStatusType.RUNNING, exec_time=now())
    monkeypatch.setattr(
        "apps.cmdb.services.collect_dispatch_service.CollectDispatchService.should_dispatch",
        staticmethod(lambda instance: False),
    )

    class FakeCollect:
        def __init__(self, task):
            self.task = task

        def main(self):
            return {}, {"add": [], "update": [], "delete": [], "association": [], "__raw_data__": []}

    monkeypatch.setattr(ct, "ProtocolCollect", FakeCollect)
    ct.sync_collect_task(task.id, preclaimed=True)

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert "未发现任何有效数据" in task.collect_digest["message"]


@pytest.mark.django_db
def test_preclaimed_collect_skips_when_claim_is_no_longer_running(monkeypatch):
    task = create_collect_task(exec_status=CollectRunStatusType.SUCCESS)
    monkeypatch.setattr(
        ct,
        "ProtocolCollect",
        lambda task: (_ for _ in ()).throw(AssertionError("失效消息不应执行")),
    )

    ct.sync_collect_task(task.id, preclaimed=True)

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.SUCCESS


@pytest.mark.django_db
def test_manual_exec_atomically_claims_and_dispatches_preclaimed(settings, mocker):
    settings.DEBUG = False
    task = create_collect_task(exec_status=CollectRunStatusType.SUCCESS)
    delay = mocker.patch("apps.cmdb.services.collect_service.sync_collect_task.delay")
    mocker.patch.object(CollectModelService, "repair_host_cloud_snapshot", return_value=False)
    mocker.patch("apps.cmdb.services.collect_service.create_change_record")

    CollectModelService.exec_task(task, operator="tester")

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_data == {}
    assert task.format_data == {}
    assert task.collect_digest == {}
    delay.assert_called_once_with(task.id, preclaimed=True)


@pytest.mark.django_db
def test_manual_exec_rejects_when_database_was_claimed_after_instance_loaded(settings, mocker):
    settings.DEBUG = False
    task = create_collect_task(exec_status=CollectRunStatusType.SUCCESS)
    stale_instance = CollectModels.objects.get(id=task.id)
    claimed_at = now()
    CollectModels.objects.filter(id=task.id).update(
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=claimed_at,
    )
    response_error = mocker.patch(
        "apps.cmdb.services.collect_service.WebUtils.response_error",
        return_value={"blocked": True},
    )
    delay = mocker.patch("apps.cmdb.services.collect_service.sync_collect_task.delay")

    result = CollectModelService.exec_task(stale_instance, operator="tester")

    assert result == {"blocked": True}
    response_error.assert_called_once_with(
        error_message="任务正在执行中!无法重复执行！",
        status_code=400,
    )
    delay.assert_not_called()


@pytest.mark.django_db
def test_manual_dispatch_failure_rolls_back_own_claim(settings, mocker):
    settings.DEBUG = False
    previous_time = now()
    task = create_collect_task(
        exec_status=CollectRunStatusType.ERROR,
        exec_time=previous_time,
        collect_data={"old": 1},
        format_data={"old": 2},
        collect_digest={"old": 3},
    )
    mocker.patch.object(CollectModelService, "repair_host_cloud_snapshot", return_value=False)
    mocker.patch(
        "apps.cmdb.services.collect_service.sync_collect_task.delay",
        side_effect=RuntimeError("broker down"),
    )

    with pytest.raises(RuntimeError, match="broker down"):
        CollectModelService.exec_task(task, operator="tester")

    task.refresh_from_db()
    assert task.exec_status == CollectRunStatusType.ERROR
    assert task.exec_time == previous_time
    assert task.collect_data == {"old": 1}
    assert task.format_data == {"old": 2}
    assert task.collect_digest == {"old": 3}
