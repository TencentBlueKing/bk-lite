import pytest

from apps.cmdb.models.change_record import MODEL_MANAGEMENT_CHANGE, UPDATE_INST, ChangeRecord
from apps.cmdb.models.operation import ChangeRecordMirrorOutbox
from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService
from apps.cmdb.utils import change_record as cr
from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.utils.operator_log import record_operator_log
from apps.system_mgmt.models.operation_log import OperationLog


@pytest.mark.django_db
def test_cmdb_management_change_mirrors_to_operation_log():
    cr.create_change_record(
        inst_id=99,
        model_id="host",
        label="模型管理",
        _type=UPDATE_INST,
        operator="alice",
        message="修改模型. 模型名称: 旧名称",
        model_object="模型管理",
        scenario=MODEL_MANAGEMENT_CHANGE,
        before_data={"model_name": "旧名称"},
        after_data={"model_name": "新名称"},
    )
    assert ChangeRecord.objects.filter(inst_id=99).exists()
    assert not OperationLog.objects.filter(app="cmdb", target_id="99").exists()

    [outbox] = list(ChangeRecordMirrorOutbox.objects.all())
    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is True
    log = OperationLog.objects.filter(app="cmdb", target_id="99", action_type="update").first()
    assert log is not None
    assert log.username == "alice"
    assert log.source_ip == "127.0.0.1"
    assert log.summary == "修改模型. 模型名称: 旧名称"
    assert log.target_type == "模型管理"
    assert log.detail.get("scenario") == MODEL_MANAGEMENT_CHANGE
    assert log.detail.get("source") == "change_record"
    assert log.detail.get("model_object") == "模型管理"
    assert log.detail.get("before_data") == {"model_name": "旧名称"}
    assert log.detail.get("after_data") == {"model_name": "新名称"}
    assert ChangeRecord.objects.filter(inst_id=99).exists()


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
