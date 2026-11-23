"""通知渠道包的校验、配置和发送。

上传请求的 purpose 决定校验路径。已入库包重新加载时才看 manifest 里有没有 notification_channel。
"""

from copy import deepcopy
from pathlib import Path

from apps.core.logger import safe_exception_info
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Channel, ChannelChoices, User
from apps.system_mgmt.providers.registry import capability_adapter_registry, get_provider_registry
from apps.system_mgmt.providers.schemas import ProviderManifest
from apps.system_mgmt.services.cloud_notify.config import mask_secret
from apps.system_mgmt.utils.i18n import system_mgmt_message

NOTIFICATION_CHANNEL = "notification_channel"
MAX_TEMPLATE_PARAMETERS = 20
_STATUSES = {"accepted", "rejected", "unknown"}
_INTEGRATION_PURPOSE = "integration"
_DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "package.json",
    "poetry.lock",
}
_SECRET_FILES = {".env", "credentials.json", "secrets.json", "secrets.yaml", "id_rsa"}
_PAGE_SUFFIXES = {".tsx", ".jsx", ".vue", ".html"}
_FAILED = "event=notification_channel_pack_failed channel_id=%s failed_stage=%s error_type=%s"
_FINISHED = "event=notification_channel_pack_finished channel_id=%s accepted=%s unknown=%s"


def upload_purpose(value) -> str:
    if value is None:
        return _INTEGRATION_PURPOSE
    text = str(value).strip()
    if not text:
        return _INTEGRATION_PURPOSE
    if text in {_INTEGRATION_PURPOSE, NOTIFICATION_CHANNEL}:
        return text
    raise ValueError("Unknown provider pack purpose")


def purpose_of(manifest: ProviderManifest | None) -> str | None:
    if manifest is None:
        return None
    if manifest.get_capability(NOTIFICATION_CHANNEL) is not None:
        return NOTIFICATION_CHANNEL
    return _INTEGRATION_PURPOSE


def is_loaded_notification_channel(channel_type: str) -> bool:
    return notification_manifest(channel_type) is not None


def notification_manifest(channel_type: str) -> ProviderManifest | None:
    if not channel_type or channel_type in set(ChannelChoices.values):
        return None
    manifest = get_provider_registry().get(channel_type)
    if manifest is None or manifest.get_capability(NOTIFICATION_CHANNEL) is None:
        return None
    return manifest


def notification_capability(manifest: ProviderManifest):
    return manifest.get_capability(NOTIFICATION_CHANNEL)


def validate_upload_files(pack_dir: Path, purpose: str) -> None:
    from apps.system_mgmt.providers.loader import validate_pack_layout

    if purpose == NOTIFICATION_CHANNEL:
        validate_pack_layout(pack_dir, notification_channel=True)
        _reject_pack_extras(pack_dir)
        return
    validate_pack_layout(pack_dir)


def validate_upload_manifest(manifest: ProviderManifest, purpose: str, pack_dir: Path | None = None) -> None:
    capability = notification_capability(manifest)
    if purpose == NOTIFICATION_CHANNEL:
        if capability is None:
            raise ValueError("Notification channel pack must declare notification_channel")
        if pack_dir is not None:
            validate_loaded_channel_pack(manifest, pack_dir)
        return
    if capability is not None:
        raise ValueError("Integration pack cannot declare notification_channel")


def validate_loaded_channel_pack(manifest: ProviderManifest, pack_dir: Path) -> None:
    if len(manifest.key) > 30:
        raise ValueError("Notification channel pack key must be at most 30 characters")
    if manifest.key in _reserved_channel_pack_keys():
        raise ValueError("Notification channel pack key is reserved")
    if len(manifest.capabilities) != 1 or manifest.capabilities[0].key != NOTIFICATION_CHANNEL:
        raise ValueError("Notification channel pack must declare only notification_channel")
    capability = manifest.capabilities[0]
    if capability.delivery not in {"template", "body"}:
        raise ValueError("notification_channel delivery must be template or body")
    if capability.delivery == "template" and capability.parameter_mode not in {"ordered", "named"}:
        raise ValueError("template delivery requires parameter_mode ordered or named")
    if capability.delivery == "body" and capability.parameter_mode is not None:
        raise ValueError("body delivery does not take parameter_mode")
    prefix = f"{manifest.key}."
    if not capability.adapter_key.startswith(prefix):
        raise ValueError(f"Adapter key '{capability.adapter_key}' must start with '{prefix}'")
    if not str(capability.adapter_path).startswith("adapters.send"):
        raise ValueError("adapter_path must point at the pack send adapter")
    _reject_pack_extras(pack_dir)


