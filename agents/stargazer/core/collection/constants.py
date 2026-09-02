"""采集运行时常量：与业务编排代码分离。"""

from __future__ import annotations

import re

# 请求参数中视为凭据字段的键（规范化时进入 credentials，不进 public params）
CREDENTIAL_KEYS = frozenset(
    {
        "credential_id",
        "credential_version",
        "username",
        "user",
        "password",
        "token",
        "secret_id",
        "secret_key",
        "community",
        "private_key",
        "private_key_content",
        "private_key_passphrase",
        "passphrase",
        "auth_type",
        "version",
        "security_level",
        "auth_protocol",
        "auth_key",
        "priv_protocol",
        "priv_key",
    }
)

# 参与 request digest 脱敏的敏感键（小写比较）
SECRET_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "secret_id",
        "secret_key",
        "private_key",
        "community",
        "authkey",
        "privkey",
    }
)

# 协议预检默认端口
DEFAULT_PORTS: dict[str, int] = {
    "mysql": 3306,
    "gbase8a": 3306,
    "postgresql": 5432,
    "pgsql": 5432,
    "greenplum": 5432,
    "kingbase": 5432,
    "opengauss": 5432,
    "vastbase": 5432,
    "mssql": 1433,
    "oracle": 1521,
    "influxdb": 8086,
    "vmware": 443,
    "vmware_vc": 443,
    "windows_wmi": 135,
}

CLOUD_TYPES = frozenset({"aliyun", "qcloud", "hwcloud"})

# 平铺 header：credential_0_username …
FLATTENED_CREDENTIAL_KEY = re.compile(r"^credential_(\d+)_(.+)$")

# 配置采集失败文案启发式分类（无结构化 probe 时的兜底）
AUTH_ERROR_WORDS = (
    "auth",
    "password",
    "credential",
    "denied",
    "unauthorized",
    "community",
    "authkey",
    "privkey",
)
UNREACHABLE_ERROR_WORDS = (
    "tcp connect",
    "connect timed out",
    "connect failed",
    "connection refused",
    "no route",
    "host is down",
    "unreachable",
)
SNMP_NO_RESPONSE_WORDS = (
    "no snmp response",
    "empty snmp response",
    "requesttimedout",
    "no response received before timeout",
)

# Redis 键前缀默认值（可被环境变量覆盖）
DEFAULT_COLLECTION_REDIS_PREFIX = "stargazer:collection:v1"

# 配置采集目标并发默认值（环境变量可覆盖；0 = 不限制）
DEFAULT_MAX_ACTIVE_TARGETS = 160
DEFAULT_CONFIGURATION_MAX_ACTIVE_TARGETS = 100
DEFAULT_MONITORING_MAX_ACTIVE_TARGETS = 30
DEFAULT_NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS = 30
DEFAULT_TARGET_TASK_WINDOW = 160
