import json

from alibabacloud_dysmsapi20170525 import models as aliyun_sms_models
from alibabacloud_dysmsapi20170525.client import Client as AliyunSmsClient
from alibabacloud_dyvmsapi20170525 import models as aliyun_voice_models
from alibabacloud_dyvmsapi20170525.client import Client as AliyunVoiceClient
from alibabacloud_tea_openapi import models as aliyun_open_api_models
from alibabacloud_tea_util import models as aliyun_util_models
from tencentcloud.common.credential import Credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.retry import NoopRetryer
from tencentcloud.sms.v20210111.sms_client import SmsClient
from tencentcloud.vms.v20200902.vms_client import VmsClient

from apps.system_mgmt.services.cloud_notify.config import TENCENT_REGION
from apps.system_mgmt.services.cloud_notify.delivery import CloudSendOutcome

_ALIYUN_SMS_ENDPOINT = "dysmsapi.aliyuncs.com"
_ALIYUN_VOICE_ENDPOINT = "dyvmsapi.aliyuncs.com"
_PLAY_TIMES = 1


def dispatch_provider(channel_type, config, phone, template_params):
    sender = _SENDERS.get((channel_type, config.get("provider")))
    if sender is None:
        return CloudSendOutcome(status="rejected", reason="unsupported_provider")
    return sender(config, phone, template_params)


def _tencent_profile():
    return ClientProfile(retryer=NoopRetryer())


def _tencent_sms(config, phone, template_params):
    from tencentcloud.sms.v20210111 import models

    request = models.SendSmsRequest()
    request.PhoneNumberSet = [phone]
    request.SmsSdkAppId = config["sdk_app_id"]
    request.TemplateId = config["template_id"]
    request.SignName = config["sign_name"]
    request.TemplateParamSet = [str(item) for item in template_params]
    client = SmsClient(Credential(config["secret_id"], config["secret_key"]), TENCENT_REGION, _tencent_profile())

    def call():
        response = client.SendSms(request)
        status = (response.SendStatusSet or [None])[0]
        request_id = response.RequestId or ""
        if status is not None and status.Code == "Ok":
            return CloudSendOutcome(status="accepted", request_id=request_id, receipt_id=status.SerialNo or "")
        return CloudSendOutcome(status="rejected", request_id=request_id, reason=getattr(status, "Code", "") or "rejected")

    return _call(call)


def _tencent_voice(config, phone, template_params):
    from tencentcloud.vms.v20200902 import models

    request = models.SendTtsVoiceRequest()
    request.TemplateId = config["template_id"]
    request.CalledNumber = phone
    request.VoiceSdkAppid = config["sdk_app_id"]
    request.TemplateParamSet = [str(item) for item in template_params]
    request.PlayTimes = _PLAY_TIMES
    client = VmsClient(Credential(config["secret_id"], config["secret_key"]), TENCENT_REGION, _tencent_profile())

    def call():
        response = client.SendTtsVoice(request)
        request_id = response.RequestId or ""
        call_id = getattr(response.SendStatus, "CallId", "") or ""
        if call_id:
            return CloudSendOutcome(status="accepted", request_id=request_id, receipt_id=call_id)
        return CloudSendOutcome(status="rejected", request_id=request_id, reason="rejected")

    return _call(call)


def _aliyun_runtime():
    return aliyun_util_models.RuntimeOptions(autoretry=False, max_attempts=1)


def _aliyun_sms(config, phone, template_params):
    request = aliyun_sms_models.SendSmsRequest(
        phone_numbers=phone,
        sign_name=config["sign_name"],
        template_code=config["template_code"],
        template_param=json.dumps(template_params, ensure_ascii=False) if template_params else None,
    )
    client = AliyunSmsClient(
        aliyun_open_api_models.Config(
            access_key_id=config["access_key_id"],
            access_key_secret=config["access_key_secret"],
            endpoint=_ALIYUN_SMS_ENDPOINT,
        )
    )

    def call():
        response = client.send_sms_with_options(request, _aliyun_runtime())
        body = response.body
        request_id = getattr(body, "request_id", "") or ""
        if getattr(body, "code", "") == "OK":
            return CloudSendOutcome(status="accepted", request_id=request_id, receipt_id=getattr(body, "biz_id", "") or "")
        return CloudSendOutcome(status="rejected", request_id=request_id, reason=getattr(body, "code", "") or "rejected")

    return _call(call)


def _aliyun_voice(config, phone, template_params):
    show_number = (config.get("called_show_number") or "").strip() or None
    request = aliyun_voice_models.SingleCallByTtsRequest(
        called_number=phone,
        called_show_number=show_number,
        tts_code=config["template_code"],
        tts_param=json.dumps(template_params, ensure_ascii=False) if template_params else None,
        play_times=_PLAY_TIMES,
    )
    client = AliyunVoiceClient(
        aliyun_open_api_models.Config(
            access_key_id=config["access_key_id"],
            access_key_secret=config["access_key_secret"],
            endpoint=_ALIYUN_VOICE_ENDPOINT,
        )
    )

    def call():
        response = client.single_call_by_tts_with_options(request, _aliyun_runtime())
        body = response.body
        request_id = getattr(body, "request_id", "") or ""
        if getattr(body, "code", "") == "OK":
            return CloudSendOutcome(status="accepted", request_id=request_id, receipt_id=getattr(body, "call_id", "") or "")
        return CloudSendOutcome(status="rejected", request_id=request_id, reason=getattr(body, "code", "") or "rejected")

    return _call(call)


_SENDERS = {
    ("sms", "tencent"): _tencent_sms,
    ("voice", "tencent"): _tencent_voice,
    ("sms", "aliyun"): _aliyun_sms,
    ("voice", "aliyun"): _aliyun_voice,
}


def _call(call):
    try:
        return call()
    except TencentCloudSDKException as error:
        if error.code == "ClientNetworkError":
            raise
        return CloudSendOutcome(status="rejected", request_id=error.requestId or "", reason=error.code or "rejected")
    except Exception as error:
        code = getattr(error, "code", None) or ""
        request_id = getattr(error, "request_id", None) or getattr(error, "requestId", None) or ""
        if code or request_id:
            return CloudSendOutcome(status="rejected", request_id=str(request_id), reason=str(code or "rejected"))
        raise