def secret_fields(manifest: ProviderManifest):
    return [field for field in manifest.instance_template if field.secret]


def validate_pack_channel_config(manifest: ProviderManifest, config, preserved_fields=()) -> dict:
    if not isinstance(config, dict):
        return {"config": "error.notification_channel_config_invalid"}
    capability = notification_capability(manifest)
    kept = set(preserved_fields)
    errors = {}
    for field in manifest.instance_template:
        if not field.required or field.key in kept:
            continue
        value = config.get(field.key)
        if value in (None, "") or (isinstance(value, str) and not value.strip()):
            errors[field.key] = "error.cloud_field_required"
    if capability is not None and capability.delivery == "template":
        errors.update(_validate_parameters(config.get("parameters", []), capability.parameter_mode))
    return errors


def runtime_pack_config(channel, manifest: ProviderManifest) -> dict:
    config = deepcopy(channel.config or {})
    for field in secret_fields(manifest):
        channel.decrypt_field(field.key, config)
    return config


def masked_pack_config(channel, manifest: ProviderManifest) -> dict:
    config = runtime_pack_config(channel, manifest)
    stored = channel.config or {}
    for field in secret_fields(manifest):
        raw = stored.get(field.key) or ""
        plain = config.get(field.key) or ""
        if isinstance(raw, str) and raw.startswith("gAAAA") and plain == raw:
            config[field.key] = "******"
        elif plain:
            config[field.key] = mask_secret(plain)
    return config


def public_channel_config(channel) -> dict:
    manifest = notification_manifest(channel.channel_type)
    if manifest is not None:
        return masked_pack_config(channel, manifest)
    return channel.config or {}


def apply_pack_secrets(config: dict, old_config, channel, manifest: ProviderManifest) -> set[str]:
    previous = old_config or {}
    revealed = runtime_pack_config_mapping(previous, channel, manifest)
    preserved = set()
    for field in secret_fields(manifest):
        incoming = config.get(field.key, "")
        old_plain = revealed.get(field.key) or ""
        if incoming in ("", None) or (old_plain and incoming == mask_secret(old_plain)):
            preserved.add(field.key)
            if previous.get(field.key):
                config[field.key] = previous[field.key]
            else:
                config.pop(field.key, None)
    return preserved


def encrypt_pack_secrets(config: dict, manifest: ProviderManifest, preserved: set[str]) -> None:
    for field in secret_fields(manifest):
        if field.key in preserved:
            continue
        Channel.encrypt_field(field.key, config)


def retain_pack_config(config: dict, manifest: ProviderManifest) -> dict:
    allowed = {field.key for field in manifest.instance_template}
    capability = notification_capability(manifest)
    if capability is not None and capability.delivery == "template":
        allowed.add("parameters")
    return {key: value for key, value in config.items() if key in allowed}


def runtime_pack_config_mapping(stored: dict, channel, manifest: ProviderManifest) -> dict:
    config = deepcopy(stored or {})
    for field in secret_fields(manifest):
        channel.decrypt_field(field.key, config)
    return config


def send_loaded_notification_channel(channel, title, content, receivers, template_params=None) -> dict:
    manifest = notification_manifest(channel.channel_type)
    if manifest is None:
        return _stopped("error.notification_channel_pack_not_loaded")
    capability = notification_capability(manifest)
    config = runtime_pack_config(channel, manifest)
    if _secrets_unreadable(channel, manifest, config):
        return _stopped("error.notification_channel_secret_unreadable")
    if validate_pack_channel_config(manifest, config):
        return _stopped("error.notification_channel_config_incomplete")
    send_config = retain_pack_config(config, manifest)
    send_config.pop("parameters", None)
    if capability.delivery == "body":
        return _send_body(channel, manifest, send_config, title, content)
    return _send_template(channel, manifest, send_config, receivers, template_params)


