import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.retry import NoopRetryer

from apps.system_mgmt.services.cloud_notify.providers import dispatch_provider

SECRET = "cloud-secret-sentinel"
PHONE = "+8613800138000"
BODY = "正文-sentinel"


def _tencent_config():
    return {
        "provider": "tencent",
        "secret_id": "AKIDexample",
        "secret_key": SECRET,
        "sdk_app_id": "1400006666",
        "sign_name": "运维平台",
        "template_id": "100001",
    }


def _aliyun_config():
    return {
        "provider": "aliyun",
        "access_key_id": "LTAIexample",
        "access_key_secret": SECRET,
        "sign_name": "运维平台",
        "template_code": "SMS_100001",
        "called_show_number": "",
    }


def test_tencent_sms_maps_accept_and_reject_without_retry():
    config = _tencent_config()
    accepted = SimpleNamespace(RequestId="req-ok", SendStatusSet=[SimpleNamespace(Code="Ok", SerialNo="serial-ok", Message=BODY)])
    rejected = SimpleNamespace(RequestId="req-bad", SendStatusSet=[SimpleNamespace(Code="InvalidParameter", SerialNo="", Message=SECRET)])
    client = SimpleNamespace(SendSms=lambda _req: accepted)

    with patch("apps.system_mgmt.services.cloud_notify.providers.SmsClient", return_value=client) as client_cls:
        outcome = dispatch_provider("sms", config, PHONE, ["标题", BODY])
    assert outcome.status == "accepted"
    assert outcome.request_id == "req-ok"
    assert outcome.receipt_id == "serial-ok"
    _region, profile = client_cls.call_args.args[1:]
    assert _region == "ap-guangzhou"
    assert isinstance(profile.retryer, NoopRetryer)

    sent = {}

    def capture(request):
        sent["request"] = request
        return rejected

    client.SendSms = capture
    with patch("apps.system_mgmt.services.cloud_notify.providers.SmsClient", return_value=client):
        outcome = dispatch_provider("sms", config, PHONE, ["标题", BODY])
    assert outcome.status == "rejected"
    assert outcome.request_id == "req-bad"
    assert outcome.reason == "InvalidParameter"
    assert SECRET not in outcome.reason
    assert sent["request"].PhoneNumberSet == [PHONE]
    assert sent["request"].TemplateParamSet == ["标题", BODY]
    assert sent["request"].SmsSdkAppId == "1400006666"


def test_tencent_voice_plays_once_and_network_error_is_unknown(caplog):
    config = _tencent_config()
    sent = {}

    def capture(request):
        sent["request"] = request
        raise TencentCloudSDKException("ClientNetworkError", f"{SECRET} {PHONE} {BODY}", "req-net")

    client = SimpleNamespace(SendTtsVoice=capture)
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.cloud_notify.providers.VmsClient",
        return_value=client,
    ), pytest.raises(TencentCloudSDKException) as caught:
        dispatch_provider("voice", config, PHONE, ["标题"])

    assert caught.value.code == "ClientNetworkError"
    assert sent["request"].PlayTimes == 1
    assert sent["request"].CalledNumber == PHONE
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []


def test_aliyun_sms_and_voice_use_domestic_endpoints_without_retry():
    sms_response = SimpleNamespace(body=SimpleNamespace(code="OK", message="OK", request_id="req-sms", biz_id="biz-1"))
    voice_response = SimpleNamespace(body=SimpleNamespace(code="isv.BUSINESS_LIMIT", message=SECRET, request_id="req-voice", call_id=""))
    sms_client = SimpleNamespace(send_sms_with_options=lambda request, runtime: sms_response)
    voice_client = SimpleNamespace(single_call_by_tts_with_options=lambda request, runtime: voice_response)
    captured = {}

    def capture_sms(request, runtime):
        captured["sms"] = (request, runtime)
        return sms_response

    def capture_voice(request, runtime):
        captured["voice"] = (request, runtime)
        return voice_response

    sms_client.send_sms_with_options = capture_sms
    voice_client.single_call_by_tts_with_options = capture_voice
    with patch("apps.system_mgmt.services.cloud_notify.providers.AliyunSmsClient", return_value=sms_client) as sms_cls, patch(
        "apps.system_mgmt.services.cloud_notify.providers.AliyunVoiceClient",
        return_value=voice_client,
    ) as voice_cls:
        sms = dispatch_provider("sms", _aliyun_config(), "13800138000", {"content": "正文"})
        voice = dispatch_provider("voice", _aliyun_config(), "13800138000", {"content": "正文"})

    assert sms.status == "accepted"
    assert sms.receipt_id == "biz-1"
    assert sms.request_id == "req-sms"
    assert voice.status == "rejected"
    assert voice.request_id == "req-voice"
    assert voice.reason == "isv.BUSINESS_LIMIT"
    assert SECRET not in voice.reason
    assert sms_cls.call_args.args[0].endpoint == "dysmsapi.aliyuncs.com"
    assert voice_cls.call_args.args[0].endpoint == "dyvmsapi.aliyuncs.com"
    sms_request, sms_runtime = captured["sms"]
    voice_request, voice_runtime = captured["voice"]
    assert sms_runtime.autoretry is False
    assert sms_runtime.max_attempts == 1
    assert voice_runtime.autoretry is False
    assert voice_request.play_times == 1
    assert json.loads(sms_request.template_param) == {"content": "正文"}
    assert voice_request.called_show_number in (None, "")
