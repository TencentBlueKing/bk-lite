import pydantic.root_model  # noqa

import pytest

from apps.system_mgmt.models import Channel
from apps.system_mgmt.models.channel import ChannelChoices
from apps.system_mgmt.utils import channel_utils

pytestmark = pytest.mark.django_db


# ----------------------- is_valid_webhook_url (纯函数) -----------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc", True),
        ("https://open.feishu.cn/open-apis/bot/v2/hook/xxx", True),
        ("http://oapi.dingtalk.com/robot/send?access_token=t", True),
        ("https://open.larksuite.com/hook", True),
        # 不在白名单
        ("https://evil.com/hook", False),
        ("https://qyapi.weixin.qq.com.evil.com/x", False),
        # 协议非法
        ("ftp://qyapi.weixin.qq.com/x", False),
        ("file:///etc/passwd", False),
        # 空
        ("", False),
        (None, False),
        # 含反斜杠绕过
        ("https://qyapi.weixin.qq.com\\@evil.com/x", False),
        # 含 userinfo @
        ("https://user@evil.com/x", False),
        # 编码绕过 hostname
        ("https://qyapi%2eweixin.qq.com/x", False),
    ],
)
def test_is_valid_webhook_url(url, expected):
    assert channel_utils.is_valid_webhook_url(url) is expected


# ----------------------- _replace_placeholder (纯函数) -----------------------


def test_replace_placeholder_嵌套结构():
    template = {"text": "{{content}}", "nested": {"a": ["{{content}}", "static"]}, "num": 5}
    out = channel_utils._replace_placeholder(template, "{{content}}", "你好")
    assert out["text"] == "你好"
    assert out["nested"]["a"] == ["你好", "static"]
    assert out["num"] == 5  # 非字符串原样返回


# ----------------------- send_by_wecom_bot -----------------------


def _make_channel(channel_type, config):
    obj = Channel(name="t", channel_type=channel_type, config=config, description="")
    return obj


def test_send_by_wecom_bot_合法url成功(mocker):
    ch = _make_channel(
        ChannelChoices.ENTERPRISE_WECHAT_BOT,
        {"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=k"},
    )
    fake_resp = mocker.Mock()
    fake_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", return_value=fake_resp)

    result = channel_utils.send_by_wecom_bot(ch, "正文", ["张三", "李四"])

    assert result == {"errcode": 0, "errmsg": "ok"}
    # 校验拼装的 payload: markdown 含 @张三 @李四
    _, kwargs = post.call_args
    assert kwargs["json"]["msgtype"] == "markdown"
    assert "@张三" in kwargs["json"]["markdown"]["content"]
    assert "正文" in kwargs["json"]["markdown"]["content"]
    assert post.call_args[0][0].startswith("https://qyapi.weixin.qq.com")


def test_send_by_wecom_bot_bot_key拼出url(mocker):
    ch = _make_channel(ChannelChoices.ENTERPRISE_WECHAT_BOT, {"bot_key": "thekey"})
    fake_resp = mocker.Mock()
    fake_resp.json.return_value = {"errcode": 0}
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", return_value=fake_resp)

    channel_utils.send_by_wecom_bot(ch, "hi", [])

    assert "key=thekey" in post.call_args[0][0]


def test_send_by_wecom_bot_非法域名被ssrf拦截(mocker):
    ch = _make_channel(ChannelChoices.ENTERPRISE_WECHAT_BOT, {"webhook_url": "https://evil.com/x"})
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post")

    result = channel_utils.send_by_wecom_bot(ch, "hi", [])

    assert result["result"] is False
    assert "allowlist" in result["message"]
    post.assert_not_called()


def test_send_by_wecom_bot_请求异常(mocker):
    ch = _make_channel(ChannelChoices.ENTERPRISE_WECHAT_BOT, {"webhook_url": "https://qyapi.weixin.qq.com/x"})
    mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", side_effect=RuntimeError("boom"))

    result = channel_utils.send_by_wecom_bot(ch, "hi", [])

    assert result == {"result": False, "message": "failed to send bot message"}


# ----------------------- send_by_feishu_bot -----------------------


def test_send_by_feishu_bot_无url():
    ch = _make_channel(ChannelChoices.FEISHU_BOT, {})
    result = channel_utils.send_by_feishu_bot(ch, "标题", "正文", [])
    assert result["result"] is False
    assert "webhook_url" in result["message"]