def _send_body(channel, manifest, config, title, content):
    if not isinstance(title, str) or not isinstance(content, str) or not content.strip():
        return _stopped("error.notification_channel_content_invalid")
    try:
        raw = _invoke_send(manifest, config, title, content)
    except Exception as error:
        logger.error(_FAILED, channel.id, "call_pack", type(error).__name__, exc_info=safe_exception_info(error))
        return _result([_recipient(None, "unknown", reason=system_mgmt_message(None, "error.notification_channel_send_unknown"))])
    logger.info(_FINISHED, channel.id, int(_outcome(raw)[0] == "accepted"), int(_outcome(raw)[0] == "unknown"))
    return _result([_from_raw(None, raw)])


def _send_template(channel, manifest, config, receivers, template_params):
    capability = notification_capability(manifest)
    prepared, error_key = _prepare_template_params(template_params, capability.parameter_mode)
    if error_key:
        return _stopped(error_key)
    people = _receiver_users(receivers)
    if not people:
        return _stopped("error.cloud_no_recipients")
    recipients = []
    called = 0
    accepted = 0
    unknown = 0
    provider_failed = False
    for user_id, user in people:
        if user is None:
            recipients.append(_recipient(user_id, "not_sent", reason=system_mgmt_message(None, "error.cloud_user_missing")))
            continue
        phone = (user.phone or "").strip()
        if not phone:
            recipients.append(_recipient(user.id, "not_sent", reason=system_mgmt_message(None, "error.notification_channel_phone_missing")))
            continue
        called += 1
        try:
            raw = _invoke_send(manifest, config, phone, prepared)
        except Exception as error:
            provider_failed = True
            unknown += 1
            logger.error(_FAILED, channel.id, "call_pack", type(error).__name__, exc_info=safe_exception_info(error))
            recipients.append(_recipient(user.id, "unknown", reason=system_mgmt_message(None, "error.notification_channel_send_unknown")))
            continue
        status, _request_id, _reason = _outcome(raw)
        if status == "accepted":
            accepted += 1
        elif status == "unknown":
            unknown += 1
        recipients.append(_from_raw(user.id, raw))
    if called and not provider_failed:
        logger.info(_FINISHED, channel.id, accepted, unknown)
    names = {user.id: _person_name(user) for _user_id, user in people if user is not None}
    return _result(recipients, names)


def _invoke_send(manifest, *args):
    capability = notification_capability(manifest)
    adapter = capability_adapter_registry.get(capability.adapter_key)
    if adapter is None:
        raise LookupError("send_adapter_missing")
    send = getattr(adapter, "send", None)
    if callable(send):
        return send(*args)
    if callable(adapter):
        return adapter(*args)
    raise TypeError("send_adapter_missing")


def declared_pack_parameter_rows(parameters, mode):
    """保存变量声明和测试值。具名模式保留参数名，顺序模式只保留槽位。"""
    rows = []
    for item in parameters or []:
        name = ""
        test_value = ""
        if isinstance(item, dict):
            if mode == "named":
                raw_name = item.get("name") or ""
                if isinstance(raw_name, str):
                    name = raw_name.strip()
            raw_test_value = item.get("test_value") or ""
            if isinstance(raw_test_value, str):
                test_value = raw_test_value.strip()
        rows.append({"name": name, "test_value": test_value})
    return rows


def _prepare_template_params(template_params, mode):
    """放行省略、对象和字符串数组。省略时按登记方式补空对象或空数组。"""
    if template_params is None:
        return ({} if mode == "named" else []), None
    if isinstance(template_params, dict):
        return template_params, None
    if isinstance(template_params, list) and all(isinstance(item, str) for item in template_params):
        return template_params, None
    return None, "error.notification_channel_template_params_invalid"


def _validate_parameters(parameters, mode) -> dict:
    if not isinstance(parameters, list):
        return {"parameters": "error.cloud_parameters_invalid"}
    if len(parameters) > MAX_TEMPLATE_PARAMETERS:
        return {"parameters": "error.cloud_parameters_limit"}
    errors = {}
    for index, item in enumerate(parameters):
        item_error = _validate_parameter(item, mode)
        if item_error:
            errors[f"parameters.{index}"] = item_error
    return errors


def _validate_parameter(item, mode) -> str:
    if not isinstance(item, dict):
        return "error.cloud_parameter_invalid"
    test_value = item.get("test_value", "")
    if test_value is None:
        test_value = ""
    if not isinstance(test_value, str):
        return "error.cloud_test_value_invalid"
    if mode != "named":
        return ""
    name = item.get("name", "")
    if not isinstance(name, str):
        return "error.cloud_parameter_name_invalid"
    if not name.strip():
        return "error.notification_channel_parameter_name_required"
    return ""


