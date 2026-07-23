"""NotifyResultService 通知结果落库覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：下游通知系统返回不归一化，约定仅 result=False 记失败，
缺省视为成功；通知结果需落库到 NotifyResult。
"""

import pydantic.root_model  # noqa

import pytest

from apps.alerts.constants.constants import NotifyResultStatus
from apps.alerts.models.alert_operator import NotifyResult
from apps.alerts.service.notify_service import NotifyResultService


# --------------------------------------------------------------------------
# format_notify_result：缺省成功，仅显式 False 失败，异常兜底失败
# --------------------------------------------------------------------------


def test_format_notify_result_default_success_when_key_missing():
    svc = NotifyResultService(
        notify_users=["op1"], channel="email", notify_result={}, notify_object="A1"
    )
    assert svc.format_notify_result() == NotifyResultStatus.SUCCESS


def test_format_notify_result_explicit_true_success():
    svc = NotifyResultService(
        notify_users=["op1"], channel="email", notify_result={"result": True}, notify_object="A1"
    )
    assert svc.format_notify_result() == NotifyResultStatus.SUCCESS


def test_format_notify_result_explicit_false_failed():
    svc = NotifyResultService(
        notify_users=["op1"], channel="email", notify_result={"result": False}, notify_object="A1"
    )
    assert svc.format_notify_result() == NotifyResultStatus.FAILED


@pytest.mark.parametrize(
    ("notify_result", "expected"),
    [
        ({"errcode": 0}, NotifyResultStatus.SUCCESS),
        ({"errcode": "0"}, NotifyResultStatus.SUCCESS),
        ({"errcode": 40013}, NotifyResultStatus.FAILED),
        ({"code": 0}, NotifyResultStatus.SUCCESS),
        ({"code": "0"}, NotifyResultStatus.SUCCESS),
        ({"code": 19002}, NotifyResultStatus.FAILED),
    ],
)
def test_format_notify_result_supports_channel_code_conventions(notify_result, expected):
    svc = NotifyResultService(
        notify_users=["op1"], channel="bot", notify_result=notify_result, notify_object="A1"
    )
    assert svc.format_notify_result() == expected


def test_format_notify_result_explicit_result_takes_precedence_over_code():
    svc = NotifyResultService(
        notify_users=["op1"],
        channel="bot",
        notify_result={"result": True, "errcode": 40013, "code": 19002},
        notify_object="A1",
    )
    assert svc.format_notify_result() == NotifyResultStatus.SUCCESS


def test_format_notify_result_non_dict_falls_back_to_failed():
    # notify_result 不是 dict 时 .get 抛 AttributeError，被 except 捕获并记失败
    svc = NotifyResultService(
        notify_users=["op1"], channel="email", notify_result="bad", notify_object="A1"
    )
    assert svc.format_notify_result() == NotifyResultStatus.FAILED


def test_format_failure_reason_extracts_sanitizes_and_truncates_message():
    svc = NotifyResultService(
        notify_users=["op1"],
        channel="webhook",
        notify_result={
            "result": False,
            "message": (
                "request https://notify.example/send?token=visible&room=ops "
                "token=abc123 password: p@ss secret=top-secret "
                + "x" * 600
            ),
        },
        notify_object="A1",
    )

    reason = svc.format_failure_reason()

    assert reason is not None
    assert len(reason) == 500
    assert "visible" not in reason
    assert "abc123" not in reason
    assert "p@ss" not in reason
    assert "top-secret" not in reason
    assert "token=***" in reason
    assert "password: ***" in reason


def test_format_failure_reason_uses_supported_fields_and_safe_fallback():
    with_errmsg = NotifyResultService(
        notify_users=["op1"],
        channel="wechat",
        notify_result={"errcode": 1, "errmsg": "invalid receiver"},
        notify_object="A1",
    )
    without_reason = NotifyResultService(
        notify_users=["op1"], channel="wechat", notify_result={"errcode": 1}, notify_object="A1"
    )

    assert with_errmsg.format_failure_reason() == "invalid receiver"
    assert without_reason.format_failure_reason() == "通知失败，渠道未返回具体原因"


def test_format_failure_reason_redacts_quoted_and_api_secret_values():
    svc = NotifyResultService(
        notify_users=["op1"],
        channel="webhook",
        notify_result={
            "result": False,
            "error": 'api_key: "private-key" token="private-token"',
        },
        notify_object="A1",
    )

    reason = svc.format_failure_reason()

    assert reason is not None
    assert "private-key" not in reason
    assert "private-token" not in reason
    assert reason.count("***") == 2


def test_format_failure_reason_is_empty_for_success():
    svc = NotifyResultService(
        notify_users=["op1"],
        channel="email",
        notify_result={"result": True, "message": "accepted"},
        notify_object="A1",
    )
    assert svc.format_failure_reason() is None


# --------------------------------------------------------------------------
# save_notify_result：真实落库，校验字段契约
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_save_notify_result_persists_success_with_object():
    svc = NotifyResultService(
        notify_users=["op1", "op2"],
        channel="wechat",
        notify_result={"result": True},
        notify_object="A100",
        notify_action_object="alert",
    )
    svc.save_notify_result()

    row = NotifyResult.objects.get(notify_object="A100")
    assert row.notify_people == ["op1", "op2"]
    assert row.notify_channel == "wechat"
    assert row.notify_result == NotifyResultStatus.SUCCESS
    assert row.notify_type == "alert"


@pytest.mark.django_db
def test_save_notify_result_persists_failed_without_object():
    # notify_object 为空字符串 → 视为 falsy，不覆盖 notify_object 字段（保持默认）
    svc = NotifyResultService(
        notify_users=["op1"],
        channel="sms",
        notify_result={"result": False},
        notify_object="",
        notify_action_object="incident",
    )
    svc.save_notify_result()

    row = NotifyResult.objects.filter(notify_channel="sms").first()
    assert row is not None
    assert row.notify_result == NotifyResultStatus.FAILED
    assert row.failure_reason == "通知失败，渠道未返回具体原因"
    assert row.notify_type == "incident"
    # notify_object 未被显式赋值，保持模型默认（None / 空）
    assert not row.notify_object


@pytest.mark.django_db
def test_save_notify_result_default_action_object_is_alert():
    svc = NotifyResultService(
        notify_users=["op1"], channel="email", notify_result={}, notify_object="A200"
    )
    svc.save_notify_result()
    row = NotifyResult.objects.get(notify_object="A200")
    assert row.notify_type == "alert"
    assert row.notify_result == NotifyResultStatus.SUCCESS
