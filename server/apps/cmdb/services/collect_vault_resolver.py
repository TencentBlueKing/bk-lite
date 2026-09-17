"""任务下发前解析仓库引用，转换为采集插件既有认证键。"""

from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_vault_binding import actual_builtin_type_keys, binding_for_collect_object
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.snmp_usm import normalize_integrity, normalize_privacy
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES
from apps.system_mgmt.services.credential_schema import SchemaError, validate_instance_fields

_TASK_METADATA = {"credential_source", "vault_credential_id", "vault_actor_context", "vault_type_key"}
_AUTH_FIELDS = CollectCredentialPoolService.VAULT_CORE_FIELDS


def _convert_auth_fields(binding, fields, model_id=None):
    key = binding.split("/", 1)[1]
    if key == "snmp":
        version = str(fields.get("version") or "").lower()
        level = str(fields.get("security_level") or "").lower()
        return {
            "version": "v2" if version == "v2c" else version,
            "community": fields.get("community", ""),
            "username": fields.get("username", ""),
            "level": level,
            "integrity": normalize_integrity(fields.get("auth_protocol")) or str(fields.get("auth_protocol") or "").lower(),
            "authkey": fields.get("auth_password", ""),
            "privacy": normalize_privacy(fields.get("priv_protocol")) or str(fields.get("priv_protocol") or "").lower(),
            "privkey": fields.get("priv_password", ""),
        }
    if key == "cloud":
        return {
            "accessKey": fields.get("access_key", ""),
            "accessSecret": fields.get("secret_key", ""),
            "access_key": fields.get("access_key", ""),
            "access_secret": fields.get("secret_key", ""),
            "secret_key": fields.get("secret_key", ""),
        }
    if key == "oauth_client":
        return {
            "client_id": fields.get("client_id", ""),
            "client_secret": fields.get("client_secret", ""),
            "tenant_id": fields.get("tenant_id", ""),
            "username": fields.get("client_id", ""),
            "password": fields.get("client_secret", ""),
        }
    if key == "sql":
        return {"username": fields.get("username", ""), "user": fields.get("username", ""), "password": fields.get("password", "")}
    if key == "ssh":
        return {field: fields[field] for field in ("username", "password", "auth_method", "private_key", "passphrase") if field in fields}
    if key == "network_cli":
        return {field: fields[field] for field in ("username", "password", "enable_password") if field in fields}
    if key == "token":
        return {"token": fields.get("token", "")}
    if key == "openstack":
        return {field: fields[field] for field in ("username", "password", "user_domain_name") if field in fields}
    converted = {field: fields[field] for field in ("username", "password") if field in fields}
    if model_id in {"winsphere", "server_bmc"}:
        converted["user"] = fields.get("username", "")
    # 这些存储入口原来通过 CloudTask 提交账户，键名沿用 accessKey/accessSecret。
    if model_id in {"dell_unity", "netapp_ontap", "hds_vsp", "pure_array", "dell_powerstore", "hp_3par"}:
        converted["accessKey"] = fields.get("username", "")
        converted["accessSecret"] = fields.get("password", "")
    return converted


def resolve_task_credential_pool(instance, *, resolver=None):
    """只在下发构建时调用；返回内存中的完整候选，不写回 CollectModels。"""
    raw = instance.decrypt_credentials or []
    pool = raw if isinstance(raw, list) else [raw]
    if not any(item.get("credential_source") == "vault" for item in pool):
        return [{key: value for key, value in item.items() if key not in _TASK_METADATA} for item in pool]

    pool = CollectCredentialPoolService.normalize_pool(pool)

    resolve = resolver or SystemMgmt().resolve_credential
    resolved_pool = []
    for item in pool:
        if item.get("credential_source") != "vault":
            resolved_pool.append({key: value for key, value in item.items() if key not in _TASK_METADATA})
            continue
        binding = binding_for_collect_object(
            getattr(instance, "collect_object_id", None) or getattr(instance, "model_id", None),
            model_id=getattr(instance, "model_id", None),
            driver_type=getattr(instance, "driver_type", None),
            protocol=item.get("credential_protocol") or (getattr(instance, "params", None) or {}).get("collection_protocol"),
            os_type=(getattr(instance, "params", None) or {}).get("os_type"),
        )
        allowed_keys = actual_builtin_type_keys(binding)
        if not allowed_keys:
            raise BaseAppException("采集对象没有可用的内置凭据类型！")
        actor_context = item.get("vault_actor_context")
        if not isinstance(actor_context, dict) or not all(actor_context.get(field) for field in ("username", "domain", "current_team")):
            raise BaseAppException("已有凭据缺少绑定人信息，请重新选择！")
        response = resolve(actor_context, item["vault_credential_id"])
        if not isinstance(response, dict) or not response.get("result"):
            raise BaseAppException("已有凭据无法使用，请检查权限或停用状态！")
        payload = response.get("data") or {}
        # 旧 JOB 任务曾绑定用户名密码类型。仅兼容该认证契约，tree 新选择仍只返回 SSH。
        auth_binding = binding
        model_id = getattr(instance, "model_id", None)
        if model_id == "network_config_file" and payload.get("type") == "platform_api":
            auth_binding = "network/platform_api"
            allowed_keys = actual_builtin_type_keys(auth_binding)
        elif binding.endswith("/ssh") and model_id not in {"pc", "network_config_file"} and payload.get("type") == "sql":
            auth_binding = binding.rsplit("/", 1)[0] + "/sql"
            allowed_keys = actual_builtin_type_keys(auth_binding)
        if not allowed_keys:
            raise BaseAppException("采集对象没有可用的内置凭据类型！")
        if (
            payload.get("type") not in allowed_keys
            or (item.get("vault_type_key") and payload.get("type") != item["vault_type_key"])
            or not isinstance(payload.get("fields"), dict)
        ):
            raise BaseAppException("已有凭据类型与采集对象不匹配！")
        preferred_key = auth_binding.split("/", 1)[1]
        type_fields = BUILTIN_TYPES[preferred_key]["fields"]
        auth_field_ids = {field["id"] for field in type_fields if field["id"] in (_AUTH_FIELDS | {"version"})}
        auth_fields = {key: value for key, value in payload["fields"].items() if key in auth_field_ids}
        try:
            auth_fields = validate_instance_fields(type_fields=type_fields, values=auth_fields, require_secrets=True)
        except SchemaError as exc:
            raise BaseAppException("已有凭据认证字段不完整，请在凭据管理中补齐！") from exc
        if model_id == "network_config_file" and preferred_key == "ssh" and auth_fields.get("auth_method") != "password":
            raise BaseAppException("网络设备配置文件采集当前仅支持 SSH 密码凭据，请重新选择！")
        dynamic = {key: value for key, value in item.items() if key not in (_TASK_METADATA | CollectCredentialPoolService.vault_managed_fields(item))}
        if preferred_key == "snmp":
            dynamic.pop("version", None)
        dynamic.update(_convert_auth_fields(auth_binding, auth_fields, getattr(instance, "model_id", None)))
        resolved_pool.append(dynamic)
    return resolved_pool