def test_send_by_feishu_bot_带签名(mocker):
    ch = _make_channel(
        ChannelChoices.FEISHU_BOT,
        {"webhook_url": "https://open.feishu.cn/hook", "sign_secret": "s3cr3t"},
    )
    fake_resp = mocker.Mock()
    fake_resp.json.return_value = {"code": 0}
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", return_value=fake_resp)

    result = channel_utils.send_by_feishu_bot(ch, "标题", "正文", ["王五"])

    assert result == {"code": 0}
    payload = post.call_args[1]["json"]
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "标题"
    assert "sign" in payload and "timestamp" in payload
    assert "@王五" in payload["card"]["elements"][0]["content"]


def test_send_by_feishu_bot_非法域名(mocker):
    ch = _make_channel(ChannelChoices.FEISHU_BOT, {"webhook_url": "http://127.0.0.1/x"})
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post")
    result = channel_utils.send_by_feishu_bot(ch, "t", "c", [])
    assert result["result"] is False
    post.assert_not_called()


# ----------------------- send_by_dingtalk_bot -----------------------


def test_send_by_dingtalk_bot_无url():
    ch = _make_channel(ChannelChoices.DINGTALK_BOT, {})
    result = channel_utils.send_by_dingtalk_bot(ch, "t", "c", [])
    assert result["result"] is False


def test_send_by_dingtalk_bot_带签名拼到url(mocker):
    ch = _make_channel(
        ChannelChoices.DINGTALK_BOT,
        {"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=t", "sign_secret": "ss"},
    )
    fake_resp = mocker.Mock()
    fake_resp.json.return_value = {"errcode": 0}
    post = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.post", return_value=fake_resp)

    result = channel_utils.send_by_dingtalk_bot(ch, "标题", "正文", [])

    assert result == {"errcode": 0}
    called_url = post.call_args[0][0]
    assert "timestamp=" in called_url and "sign=" in called_url
    payload = post.call_args[1]["json"]
    assert payload["msgtype"] == "markdown"
    assert payload["markdown"]["title"] == "标题"


# ----------------------- send_by_custom_webhook -----------------------


def test_send_by_custom_webhook_无url():
    ch = _make_channel(ChannelChoices.CUSTOM_WEBHOOK, {})
    result = channel_utils.send_by_custom_webhook(ch, "c", [])
    assert result["result"] is False


def test_send_by_custom_webhook_json模板替换(mocker):
    ch = _make_channel(
        ChannelChoices.CUSTOM_WEBHOOK,
        {
            "webhook_url": "https://oapi.dingtalk.com/x",
            "body_template": '{"msg": "{{content}}"}',
            "headers": '{"X-Token": "abc"}',
            "request_method": "post",
        },
    )
    fake_resp = mocker.Mock()
    fake_resp.json.return_value = {"ok": 1}
    req = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.request", return_value=fake_resp)

    result = channel_utils.send_by_custom_webhook(ch, "告警内容", [])

    assert result == {"ok": 1}
    args, kwargs = req.call_args
    assert args[0] == "POST"  # 大写转换
    assert kwargs["json"] == {"msg": "告警内容"}
    assert kwargs["headers"]["X-Token"] == "abc"


def test_send_by_custom_webhook_非json模板走文本分支(mocker):
    ch = _make_channel(
        ChannelChoices.CUSTOM_WEBHOOK,
        {
            "webhook_url": "https://oapi.dingtalk.com/x",
            "body_template": "raw text {{content}}",
            "headers": "not-json",
        },
    )
    fake_resp = mocker.Mock()
    fake_resp.json.return_value = {"ok": 1}
    req = mocker.patch("apps.system_mgmt.utils.channel_utils.requests.request", return_value=fake_resp)

    result = channel_utils.send_by_custom_webhook(ch, "X", ["u1"])

    assert result == {"ok": 1}
    args, kwargs = req.call_args
    # body 非 json -> data 字节流, 默认 Content-Type text/plain
    assert "data" in kwargs
    assert kwargs["headers"]["Content-Type"] == "text/plain"
    assert b"raw text X" in kwargs["data"]


def test_send_by_custom_webhook_请求异常(mocker):
    ch = _make_channel(
        ChannelChoices.CUSTOM_WEBHOOK,
        {"webhook_url": "https://oapi.dingtalk.com/x", "body_template": '{"a":"{{content}}"}'},
    )
    mocker.patch("apps.system_mgmt.utils.channel_utils.requests.request", side_effect=RuntimeError("x"))
    result = channel_utils.send_by_custom_webhook(ch, "c", [])
    assert result == {"result": False, "message": "failed to send custom webhook message"}


