import json

import pytest

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_access_check import CollectAccessCheck, CollectAccessCheckRow
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_access_check_service import CollectAccessCheckService, apply_access_check_callback
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.stargazer_collect_trigger import AccessCheckRemoteError, StargazerCollectTriggerClient

pytestmark = pytest.mark.django_db


def _task(**overrides):
    payload = {
        "name": "access-check-task",
        "task_type": "protocol",
        "driver_type": "protocol",
        "model_id": "mysql",
        "team": [1],
        "timeout": 60,
        "cycle_value_type": "cycle",
        "ip_range": "10.0.0.8,10.0.0.9",
        "credential": [
            {"credential_id": "credential-1", "name": "凭据 1", "password": "secret-value"},
            {"credential_id": "credential-2", "name": "凭据 2", "password": "other-secret", "target_host": "10.0.0.9"},
        ],
        "params": {},
        "enabled": True,
    }
    payload.update(overrides)
    return CollectModels.objects.create(**payload)


class _Hosts:
    def get_hosts(self):
        return "hosts", "10.0.0.8,10.0.0.9"


@pytest.mark.parametrize(
    "model_id",
    [
        "host",
        "network",
        "k8s",
        "k8s_cluster",
        "ip",
        "ip_discovery",
        "network_config_file",
        "redis",
        "physcial_server_ipmi",
        "dell_unity",
    ],
)
def test_out_of_scope_task_is_rejected_without_calling_stargazer(model_id, mocker):
    client = mocker.patch("apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.admit_access_check")
    task = _task(name=f"out-{model_id}", model_id=model_id, task_type="protocol", driver_type="protocol")

    response = CollectAccessCheckService.start(task, "admin")

    assert response.status_code == 400
    assert json.loads(response.content)["data"]["error_code"] == "out_of_scope"
    client.assert_not_called()
    assert CollectAccessCheck.objects.filter(task=task).count() == 0


def test_ip_range_is_one_row_per_address(mocker):
    class _RangeHosts:
        def get_hosts(self):
            return "hosts", "127.0.0.1-127.0.0.3,10.0.0.8"

    mocker.patch(
        "apps.cmdb.services.collect_access_check_service.NodeParamsFactory.get_node_params",
        return_value=_RangeHosts(),
    )
    mocker.patch(
        "apps.cmdb.services.collect_access_check_service.StargazerCollectTriggerClient.admit_access_check",
        return_value="accepted",
    )
    task = _task(
        ip_range="127.0.0.1-127.0.0.3,10.0.0.8",
        credential=[{"credential_id": "credential-1", "name": "凭据 1", "password": "secret-value"}],
    )

    response = CollectAccessCheckService.start(task, "admin")

    body = json.loads(response.content)
    assert response.status_code == 202
    assert [row["target"] for row in body["data"]["rows"]] == [
        "127.0.0.1",
        "127.0.0.2",
        "127.0.0.3",
        "10.0.0.8",
    ]
    assert {row["conclusion"] for row in body["data"]["rows"]} == {"pending"}
    assert body["data"]["total_count"] == 4


def test_in_scope_start_keeps_task_status_and_hides_secrets(mocker):
    mocker.patch(
        "apps.cmdb.services.collect_access_check_service.NodeParamsFactory.get_node_params",
        return_value=_Hosts(),
    )
    admit = mocker.patch(
        "apps.cmdb.services.collect_access_check_service.StargazerCollectTriggerClient.admit_access_check",
        return_value="accepted",
    )
    task = _task()

    response = CollectAccessCheckService.start(task, "admin")

    task.refresh_from_db()
    body = json.loads(response.content)
    assert response.status_code == 202
    assert body["data"]["status"] == "running"
    assert task.exec_status == CollectRunStatusType.NOT_START
    assert task.enabled is True
    assert "secret-value" not in response.content.decode()
    assert "other-secret" not in response.content.decode()
    assert [row["conclusion"] for row in body["data"]["rows"]] == ["pending", "pending", "pending"]
    admit.assert_called_once()


