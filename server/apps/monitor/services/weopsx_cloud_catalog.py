"""代理 WeOpsX 已装云目录；失败降级为空列表，不阻断 bk-lite 侧栏。"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import httpx

from apps.core.logger import monitor_logger as logger
from apps.core.logger import safe_exception_info, safe_log_value

# 契约对齐 WeOpsX-Enterprise#231：GET /api/v1/cmp/cloud-nav/catalog
DEFAULT_CATALOG_PATH = "/api/v1/cmp/cloud-nav/catalog"
DEFAULT_DEEP_LINK_TEMPLATE = "/monitor/view/dashboard/{id}"
MAX_CATALOG_ITEMS = 200
MAX_DEEP_LINK_LEN = 2048
CATALOG_TIMEOUT_SECONDS = 5.0
_MIN_OVERLAP_TOKEN_LEN = 4

# type=Cloud 及历史入根别名；与侧栏 isCloudFamilySidebarType 对齐。
CLOUD_FAMILY_TYPE_IDS = ("Cloud", "Tencent Cloud", "Aliyun Cloud")

# 产品路径已装云：腾讯云 / 阿里云 / 深信服 SCP / 云宏 CNware，及 WeOpsX 目录同义 id。
_EXCLUDED_ID_MARKERS = (
    "qcloud",
    "tencent",
    "sangfordesktop",
    "aliyun",
    "sangforscp",
    "cnware",
)
_EXCLUDED_NAME_MARKERS = (
    "qcloud",
    "tencent",
    "腾讯",
    "sangfordesktop",
    "aliyun",
    "阿里云",
    "sangforscp",
    "sangfor scp",
    "深信服scp",
    "深信服 scp",
    "cnware",
    "云宏",
)

LOG_FETCHED = "event=weopsx_cloud_catalog_fetched item_count=%s"
LOG_DEGRADED = "event=weopsx_cloud_catalog_degraded failed_stage=%s error_type=%s item_count=%s"
LOG_FAILED = "event=weopsx_cloud_catalog_failed failed_stage=%s error_type=%s item_count=%s"
LOG_LOCAL_IDENTITIES = "event=weopsx_cloud_catalog_local_identities_unavailable failed_stage=%s error_type=%s"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _validate_base_url(raw: str) -> str | None:
    text = (raw or "").strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if parsed.query or parsed.fragment:
        return None
    return text


def _validate_catalog_path(raw: str) -> str:
    path = (raw or DEFAULT_CATALOG_PATH).strip() or DEFAULT_CATALOG_PATH
    if not path.startswith("/"):
        path = f"/{path}"
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return DEFAULT_CATALOG_PATH
    parts = [part for part in parsed.path.split("/") if part]
    if ".." in parts:
        return DEFAULT_CATALOG_PATH
    return "/" + "/".join(parts)


def _fold_identity(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", (text or "").lower())


def _identity_tokens(*parts: str) -> set[str]:
    tokens = set()
    for part in parts:
        folded = _fold_identity(part)
        if folded:
            tokens.add(folded)
    return tokens


def _identities_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= _MIN_OVERLAP_TOKEN_LEN and shorter in longer


def _is_excluded_cloud(plugin_id: str, name: str, cn_name: str) -> bool:
    identity = _fold_identity(plugin_id)
    if identity == "tcp":
        return True
    if any(marker and marker in identity for marker in (_fold_identity(item) for item in _EXCLUDED_ID_MARKERS)):
        return True
    joined = _fold_identity(f"{name} {cn_name}")
    return any(marker and marker in joined for marker in (_fold_identity(item) for item in _EXCLUDED_NAME_MARKERS))


def _overlaps_local_cloud(plugin_id: str, name: str, cn_name: str, local_identities) -> bool:
    if not local_identities:
        return False
    catalog_tokens = _identity_tokens(plugin_id, name, cn_name)
    for catalog_token in catalog_tokens:
        for local_token in local_identities:
            if _identities_overlap(catalog_token, local_token):
                return True
    return False


def load_local_cloud_family_identities() -> frozenset[str]:
    """已装 type=Cloud（含历史别名）平台基对象的 name / display_name，供目录去重。"""
    try:
        from apps.monitor.models.monitor_object import MonitorObject

        rows = MonitorObject.objects.filter(type_id__in=CLOUD_FAMILY_TYPE_IDS).exclude(level="derivative").values_list("name", "display_name")
        tokens = set()
        for name, display_name in rows:
            tokens.update(_identity_tokens(name, display_name))
        return frozenset(tokens)
    except Exception as exc:
        logger.warning(LOG_LOCAL_IDENTITIES, "query", type(exc).__name__)
        return frozenset()


def _as_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _catalog_locale(raw: str | None) -> str:
    text = _as_text(raw).lower()
    if not text:
        return ""
    if text.startswith("zh"):
        return "zh-Hans"
    return "en"


def _resolve_deep_link(raw: str, plugin_id: str) -> str:
    """Keep same-origin relative paths; do not join the catalog API origin."""
    fallback = DEFAULT_DEEP_LINK_TEMPLATE.format(id=plugin_id)
    link = _as_text(raw) or fallback
    if len(link) > MAX_DEEP_LINK_LEN:
        link = fallback
    parsed = urlsplit(link)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        return link
    if parsed.scheme:
        link = fallback
    if not link.startswith("/"):
        link = f"/{link}"
    return link


def _extract_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if isinstance(items, list):
        return items
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return []


def normalize_weopsx_catalog_items(payload, local_identities=None) -> list[dict]:
    identities = frozenset(local_identities or ())
    normalized = []
    seen = set()
    for raw in _extract_items(payload):
        if len(normalized) >= MAX_CATALOG_ITEMS:
            break
        if not isinstance(raw, dict):
            continue
        plugin_id = _as_text(raw.get("id") or raw.get("name"))
        if not plugin_id or plugin_id in seen:
            continue
        name = _as_text(raw.get("name")) or plugin_id
        cn_name = _as_text(raw.get("cn_name")) or name
        if _is_excluded_cloud(plugin_id, name, cn_name) or _overlaps_local_cloud(plugin_id, name, cn_name, identities):
            continue
        children_count = raw.get("children_count", 0)
        try:
            count = int(children_count)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        seen.add(plugin_id)
        normalized.append(
            {
                "id": plugin_id,
                "name": name,
                "cn_name": cn_name,
                "account_obj_id": _as_text(raw.get("account_obj_id")) or f"{plugin_id}_account",
                "children_count": count,
                "deep_link": _resolve_deep_link(_as_text(raw.get("deep_link")), plugin_id),
            }
        )
    return normalized


def _empty_catalog(*, failed_stage: str, error_type: str, with_traceback: bool = False, error=None) -> dict:
    if with_traceback and error is not None:
        logger.error(
            LOG_FAILED,
            failed_stage,
            error_type,
            0,
            exc_info=safe_exception_info(error),
        )
    else:
        logger.warning(LOG_DEGRADED, failed_stage, error_type, 0)
    return {"items": [], "degraded": True, "error_type": error_type}


def fetch_weopsx_cloud_catalog(*, locale: str | None = None, authorization: str | None = None) -> dict:
    # WEOPSX_BASE_URL 开启双源云侧栏；应指向真实 WeOpsX 目录，不要指向校验用 stub。
    base_url = _validate_base_url(_env("WEOPSX_BASE_URL"))
    if not base_url:
        return _empty_catalog(failed_stage="configure", error_type="unconfigured")

    catalog_path = _validate_catalog_path(_env("WEOPSX_CLOUD_CATALOG_PATH", DEFAULT_CATALOG_PATH))
    token = _env("WEOPSX_TOKEN") or _env("WEOPSX_API_TOKEN")
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif authorization:
        headers["Authorization"] = authorization

    params = {}
    locale_text = _catalog_locale(locale)
    if locale_text:
        params["locale"] = locale_text

    url = f"{base_url}{catalog_path}"
    try:
        timeout_raw = _env("WEOPSX_CLOUD_CATALOG_TIMEOUT", str(CATALOG_TIMEOUT_SECONDS))
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = CATALOG_TIMEOUT_SECONDS
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            response = client.get(url, headers=headers, params=params or None)
    except httpx.HTTPError as exc:
        return _empty_catalog(
            failed_stage="request",
            error_type=type(exc).__name__,
            with_traceback=True,
            error=exc,
        )

    if response.status_code in {401, 403}:
        logger.warning(
            LOG_DEGRADED,
            "auth",
            f"http_{response.status_code}",
            0,
        )
        return {"items": [], "degraded": True, "error_type": f"http_{response.status_code}"}
    if response.status_code >= 400:
        logger.warning(
            LOG_DEGRADED,
            "upstream",
            f"http_{response.status_code}",
            0,
        )
        return {"items": [], "degraded": True, "error_type": f"http_{response.status_code}"}

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning(
            "event=weopsx_cloud_catalog_degraded failed_stage=%s error_type=%s item_count=%s host=%s",
            "decode",
            type(exc).__name__,
            0,
            safe_log_value(urlsplit(base_url).hostname),
        )
        return {"items": [], "degraded": True, "error_type": "invalid_json"}

    items = normalize_weopsx_catalog_items(
        payload,
        local_identities=load_local_cloud_family_identities(),
    )
    logger.info(LOG_FETCHED, len(items))
    return {"items": items, "degraded": False}
