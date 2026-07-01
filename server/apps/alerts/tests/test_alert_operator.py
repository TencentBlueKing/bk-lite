"""告警操作状态机覆盖测试。

对照 spec/prd/告警中心·告警：未分派→待响应→处理中→关闭，含转派/认领与权限校验。
"""

from unittest import mock

import pytest

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.models import Alert
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.service.alter_operator import AlertOperator


@pytest.fixture
def sys_user(db):
    from apps.system_mgmt.models.user import User

    return User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])


def _make_alert(alert_id="A1", status=AlertStatus.UNASSIGNED, operator=None, team=None):
    return Alert.objects.create(
        alert_id=alert_id, level="0", title="t", content="c", fingerprint="fp",
        status=status, operator=operator or [], team=team or [1],
    )


# --------------------------------------------------------------------------
# operate dispatch
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_operate_unknown_action_raises():
    _make_alert()
    op = AlertOperator(user="op1")
    with pytest.raises(ValueError):
        op.operate("teleport", "A1", {})


@pytest.mark.django_db
def test_operate_not_allowed_alert():
    _make_alert()
    op = AlertOperator(user="op1", allowed_alert_ids=["other"])
    result = op.operate("assign", "A1", {})
    assert result["result"] is False
    assert "权限" in result["message"]


# --------------------------------------------------------------------------
# assign
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_assign_success(sys_user):
    _make_alert(status=AlertStatus.UNASSIGNED, team=[1])
    op = AlertOperator(user="system")
    result = op.operate("assign", "A1", {"assignee": ["op1"]})
    assert result["result"] is True
    alert = Alert.objects.get(alert_id="A1")
    assert alert.status == AlertStatus.PENDING
    assert alert.operator == ["op1"]
    assert OperatorLog.objects.filter(operator_object="告警处理-分派").exists()


@pytest.mark.django_db
def test_assign_wrong_status():
    _make_alert(status=AlertStatus.PROCESSING)
    op = AlertOperator(user="system")
    result = op.operate("assign", "A1", {"assignee": ["op1"]})
    assert result["result"] is False
    assert "无法进行分派" in result["message"]


@pytest.mark.django_db
def test_assign_no_assignee():
    _make_alert(status=AlertStatus.UNASSIGNED)
    op = AlertOperator(user="system")
    result = op.operate("assign", "A1", {"assignee": []})
    assert result["result"] is False
    assert "请指定处理人" in result["message"]


@pytest.mark.django_db
def test_assign_nonexistent_alert():
    op = AlertOperator(user="system")
    result = op.operate("assign", "missing", {"assignee": ["op1"]})
    assert result["result"] is False
    assert "不存在" in result["message"]


@pytest.mark.django_db
def test_assign_invalid_assignee_out_of_scope():
    from apps.system_mgmt.models.user import User

    User.objects.create(username="outsider", domain="domain.com", group_list=[{"id": 99}])
    _make_alert(status=AlertStatus.UNASSIGNED, team=[1])
    op = AlertOperator(user="system")
    result = op.operate("assign", "A1", {"assignee": ["outsider"]})
    assert result["result"] is False


# --------------------------------------------------------------------------
# acknowledge
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_acknowledge_success():
    _make_alert(status=AlertStatus.PENDING, operator=["op1"])
    op = AlertOperator(user="op1")
    result = op.operate("acknowledge", "A1", {})
    assert result["result"] is True
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PROCESSING


@pytest.mark.django_db
def test_acknowledge_wrong_status():
    _make_alert(status=AlertStatus.UNASSIGNED, operator=["op1"])
    op = AlertOperator(user="op1")
    result = op.operate("acknowledge", "A1", {})
    assert result["result"] is False


@pytest.mark.django_db
def test_acknowledge_no_permission():
    _make_alert(status=AlertStatus.PENDING, operator=["someoneelse"])
    op = AlertOperator(user="op1")
    result = op.operate("acknowledge", "A1", {})
    assert result["result"] is False
    assert "权限" in result["message"]