def test_running_access_check_blocks_execute():
    task = _task(name="running-check")
    check = CollectAccessCheck.objects.create(
        task=task,
        status="running",
        total_count=1,
        finished_count=0,
        started_at=task.created_at,
        operator="admin",
    )
    check.rows.create(
        position=0,
        target="10.0.0.8",
        credential_id="credential-1",
        credential_name="凭据 1",
        conclusion="pending",
    )

    response = CollectModelService.exec_task(task, "admin")

    task.refresh_from_db()
    assert response.status_code == 409
    assert json.loads(response.content)["data"]["error_code"] == "check_running"
    assert task.exec_status == CollectRunStatusType.NOT_START


def test_deleting_the_task_deletes_its_access_check_and_rows():
    task = _task(name="delete-check")
    check = CollectAccessCheck.objects.create(
        task=task,
        status="finished",
        total_count=1,
        finished_count=1,
        started_at=task.created_at,
        operator="admin",
    )
    check.rows.create(
        position=0,
        target="10.0.0.8",
        credential_id="credential-1",
        credential_name="凭据 1",
        conclusion="credential_rejected",
        detail_code="credential_password",
        attempted=True,
    )
    task_id = task.id
    check_id = check.id

    task.delete()

    assert not CollectModels.objects.filter(id=task_id).exists()
    assert not CollectAccessCheck.objects.filter(id=check_id).exists()
    assert not CollectAccessCheckRow.objects.filter(access_check_id=check_id).exists()


def test_remote_rows_replace_pending_without_storing_secrets():
    task = _task(name="remote-rows")
    check = CollectAccessCheck.objects.create(
        task=task,
        status="running",
        total_count=1,
        finished_count=0,
        started_at=task.created_at,
        operator="admin",
    )
    check.rows.create(
        position=0,
        target="10.0.0.8",
        credential_id="credential-1",
        credential_name="凭据 1",
        conclusion="pending",
    )

    CollectAccessCheckService.apply_remote_rows(
        check,
        [
            {
                "target": "10.0.0.8",
                "credential_id": "credential-1",
                "credential_name": "凭据 1",
                "conclusion": "credential_ok",
                "detail_code": "authentication_failed; password=secret-value",
                "attempted": True,
                "password": "secret-value",
            }
        ],
    )

    check.refresh_from_db()
    task.refresh_from_db()
    row = check.rows.get()
    assert check.status == "finished"
    assert row.conclusion == "credential_ok"
    assert row.detail_code == ""
    assert task.exec_status == CollectRunStatusType.NOT_START
    assert "secret-value" not in row.credential_name


def test_timeout_waits_for_every_target_and_does_not_mark_probe_error():
    from datetime import timedelta

    from django.utils.timezone import now

    task = _task(name="timeout-scale", timeout=60)
    check = CollectAccessCheck.objects.create(
        task=task,
        status="running",
        total_count=2,
        finished_count=0,
        started_at=now() - timedelta(seconds=100),
        operator="admin",
    )
    for index, target in enumerate(("10.0.0.8", "10.0.0.9")):
        check.rows.create(
            position=index,
            target=target,
            credential_id="credential-1",
            credential_name="凭据 1",
            conclusion="pending",
        )

    CollectAccessCheckService._expire_if_stale(check, task)

    check.refresh_from_db()
    assert check.status == "running"
    check.started_at = now() - timedelta(seconds=200)
    check.save(update_fields=["started_at"])
    CollectAccessCheckService._expire_if_stale(check, task)
    check.refresh_from_db()
    row = check.rows.get(target="10.0.0.8")
    assert check.status == "failed"
    assert check.error_code == "stargazer_timeout"
    assert row.conclusion == "no_response"
    assert row.detail_code == "stargazer_timeout"
    assert row.attempted is False


