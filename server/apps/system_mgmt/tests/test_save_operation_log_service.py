import pytest

from apps.system_mgmt.models.operation_log import OperationLog
from apps.system_mgmt.nats_api import save_operation_log, save_operation_logs


@pytest.mark.django_db
def test_save_operation_log_persists_target_and_detail():
    res = save_operation_log(
        username="alice",
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="编辑模型",
        target_type="host",
        target_id="42",
        detail={"scenario": "model_management_change"},
    )
    assert res["result"] is True
    log = OperationLog.objects.get()
    assert (log.target_type, log.target_id) == ("host", "42")
    assert log.detail == {"scenario": "model_management_change"}


@pytest.mark.django_db
def test_save_operation_log_backward_compatible_without_new_params():
    res = save_operation_log(username="bob", source_ip="127.0.0.1", app="job", action_type="create", summary="x")
    assert res["result"] is True
    log = OperationLog.objects.get()
    assert log.target_type == "" and log.detail == {}


@pytest.mark.django_db
def test_save_operation_log_rejects_bad_action_type():
    res = save_operation_log(username="x", source_ip="127.0.0.1", app="cmdb", action_type="frobnicate")
    assert res["result"] is False


@pytest.mark.django_db
def test_save_operation_logs_is_idempotent():
    payload = {
        "username": "alice",
        "source_ip": "127.0.0.1",
        "app": "cmdb",
        "action_type": "update",
        "summary": "编辑模型",
        "idempotency_key": "event-1:0",
        "detail": {"scenario": "model_management_change"},
    }
    first = save_operation_logs(logs=[payload, {**payload, "idempotency_key": "event-1:1", "summary": "第二条"}])
    second = save_operation_logs(logs=[payload])
    assert first == {"result": True, "saved": 2, "duplicates": 0}
    assert second == {"result": True, "saved": 0, "duplicates": 1}
    assert OperationLog.objects.count() == 2
