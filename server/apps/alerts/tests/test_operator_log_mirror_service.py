from unittest.mock import patch

import pytest

from apps.alerts.constants.constants import LogAction, LogTargetType
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.utils.operator_log import record_operator_log, record_operator_logs_bulk


@pytest.mark.django_db
@patch("apps.alerts.utils.operator_log.SystemMgmt")
def test_record_operator_log_writes_and_mirrors(mock_sm):
    obj = record_operator_log(
        action=LogAction.ADD, target_type=LogTargetType.SYSTEM, operator="alice",
        operator_object="告警分派策略-创建", target_id="5", overview="创建告警分派策略[x]",
    )
    assert OperatorLog.objects.filter(id=obj.id).exists()
    kw = mock_sm.return_value.save_operation_log.call_args.kwargs
    assert kw["app"] == "alarm"
    assert kw["action_type"] == "create"          # add -> create
    assert kw["target_type"] == LogTargetType.SYSTEM
    assert kw["target_id"] == "5"
    assert kw["summary"] == "创建告警分派策略[x]"
    assert kw["detail"]["operator_object"] == "告警分派策略-创建"


@pytest.mark.django_db
@patch("apps.alerts.utils.operator_log.SystemMgmt")
def test_bulk_mirrors_each(mock_sm):
    items = [
        dict(action=LogAction.MODIFY, target_type=LogTargetType.ALERT, operator="system",
             operator_object="告警处理-自动分派", target_id=f"a{i}", overview="x")
        for i in range(3)
    ]
    objs = record_operator_logs_bulk(items)
    assert len(objs) == 3
    assert mock_sm.return_value.save_operation_log.call_count == 3


@pytest.mark.django_db
@patch("apps.alerts.utils.operator_log.SystemMgmt")
def test_mirror_failure_does_not_break_write(mock_sm):
    mock_sm.return_value.save_operation_log.side_effect = RuntimeError("nats down")
    obj = record_operator_log(
        action=LogAction.DELETE, target_type=LogTargetType.INCIDENT, operator="bob",
        operator_object="事故-删除", target_id="INC-1", overview="删",
    )
    assert OperatorLog.objects.filter(id=obj.id).exists()
