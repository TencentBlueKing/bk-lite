"""KV 注册条目校验与 Traefik 动态配置渲染。

纪律（design.md 3.5.3，全部 fail-closed）：
1. 单条目校验失败跳过并告警，不影响其余条目；
2. token_ref / shared_secret_ref 的引用可解析性纳入校验，失败即跳过，
   不得静默降级为无凭据转发；
3. base_url 必须落在部署侧允许清单（OPENAPI_BASEURL_ALLOWLIST）内；
   未配置允许清单时拒绝一切外部条目；
4. schema_version 未知 / 枚举值未知 → 整条跳过；未知字段忽略（前向兼容）；
5. ForwardAuth 地址（OPENAPI_AUTH_ADDRESS）未配置时不渲染任何外部路由。

渲染层持有最近一次成功快照：KV 整体不可达时返回快照并告警
（Traefik providers.http 拉取失败时自身也保留最后配置，双层兜底）。
"""

import os
import threading
from urllib.parse import urlparse

from apps.core.logger import openapi_logger as logger
from apps.core.openapi.kv import fetch_entries
from apps.core.openapi.registry import SERVICE_NAME_RE

ACTIVE_GATEWAY_VERSIONS = ("v1",)
SUPPORTED_SCHEMA_VERSIONS = {1}
VALID_TYPES = {"http"}
VALID_AUTH_MODES = {"trusted-header", "service-token"}

_lock = threading.Lock()
_snapshot = {"config": None, "services": [], "entries": {}}


def _resolve_ref(ref):
    """解析 "env:VAR" 形式的引用；不可解析返回 None。"""
    if not isinstance(ref, str) or not ref.startswith("env:"):
        return None
    return os.getenv(ref[len("env:"):]) or None


def _base_url_allowed(base_url: str) -> bool:
    allow = [
        item.strip()
        for item in os.getenv("OPENAPI_BASEURL_ALLOWLIST", "").split(",")
        if item.strip()
    ]
    if not allow:
        return False
    if "*" in allow:
        return True
    host = urlparse(base_url).hostname or ""
    return any(host == item or host.endswith(item) for item in allow)


def validate_entry(name: str, entry, internal_services=()):
    """返回 (normalized_entry | None, reason)。reason 为空串表示有效。"""
    if not isinstance(entry, dict):
        return None, "entry is not an object"
    if name.startswith("_") or not SERVICE_NAME_RE.match(name):
        return None, "invalid service name"
    if name in internal_services:
        return None, "conflicts with internal service"

    schema_version = entry.get("schema_version", 1)
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return None, f"unsupported schema_version {schema_version!r}"

    if entry.get("enabled", True) is False:
        return None, "disabled"

    entry_type = entry.get("type")
    if entry_type not in VALID_TYPES:
        return None, f"unknown type {entry_type!r}"

    base_url = entry.get("base_url")
    if not isinstance(base_url, str) or urlparse(base_url).scheme not in ("http", "https"):
        return None, "invalid base_url"
    if not _base_url_allowed(base_url):
        return None, "base_url not in allowlist"

    auth_mode = entry.get("auth_mode")
    if auth_mode not in VALID_AUTH_MODES:
        return None, f"unknown auth_mode {auth_mode!r}"

    secrets = {}
    if auth_mode == "trusted-header":
        secret = _resolve_ref(entry.get("shared_secret_ref"))
        if not secret:
            return None, "shared_secret_ref unresolvable"
        secrets["shared_secret"] = secret
    else:  # service-token
        token = _resolve_ref(entry.get("token_ref"))
        if not token:
            return None, "token_ref unresolvable"
        secrets["service_token"] = token

    paths = entry.get("paths")
    if paths is not None and (
        not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths)
    ):
        return None, "invalid paths"

    rate_limit = entry.get("rate_limit")
    if rate_limit is not None and (
        not isinstance(rate_limit, dict)
        or not all(isinstance(rate_limit.get(k), int) for k in ("average", "burst"))
    ):
        return None, "invalid rate_limit"

    versions = entry.get("gateway_versions")
    if versions is not None and (
        not isinstance(versions, list) or not all(isinstance(v, str) for v in versions)
    ):
        return None, "invalid gateway_versions"
    active = [v for v in (versions or ACTIVE_GATEWAY_VERSIONS) if v in ACTIVE_GATEWAY_VERSIONS]
    if not active:
        return None, "no active gateway version"

    required_roles = entry.get("required_roles") or []
    if not isinstance(required_roles, list):
        return None, "invalid required_roles"

    return (
        {
            "name": name,
            "base_url": base_url.rstrip("/"),
            "strip_prefix": bool(entry.get("strip_prefix", True)),
            "paths": paths or [],
            "auth_mode": auth_mode,
            "secrets": secrets,
            "rate_limit": rate_limit,
            "required_roles": required_roles,
            "doc_url": entry.get("doc_url", ""),
            "versions": active,
        },
        "",
    )


