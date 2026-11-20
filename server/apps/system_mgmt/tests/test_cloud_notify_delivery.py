import logging
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password

from apps.core.logger import SafeLogException
from apps.system_mgmt.models import Channel, User
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt.nats.channels import send_msg_with_channel
from apps.system_mgmt.services.cloud_notify.delivery import CloudSendOutcome

pytestmark = pytest.mark.django_db

_FINISHED = "event=cloud_notification_finished channel_id=%s accepted=%s unknown=%s rejected=%s"
_FAILED = "event=cloud_notification_failed channel_id=%s failed_stage=%s error_type=%s"
_REJECTED = "event=cloud_notification_rejected channel_id=%s failed_stage=%s error_type=%s count=%s"
SECRET = "cloud-secret-sentinel"
PHONE = "13800138000"
TITLE = "告警\n标题-sentinel"
BODY = "正文-sentinel"


def _user(**kwargs):
    defaults = dict(
        username="cloud-user",
        display_name="云用户",
        email="cloud-user@example.com",
        password=make_password("secret-pass"),
        domain="domain.com",
        group_list=[1],
        phone=PHONE,
    )
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def _sms_channel():
    config = {
        "provider": "tencent",
        "secret_id": "AKIDexample",
        "secret_key": SECRET,
        "sdk_app_id": "1400006666",
        "sign_name": "运维平台",
        "template_id": "100001",
        "parameters": [
            {"source": "title", "name": "", "value": ""},
            {"source": "content", "name": "", "value": ""},
        ],
    }
    Channel.encrypt_field("secret_key", config)
    return Channel.objects.create(name="短信", channel_type=ChannelChoices.SMS, description="告警短信", team=[1], config=config)


def _outcome(status, request_id="", receipt_id="", reason=""):
    return CloudSendOutcome(status=status, request_id=request_id, receipt_id=receipt_id, reason=reason)


def test_sms_skips_missing_phone_and_accepts_the_other_recipient():
    channel = _sms_channel()
    missing = _user(username="no-phone", display_name="无号用户", email="no-phone@example.com", phone="")
    ready = _user(username="ready", display_name="有号用户", email="ready@example.com")

    with patch("apps.system_mgmt.services.cloud_notify.delivery.call_provider", return_value=_outcome("accepted", "req-1", "serial-1")) as send:
        result = send_msg_with_channel(channel.id, TITLE, BODY, [missing.id, ready.id], template_params=[TITLE, BODY])

    assert send.call_count == 1
    channel_type, config, phone, params = send.call_args.args
    assert channel_type == ChannelChoices.SMS
    assert config["secret_key"] == SECRET
    assert phone == f"+86{PHONE}"
    assert params == ["告警 标题-sentinel", "正文-sentinel"]
    assert result["result"] is False
    assert result["retryable"] is False
    assert "无号用户" in result["message"]
    assert "没有可用手机号" in result["message"]
    assert SECRET not in result["message"]
    assert PHONE not in result["message"]
    by_user = {item["user_id"]: item for item in result["recipients"]}
    assert by_user[missing.id]["status"] == "not_sent"
    assert by_user[ready.id] == {
        "user_id": ready.id,
        "status": "accepted",
        "request_id": "req-1",
        "receipt_id": "serial-1",
        "reason": "",
    }