def test_system_error_row_drops_exception_text():
    task = _task(name="system-error-row")
    check = CollectAccessCheck.objects.create(
        task=task,
        status="running",
        total_count=1,
        finished_count=0,
        started_at=task.created_at,
        operator="admin",
    )
    check.rows.create(
        position=0,
        target="10.0.0.8",
        credential_id="credential-1",
        credential_name="凭据 1",
        conclusion="pending",
    )

    CollectAccessCheckService.apply_remote_rows(
        check,
        [
            {
                "target": "10.0.0.8",
                "credential_id": "credential-1",
                "credential_name": "凭据 1",
                "conclusion": "system_error",
                "detail_code": "ValueError password=secret-value",
                "attempted": True,
            }
        ],
    )

    row = check.rows.get()
    assert row.conclusion == "system_error"
    assert row.detail_code == ""
    assert "secret-value" not in row.detail_code


def _running_check(name, targets):
    task = _task(name=name)
    check = CollectAccessCheck.objects.create(
        task=task,
        status="running",
        total_count=len(targets),
        finished_count=0,
        started_at=task.created_at,
        operator="admin",
    )
    for index, target in enumerate(targets):
        check.rows.create(
            position=index,
            target=target,
            credential_id="credential-1",
            credential_name="凭据 1",
            conclusion="pending",
        )
    return task, check


def test_batches_keep_the_check_running_until_every_row_returns():
    task, check = _running_check("batch-order", ("10.0.0.8", "10.0.0.9"))

    apply_access_check_callback(
        {
            "collect_task_id": str(task.id),
            "check_id": str(check.id),
            "status": "running",
            "error_code": "",
            "rows": [
                {
                    "target": "10.0.0.8",
                    "credential_id": "credential-1",
                    "credential_name": "凭据 1",
                    "conclusion": "network_unreachable",
                    "detail_code": "tcp_connection_refused",
                    "attempted": False,
                }
            ],
        }
    )

    check.refresh_from_db()
    assert check.status == "running"
    assert check.finished_count == 1
    assert check.rows.get(target="10.0.0.9").conclusion == "pending"

    apply_access_check_callback(
        {
            "collect_task_id": str(task.id),
            "check_id": str(check.id),
            "status": "finished",
            "error_code": "",
            "rows": [
                {
                    "target": "10.0.0.9",
                    "credential_id": "credential-1",
                    "credential_name": "凭据 1",
                    "conclusion": "credential_rejected",
                    "detail_code": "credential_password",
                    "attempted": True,
                }
            ],
        }
    )

    check.refresh_from_db()
    assert check.status == "finished"
    assert check.finished_count == 2
    assert check.error_code == ""
    assert check.rows.get(target="10.0.0.8").detail_code == "tcp_connection_refused"


def test_later_batch_can_arrive_before_the_earlier_one():
    task, check = _running_check("batch-reorder", ("10.0.0.8", "10.0.0.9"))
    finished = {
        "collect_task_id": str(task.id),
        "check_id": str(check.id),
        "status": "finished",
        "error_code": "",
        "rows": [
            {
                "target": "10.0.0.9",
                "credential_id": "credential-1",
                "credential_name": "凭据 1",
                "conclusion": "credential_ok",
                "detail_code": "",
                "attempted": True,
            }
        ],
    }
    earlier = {
        "collect_task_id": str(task.id),
        "check_id": str(check.id),
        "status": "running",
        "error_code": "",
        "rows": [
            {
                "target": "10.0.0.8",
                "credential_id": "credential-1",
                "credential_name": "凭据 1",
                "conclusion": "network_unreachable",
                "detail_code": "tcp_connect_timeout",
                "attempted": False,
            }
        ],
    }

    apply_access_check_callback(finished)
    check.refresh_from_db()
    assert check.status == "running"
    assert check.rows.get(target="10.0.0.8").conclusion == "pending"

    apply_access_check_callback(earlier)
    check.refresh_from_db()
    assert check.status == "finished"
    assert check.rows.get(target="10.0.0.8").detail_code == "tcp_connect_timeout"
    assert check.rows.get(target="10.0.0.9").conclusion == "credential_ok"


