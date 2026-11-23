import re
from collections import Counter
from dataclasses import dataclass

from apps.core.logger import safe_exception_info
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import User
from apps.system_mgmt.services.cloud_notify.config import match_template_params, runtime_config, validate_cloud_config
from apps.system_mgmt.utils.i18n import system_mgmt_message

_FINISHED = "event=cloud_notification_finished channel_id=%s accepted=%s unknown=%s rejected=%s"
_FAILED = "event=cloud_notification_failed channel_id=%s failed_stage=%s error_type=%s"
_REJECTED = "event=cloud_notification_rejected channel_id=%s failed_stage=%s error_type=%s count=%s"
_PROVIDER_ERROR_CODE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_STATUSES = {"accepted", "rejected", "unknown"}


@dataclass
class CloudSendOutcome:
    status: str
    request_id: str = ""
    receipt_id: str = ""
    reason: str = ""


def call_provider(channel_type, config, phone, template_params):
    """交给厂商。测试替换这个边界，真实实现留在适配器里。"""
    from apps.system_mgmt.services.cloud_notify.providers import dispatch_provider

    return dispatch_provider(channel_type, config, phone, template_params)


def send_cloud_notification(channel, title, content, receivers, template_params=None):
    """title 和 content 留给共用发送入口，不填入云模板变量。"""
    del title, content
    config = runtime_config(channel)
    if _secrets_unreadable(channel, config):
        return _stopped(system_mgmt_message(None, "error.cloud_secret_unreadable"))
    errors = validate_cloud_config(channel.channel_type, config)
    if errors:
        return _stopped(system_mgmt_message(None, "error.cloud_config_incomplete"))
    people = _receiver_users(receivers)
    if not people:
        return _stopped(system_mgmt_message(None, "error.cloud_no_recipients"))

    params, error_key = match_template_params(config, template_params)
    if error_key:
        return _stopped(system_mgmt_message(None, error_key))
    recipients = []
    provider_called = False
    provider_failed = False
    rejected_codes = Counter()
    for user_id, user in people:
        if user is None:
            recipients.append(_recipient(user_id, "not_sent", reason=system_mgmt_message(None, "error.cloud_user_missing")))
            continue
        phone_raw = (user.phone or "").strip()
        if not phone_raw:
            recipients.append(_recipient(user.id, "not_sent", reason=system_mgmt_message(None, "error.cloud_phone_missing")))
            continue
        phone = _provider_phone(phone_raw, config.get("provider"))
        if not phone:
            recipients.append(_recipient(user.id, "not_sent", reason=system_mgmt_message(None, "error.cloud_phone_unusable")))
            continue
        provider_called = True
        try:
            outcome = call_provider(channel.channel_type, config, phone, params)
        except Exception as error:
            provider_failed = True
            logger.error(_FAILED, channel.id, "call_provider", type(error).__name__, exc_info=safe_exception_info(error))
            recipients.append(_recipient(user.id, "unknown", reason=system_mgmt_message(None, "error.cloud_send_unknown")))
            continue
        if outcome.status == "rejected":
            rejected_codes[_provider_error_code(outcome.reason)] += 1
        recipients.append(_from_outcome(user.id, outcome))

    for code, count in sorted(rejected_codes.items()):
        logger.warning(_REJECTED, channel.id, "provider_rejected", code, count)
    if provider_called and not provider_failed:
        accepted = sum(item["status"] == "accepted" for item in recipients)
        unknown = sum(item["status"] == "unknown" for item in recipients)
        logger.info(_FINISHED, channel.id, accepted, unknown, sum(rejected_codes.values()))
    return _result(recipients, people)


def _provider_error_code(reason):
    code = str(reason or "").strip()
    if _PROVIDER_ERROR_CODE.fullmatch(code):
        return code
    return "rejected"


def _stopped(message):
    return {"result": False, "retryable": False, "message": message, "recipients": []}


def _result(recipients, people):
    names = {user.id: _person_name(user) for _user_id, user in people if user is not None}
    failed = [item for item in recipients if item["status"] != "accepted"]
    if not failed:
        return {"result": True, "retryable": False, "message": "success", "recipients": recipients}
    message = "；".join(f"{names.get(item['user_id'], item['user_id'])}：{item['reason']}" for item in failed)
    return {"result": False, "retryable": False, "message": message, "recipients": recipients}


def _from_outcome(user_id, outcome):
    status = outcome.status if outcome.status in _STATUSES else "unknown"
    reason = outcome.reason or ""
    if status == "rejected":
        reason = system_mgmt_message(None, "error.cloud_send_rejected")
        if outcome.reason:
            reason = f"{reason}（{outcome.reason}）"
    elif status == "unknown" and not reason:
        reason = system_mgmt_message(None, "error.cloud_send_unknown")
    elif status == "accepted":
        reason = ""
    return _recipient(user_id, status, outcome.request_id, outcome.receipt_id, reason)


def _recipient(user_id, status, request_id="", receipt_id="", reason=""):
    return {
        "user_id": user_id,
        "status": status,
        "request_id": request_id or "",
        "receipt_id": receipt_id or "",
        "reason": reason or "",
    }


def _receiver_users(receivers):
    if not receivers:
        return []
    if all(isinstance(item, int) or (isinstance(item, str) and item.isdigit()) for item in receivers):
        ids = [int(item) for item in receivers]
        found = {user.id: user for user in User.objects.filter(id__in=ids)}
        return [(int(item), found.get(int(item))) for item in receivers]
    if all(isinstance(item, str) and item.strip() and not item.isdigit() for item in receivers):
        names = [item.strip() for item in receivers]
        found = {user.username: user for user in User.objects.filter(username__in=names)}
        return [(item, found.get(item.strip())) for item in receivers]
    return [(item, None) for item in receivers]


def _person_name(user):
    return (user.display_name or user.username or str(user.id)).strip()


def _provider_phone(raw, provider):
    number = _mainland_mobile(raw)
    if not number:
        return ""
    if provider == "tencent":
        return f"+86{number}"
    if provider == "aliyun":
        return number
    return ""


def _mainland_mobile(raw):
    text = "".join(char for char in str(raw or "") if char.isdigit() or char == "+")
    if text.startswith("+"):
        digits = text[1:]
        if not digits.startswith("86"):
            return ""
        digits = digits[2:]
    else:
        digits = text
        if digits.startswith("86") and len(digits) == 13:
            digits = digits[2:]
    if len(digits) == 11 and digits.startswith("1") and digits.isdigit():
        return digits
    return ""


def _secrets_unreadable(channel, config):
    stored = channel.config or {}
    provider = config.get("provider")
    fields = ("secret_id", "secret_key") if provider == "tencent" else ("access_key_id", "access_key_secret")
    for field in fields:
        raw = stored.get(field) or ""
        if isinstance(raw, str) and raw.startswith("gAAAA") and config.get(field) == raw:
            return True
    return False