def test_sms_maps_provider_accept_reject_and_network_outcomes():
    channel = _sms_channel()
    accepted = _user(username="accepted", display_name="受理", email="accepted@example.com", phone="13800138001")
    rejected = _user(username="rejected", display_name="拒绝", email="rejected@example.com", phone="13800138002")
    unknown = _user(username="unknown", display_name="未知", email="unknown@example.com", phone="13800138003")
    outcomes = {
        "+8613800138001": _outcome("accepted", "req-ok", "serial-ok"),
        "+8613800138002": _outcome("rejected", "req-bad", "", "InvalidParameter"),
        "+8613800138003": _outcome("unknown", "req-net", "", ""),
    }

    with patch("apps.system_mgmt.services.cloud_notify.delivery.call_provider", side_effect=lambda *_args: outcomes[_args[2]]):
        result = send_msg_with_channel(channel.id, "标题", "正文", [accepted.id, rejected.id, unknown.id], template_params=["标题", "正文"])

    assert result["result"] is False
    assert result["retryable"] is False
    by_user = {item["user_id"]: item for item in result["recipients"]}
    assert by_user[accepted.id]["status"] == "accepted"
    assert by_user[accepted.id]["receipt_id"] == "serial-ok"
    assert by_user[rejected.id]["status"] == "rejected"
    assert by_user[rejected.id]["request_id"] == "req-bad"
    assert "InvalidParameter" in by_user[rejected.id]["reason"]
    assert by_user[unknown.id]["status"] == "unknown"
    assert by_user[unknown.id]["request_id"] == "req-net"
    assert "拒绝" in result["message"]
    assert "未知" in result["message"]


def test_sms_provider_rejection_logs_warning_by_code(caplog):
    channel = _sms_channel()
    first = _user(username="reject-one", display_name="拒绝一", email="reject-one@example.com", phone="13800138001")
    second = _user(username="reject-two", display_name="拒绝二", email="reject-two@example.com", phone="13800138002")
    leaked = _user(username="reject-leak", display_name="拒绝三", email="reject-leak@example.com", phone="13800138003")
    accepted = _user(username="accepted-user", display_name="受理", email="accepted-user@example.com", phone="13800138004")
    leak = f"leak {SECRET} {PHONE} {TITLE}"
    outcomes = {
        "+8613800138001": _outcome("rejected", "req-1", "", "isv.SMS_TEMPLATE_ILLEGAL"),
        "+8613800138002": _outcome("rejected", "req-2", "", "isv.SMS_TEMPLATE_ILLEGAL"),
        "+8613800138003": _outcome("rejected", "req-3", "", leak),
        "+8613800138004": _outcome("accepted", "req-ok", "serial-ok"),
    }

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.cloud_notify.delivery.call_provider",
        side_effect=lambda *_args: outcomes[_args[2]],
    ):
        result = send_msg_with_channel(channel.id, TITLE, BODY, [first.id, second.id, leaked.id, accepted.id], template_params=["甲", "乙"])

    assert result["result"] is False
    assert result["retryable"] is False
    by_user = {item["user_id"]: item for item in result["recipients"]}
    assert by_user[first.id]["status"] == "rejected"
    assert "isv.SMS_TEMPLATE_ILLEGAL" in by_user[first.id]["reason"]
    assert leak in by_user[leaked.id]["reason"]
    assert by_user[accepted.id]["status"] == "accepted"
    warnings = [record for record in caplog.records if record.msg == _REJECTED]
    assert [(record.args, record.levelno, record.exc_info) for record in warnings] == [
        ((channel.id, "provider_rejected", "isv.SMS_TEMPLATE_ILLEGAL", 2), logging.WARNING, None),
        ((channel.id, "provider_rejected", "rejected", 1), logging.WARNING, None),
    ]
    finished = [record for record in caplog.records if record.msg == _FINISHED]
    assert len(finished) == 1
    assert finished[0].args == (channel.id, 1, 0, 3)
    assert finished[0].levelno == logging.INFO
    formatted = "\n".join(logging.Formatter("%(levelname)s %(message)s").format(record) for record in warnings + finished)
    assert "WARNING event=cloud_notification_rejected" in formatted
    assert "isv.SMS_TEMPLATE_ILLEGAL" in formatted
    assert "INFO event=cloud_notification_finished" in formatted
    assert SECRET not in formatted
    assert PHONE not in formatted
    assert "标题-sentinel" not in formatted
    assert "正文-sentinel" not in formatted
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