# --------------------------------------------------------------------------
# close
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_close_success():
    _make_alert(status=AlertStatus.PROCESSING, operator=["op1"])
    op = AlertOperator(user="op1")
    result = op.operate("close", "A1", {"reason": "已修复"})
    assert result["result"] is True
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.CLOSED
    assert result["data"]["close_reason"] == "已修复"


@pytest.mark.django_db
def test_close_wrong_status():
    _make_alert(status=AlertStatus.PENDING, operator=["op1"])
    op = AlertOperator(user="op1")
    result = op.operate("close", "A1", {})
    assert result["result"] is False


@pytest.mark.django_db
def test_close_no_permission():
    _make_alert(status=AlertStatus.PROCESSING, operator=["other"])
    op = AlertOperator(user="op1")
    result = op.operate("close", "A1", {})
    assert result["result"] is False


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# reassign
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_reassign_success(sys_user):
    # 转派要求当前用户是现处理人之一
    _make_alert(status=AlertStatus.PROCESSING, operator=["mover"], team=[1])
    op = AlertOperator(user="mover")
    result = op.operate("reassign", "A1", {"assignee": ["op1"]})
    assert result["result"] is True
    alert = Alert.objects.get(alert_id="A1")
    assert alert.status == AlertStatus.PENDING
    assert alert.operator == ["op1"]


@pytest.mark.django_db
def test_reassign_wrong_status():
    _make_alert(status=AlertStatus.CLOSED, operator=["mover"])
    op = AlertOperator(user="mover")
    result = op.operate("reassign", "A1", {"assignee": ["op1"]})
    assert result["result"] is False


@pytest.mark.django_db
def test_reassign_no_assignee():
    _make_alert(status=AlertStatus.PROCESSING, operator=["mover"])
    op = AlertOperator(user="mover")
    result = op.operate("reassign", "A1", {"assignee": []})
    assert result["result"] is False


# --------------------------------------------------------------------------
# resolve
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_success():
    _make_alert(status=AlertStatus.PROCESSING, operator=["op1"])
    op = AlertOperator(user="op1")
    result = op.operate("resolve", "A1", {"note": "已处理"})
    assert result["result"] is True
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.RESOLVED


@pytest.mark.django_db
def test_resolve_wrong_status():
    _make_alert(status=AlertStatus.PENDING, operator=["op1"])
    op = AlertOperator(user="op1")
    result = op.operate("resolve", "A1", {})
    assert result["result"] is False


@pytest.mark.django_db
def test_resolve_no_permission():
    _make_alert(status=AlertStatus.PROCESSING, operator=["other"])
    op = AlertOperator(user="op1")
    result = op.operate("resolve", "A1", {})
    assert result["result"] is False


@pytest.mark.django_db
def test_assign_with_assignment_id_creates_reminder(sys_user):
    from apps.alerts.models.alert_operator import AlertAssignment, AlertReminderTask

    assignment = AlertAssignment.objects.create(
        name="分派", match_type="all", is_active=True,
        notification_frequency={"0": {"interval_minutes": 30}},
    )
    _make_alert(status=AlertStatus.UNASSIGNED, team=[1], alert_id="A1")
    op = AlertOperator(user="system")
    result = op.operate("assign", "A1", {"assignee": ["op1"], "assignment_id": assignment.id})
    assert result["result"] is True
    assert AlertReminderTask.objects.filter(alert__alert_id="A1").exists()


