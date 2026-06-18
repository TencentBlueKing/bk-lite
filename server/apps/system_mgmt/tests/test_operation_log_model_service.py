import pytest

from apps.system_mgmt.models.operation_log import OperationLog


@pytest.mark.django_db
def test_operation_log_stores_target_and_detail():
    log = OperationLog.objects.create(
        username="alice", source_ip="1.2.3.4", app="cmdb", action_type="update",
        summary="编辑模型", target_type="host", target_id="42",
        detail={"before_data": {"a": 1}, "after_data": {"a": 2}, "scenario": "model_management_change"},
    )
    log.refresh_from_db()
    assert log.target_type == "host"
    assert log.target_id == "42"
    assert log.detail["after_data"] == {"a": 2}


@pytest.mark.django_db
def test_operation_log_target_detail_default_empty():
    log = OperationLog.objects.create(
        username="bob", source_ip="1.2.3.4", app="job", action_type="create", summary="x",
    )
    assert log.target_type == ""
    assert log.target_id == ""
    assert log.detail == {}
