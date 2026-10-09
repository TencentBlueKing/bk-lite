"""Map vault fields onto collect-config form keys and storage locations."""

from __future__ import annotations

import re
from urllib.parse import quote

from .binding import delete_path, get_path, set_path
from .errors import VaultCredentialError

_NEVER_ENCODE = {"ENV_AUTH_PASSWORD", "ENV_PRIV_PASSWORD", "ENV_BEARER_TOKEN"}
_PLAIN_PASSWORD_COLLECT_TYPES = {"web", "bkpull", "custom_pull"}
_PLAIN_PASSWORD_CONFIG_TYPES = {"qcloud", "windows_wmi", "cisco_meraki", "aliyun", "cnware", "custom_pull", "bkpull"}
_USERNAME_PUNCTUATION = (":", "@", "/", ";")
_AUTH_PROTOCOL = {
    "MD5": "MD5",
    "SHA": "SHA",
    "SHA-1": "SHA",
    "SHA1": "SHA",
    "SHA-224": "SHA224",
    "SHA224": "SHA224",
    "SHA-256": "SHA256",
    "SHA256": "SHA256",
    "SHA-384": "SHA384",
    "SHA384": "SHA384",
    "SHA-512": "SHA512",
    "SHA512": "SHA512",
}
_PRIV_PROTOCOL = {
    "DES": "DES",
    "AES": "AES",
    "AES-128": "AES",
    "AES128": "AES",
    "AES-256": "AES256",
    "AES256": "AES256",
}


def should_url_encode_secret(field_name, collect_type, config_types, encrypted):
    if not encrypted:
        return False
    name = str(field_name or "")
    if name in _NEVER_ENCODE:
        return False
    if name == "ENV_PASSWORD":
        if str(collect_type or "") in _PLAIN_PASSWORD_COLLECT_TYPES:
            return False
        types = config_types if isinstance(config_types, (list, tuple, set)) else ([config_types] if config_types else [])
        if any(str(item) in _PLAIN_PASSWORD_CONFIG_TYPES for item in types):
            return False
    return True


def encode_secret(value):
    return quote(str(value), safe="-_.!~*'()")


def form_values_for_credential(resolved, variant, binding, *, encode=True):
    profile = (variant or {}).get("_profile")
    fields = dict(resolved.fields or {})
    values = _profile_values(profile, fields, getattr(resolved, "type_key", ""), variant)
    if encode:
        values = _encode_values(values, variant, binding)
    _reject_invalid_usernames(values, variant)
    return values


def to_create_fields(resolved, variant, binding):
    values = form_values_for_credential(resolved, variant, binding, encode=True)
    created = {}
    targets = {target.get("field"): target for target in (variant or {}).get("_targets") or []}
    for name, value in values.items():
        target = targets.get(name) or {}
        if target.get("kind") == "env" and target.get("env_name"):
            created[f"ENV_{target['env_name']}"] = value
        else:
            created[name] = value
    return created


def to_storage_writes(resolved, variant, binding, configs, *, encode=True, inline_values=None):
    if inline_values is None:
        values = form_values_for_credential(resolved, variant, binding, encode=encode)
    else:
        values = dict(inline_values)
        if encode:
            values = _encode_values(values, variant, binding)
        _reject_invalid_usernames(values, variant)
    writes = []
    targets = [target for target in (variant or {}).get("_targets") or [] if target.get("field") in values]
    child_ids = [str(row.id) for row in configs if getattr(row, "is_child", True)]
    base_ids = [str(row.id) for row in configs if not getattr(row, "is_child", True)]
    for target in targets:
        value = values[target["field"]]
        if target.get("kind") == "env":
            env_name = target.get("env_name") or ""
            scope_ids = child_ids if target.get("scope") == "child" else base_ids
            for config_id in scope_ids:
                key = f"{env_name}__{config_id.upper()}" if target.get("scope") == "child" else env_name
                writes.append({"config_id": config_id, "kind": "env", "env_key": key, "value": value})
            if target.get("scope") == "child" and base_ids and env_name:
                for config_id in base_ids:
                    writes.append({"config_id": config_id, "kind": "env", "env_key": env_name, "value": value})
            continue
        scope_ids = child_ids if target.get("scope") == "child" else base_ids
        for config_id in scope_ids:
            written = value
            if encode and _dsn_user_uses_urlencode(target):
                written = quote(str(value), safe="/")
            writes.append(
                {
                    "config_id": config_id,
                    "kind": target.get("kind") or "content",
                    "path": target.get("path"),
                    "regex": target.get("regex"),
                    "value": written,
                    "field": target.get("field"),
                }
            )
    return writes


