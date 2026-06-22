from datetime import datetime
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.services.collect_dispatch_service import CollectDispatchService, DispatchAttemptResult
from apps.cmdb.services.collect_target_service import CollectTargetService
from apps.cmdb.tasks.celery_tasks import sync_collect_task


def _create_task(task_type=CollectPluginTypes.HOST, driver_type=CollectDriverTypes.JOB):
    return CollectModels.objects.create(
        name=f"dispatch-{task_type}-{driver_type}",
        task_type=task_type,
        driver_type=driver_type,
        model_id="host" if task_type != CollectPluginTypes.PROTOCOL else "mysql",
        cycle_value_type="cycle",
        credential=[
            {"credential_id": "cred-1", "username": "admin", "password": "plain-1", "port": 22},
            {"credential_id": "cred-2", "username": "ops", "password": "plain-2", "port": 22},
        ],
        instances=[
            {"_id": "host-1", "model_id": "host", "inst_name": "10.0.0.1", "ip": "10.0.0.1"},
        ],
    )


def _create_single_credential_config_file_task():
    return CollectModels.objects.create(
        name="dispatch-config-file-single-credential",
        task_type=CollectPluginTypes.CONFIG_FILE,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential={"credential_id": "cred-1", "username": "admin", "password": "plain-1", "port": 22},
        params={"config_file_path": "/opt/bk-lite/common.env"},
        instances=[
            {"_id": "host-1", "model_id": "host", "inst_name": "10.0.0.1", "ip": "10.0.0.1"},
        ],
    )


@pytest.mark.django_db
def test_collect_dispatch_plan_prefers_success_state_and_skips_cooldown():
    task = _create_task()
    targets = CollectTargetService.build_targets(task)
    object_key = CollectTargetService.build_object_key(targets[0])
    retry_at = timezone.make_aware(datetime(2026, 6, 3, 20, 0, 0))
    CollectTaskCredentialHit.objects.create(
        task=task,
        object_key=object_key,
        credential_id="cred-1",
        status=CollectTaskCredentialHit.STATUS_KNOWN_FAILED,
        next_retry_at=retry_at,
    )
    CollectTaskCredentialHit.objects.create(
        task=task,
        object_key=object_key,
        credential_id="cred-2",
        status=CollectTaskCredentialHit.STATUS_SUCCESS,
    )

    plan = CollectDispatchService.plan_dispatch(
        task,
        targets,
        task.decrypt_credentials,
        {(state.object_key, state.credential_id): state for state in CollectTaskCredentialHit.objects.all()},
    )

    assert list(plan.keys()) == ["cred-2"]
    assert plan["cred-2"][0].host == "10.0.0.1"


@pytest.mark.django_db
def test_collect_dispatch_execute_task_falls_back_to_next_credential(monkeypatch):
    task = _create_task()

    def fake_run_job_batch(inner_task, credential, targets):
        target = targets[0]
        object_key = CollectTargetService.build_object_key(target)
        if credential["credential_id"] == "cred-1":
            return [
                DispatchAttemptResult(
                    object_key=object_key,
                    credential_id="cred-1",
                    success=False,
                    failure_kind="credential",
                    error_message="auth failed",
                )
            ]
        return [
            DispatchAttemptResult(
                object_key=object_key,
                credential_id="cred-2",
                success=True,
                failure_kind="",
                raw_payload={
                    "collect_data": {"host": {"10.0.0.1": {"status": "ok"}}},
                    "format_data": {
                        "add": [{"_status": "success", "inst_name": "10.0.0.1", "ip_addr": "10.0.0.1"}],
                        "update": [],
                        "delete": [],
                        "association": [],
                        "__raw_data__": [{"inst_name": "10.0.0.1", "ip_addr": "10.0.0.1"}],
                        "all": 1,
                    },
                },
            )
        ]

    monkeypatch.setattr(CollectDispatchService, "run_job_batch", staticmethod(fake_run_job_batch))

    collect_data, format_data = CollectDispatchService.execute_task(task)

    assert collect_data == {"host": {"10.0.0.1": {"status": "ok"}}}
    assert format_data["all"] == 1
    assert format_data["add"][0]["inst_name"] == "10.0.0.1"

    first_state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    second_state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-2")
    assert first_state.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert second_state.status == CollectTaskCredentialHit.STATUS_SUCCESS


@pytest.mark.django_db
def test_sync_collect_task_uses_dispatch_service_for_multicred(monkeypatch):
    task = _create_task()
    called = {}

    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot",
        lambda instance: None,
    )
    monkeypatch.setattr(
        CollectDispatchService,
        "execute_task",
        staticmethod(
            lambda instance: (
                called.setdefault("task_id", instance.id) or {"demo": {"ok": True}},
                {
                    "add": [{"_status": "success", "inst_name": "10.0.0.1"}],
                    "update": [],
                    "delete": [],
                    "association": [],
                    "__raw_data__": [{"inst_name": "10.0.0.1"}],
                    "all": 1,
                },
            )
        ),
    )

    sync_collect_task(task.id)
    task.refresh_from_db()

    assert called["task_id"] == task.id
    assert task.exec_status == CollectRunStatusType.SUCCESS
    assert task.collect_digest["all"] == 1


@pytest.mark.django_db
def test_sync_collect_task_keeps_single_credential_config_file_on_legacy_path(monkeypatch):
    task = _create_single_credential_config_file_task()
    collect = MagicMock()
    collect.main.return_value = ({"config_file": {"status": "pending"}}, {})

    monkeypatch.setattr(
        "apps.cmdb.services.collect_service.CollectModelService.repair_host_cloud_snapshot",
        lambda instance: None,
    )
    monkeypatch.setattr("apps.cmdb.tasks.celery_tasks.JobCollect", lambda task: collect)
    monkeypatch.setattr(
        CollectDispatchService,
        "execute_task",
        staticmethod(lambda instance: (_ for _ in ()).throw(AssertionError("dispatch should not run for old single-credential tasks"))),
    )

    sync_collect_task(task.id)
    task.refresh_from_db()

    collect.main.assert_called_once_with()
    assert CollectDispatchService.should_dispatch(task) is False
    assert task.exec_status == CollectRunStatusType.RUNNING
    assert task.collect_data == {"config_file": {"status": "pending"}}
    assert task.collect_digest["message"] == "配置文件采集已触发，等待回传中"