def _router_rule(version: str, name: str, paths) -> str:
    base = f"/openapi/{version}/{name}"
    if not paths:
        return f"PathPrefix(`{base}`)"
    prefixes = []
    for item in paths:
        sub = item[:-2] if item.endswith("/*") else item
        sub = "/" + sub.strip("/")
        prefixes.append(f"PathPrefix(`{base}{sub}`)")
    return " || ".join(prefixes)


def render_traefik_config(entries: dict, internal_services=()):
    """将注册条目渲染为 Traefik 动态配置（原生格式，供 providers.http）。

    返回 (config, report)。KV 字段与 Traefik 参数经本函数显式映射，
    两端命名不耦合。
    """
    report = {"rendered": [], "skipped": {}}
    routers, middlewares, services = {}, {}, {}

    auth_address = os.getenv("OPENAPI_AUTH_ADDRESS", "")
    if not auth_address:
        logger.warning("OPENAPI_AUTH_ADDRESS 未配置，不渲染任何外部服务路由（fail-closed）")
        for name in entries:
            report["skipped"][name] = "auth address unconfigured"
        return {"http": {"routers": {}, "middlewares": {}, "services": {}}}, report

    # 全局中间件：入站身份头清除（红线 1）与 ForwardAuth
    middlewares["openapi-clear-headers"] = {
        "headers": {
            "customRequestHeaders": {
                "X-BK-User": "",
                "X-BK-Team": "",
                "X-BK-Gateway-Auth": "",
            }
        }
    }
    middlewares["openapi-auth"] = {
        "forwardAuth": {
            "address": auth_address,
            "authResponseHeaders": ["X-BK-User", "X-BK-Team", "X-On-Behalf-Of"],
        }
    }

    for name in sorted(entries):
        normalized, reason = validate_entry(name, entries[name], internal_services)
        if normalized is None:
            report["skipped"][name] = reason
            if reason != "disabled":
                logger.warning("openapi_registry 条目 %s 被跳过：%s", name, reason)
            continue

        chain = ["openapi-clear-headers"]
        if normalized["rate_limit"]:
            mw = f"openapi-{name}-ratelimit"
            middlewares[mw] = {
                "rateLimit": {
                    "average": normalized["rate_limit"]["average"],
                    "burst": normalized["rate_limit"]["burst"],
                }
            }
            chain.append(mw)
        chain.append("openapi-auth")

        inject = f"openapi-{name}-inject"
        if normalized["auth_mode"] == "trusted-header":
            middlewares[inject] = {
                "headers": {
                    "customRequestHeaders": {
                        "X-BK-Gateway-Auth": normalized["secrets"]["shared_secret"]
                    }
                }
            }
        else:
            middlewares[inject] = {
                "headers": {
                    "customRequestHeaders": {
                        "Authorization": f"Bearer {normalized['secrets']['service_token']}"
                    }
                }
            }
        chain.append(inject)

        services[f"openapi-{name}"] = {
            "loadBalancer": {"servers": [{"url": normalized["base_url"]}]}
        }

        for version in normalized["versions"]:
            router_chain = list(chain)
            if normalized["strip_prefix"]:
                strip = f"openapi-{name}-strip-{version}"
                middlewares[strip] = {
                    "stripPrefix": {"prefixes": [f"/openapi/{version}/{name}"]}
                }
                router_chain.append(strip)
            routers[f"openapi-{version}-{name}"] = {
                "rule": _router_rule(version, name, normalized["paths"]),
                "service": f"openapi-{name}",
                "middlewares": router_chain,
            }
        report["rendered"].append(name)

    config = {"http": {"routers": routers, "middlewares": middlewares, "services": services}}
    return config, report


def refresh_snapshot(internal_services=()):
    """拉取 KV 并渲染；KV 不可达时保留最近一次成功快照（告警）。"""
    entries = fetch_entries()
    with _lock:
        if entries is None:
            if _snapshot["config"] is None:
                logger.warning("openapi_registry 不可达且无历史快照，返回空配置")
                return {"http": {"routers": {}, "middlewares": {}, "services": {}}}
            logger.warning("openapi_registry 不可达，沿用最近一次成功快照")
            return _snapshot["config"]

        config, report = render_traefik_config(entries, internal_services)
        _snapshot["config"] = config
        _snapshot["entries"] = entries
        _snapshot["services"] = list(report["rendered"])
        return config


def get_external_services():
    """最近一次成功快照中的外部 service 名（_me 使用，最终一致）。"""
    with _lock:
        return list(_snapshot["services"])


def get_external_entry(name: str):
    """按名取最近快照中的有效外部条目（ForwardAuth 授权检查使用）。"""
    with _lock:
        entry = _snapshot["entries"].get(name)
    if entry is None:
        return None
    normalized, _ = validate_entry(name, entry)
    return normalized


def get_external_catalog():
    """最近快照中有效外部条目的目录信息（_docs 使用，最终一致）。"""
    catalog = []
    for name in get_external_services():
        normalized = get_external_entry(name)
        if normalized is not None:
            catalog.append({"name": name, "doc_url": normalized["doc_url"]})
    return catalog
