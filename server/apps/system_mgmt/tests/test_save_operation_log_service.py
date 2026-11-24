import json

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
    assert log.outcome == ""
    assert log.target_name == ""


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


@pytest.mark.django_db
def test_save_operation_log_redacts_detail_and_accepts_new_fields():
    res = save_operation_log(
        username="alice",
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="改密",
        target_type="user",
        target_id="7",
        target_name="bob",
        outcome="failure",
        failure_reason="密码不符合策略",
        detail={"password": "plain-secret", "keep": 1},
    )
    assert res["result"] is True
    log = OperationLog.objects.get()
    assert log.outcome == "failure"
    assert log.target_name == "bob"
    assert log.failure_reason == "密码不符合策略"
    assert log.detail["password"] == "已修改"
    assert log.detail["keep"] == 1
    assert "plain-secret" not in json.dumps(log.detail)


@pytest.mark.django_db
def test_save_operation_logs_does_not_rewrite_failure_to_success():
    failure = {
        "username": "alice",
        "source_ip": "127.0.0.1",
        "app": "cmdb",
        "action_type": "update",
        "summary": "失败",
        "idempotency_key": "event-fail:0",
        "outcome": "failure",
        "failure_reason": "校验失败",
        "detail": {"after_data": {"name": "submitted"}},
    }
    success = {
        **failure,
        "idempotency_key": "event-ok:0",
        "summary": "成功",
        "outcome": "success",
        "failure_reason": "",
        "detail": {"before_data": {"name": "old"}, "after_data": {"name": "new"}},
    }
    save_operation_logs(logs=[failure])
    save_operation_logs(logs=[success])
    save_operation_logs(logs=[{**failure, "outcome": "success", "summary": "改写"}])
    rows = list(OperationLog.objects.order_by("id"))
    assert len(rows) == 2
    assert rows[0].outcome == "failure"
    assert rows[0].summary == "失败"
    assert rows[1].outcome == "success"
