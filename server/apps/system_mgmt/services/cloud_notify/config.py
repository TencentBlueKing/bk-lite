from copy import deepcopy

CLOUD_SECRET_FIELDS = ("secret_id", "secret_key", "access_key_id", "access_key_secret")
MAX_TEMPLATE_PARAMETERS = 20
TENCENT_REGION = "ap-guangzhou"

_REQUIRED = {
    ("sms", "tencent"): ("secret_id", "secret_key", "sdk_app_id", "sign_name", "template_id"),
    ("sms", "aliyun"): ("access_key_id", "access_key_secret", "sign_name", "template_code"),
    ("voice", "tencent"): ("secret_id", "secret_key", "sdk_app_id", "template_id"),
    ("voice", "aliyun"): ("access_key_id", "access_key_secret", "template_code"),
}


def mask_secret(value):
    text = str(value or "")
    if not text:
        return ""
    return f"******{text[-4:]}"


def validate_cloud_config(channel_type, config, preserved_fields=()):
    """返回字段错误。空字典表示配置可用于保存或发送。"""
    if not isinstance(config, dict):
        return {"config": "error.cloud_config_invalid"}
    provider = config.get("provider")
    required = _REQUIRED.get((channel_type, provider))
    if required is None:
        return {"provider": "error.cloud_provider_invalid"}
    kept = set(preserved_fields)
    errors = {}
    for field in required:
        if field in kept:
            continue
        value = config.get(field)
        if not isinstance(value, str) or not value.strip():
            errors[field] = "error.cloud_field_required"
    parameters = config.get("parameters", [])
    if not isinstance(parameters, list):
        errors["parameters"] = "error.cloud_parameters_invalid"
    elif len(parameters) > MAX_TEMPLATE_PARAMETERS:
        errors["parameters"] = "error.cloud_parameters_limit"
    else:
        seen_names = set()
        for index, item in enumerate(parameters):
            item_errors = _validate_parameter(item, provider, seen_names)
            if item_errors:
                errors[f"parameters.{index}"] = item_errors
    called_show_number = config.get("called_show_number")
    if called_show_number not in (None, "") and not isinstance(called_show_number, str):
        errors["called_show_number"] = "error.cloud_called_show_number_invalid"
    return errors


def _validate_parameter(item, provider, seen_names):
    if not isinstance(item, dict):
        return "error.cloud_parameter_invalid"
    test_value = item.get("test_value", "")
    if test_value is None:
        test_value = ""
    if not isinstance(test_value, str):
        return "error.cloud_test_value_invalid"
    name = item.get("name", "")
    if not isinstance(name, str):
        return "error.cloud_parameter_name_invalid"
    if provider != "aliyun":
        return ""
    stripped = name.strip()
    if not stripped:
        return "error.cloud_parameter_name_required"
    if stripped in seen_names:
        return "error.cloud_parameter_name_duplicate"
    seen_names.add(stripped)
    return ""


def declared_parameter_rows(parameters, provider):
    """保存变量声明和测试值。阿里云保留参数名，腾讯云只保留顺序。"""
    rows = []
    for item in parameters or []:
        name = ""
        test_value = ""
        if isinstance(item, dict):
            if provider == "aliyun":
                name = str(item.get("name") or "").strip()
            raw_test_value = item.get("test_value") or ""
            if isinstance(raw_test_value, str):
                test_value = raw_test_value.strip()
        rows.append({"name": name, "test_value": test_value})
    return rows


def match_template_params(config, template_params):
    """按渠道登记的变量检查本次发送的参数。返回 (厂商参数, 错误键)。"""
    provider = config.get("provider")
    declared = [item for item in (config.get("parameters") or []) if isinstance(item, dict)]
    if provider == "aliyun":
        names = [str(item.get("name") or "").strip() for item in declared]
        if any(not name for name in names):
            return None, "error.cloud_parameter_name_required"
        if len(set(names)) != len(names):
            return None, "error.cloud_parameter_name_duplicate"
        if not names:
            if template_params in (None, {}, []):
                return {}, None
            return None, "error.cloud_template_params_unexpected"
        if not isinstance(template_params, dict):
            return None, "error.cloud_template_params_mismatch" if template_params is None else "error.cloud_template_params_object"
        if set(template_params) != set(names):
            return None, "error.cloud_template_params_mismatch"
        values = {}
        for name in names:
            flattened = _flatten_template_value(template_params.get(name))
            if flattened is None:
                return None, "error.cloud_template_params_value"
            values[name] = flattened
        return values, None
    count = len(declared)
    if count == 0:
        if template_params in (None, {}, []):
            return [], None
        return None, "error.cloud_template_params_unexpected"
    if not isinstance(template_params, list):
        return None, "error.cloud_template_params_mismatch" if template_params is None else "error.cloud_template_params_array"
    if len(template_params) != count:
        return None, "error.cloud_template_params_mismatch"
    values = []
    for item in template_params:
        flattened = _flatten_template_value(item)
        if flattened is None:
            return None, "error.cloud_template_params_value"
        values.append(flattened)
    return values, None


def _flatten_template_value(value):
    if not isinstance(value, str):
        return None
    text = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ").strip()
    if not text:
        return None
    return text


def runtime_config(channel):
    """解密后的发送配置。调用方不得把返回值写回页面。"""
    config = deepcopy(channel.config or {})
    for field in CLOUD_SECRET_FIELDS:
        channel.decrypt_field(field, config)
    return config


def masked_config(channel):
    config = runtime_config(channel)
    for field in CLOUD_SECRET_FIELDS:
        if config.get(field):
            config[field] = mask_secret(config[field])
    return config


def fields_preserving_existing_secret(config, old_config, channel):
    """更新时空值或当前掩码，且旧配置已有密文的密钥字段。这些字段不必重新填写。"""
    if not isinstance(config, dict):
        return set()
    previous = old_config or {}
    revealed = runtime_config_from_mapping(previous, channel)
    kept = set()
    for field in CLOUD_SECRET_FIELDS:
        incoming = config.get(field, "")
        old_plain = revealed.get(field) or ""
        if previous.get(field) and (incoming in ("", None) or (old_plain and incoming == mask_secret(old_plain))):
            kept.add(field)
    return kept


def apply_preserved_secrets(config, old_config, channel):
    """空值或当前掩码保留原密文。返回这些字段，调用方不得再次加密。"""
    previous = old_config or {}
    revealed = runtime_config_from_mapping(previous, channel)
    preserved = set()
    for field in CLOUD_SECRET_FIELDS:
        incoming = config.get(field, "")
        old_plain = revealed.get(field) or ""
        if incoming in ("", None) or (old_plain and incoming == mask_secret(old_plain)):
            preserved.add(field)
            if previous.get(field):
                config[field] = previous[field]
            else:
                config.pop(field, None)
    return preserved


def runtime_config_from_mapping(config, channel):
    revealed = deepcopy(config or {})
    for field in CLOUD_SECRET_FIELDS:
        channel.decrypt_field(field, revealed)
    return revealed
