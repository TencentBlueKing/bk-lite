"""OpenAPI 网关 base_url 允许清单：DB 存储 + 环境变量兜底。

清单决定哪些上游主机可被网关反代，是部署侧的安全边界（design.md 3.5.3）：
**未配置即拒绝一切**，不得因读取异常静默放宽。

两处来源取并集：

- 环境变量 ``OPENAPI_BASEURL_ALLOWLIST``：存量部署的既有配置，改动要重建 server；
- ``SystemSettings`` 表：新增主机走这里，改完一个拉取周期内生效，无需重建容器。

DB 读取失败时**不得**静默降级为「只剩 env」——那会让仅登记在 DB 的主机整批
落选，已在线的路由被摘除。``load_allowlist`` 因此返回 ``(hosts, db_ok)``，由
调用方决定沿用快照还是按冷启动兜底继续。
"""

import os
import re

from apps.core.logger import openapi_logger as logger

SETTINGS_KEY = "openapi_baseurl_allowlist"
ENV_KEY = "OPENAPI_BASEURL_ALLOWLIST"
WILDCARD = "*"

# 主机名 / IP，允许前导点表示按点边界的后缀匹配；单独的 * 表示放行一切
_HOST_RE = re.compile(r"^\.?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


class AllowlistError(ValueError):
    """主机名不合法，携带稳定错误码。"""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


def normalize_host(value) -> str:
    """校验并规范化一个清单条目；非法时抛 AllowlistError。"""
    if not isinstance(value, str):
        raise AllowlistError("invalid_host", "host must be a string")
    host = value.strip().lower()
    if not host:
        raise AllowlistError("invalid_host", "host must not be empty")
    if host == WILDCARD:
        return WILDCARD
    if len(host) > 253 or not _HOST_RE.match(host):
        raise AllowlistError("invalid_host", f"invalid host: {value!r}")
    return host


def _split(raw) -> list:
    return [item.strip().lower() for item in (raw or "").split(",") if item.strip()]


def env_hosts() -> list:
    """环境变量侧的清单（不校验格式：存量配置原样沿用）。"""
    return _split(os.getenv(ENV_KEY, ""))


def db_hosts() -> list:
    """DB 侧的清单。表中无该行按空清单处理（正常初始状态）。"""
    from apps.system_mgmt.models.system_settings import SystemSettings

    row = SystemSettings.objects.filter(key=SETTINGS_KEY).values_list("value", flat=True).first()
    return _split(row)


def load_allowlist():
    """返回 (hosts, db_ok)。db_ok 为 False 表示 DB 侧未能读到，调用方须 fail-closed。"""
    hosts = list(env_hosts())
    try:
        hosts.extend(db_hosts())
    except Exception as exc:
        logger.warning(
            "openapi allowlist 读取失败 failed_stage=db_lookup error_type=%s",
            type(exc).__name__,
        )
        return tuple(dict.fromkeys(hosts)), False
    return tuple(dict.fromkeys(hosts)), True


def host_allowed(host: str, allow) -> bool:
    """主机是否落在清单内；后缀匹配必须落在点边界上。"""
    if not allow:
        return False
    if WILDCARD in allow:
        return True
    host = (host or "").lower()
    if not host:
        return False
    for item in allow:
        item = item.lower()
        # allow=itsm-svc 不得放行 evil-itsm-svc
        suffix = item if item.startswith(".") else "." + item
        if host == item.lstrip(".") or host.endswith(suffix):
            return True
    return False


def _save(hosts) -> list:
    from apps.system_mgmt.models.system_settings import SystemSettings

    ordered = list(dict.fromkeys(hosts))
    SystemSettings.objects.update_or_create(key=SETTINGS_KEY, defaults={"value": ",".join(ordered)})
    return ordered


def add_host(host: str) -> list:
    """把主机加入 DB 侧清单（幂等），返回写入后的完整清单。"""
    normalized = normalize_host(host)
    hosts = db_hosts()
    if normalized not in hosts:
        hosts.append(normalized)
    saved = _save(hosts)
    logger.info("openapi allowlist 已新增主机 host=%s size=%s", normalized, len(saved))
    return saved


def remove_host(host: str) -> list:
    """把主机移出 DB 侧清单（幂等），返回写入后的完整清单。"""
    normalized = normalize_host(host)
    hosts = [item for item in db_hosts() if item != normalized]
    saved = _save(hosts)
    logger.info("openapi allowlist 已移除主机 host=%s size=%s", normalized, len(saved))
    return saved
