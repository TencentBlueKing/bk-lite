"""Authoritative built-in credential type definitions."""

from copy import deepcopy

BUILTIN_TYPES = {
    "ssh": {
        "name": "SSH",
        "categories": ["host"],
        "fields": [
            {"id": "auth_method", "name": "认证方式", "kind": "enum", "values": ["password", "key"], "required": True},
            {"id": "username", "name": "用户名", "kind": "string", "required": True},
            {
                "id": "password",
                "name": "密码",
                "kind": "secret",
                "required": True,
                "visible_when": {"auth_method": "password"},
            },
            {
                "id": "private_key",
                "name": "私钥内容",
                "kind": "secret",
                "required": True,
                "visible_when": {"auth_method": "key"},
            },
            {"id": "port", "name": "端口", "kind": "number"},
        ],
    },
    "winrm": {
        "name": "WinRM",
        "categories": ["host"],
        "fields": [
            {"id": "username", "name": "用户名", "kind": "string", "required": True},
            {"id": "password", "name": "密码", "kind": "secret", "required": True},
        ],
    },
    "ipmi": {
        "name": "IPMI",
        "categories": ["host"],
        "fields": [
            {"id": "username", "name": "用户名", "kind": "string", "required": True},
            {"id": "password", "name": "密码", "kind": "secret", "required": True},
        ],
    },
    "snmp": {
        "name": "SNMP",
        "categories": ["network"],
        "fields": [
            {"id": "version", "name": "SNMP 版本", "kind": "enum", "values": ["v2c", "v3"], "required": True},
            {
                "id": "community",
                "name": "Community 团体名",
                "kind": "secret",
                "required": True,
                "visible_when": {"version": "v2c"},
            },
            {
                "id": "security_level",
                "name": "安全级别",
                "kind": "enum",
                "values": ["noAuthNoPriv", "authNoPriv", "authPriv"],
                "visible_when": {"version": "v3"},
            },
            {
                "id": "username",
                "name": "用户名 (Security Name)",
                "kind": "string",
                "visible_when": {"version": "v3"},
            },
            {
                "id": "auth_protocol",
                "name": "认证算法",
                "kind": "enum",
                "values": ["MD5", "SHA"],
                "visible_when": {"security_level": {"op": "ne", "value": "noAuthNoPriv"}},
            },
            {
                "id": "auth_password",
                "name": "认证密码",
                "kind": "secret",
                "visible_when": {"security_level": {"op": "ne", "value": "noAuthNoPriv"}},
            },
            {
                "id": "priv_protocol",
                "name": "加密算法",
                "kind": "enum",
                "values": ["DES", "AES"],
                "visible_when": {"security_level": "authPriv"},
            },
            {
                "id": "priv_password",
                "name": "加密密码",
                "kind": "secret",
                "visible_when": {"security_level": "authPriv"},
            },
        ],
    },
    "sql": {
        "name": "用户名密码",
        "categories": ["database", "middleware"],
        "fields": [
            {"id": "username", "name": "用户名", "kind": "string", "required": True},
            {"id": "password", "name": "密码", "kind": "secret", "required": True},
        ],
    },
    "cloud": {
        "name": "云平台 AK/SK",
        "categories": ["cloud"],
        "fields": [
            {"id": "access_key", "name": "Access Key (AK)", "kind": "string", "required": True},
            {"id": "secret_key", "name": "Secret Key (SK)", "kind": "secret", "required": True},
            {"id": "extra", "name": "附加标识（如 Project ID）", "kind": "string"},
        ],
    },
    "platform_api": {
        "name": "HTTPS 平台账户",
        "categories": ["cloud", "storage"],
        "fields": [
            {"id": "username", "name": "用户名", "kind": "string", "required": True},
            {"id": "password", "name": "密码", "kind": "secret", "required": True},
            {"id": "port", "name": "端口", "kind": "number", "required": True},
            {
                "id": "verify_tls",
                "name": "校验 TLS 证书",
                "kind": "enum",
                "values": ["true", "false"],
                "required": True,
            },
        ],
    },
    "network_cli": {
        "name": "网络设备账户",
        "categories": ["network"],
        "fields": [
            {"id": "username", "name": "用户名", "kind": "string", "required": True},
            {"id": "password", "name": "密码", "kind": "secret", "required": True},
            {"id": "port", "name": "端口", "kind": "number"},
            {"id": "enable_password", "name": "Enable 密码", "kind": "secret"},
        ],
    },
    "token": {
        "name": "API Token",
        "categories": ["database", "other"],
        "fields": [
            {"id": "token", "name": "Token", "kind": "secret", "required": True},
        ],
    },
    "gateway_secret": {
        "name": "OpenAPI 网关密钥",
        "categories": ["other"],
        "fields": [
            {"id": "secret", "name": "共享密钥 / 服务令牌", "kind": "secret", "required": True},
        ],
    },
    "oauth_client": {
        "name": "OAuth 客户端",
        "categories": ["cloud"],
        "fields": [
            {"id": "client_id", "name": "Client ID", "kind": "string", "required": True},
            {"id": "client_secret", "name": "Client Secret", "kind": "secret", "required": True},
            {"id": "tenant_id", "name": "Tenant ID", "kind": "string", "required": True},
            {"id": "extra", "name": "附加标识（如 Subscription ID）", "kind": "string"},
        ],
    },
}

# A named alias keeps the seed data discoverable to callers without exposing
# mutable references to the definitions.
BUILTIN_TYPE_SEEDS = BUILTIN_TYPES


def builtin_type_payloads():
    """Return deep-copied seed payloads for safe use by ORM callers."""
    return {key: deepcopy(value) for key, value in BUILTIN_TYPES.items()}
