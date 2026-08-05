"""采集凭据的静态契约。

契约描述连接配置的结构与校验规则，不保存任何凭据值，因此不需要数据库模型。
"""

from copy import deepcopy


API_SECRET_MASK = "******"


COLLECT_CREDENTIAL_CONTRACTS = {
    "winsphere": {
        "schema_version": 1,
        "requires_enabled_collect_object": True,
        "task_type": "cloud",
        "driver_type": "protocol",
        "allow_multiple": False,
        "allow_unknown_fields": False,
        "encrypted_fields": ["password"],
        "fields": [
            {
                "key": "user",
                "type": "string",
                "required": True,
                "label": "WinSphere账号",
            },
            {
                "key": "password",
                "type": "password",
                "required": True,
                "label": "密码",
            },
            {
                "key": "https_port",
                "type": "integer",
                "required": True,
                "default": 443,
                "min": 1,
                "max": 65535,
                "label": "HTTPS端口",
            },
            {
                "key": "verify_tls",
                "type": "boolean",
                "required": True,
                "default": False,
                "label": "TLS证书校验",
            },
        ],
    },
}


class CredentialContractError(ValueError):
    def __init__(self, errors):
        super().__init__("采集凭据不符合连接契约")
        self.errors = errors


def register_collect_credential_contract(model_id, contract, *, replace=False):
    """注册无数据库凭据契约，供能力扩展在进程启动时声明。"""
    if not model_id or not isinstance(contract, dict):
        raise ValueError("采集凭据契约格式错误")
    if model_id in COLLECT_CREDENTIAL_CONTRACTS and not replace:
        raise ValueError(f"采集凭据契约已注册: {model_id}")
    COLLECT_CREDENTIAL_CONTRACTS[model_id] = deepcopy(contract)


def get_collect_credential_contract(model_id):
    return deepcopy(COLLECT_CREDENTIAL_CONTRACTS.get(model_id))


def validate_collect_credential(
    model_id,
    raw_credential,
    *,
    existing_credential=None,
):
    contract = get_collect_credential_contract(model_id)
    if not contract:
        return raw_credential

    if isinstance(raw_credential, dict):
        pool = [deepcopy(raw_credential)]
    elif isinstance(raw_credential, list):
        pool = deepcopy(raw_credential)
    else:
        raise CredentialContractError({"non_field_errors": "凭据格式错误"})

    if not contract["allow_multiple"] and len(pool) != 1:
        raise CredentialContractError(
            {"non_field_errors": "WinSphere 仅支持一组连接凭据"}
        )
    if len(pool) != 1 or not isinstance(pool[0], dict):
        raise CredentialContractError({"non_field_errors": "凭据格式错误"})

    credential = pool[0]
    existing = _first_credential(existing_credential)
    fields = {field["key"]: field for field in contract["fields"]}
    allowed_fields = set(fields) | {"credential_id"}
    unknown_fields = sorted(set(credential) - allowed_fields)
    errors = {}
    if unknown_fields and not contract["allow_unknown_fields"]:
        errors["fields"] = f"不支持字段: {', '.join(unknown_fields)}"

    normalized = {}
    if credential.get("credential_id"):
        normalized["credential_id"] = credential["credential_id"]
    elif existing.get("credential_id"):
        normalized["credential_id"] = existing["credential_id"]

    for key, field in fields.items():
        value = credential.get(key)
        if field["type"] == "password" and value == API_SECRET_MASK:
            value = existing.get(key)
        if value is None and "default" in field:
            value = field.get("default")
        if (
            field["type"] == "password"
            and value in (None, "")
            and existing.get(key) not in (None, "")
        ):
            value = existing[key]

        error = _validate_field(field, value)
        if error:
            errors[key] = error
            continue
        if field["type"] == "string":
            value = value.strip()
        elif field["type"] == "integer":
            value = int(value)
        normalized[key] = value

    if errors:
        raise CredentialContractError(errors)
    return [normalized]


def _first_credential(raw_credential):
    if isinstance(raw_credential, dict):
        return raw_credential
    if (
        isinstance(raw_credential, list)
        and len(raw_credential) == 1
        and isinstance(raw_credential[0], dict)
    ):
        return raw_credential[0]
    return {}


def _validate_field(field, value):
    label = field["label"]
    if field.get("required") and value in (None, ""):
        return f"请输入{label}"

    field_type = field["type"]
    if field_type in {"string", "password"}:
        if not isinstance(value, str):
            return f"{label}必须为字符串"
        if field.get("required") and not value.strip():
            return f"请输入{label}"
        return None
    if field_type == "integer":
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return f"{label}必须为整数"
        if parsed < field.get("min", parsed) or parsed > field.get("max", parsed):
            return (
                f"{label}必须在 {field.get('min')} 到 "
                f"{field.get('max')} 之间"
            )
        return None
    if field_type == "boolean" and not isinstance(value, bool):
        return f"{label}必须为布尔值"
    return None