def apply_storage_writes(env_by_config, content_by_config, writes):
    envs = {key: dict(value or {}) for key, value in (env_by_config or {}).items()}
    contents = {key: _copy_content(value) for key, value in (content_by_config or {}).items()}
    for write in writes or []:
        config_id = str(write.get("config_id"))
        if write.get("kind") == "env":
            env = envs.setdefault(config_id, {})
            env[write["env_key"]] = write.get("value")
            continue
        content = contents.setdefault(config_id, {})
        if write.get("kind") == "dsn":
            current = get_path(content, write.get("path"))
            if not isinstance(current, str):
                raise VaultCredentialError("apply_failed")
            contents[config_id] = content
            set_path(content, write.get("path"), _replace_capture(write.get("regex"), current, write.get("value")))
            continue
        if write.get("path"):
            set_path(content, write.get("path"), write.get("value"))
    return envs, contents


def strip_managed_values(env_by_config, content_by_config, targets):
    envs = {key: dict(value or {}) for key, value in (env_by_config or {}).items()}
    contents = {key: _copy_content(value) for key, value in (content_by_config or {}).items()}
    for target in targets or []:
        config_id = str(target.get("config_id") or "")
        if target.get("kind") == "env" and target.get("env_key"):
            env = envs.get(config_id)
            if isinstance(env, dict):
                env.pop(target["env_key"], None)
            continue
        content = contents.get(config_id)
        if isinstance(content, dict) and target.get("path") and target.get("kind") != "dsn":
            delete_path(content, target["path"])
    return envs, contents


def _profile_values(profile, fields, type_key, variant):
    managed = set((variant or {}).get("managed_fields") or [])

    def keep(values):
        if not managed:
            return values
        return {key: value for key, value in values.items() if key in managed}

    if profile == "snmp_v2":
        return keep({"community": _raw(fields, "community")})
    if profile == "snmp_v3":
        level = str(fields.get("security_level") or "")
        values = {"sec_name": _raw(fields, "username"), "sec_level": level}
        if level in {"authNoPriv", "authPriv"}:
            values["auth_protocol"] = _protocol(_AUTH_PROTOCOL, fields.get("auth_protocol"))
            password = _raw(fields, "auth_password")
            if "ENV_AUTH_PASSWORD" in managed:
                values["ENV_AUTH_PASSWORD"] = password
            if "auth_password" in managed:
                values["auth_password"] = password
        if level == "authPriv":
            values["priv_protocol"] = _protocol(_PRIV_PROTOCOL, fields.get("priv_protocol"))
            password = _raw(fields, "priv_password")
            if "ENV_PRIV_PASSWORD" in managed:
                values["ENV_PRIV_PASSWORD"] = password
            if "priv_password" in managed:
                values["priv_password"] = password
        return keep(values)
    if profile == "ssh":
        method = "private_key" if fields.get("auth_method") == "key" else "password"
        values = {"username": _raw(fields, "username"), "auth_type": method}
        if method == "password":
            values["ENV_PASSWORD"] = _raw(fields, "password")
        else:
            values["private_key_content"] = _raw(fields, "private_key")
            if fields.get("passphrase") not in (None, ""):
                values["private_key_passphrase"] = _raw(fields, "passphrase")
        return keep(values)
    if profile == "user_password":
        user_name = next((name for name in (variant or {}).get("managed_fields") or [] if "password" not in str(name).lower()), "username")
        password_name = next((name for name in (variant or {}).get("managed_fields") or [] if name != user_name), "ENV_PASSWORD")
        user_source = "user" if user_name == "ENV_USER" and "user" in fields and "username" not in fields else "username"
        if user_source not in fields and "user" in fields:
            user_source = "user"
        return {user_name: _raw(fields, user_source), password_name: _raw(fields, "password")}
    if profile in {"winrm", "redfish", "platform_api", "basic"}:
        return keep({"username": _raw(fields, "username"), "ENV_PASSWORD": _raw(fields, "password")})
    if profile == "cloud":
        return keep({"username": _raw(fields, "access_key"), "ENV_PASSWORD": _raw(fields, "secret_key")})
    if profile == "ipmi":
        return keep({"username": _raw(fields, "username"), "ENV_PASSWORD": _raw(fields, "password")})
    if profile == "bearer":
        return keep({"ENV_BEARER_TOKEN": _raw(fields, "token")})
    if profile == "kafka":
        return keep({"ENV_SASL_USERNAME": _raw(fields, "username"), "ENV_SASL_PASSWORD": _raw(fields, "password")})
    if profile == "jmx":
        return keep({"username": _raw(fields, "username"), "password": _raw(fields, "password")})
    if profile == "influx":
        if type_key == "token":
            return keep({"username": "", "ENV_PASSWORD": _raw(fields, "token")})
        return keep({"username": _raw(fields, "username"), "ENV_PASSWORD": _raw(fields, "password")})
    if profile == "token":
        password_name = next(iter((variant or {}).get("managed_fields") or []), "token")
        return {password_name: _raw(fields, "token")}
    raise VaultCredentialError("apply_failed")


