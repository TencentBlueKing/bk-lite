import uuid
from unittest.mock import patch

import pytest
from django.db import transaction

from apps.cmdb.models.change_record import (
    CREATE_INST,
    MODEL_MANAGEMENT_CHANGE,
    ORDINARY_ATTRIBUTE_CHANGE,
    UPDATE_INST,
    ChangeRecord,
)
from apps.cmdb.models.operation import ChangeRecordMirrorOutbox
from apps.cmdb.services.change_record_mirror import ChangeRecordMirrorService
from apps.cmdb.utils import change_record as cr


def _edit_model_name(**overrides):
    kwargs = dict(
        inst_id=42,
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
    kwargs.update(overrides)
    return kwargs


@pytest.mark.django_db
@patch("apps.cmdb.services.change_record_mirror.dispatch_change_record_mirror")
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_management_scenario_is_mirrored(mock_sm, _mock_dispatch):
    mock_sm.return_value.save_operation_log.return_value = {"result": True}
    edit = _edit_model_name()
    cr.create_change_record(**edit)

    assert not mock_sm.return_value.save_operation_log.called
    [outbox] = list(ChangeRecordMirrorOutbox.objects.all())
    assert outbox.payloads == [
        cr._build_mirror_payload(
            inst_id=edit["inst_id"],
            model_id=edit["model_id"],
            _type=edit["_type"],
            operator=edit["operator"],
            scenario=edit["scenario"],
            message=edit["message"],
            model_object=edit["model_object"],
            before_data=edit["before_data"],
            after_data=edit["after_data"],
        )
    ]
    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is True
    kw = mock_sm.return_value.save_operation_log.call_args.kwargs
    assert kw["app"] == "cmdb"
    assert kw["action_type"] == "update"
    assert kw["target_id"] == "42"
    assert kw["target_type"] == "模型管理"
    assert kw["summary"] == "修改模型. 模型名称: 旧名称"
    assert kw["detail"]["scenario"] == MODEL_MANAGEMENT_CHANGE
    assert kw["detail"]["source"] == "change_record"
    assert kw["detail"]["before_data"] == {"model_name": "旧名称"}
    assert kw["detail"]["after_data"] == {"model_name": "新名称"}
    assert ChangeRecord.objects.filter(inst_id=42).exists()


@pytest.mark.django_db
def test_ordinary_attribute_change_is_NOT_mirrored():
    cr.create_change_record(
        inst_id=1,
        model_id="host",
        label="主机",
        _type=CREATE_INST,
        operator="alice",
        scenario=ORDINARY_ATTRIBUTE_CHANGE,
    )
    assert ChangeRecordMirrorOutbox.objects.count() == 0


@pytest.mark.django_db
@patch("apps.cmdb.services.change_record_mirror.dispatch_change_record_mirror")
@patch("apps.cmdb.services.change_record_mirror.SystemMgmt")
def test_mirror_failure_does_not_break_change_record(mock_sm, _mock_dispatch):
    mock_sm.return_value.save_operation_log.side_effect = RuntimeError("nats down")
    cr.create_change_record(**_edit_model_name(inst_id=7))

    assert ChangeRecord.objects.filter(inst_id=7).exists()
    [outbox] = list(ChangeRecordMirrorOutbox.objects.all())
    assert ChangeRecordMirrorService.consume(outbox.event_id, owner_token="worker-1") is False
    outbox.refresh_from_db()
    assert outbox.status == "retry"
    assert "nats down" not in outbox.last_error
    assert ChangeRecord.objects.filter(inst_id=7).exists()


@pytest.mark.django_db
def test_same_operation_event_id_does_not_enqueue_twice():
    event_id = uuid.uuid4()
    cr.create_change_record(**_edit_model_name(operation_event_id=event_id))
    cr.create_change_record(**_edit_model_name(operation_event_id=event_id))

    assert ChangeRecord.objects.filter(operation_event_id=event_id).count() == 1
    assert ChangeRecordMirrorOutbox.objects.count() == 1


@pytest.mark.django_db
def test_caller_rollback_removes_change_record_and_outbox():
    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            cr.create_change_record(**_edit_model_name(inst_id=8))
            raise RuntimeError("rollback")

    assert not ChangeRecord.objects.filter(inst_id=8).exists()
    assert ChangeRecordMirrorOutbox.objects.count() == 0