# ----------------------- send_email_to_user -----------------------


def test_send_email_to_user_成功(mocker):
    config = {
        "mail_sender": "from@x.com",
        "smtp_server": "smtp.x.com",
        "port": 25,
        "smtp_user": "u",
        "smtp_pwd": "p",
    }
    fake_server = mocker.Mock()
    smtp = mocker.patch("apps.system_mgmt.utils.channel_utils.smtplib.SMTP", return_value=fake_server)

    result = channel_utils.send_email_to_user(config, "<b>hi</b>", ["a@x.com", "b@x.com"], "主题")

    assert result == {"result": True, "message": "Successfully sent email"}
    smtp.assert_called_once_with("smtp.x.com", 25)
    fake_server.login.assert_called_once_with("u", "p")
    fake_server.send_message.assert_called_once()
    fake_server.quit.assert_called_once()


def test_send_email_to_user_ssl与tls与附件(mocker):
    config = {
        "mail_sender": "from@x.com",
        "smtp_server": "smtp.x.com",
        "port": 465,
        "smtp_user": "u",
        "smtp_pwd": "p",
        "smtp_usessl": True,
        "smtp_usetls": True,
    }
    fake_server = mocker.Mock()
    ssl = mocker.patch("apps.system_mgmt.utils.channel_utils.smtplib.SMTP_SSL", return_value=fake_server)
    import base64

    attachments = [
        {"filename": "中文.txt", "content": base64.b64encode(b"hello").decode()},
        {"filename": "raw.bin", "data": b"\x00\x01"},
        {"filename": "skip"},  # 无 content/data -> continue
    ]

    result = channel_utils.send_email_to_user(config, "body", ["a@x.com"], "主题", attachments)

    assert result["result"] is True
    ssl.assert_called_once_with("smtp.x.com", 465)
    fake_server.starttls.assert_called_once()


def test_send_email_to_user_异常(mocker):
    config = {"mail_sender": "f", "smtp_server": "s", "port": 25, "smtp_user": "u", "smtp_pwd": "p"}
    mocker.patch("apps.system_mgmt.utils.channel_utils.smtplib.SMTP", side_effect=OSError("conn refused"))
    result = channel_utils.send_email_to_user(config, "b", ["a@x.com"], "t")
    assert result["result"] is False
    assert "conn refused" in result["message"]


# ----------------------- send_nats_message -----------------------


def test_send_nats_message_缺配置():
    ch = _make_channel(ChannelChoices.NATS, {"namespace": "", "method_name": ""})
    result = channel_utils.send_nats_message(ch, {"x": 1})
    assert result["result"] is False
    assert "namespace" in result["message"]


def test_send_nats_message_trigger_workflow缺bot(mocker):
    ch = _make_channel(
        ChannelChoices.NATS,
        {"namespace": "ns", "method_name": "trigger_workflow_by_nats", "bot_id": None, "node_id": ""},
    )
    result = channel_utils.send_nats_message(ch, {"x": 1})
    assert result["result"] is False
    assert "bot_id" in result["message"]


def test_send_nats_message_成功透传payload(mocker):
    ch = _make_channel(
        ChannelChoices.NATS,
        {"namespace": "ns", "method_name": "trigger_workflow_by_nats", "bot_id": 7, "node_id": "n1", "timeout": 30},
    )
    req = mocker.patch(
        "apps.system_mgmt.utils.channel_utils.nats_client.request_sync",
        return_value={"result": True, "data": "ok"},
    )

    result = channel_utils.send_nats_message(ch, {"content": "x"})

    assert result == {"result": True, "data": "ok"}
    args, kwargs = req.call_args
    assert args == ("ns", "trigger_workflow_by_nats")
    assert kwargs["_timeout"] == 30
    assert kwargs["bot_id"] == 7 and kwargs["node_id"] == "n1"
    assert kwargs["content"] == "x"


def test_send_nats_message_异常(mocker):
    ch = _make_channel(ChannelChoices.NATS, {"namespace": "ns", "method_name": "do"})
    mocker.patch(
        "apps.system_mgmt.utils.channel_utils.nats_client.request_sync",
        side_effect=RuntimeError("nats down"),
    )
    result = channel_utils.send_nats_message(ch, {})
    assert result["result"] is False
    assert "nats down" in result["message"]
