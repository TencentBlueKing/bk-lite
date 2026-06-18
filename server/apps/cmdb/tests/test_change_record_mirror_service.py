from unittest.mock import patch

import pytest

from apps.cmdb.models.change_record import CREATE_INST, MODEL_MANAGEMENT_CHANGE, ORDINARY_ATTRIBUTE_CHANGE
from apps.cmdb.utils import change_record as cr


@pytest.mark.django_db
@patch("apps.cmdb.utils.change_record.SystemMgmt")
def test_management_scenario_is_mirrored(mock_sm):
    cr.create_change_record(
        inst_id=42, model_id="host", label="主机", _type=CREATE_INST,
        after_data={"name": "h1"}, operator="alice", message="新增模型 host",
        model_object="host", scenario=MODEL_MANAGEMENT_CHANGE,
    )
    call = mock_sm.return_value.save_operation_log
    assert call.called
    kw = call.call_args.kwargs
    assert kw["app"] == "cmdb"
    assert kw["action_type"] == "create"
    assert kw["target_id"] == "42"
    assert kw["detail"]["scenario"] == MODEL_MANAGEMENT_CHANGE
    assert kw["detail"]["after_data"] == {"name": "h1"}


@pytest.mark.django_db
@patch("apps.cmdb.utils.change_record.SystemMgmt")
def test_ordinary_attribute_change_is_NOT_mirrored(mock_sm):
    cr.create_change_record(inst_id=1, model_id="host", label="主机", _type=CREATE_INST,
                            operator="alice", scenario=ORDINARY_ATTRIBUTE_CHANGE)
    assert not mock_sm.return_value.save_operation_log.called


@pytest.mark.django_db
@patch("apps.cmdb.utils.change_record.SystemMgmt")
def test_mirror_failure_does_not_break_change_record(mock_sm):
    from apps.cmdb.models.change_record import ChangeRecord
    mock_sm.return_value.save_operation_log.side_effect = RuntimeError("nats down")
    cr.create_change_record(inst_id=7, model_id="host", label="主机", _type=CREATE_INST,
                            operator="alice", scenario=MODEL_MANAGEMENT_CHANGE)
    assert ChangeRecord.objects.filter(inst_id=7).exists()