@pytest.mark.django_db
def test_format_notify_data_no_channel_returns_empty():
    alert = _make_alert(status=AlertStatus.PENDING)
    op = AlertOperator(user="u1")
    # 收口后统一返回 list(sync_notify 期望 list[dict]);无渠道 → 空列表
    assert op.format_notify_data(["op1"], alert) == []


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="c")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="t")
@mock.patch("apps.alerts.service.alter_operator.get_default_notify_params", return_value=("email", 5))
def test_format_notify_data_returns_list_of_params(_mock_chan, _mt, _mc):
    """收口后:配了默认渠道时返回 list[dict](修掉原先返回单 dict 致 sync_notify 崩的 bug)。"""
    alert = _make_alert(status=AlertStatus.PENDING, alert_id="A-NOTIFY")
    op = AlertOperator(user="u1")
    result = op.format_notify_data(["op1", "u1"], alert)  # u1 是操作者自己,应被排除
    assert isinstance(result, list) and len(result) == 1
    assert result[0]["channel_type"] == "email"
    assert result[0]["channel_id"] == 5
    assert result[0]["username_list"] == ["op1"]
    assert result[0]["object_id"] == alert.alert_id


@pytest.mark.django_db
def test_stop_reminder_tasks_noop_when_none():
    alert = _make_alert()
    op = AlertOperator(user="u1")
    op._stop_reminder_tasks(alert)


@pytest.mark.django_db
def test_assign_missing_assignment_id_is_graceful(sys_user):
    from apps.alerts.models.alert_operator import AlertReminderTask

    _make_alert(status=AlertStatus.UNASSIGNED, team=[1], alert_id="A1")
    op = AlertOperator(user="system")
    result = op.operate("assign", "A1", {"assignee": ["op1"], "assignment_id": 999999})
    assert result["result"] is True
    assert not AlertReminderTask.objects.filter(alert__alert_id="A1").exists()


@pytest.mark.django_db
def test_ensure_reminder_tasks_invalid_assignment_id():
    alert = _make_alert()
    op = AlertOperator(user="u1")
    op._ensure_reminder_tasks(alert, assignment_id="notanint")


@pytest.mark.django_db
def test_get_alert_raises_when_missing():
    from django.db import transaction

    op = AlertOperator(user="u1")
    with pytest.raises(Alert.DoesNotExist):
        with transaction.atomic():
            op.get_alert("missing")


def test_is_alert_allowed_none_allows_all():
    op = AlertOperator(user="op1", allowed_alert_ids=None)
    assert op._is_alert_allowed("anything") is True


def test_is_alert_allowed_restricts():
    op = AlertOperator(user="op1", allowed_alert_ids=["A1"])
    assert op._is_alert_allowed("A1") is True
    assert op._is_alert_allowed("A2") is False


# --------------------------------------------------------------------------
# format_assignment_notify_data（auto-dispatch 按策略勾选的 notify_channels）
# --------------------------------------------------------------------------


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="正文")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="标题")
def test_format_assignment_notify_data_builds_from_notify_channels(_mt, _mc):
    from apps.alerts.models.alert_operator import AlertAssignment

    assignment = AlertAssignment.objects.create(
        name="分派", match_type="all", is_active=True,
        notify_channels=[{"id": 9, "channel_type": "nats"}, {"id": 3, "channel_type": "email"}],
    )
    alert = _make_alert(status=AlertStatus.PENDING, alert_id="A-AN", team=[2])
    # 自动分派操作人=系统(SYSTEM_OPERATOR_USER="admin")；策略也分派给 admin，
    # 不能把与操作人同名的收件人过滤掉，否则收件人为空、不发通知。
    op = AlertOperator(user="admin")

    result = op.format_assignment_notify_data(assignment, ["admin", "op1"], alert)

    nats = next(p for p in result if p["channel_type"] == "nats")
    assert nats["channel_id"] == 9
    assert nats["content"] == {"message": "正文", "team": 2, "user_ids": ["admin", "op1"]}
    assert nats["object_id"] == "A-AN"
    email = next(p for p in result if p["channel_type"] == "email")
    assert email["channel_id"] == 3
    assert email["content"] == "正文"
    assert email["username_list"] == ["admin", "op1"]


@pytest.mark.django_db
def test_format_assignment_notify_data_none_returns_empty():
    alert = _make_alert(status=AlertStatus.PENDING, alert_id="A-NF")
    op = AlertOperator(user="system")
    assert op.format_assignment_notify_data(None, ["op1"], alert) == []


