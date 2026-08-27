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

读侧（_me / _docs / _auth）在快照距上次 KV 对账超过 TTL 时触发回源
（OPENAPI_REGISTRY_CACHE_TTL，默认 10 秒，0 表示每次读都回源），把多 worker
下「等 Traefik 轮询轮到本进程」的无界滞后收敛到 ≤ TTL + 一次对账耗时；
KV 不可达时仍降级到最近快照。温快照的回源走后台线程
（stale-while-revalidate）：请求线程立即以现有快照响应、绝不等待 NATS，
_auth 的请求时延与 KV/NATS 健康状况解耦；仅进程冷启动首次对账与 TTL=0
保持同步。并发写回以发起时间为围栏，乱序完成的旧回源不会覆盖更新的数据。
注意这只保证注册表数据的新鲜度，外部服务实际可调还取决于 Traefik 已拉取
渲染配置，故 _docs / _me 依旧不可作为可用性判据。
"""

import os
import threading
import time
from urllib.parse import urlparse

from apps.core.logger import openapi_logger as logger
from apps.core.openapi.kv import fetch_entries
from apps.core.openapi.registry import SERVICE_NAME_RE

ACTIVE_GATEWAY_VERSIONS = ("v1",)
SUPPORTED_SCHEMA_VERSIONS = {1}
VALID_TYPES = {"http"}
VALID_AUTH_MODES = {"trusted-header", "service-token"}

DEFAULT_REGISTRY_CACHE_TTL = 10.0

_lock = threading.Lock()
_snapshot = {
    "config": None,
    "services": [],
    "entries": {},
    "checked_at": 0.0,
    "fetch_started_at": 0.0,
}


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
    host = (urlparse(base_url).hostname or "").lower()
    if not host:
        return False
    for item in allow:
        item = item.lower()
        # 后缀匹配必须落在点边界上，否则 allow=itsm-svc 会放行 evil-itsm-svc
        suffix = item if item.startswith(".") else "." + item
        if host == item.lstrip(".") or host.endswith(suffix):
            return True
    return False


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
        return _pack({}, {}, {}), report

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
                        "X-BK-Gateway-Auth": normalized["secrets"]["shared_secret"],
                        # 清除调用方的平台凭据：信任头模式下上游按注入的身份头
                        # 识别用户，不需要也不应看到调用方的 API 令牌 / JWT——
                        # 否则半可信上游可凭其冒充调用方回调平台。
                        # service-token 模式天然覆盖该头，无此问题。
                        "Authorization": "",
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

    return _pack(routers, middlewares, services), report


def _pack(routers, middlewares, services):
    """组装动态配置，省略空小节。

    Traefik 的动态配置解码器不接受空 map：整份配置里出现 "routers": {} 会以
    `routers cannot be a standalone element` 整份拒绝（连同其中合法的
    middlewares 一起失效）。未注册任何外部服务是常态（首次部署即如此），
    因此空小节必须省略而非置空；三者皆空时返回 {"http": {}}。
    真机验证：.149 HA 栈曾因此让 http provider 配置持续被拒。
    """
    if not routers:
        # 无路由时全局中间件没有任何引用方，整份省略；避免下发只含孤立
        # 中间件的配置，也规避空 map 触发的解码拒绝
        return {"http": {}}
    http = {"routers": routers}
    if middlewares:
        http["middlewares"] = middlewares
    if services:
        http["services"] = services
    return {"http": http}


def refresh_snapshot(internal_services=()):
    """拉取 KV 并渲染；KV 不可达时保留最近一次成功快照（告警）。

    写回以发起时间为围栏：provider 轮询与读侧后台对账可同时在途，写回
    顺序由网络快慢决定，「发起早、完成晚」的旧结果不得覆盖已写入的更新
    数据——否则 KV 中刚发生的禁用 / 注销会被旧数据短暂复活，超出承诺的
    滞后上界。被丢弃时返回当前（更新的）快照。
    """
    started = time.monotonic()
    entries = fetch_entries()
    with _lock:
        # 无论成败都记账：本次已付过一次 KV 往返，读侧 TTL 窗口内不再重试
        _snapshot["checked_at"] = time.monotonic()
        if entries is None:
            if _snapshot["config"] is None:
                logger.warning("openapi_registry 不可达且无历史快照，返回空配置")
                return _pack({}, {}, {})
            logger.warning("openapi_registry 不可达，沿用最近一次成功快照")
            return _snapshot["config"]

        if started < _snapshot["fetch_started_at"]:
            logger.warning("openapi_registry 乱序回源结果被丢弃（发起早于当前快照数据）")
            return _snapshot["config"]
        _snapshot["fetch_started_at"] = started
        config, report = render_traefik_config(entries, internal_services)
        _snapshot["config"] = config
        _snapshot["entries"] = entries
        _snapshot["services"] = list(report["rendered"])
        return config


def _cache_ttl():
    raw = os.getenv("OPENAPI_REGISTRY_CACHE_TTL", "")
    if not raw:
        return DEFAULT_REGISTRY_CACHE_TTL
    try:
        return max(float(raw), 0.0)
    except ValueError:
        logger.warning(
            "OPENAPI_REGISTRY_CACHE_TTL=%r 非法，使用默认 %s 秒",
            raw,
            DEFAULT_REGISTRY_CACHE_TTL,
        )
        return DEFAULT_REGISTRY_CACHE_TTL


def _internal_services():
    from apps.core.openapi.registry import default_registry

    return default_registry.services()


def _ensure_snapshot_fresh():
    """读侧新鲜度兜底（stale-while-revalidate）：距上次 KV 对账超过 TTL 时触发回源。

    - checked_at 记录的是最近一次「尝试」而非「成功」——KV 故障期间不得让
      _me / _docs / _auth 的每次读取都付一次 NATS 往返（放大故障、打穿
      NATS），失败后同样要等下个 TTL 窗口再试。锁内先占位再触发回源，
      并发读不会齐发（TTL>0 时每 worker 每 TTL 至多新发一次）。
    - 温快照（本进程已有成功对账）过期时：立即以现有快照响应，由后台
      线程对账——请求线程绝不等待 NATS，_auth 等请求时延与 KV/NATS 健康
      状况解耦；数据可见滞后 ≤ TTL + 一次对账耗时。
    - 仅两种情况同步回源并等待结果：进程冷启动（尚无任何成功快照，避免
      网关重启后外部服务在快照就绪前多一窗 404）与 TTL=0（显式要求读
      时点新鲜度）。此时最坏阻塞为 kv.fetch_entries 的整体硬预算。
    """
    ttl = _cache_ttl()
    now = time.monotonic()
    with _lock:
        if ttl > 0 and now - _snapshot["checked_at"] < ttl:
            return
        _snapshot["checked_at"] = now
        cold = _snapshot["config"] is None
    if cold or ttl == 0:
        refresh_snapshot(internal_services=_internal_services())
    else:
        _refresh_in_background()


def _background_refresh_run():
    try:
        refresh_snapshot(internal_services=_internal_services())
    except Exception:  # 后台对账绝不外抛
        logger.exception("openapi_registry 后台对账失败")


def _refresh_in_background():
    threading.Thread(target=_background_refresh_run, name="openapi-registry-refresh", daemon=True).start()


def _get_entry_normalized(name: str):
    with _lock:
        entry = _snapshot["entries"].get(name)
    if entry is None:
        return None
    normalized, _ = validate_entry(name, entry)
    return normalized


def get_external_services():
    """外部 service 名（_me 使用）：快照 + TTL 回源，KV 不可达时最终一致。"""
    _ensure_snapshot_fresh()
    with _lock:
        return list(_snapshot["services"])


def get_external_entry(name: str):
    """按名取有效外部条目（ForwardAuth 授权检查使用）。

    查找前先经 TTL 闸门与 KV 对账，新注册服务在本进程的 miss 窗口 ≤ TTL；
    fail-closed 语义不变：对账后仍查无此名即返回 None（上层 404）。
    """
    _ensure_snapshot_fresh()
    return _get_entry_normalized(name)


def get_external_catalog():
    """有效外部条目的目录信息（_docs 使用）：快照 + TTL 回源。"""
    _ensure_snapshot_fresh()
    with _lock:
        services = list(_snapshot["services"])
    catalog = []
    for name in services:
        normalized = _get_entry_normalized(name)
        if normalized is not None:
            catalog.append({"name": name, "doc_url": normalized["doc_url"]})
    return catalog