def _encode_values(values, variant, binding):
    collect_type = (binding or {}).get("_collect_type")
    config_types = (binding or {}).get("_config_types") or []
    targets = {target.get("field"): target for target in (variant or {}).get("_targets") or []}
    encoded = {}
    for name, value in values.items():
        target = targets.get(name) or {}
        field_name = name
        if should_url_encode_secret(field_name, collect_type, config_types, target.get("encrypted")):
            encoded[name] = encode_secret(value)
        else:
            encoded[name] = value
    return encoded


def _reject_invalid_usernames(values, variant):
    for target in (variant or {}).get("_targets") or []:
        if target.get("kind") != "dsn":
            continue
        value = values.get(target.get("field"))
        if value in (None, ""):
            continue
        text = str(value)
        if any(char in text for char in _USERNAME_PUNCTUATION):
            raise VaultCredentialError("username_invalid")
        if _regex_rejects(target.get("regex"), text):
            raise VaultCredentialError("username_invalid")


def _regex_rejects(pattern, text):
    if not pattern:
        return False
    try:
        compiled = re.compile(pattern)
    except re.error:
        return False
    source = compiled.pattern
    group_match = re.search(r"\((?P<body>\[[^\]]+\])", source)
    if not group_match:
        return False
    body = group_match.group("body")
    if body.startswith("[^"):
        excluded = body[2:-1]
        return any(char in excluded for char in text)
    return False


def _dsn_user_uses_urlencode(target):
    """新建模板对 URL 型 DSN 用户名使用 Jinja ``| urlencode``（``quote(safe="/")``）。"""
    if target.get("kind") != "dsn":
        return False
    regex = str(target.get("regex") or "")
    if "://" in regex:
        return True
    # SQL Server 模板是 sqlserver://用户名，UI 正则仍是 ADO 的 User Id=
    return "User Id=" in regex


_SQLSERVER_USERINFO = re.compile(r"://([^:]+):")


def _capture_match(pattern, text):
    text = "" if text is None else str(text)
    try:
        compiled = re.compile(pattern or "")
    except re.error as exc:
        raise VaultCredentialError("apply_failed") from exc
    matches = list(compiled.finditer(text))
    if len(matches) == 1 and matches[0].lastindex is not None and matches[0].lastindex >= 1:
        return matches[0]
    if "sqlserver://" in text and "User Id=" in str(pattern or ""):
        url_matches = list(_SQLSERVER_USERINFO.finditer(text))
        if len(url_matches) == 1:
            return url_matches[0]
    raise VaultCredentialError("apply_failed")