def test_sms_provider_exception_is_unknown_and_logs_one_sanitized_error(caplog):
    channel = _sms_channel()
    user = _user()

    caught = {}

    def explode(*_args):
        error = RuntimeError(f"{SECRET} {PHONE} {TITLE} {BODY}")
        caught["error"] = error
        raise error

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.cloud_notify.delivery.call_provider",
        side_effect=explode,
    ):
        result = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params=["标题", "正文"])

    error = caught["error"]
    assert str(error) == f"{SECRET} {PHONE} {TITLE} {BODY}"
    assert result["result"] is False
    assert result["retryable"] is False
    assert result["recipients"][0]["status"] == "unknown"
    records = [record for record in caplog.records if record.msg == _FAILED]
    assert len(records) == 1
    record = records[0]
    assert record.args == (channel.id, "call_provider", "RuntimeError")
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[1] is not error
    assert record.exc_info[2] is error.__traceback__
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    assert SECRET not in formatted
    assert PHONE not in formatted
    assert "标题-sentinel" not in formatted
    assert "正文-sentinel" not in formatted
    finished = [record for record in caplog.records if record.msg == _FINISHED]
    assert finished == []


def test_sms_rejects_template_params_that_do_not_match_the_channel():
    channel = _sms_channel()
    user = _user()

    with patch("apps.system_mgmt.services.cloud_notify.delivery.call_provider") as send:
        missing = send_msg_with_channel(channel.id, TITLE, BODY, [user.id])
        extra = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params=["只有一个"])
        wrong_shape = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params={"1": "4370"})

    assert send.call_count == 0
    assert missing["result"] is False
    assert missing["retryable"] is False
    assert missing["recipients"] == []
    assert "不一致" in missing["message"]
    assert extra["message"] == missing["message"]
    assert "字符串数组" in wrong_shape["message"]


def test_aliyun_sms_sends_named_template_params_and_ignores_title():
    config = {
        "provider": "aliyun",
        "access_key_id": "LTAIexample",
        "access_key_secret": SECRET,
        "sign_name": "运维平台",
        "template_code": "SMS_1",
        "parameters": [{"name": "scene"}, {"name": "level"}],
    }
    Channel.encrypt_field("access_key_secret", config)
    channel = Channel.objects.create(name="阿里云短信", channel_type=ChannelChoices.SMS, description="告警短信", team=[1], config=config)
    user = _user(username="aliyun-user", email="aliyun-user@example.com")

    with patch("apps.system_mgmt.services.cloud_notify.delivery.call_provider", return_value=_outcome("accepted", "req-1", "biz-1")) as send:
        wrong_shape = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params=["磁盘", "严重"])
        result = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params={"level": "严重", "scene": "告警\n平台"})

    assert "JSON 对象" in wrong_shape["message"]
    assert result["result"] is True
    assert send.call_count == 1
    assert send.call_args.args[3] == {"scene": "告警 平台", "level": "严重"}


def test_saved_test_values_do_not_fill_a_formal_send():
    channel = _sms_channel()
    channel.config["parameters"] = [{"name": "", "test_value": "磁盘"}, {"name": "", "test_value": "严重"}]
    channel.save(update_fields=["config"])
    user = _user(username="sample-user", email="sample-user@example.com")

    with patch("apps.system_mgmt.services.cloud_notify.delivery.call_provider", return_value=_outcome("accepted", "req-1", "serial-1")) as send:
        missing = send_msg_with_channel(channel.id, TITLE, BODY, [user.id])
        sent = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params=["甲", "乙"])

    assert missing["result"] is False
    assert "不一致" in missing["message"]
    assert sent["result"] is True
    assert send.call_count == 1
    assert send.call_args.args[3] == ["甲", "乙"]


def test_sms_without_variables_omits_template_params():
    channel = _sms_channel()
    channel.config["parameters"] = []
    channel.save(update_fields=["config"])
    user = _user(username="plain-user", email="plain-user@example.com")

    with patch("apps.system_mgmt.services.cloud_notify.delivery.call_provider", return_value=_outcome("accepted", "req-1", "serial-1")) as send:
        result = send_msg_with_channel(channel.id, TITLE, BODY, [user.id], template_params={"scene": "告警"})

    assert send.call_count == 0
    assert result["result"] is False
    assert "没有变量" in result["message"]