@pytest.mark.django_db
def test_format_assignment_notify_data_empty_channels_returns_empty():
    from apps.alerts.models.alert_operator import AlertAssignment

    assignment = AlertAssignment.objects.create(
        name="分派", match_type="all", is_active=True, notify_channels=[],
    )
    alert = _make_alert(status=AlertStatus.PENDING, alert_id="A-EC", team=[2])
    op = AlertOperator(user="system")
    assert op.format_assignment_notify_data(assignment, ["op1"], alert) == []


# --------------------------------------------------------------------------
# _assign_alert 通知分流：auto→notify_channels / manual→默认邮件
# --------------------------------------------------------------------------


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="正文")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="标题")
@mock.patch("apps.alerts.common.notify.dispatcher.enqueue_notifications")
def test_assign_auto_dispatch_notifies_via_notify_channels(mock_enqueue, _mt, _mc, sys_user):
    from apps.alerts.models.alert_operator import AlertAssignment

    assignment = AlertAssignment.objects.create(
        name="分派", match_type="all", is_active=True,
        personnel=["op1"],
        notify_channels=[{"id": 9, "channel_type": "nats"}],
        notification_frequency={"0": {"interval_minutes": 30}},
    )
    _make_alert(status=AlertStatus.UNASSIGNED, team=[1], alert_id="A1")
    op = AlertOperator(user="system")

    result = op.operate("assign", "A1", {"assignee": ["op1"], "assignment_id": assignment.id})

    assert result["result"] is True
    assert mock_enqueue.called
    params = mock_enqueue.call_args.args[0]
    assert len(params) == 1
    nats = next((p for p in params if p["channel_type"] == "nats"), None)
    assert nats is not None, "expected nats channel in enqueued params"
    assert nats["content"] == {"message": "正文", "team": 1, "user_ids": ["op1"]}
    assert all(p["channel_type"] != "email" for p in params)


@pytest.mark.django_db
@mock.patch("apps.alerts.service.alter_operator.get_default_notify_params", return_value=("email", 5))
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="c")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="t")
@mock.patch("apps.alerts.common.notify.dispatcher.enqueue_notifications")
def test_assign_manual_still_uses_default_email(mock_enqueue, _mt, _mc, _chan, sys_user):
    _make_alert(status=AlertStatus.UNASSIGNED, team=[1], alert_id="A1")
    op = AlertOperator(user="system")

    result = op.operate("assign", "A1", {"assignee": ["op1"]})  # 无 assignment_id → manual

    assert result["result"] is True
    assert mock_enqueue.called
    params = mock_enqueue.call_args.args[0]
    assert len(params) == 1
    assert params[0]["channel_type"] == "email" and params[0]["channel_id"] == 5


@pytest.mark.django_db
@mock.patch("apps.alerts.service.alter_operator.get_default_notify_params", return_value=("email", 5))
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="c")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="t")
@mock.patch("apps.alerts.common.notify.dispatcher.enqueue_notifications")
def test_assign_inactive_assignment_falls_back_to_default_email(mock_enqueue, _mt, _mc, _chan, sys_user):
    from apps.alerts.models.alert_operator import AlertAssignment

    # 非活跃策略：_assign_alert 用 is_active=True 查不到 → assignment=None → 回退默认邮件
    assignment = AlertAssignment.objects.create(
        name="分派", match_type="all", is_active=False,
        notify_channels=[{"id": 9, "channel_type": "nats"}],
    )
    _make_alert(status=AlertStatus.UNASSIGNED, team=[1], alert_id="A1")
    op = AlertOperator(user="system")

    result = op.operate("assign", "A1", {"assignee": ["op1"], "assignment_id": assignment.id})

    assert result["result"] is True
    assert mock_enqueue.called
    params = mock_enqueue.call_args.args[0]
    assert len(params) == 1
    assert params[0]["channel_type"] == "email" and params[0]["channel_id"] == 5
