import pytest

from apps.cmdb.models.change_record import CREATE_INST, MODEL_MANAGEMENT_CHANGE
from apps.cmdb.utils import change_record as cr
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.utils.operator_log import record_operator_log
from apps.system_mgmt.models.operation_log import OperationLog


@pytest.mark.django_db
def test_cmdb_management_change_mirrors_to_operation_log():
    cr.create_change_record(
        inst_id=99, model_id="host", label="主机", _type=CREATE_INST,
        operator="alice", message="新增模型 host", model_object="host",
        scenario=MODEL_MANAGEMENT_CHANGE,
    )
    log = OperationLog.objects.filter(app="cmdb", target_id="99", action_type="create").first()
    assert log is not None
    assert log.detail.get("scenario") == MODEL_MANAGEMENT_CHANGE
    assert log.detail.get("source") == "change_record"


@pytest.mark.django_db
def test_alert_operator_log_mirrors_to_operation_log():
    record_operator_log(
        action=LogAction.ADD, target_type=LogTargetType.SYSTEM, operator="bob",
        operator_object="告警分派策略-创建", target_id="7", overview="创建[x]",
    )
    log = OperationLog.objects.filter(app="alarm", target_id="7", action_type="create").first()
    assert log is not None
    assert log.detail.get("operator_object") == "告警分派策略-创建"
    assert log.detail.get("source") == "operator_log"