def test_admission_failure_marks_check_failed_and_returns_error(mocker):
    mocker.patch(
        "apps.cmdb.services.collect_access_check_service.NodeParamsFactory.get_node_params",
        return_value=_Hosts(),
    )
    mocker.patch(
        "apps.cmdb.services.collect_access_check_service.StargazerCollectTriggerClient.admit_access_check",
        side_effect=AccessCheckRemoteError("stargazer_unavailable"),
    )
    task = _task(name="admit-failed")

    response = CollectAccessCheckService.start(task, "admin")

    check = CollectAccessCheck.objects.get(task=task)
    assert response.status_code == 503
    assert json.loads(response.content)["data"]["error_code"] == "stargazer_unavailable"
    assert check.status == "failed"
    assert check.rows.filter(conclusion="pending").count() == 0
    assert check.rows.filter(conclusion="system_error", detail_code="system_error").count() == check.rows.count()


def test_callback_worker_writes_rows_and_ignores_a_finished_check():
    task = _task(name="callback-worker")
    check = CollectAccessCheck.objects.create(
        task=task,
        status="running",
        total_count=1,
        finished_count=0,
        started_at=task.created_at,
        operator="admin",
    )
    check.rows.create(
        position=0,
        target="10.0.0.8",
        credential_id="credential-1",
        credential_name="凭据 1",
        conclusion="pending",
    )
    payload = {
        "collect_task_id": str(task.id),
        "check_id": str(check.id),
        "status": "finished",
        "error_code": "",
        "rows": [
            {
                "target": "10.0.0.8",
                "credential_id": "credential-1",
                "credential_name": "凭据 1",
                "conclusion": "credential_rejected",
                "detail_code": "authentication_failed",
                "attempted": True,
                "password": "secret-value",
            }
        ],
    }

    apply_access_check_callback(payload)
    apply_access_check_callback(payload)

    check.refresh_from_db()
    row = check.rows.get()
    assert check.status == "finished"
    assert row.conclusion == "credential_rejected"
    assert row.detail_code == "authentication_failed"
    assert "secret-value" not in row.credential_name


def test_receive_result_queues_without_secrets(mocker):
    delay = mocker.patch("apps.cmdb.tasks.celery_tasks.apply_access_check_result.delay")
    from apps.cmdb.nats.nats import receive_access_check_result

    result = receive_access_check_result(
        {
            "check_id": "6",
            "collect_task_id": "50",
            "status": "finished",
            "password": "secret-value",
            "rows": [
                {
                    "target": "127.0.0.1",
                    "credential_name": "凭据 1",
                    "conclusion": "credential_ok",
                    "detail_code": "",
                    "attempted": True,
                    "password": "secret-value",
                }
            ],
        }
    )

    assert result == {"accepted": True, "check_id": "6"}
    queued = delay.call_args.args[0]
    assert "secret-value" not in json.dumps(queued)
    assert queued["rows"][0]["target"] == "127.0.0.1"


def test_admit_targets_cloud_region_stargazer(mocker):
    task = _task(name="zone-task", access_point=[{"cloud_name": "zone-a"}])
    mocker.patch.object(
        StargazerCollectTriggerClient,
        "_build_request",
        return_value=("http://stargazer", {}, {"cmdbmodel_id": "mysql", "cmdbhosts": "10.0.0.8"}),
    )
    client = mocker.Mock()
    client.request.return_value = {"success": True, "status": "accepted"}
    stargazer = mocker.patch("apps.cmdb.services.stargazer_collect_trigger.Stargazer")
    stargazer.return_value.client = client

    assert StargazerCollectTriggerClient().admit_access_check(task, task.id) == "accepted"

    assert stargazer.call_args.kwargs["instance_id"] == "zone-a_stargazer"
    sent = client.request.call_args.kwargs
    assert sent["_timeout"] == 10
    assert sent["check_id"] == str(task.id)
    assert sent["collect_task_id"] == str(task.id)
    assert "run_purpose" not in sent
    assert "password" not in sent