def _secrets_unreadable(channel, manifest, config) -> bool:
    stored = channel.config or {}
    for field in secret_fields(manifest):
        raw = stored.get(field.key) or ""
        if isinstance(raw, str) and raw.startswith("gAAAA") and config.get(field.key) == raw:
            return True
    return False


def _receiver_users(receivers):
    if not receivers:
        return []
    if all(isinstance(item, int) or (isinstance(item, str) and str(item).isdigit()) for item in receivers):
        ids = [int(item) for item in receivers]
        found = {user.id: user for user in User.objects.filter(id__in=ids)}
        return [(int(item), found.get(int(item))) for item in receivers]
    if all(isinstance(item, str) and item.strip() and not item.isdigit() for item in receivers):
        names = [item.strip() for item in receivers]
        found = {user.username: user for user in User.objects.filter(username__in=names)}
        return [(item, found.get(item.strip())) for item in receivers]
    return [(item, None) for item in receivers]


def _person_name(user) -> str:
    return (user.display_name or user.username or str(user.id)).strip()


def _outcome(raw):
    if not isinstance(raw, dict):
        return "unknown", "", ""
    status = raw.get("status")
    if status not in _STATUSES:
        status = "unknown"
    request_id = raw.get("request_id") or ""
    reason = raw.get("reason") or ""
    if not isinstance(request_id, str):
        request_id = str(request_id)
    if not isinstance(reason, str):
        reason = ""
    return status, request_id[:128], reason[:500]


def _from_raw(user_id, raw):
    status, request_id, reason = _outcome(raw)
    if status == "rejected":
        visible = system_mgmt_message(None, "error.notification_channel_send_rejected")
        if reason:
            visible = f"{visible}（{reason}）"
        reason = visible
    elif status == "unknown" and not reason:
        reason = system_mgmt_message(None, "error.notification_channel_send_unknown")
    elif status == "accepted":
        reason = ""
    return _recipient(user_id, status, request_id, reason)


def _recipient(user_id, status, request_id="", reason=""):
    return {
        "user_id": user_id,
        "status": status,
        "request_id": request_id or "",
        "reason": reason or "",
    }


def _stopped(message_key: str) -> dict:
    return {
        "result": False,
        "code": message_key.removeprefix("error."),
        "retryable": False,
        "message": system_mgmt_message(None, message_key),
        "recipients": [],
    }


def _result(recipients, names=None) -> dict:
    names = names or {}
    failed = [item for item in recipients if item["status"] != "accepted"]
    if not failed:
        return {"result": True, "code": "delivered", "retryable": False, "message": "success", "recipients": recipients}
    parts = []
    for item in failed:
        who = names.get(item["user_id"], item["user_id"])
        if who in (None, ""):
            parts.append(item["reason"])
        else:
            parts.append(f"{who}：{item['reason']}")
    return {
        "result": False,
        "code": "notification_channel_delivery_failed",
        "retryable": False,
        "message": "；".join(part for part in parts if part),
        "recipients": recipients,
    }


def _reserved_channel_pack_keys() -> set[str]:
    from apps.system_mgmt.providers.loader import discover_builtin_provider_packs, discover_enterprise_builtin_provider_packs

    keys = set(ChannelChoices.values)
    keys.add("im_notification")
    keys.update(path.name for _module_path, path in discover_builtin_provider_packs())
    keys.update(path.name for _module_path, path in discover_enterprise_builtin_provider_packs())
    return keys


def _reject_pack_extras(pack_dir: Path) -> None:
    for path in pack_dir.rglob("*"):
        if path.is_dir() and path.name == "pages":
            raise ValueError("Notification channel pack cannot include pages, secrets, or dependencies")
        if not path.is_file():
            continue
        name = path.name.lower()
        if name in _DEPENDENCY_FILES or name.startswith(".env") or name in _SECRET_FILES or path.suffix.lower() in {".pem", ".key"}:
            raise ValueError("Notification channel pack cannot include pages, secrets, or dependencies")
        if path.suffix.lower() in _PAGE_SUFFIXES or "pages" in path.parts:
            raise ValueError("Notification channel pack cannot include pages, secrets, or dependencies")