def _replace_capture(pattern, text, value):
    match = _capture_match(pattern, text)
    start, end = match.span(1)
    return text[:start] + str(value) + text[end:]


def _protocol(mapping, value):
    text = str(value or "")
    if text not in mapping:
        raise VaultCredentialError("apply_failed")
    return mapping[text]


def _raw(fields, key):
    value = fields.get(key)
    if value is None:
        return ""
    return value


def stored_writes_for_variant(variant, env_by_config, content_by_config, configs):
    """把每一行自己的受管值写回同一行，不把第一行的密文复制到其他行。"""
    writes = []
    child_ids = [str(row.id) for row in configs if getattr(row, "is_child", True)]
    base_ids = [str(row.id) for row in configs if not getattr(row, "is_child", True)]
    for target in (variant or {}).get("_targets") or []:
        if target.get("kind") == "env":
            env_name = target.get("env_name") or ""
            scope_ids = child_ids if target.get("scope") == "child" else base_ids
            for config_id in scope_ids:
                key = f"{env_name}__{config_id.upper()}" if target.get("scope") == "child" else env_name
                env = (env_by_config or {}).get(str(config_id)) or {}
                if key not in env:
                    continue
                writes.append({"config_id": config_id, "kind": "env", "env_key": key, "value": env.get(key)})
            if target.get("scope") == "child" and base_ids and env_name:
                for config_id in base_ids:
                    env = (env_by_config or {}).get(str(config_id)) or {}
                    if env_name not in env:
                        continue
                    writes.append({"config_id": config_id, "kind": "env", "env_key": env_name, "value": env.get(env_name)})
            continue
        scope_ids = child_ids if target.get("scope") == "child" else base_ids
        for config_id in scope_ids:
            content = (content_by_config or {}).get(str(config_id))
            current = get_path(content, target.get("path"))
            if target.get("kind") == "dsn":
                if not isinstance(current, str):
                    continue
                value = _extract_capture(target.get("regex"), current)
            else:
                value = current
            if value is None:
                continue
            writes.append(
                {
                    "config_id": config_id,
                    "kind": target.get("kind") or "content",
                    "path": target.get("path"),
                    "regex": target.get("regex"),
                    "value": value,
                    "field": target.get("field"),
                }
            )
    return writes


def stored_values_for_variant(variant, env_by_config, content_by_config, configs):
    """Read the current branch values already stored on the node. Does not decrypt."""
    values = {}
    child_ids = [str(row.id) for row in configs if getattr(row, "is_child", True)]
    base_ids = [str(row.id) for row in configs if not getattr(row, "is_child", True)]
    for target in (variant or {}).get("_targets") or []:
        field = target.get("field")
        if not field or field in values:
            continue
        scope_ids = child_ids if target.get("scope") == "child" else base_ids
        found = _read_target_value(target, scope_ids, env_by_config, content_by_config)
        if found is None and target.get("kind") == "env" and target.get("scope") == "child" and base_ids:
            base_target = dict(target)
            base_target["scope"] = "base"
            found = _read_target_value(base_target, base_ids, env_by_config, content_by_config)
        if found is not None:
            values[field] = found
    return values


def _read_target_value(target, config_ids, env_by_config, content_by_config):
    for config_id in config_ids:
        if target.get("kind") == "env":
            env_name = target.get("env_name") or ""
            key = f"{env_name}__{str(config_id).upper()}" if target.get("scope") == "child" else env_name
            env = (env_by_config or {}).get(str(config_id)) or {}
            if key in env:
                return env.get(key)
            continue
        content = (content_by_config or {}).get(str(config_id))
        current = get_path(content, target.get("path"))
        if target.get("kind") == "dsn":
            if not isinstance(current, str):
                continue
            return _extract_capture(target.get("regex"), current)
        if current is not None:
            return current
    return None


def _extract_capture(pattern, text):
    return _capture_match(pattern, text).group(1)


def _copy_content(value):
    if isinstance(value, dict):
        return {key: _copy_content(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_content(item) for item in value]
    return value
