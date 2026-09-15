"""Shared Meraki Dashboard API v1 client, probe helpers, and metric primitives."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.logger import logger, safe_log_value
from tasks.collectors.base_collector import BaseCollector
from utils.convert import convert_to_prometheus

ALLOWED_API_HOSTS = frozenset(
    {
        "api.meraki.com",
        "api.meraki.in",
        "api.meraki.ca",
        "api.meraki.cn",
        "api.gov-meraki.com",
    }
)
DEFAULT_ORIGIN = "https://api.meraki.com"
API_PREFIX = "/api/v1"
MAX_RETRIES = 5
MAX_RETRY_AFTER_SECONDS = 30
_LINK_NEXT = re.compile(r"<([^>]+)>\s*;\s*rel=\"?next\"?", re.I)
_AUTH_STATUS = frozenset({401, 403})
MONITOR_TYPE = "cisco_meraki"

ORG_RESOURCE = "meraki_org"
NETWORK_RESOURCE = "meraki_network"
DEVICE_INVENTORY_RESOURCE = "meraki_device_inventory"
DEVICE_RESOURCE = "meraki_device"
WIRELESS_INVENTORY_RESOURCE = "meraki_wireless_inventory"
WIRELESS_RESOURCE = "meraki_wireless_ap"
SWITCH_INVENTORY_RESOURCE = "meraki_switch_inventory"
SWITCH_RESOURCE = "meraki_switch"
APPLIANCE_INVENTORY_RESOURCE = "meraki_appliance_inventory"
APPLIANCE_RESOURCE = "meraki_appliance"

CONNECT_STATUS_METRICS = (
    (ORG_RESOURCE, "meraki_org_connect_status"),
    (DEVICE_INVENTORY_RESOURCE, "meraki_device_connect_status"),
    (WIRELESS_INVENTORY_RESOURCE, "meraki_wireless_connect_status"),
    (SWITCH_INVENTORY_RESOURCE, "meraki_switch_connect_status"),
    (APPLIANCE_INVENTORY_RESOURCE, "meraki_appliance_connect_status"),
)


def now_ms() -> int:
    return int(time.time() * 1000)


def gauge(value: Any) -> list[tuple[int, Any]]:
    return [(now_ms(), value)]


def dim_gauge(dims: list[tuple[str, str]], value: Any) -> dict:
    return {tuple(dims): gauge(value)}


def as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    parsed = as_float(value)
    if parsed is None:
        return default
    return int(parsed)


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    parsed = as_int(value, default)
    return max(minimum, min(parsed, maximum))


def status_code(status: str | None, mapping: dict[str, int], default: int = 0) -> int:
    if not status:
        return default
    return mapping.get(str(status).strip().lower(), default)


class MerakiDashboardClient:
    """HTTP client for Meraki Dashboard API v1 (API key, region host, 429, Link pagination)."""

    def __init__(self, *, base_url: str, api_key: str, timeout: float = 60.0):
        self.api_root = self._normalize_base_url(base_url)
        self.api_key = api_key or ""
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _normalize_base_url(raw: str) -> str:
        text = (raw or "").strip() or DEFAULT_ORIGIN
        if "://" not in text:
            text = "https://" + text
        parsed = urlparse(text)
        if parsed.scheme != "https":
            raise ValueError("Meraki Dashboard base URL must use https")
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_API_HOSTS:
            raise ValueError("Meraki Dashboard base URL host is not an allowed regional endpoint")
        path = parsed.path.rstrip("/")
        if path in {"", "/api"}:
            path = API_PREFIX
        elif not path.startswith(API_PREFIX):
            path = API_PREFIX
        return f"https://{host}{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "X-Cisco-Meraki-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "BK-Lite-Cisco-Meraki-Monitor",
        }

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=False)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        return False

    def _absolute(self, url_or_path: str) -> str:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            parsed = urlparse(url_or_path)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or host not in ALLOWED_API_HOSTS:
                raise ValueError("Meraki pagination URL host is not an allowed regional endpoint")
            return url_or_path
        return urljoin(self.api_root.rstrip("/") + "/", url_or_path.lstrip("/"))

    async def request(self, method: str, url_or_path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("Meraki Dashboard client is not started")
        url = self._absolute(url_or_path)
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self._client.request(method, url, headers=self._headers(), params=params)
            except httpx.TimeoutException as error:
                last_error = error
                logger.warning(
                    "event=meraki_http_timeout attempt=%s failed_stage=http error_type=%s",
                    attempt,
                    type(error).__name__,
                )
                await asyncio.sleep(min(attempt, MAX_RETRY_AFTER_SECONDS))
                continue
            except httpx.RequestError as error:
                last_error = error
                logger.warning(
                    "event=meraki_http_request_error attempt=%s failed_stage=http error_type=%s",
                    attempt,
                    type(error).__name__,
                )
                await asyncio.sleep(min(attempt, MAX_RETRY_AFTER_SECONDS))
                continue
            if response.status_code == 429:
                retry_after = as_int(response.headers.get("Retry-After"), 1)
                wait_seconds = min(max(retry_after, 1), MAX_RETRY_AFTER_SECONDS)
                logger.warning(
                    "event=meraki_rate_limited attempt=%s wait_seconds=%s failed_stage=http error_type=RateLimited",
                    attempt,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                continue
            return response
        if last_error is not None:
            raise last_error
        raise RuntimeError("Meraki Dashboard API rate limit retries exhausted")

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        items: list[Any] = []
        url: str | None = path
        query = dict(params) if params else None
        first = True
        while url:
            response = await self.request("GET", url, params=query if first else None)
            first = False
            query = None
            if response.status_code in _AUTH_STATUS:
                raise PermissionError("Meraki Dashboard API authentication failed")
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                raise RuntimeError(f"Meraki Dashboard API HTTP {response.status_code}")
            payload = response.json() if response.content else None
            next_url = ""
            match = _LINK_NEXT.search(response.headers.get("Link") or "")
            if match:
                next_url = match.group(1)
            if isinstance(payload, list):
                items.extend(payload)
                url = next_url or None
                continue
            if next_url:
                logger.debug("event=meraki_ignore_next_link_on_object_payload")
            return payload
        return items


def required_params(collector: BaseCollector) -> dict[str, Any]:
    api_key = str(collector.params.get("password") or collector.params.get("token") or "").strip()
    organization_id = str(collector.params.get("organization_id") or "").strip()
    base_url = str(collector.params.get("base_url") or collector.params.get("host") or DEFAULT_ORIGIN).strip()
    if not api_key:
        raise ValueError("missing Meraki Dashboard API key")
    if not organization_id:
        raise ValueError("missing organization_id")
    try:
        timeout = float(collector.params.get("timeout") or 120)
    except (TypeError, ValueError):
        timeout = 120.0
    try:
        timespan = int(collector.params.get("timespan") or 86400)
    except (TypeError, ValueError):
        timespan = 86400
    return {
        "api_key": api_key,
        "organization_id": organization_id,
        "base_url": base_url,
        "timeout": timeout,
        "timespan": max(timespan, 1),
    }


async def require_organization(client: MerakiDashboardClient, organization_id: str) -> dict[str, Any]:
    organization = await client.get_json(f"/organizations/{organization_id}")
    if not organization:
        raise RuntimeError("Meraki organization not found")
    if not isinstance(organization, dict):
        raise RuntimeError("Meraki organization payload is invalid")
    return organization


async def require_list(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> list:
    payload = await client.get_json(path, params)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    raise RuntimeError("Meraki required endpoint returned a non-list payload")


async def require_object(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = await client.get_json(path, params)
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Meraki required endpoint returned a non-object payload")


async def optional_json(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return await client.get_json(path, params)
    except PermissionError:
        raise
    except (RuntimeError, httpx.TimeoutException, httpx.RequestError) as error:
        logger.warning(
            "event=meraki_optional_endpoint_skipped path=%s failed_stage=collect error_type=%s",
            safe_log_value(path.split("?")[0]),
            type(error).__name__,
        )
        return None


async def optional_list(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> list:
    payload = await optional_json(client, path, params)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return [payload] if payload else []


def connect_status_output(organization_id: str, status: int, families: tuple[tuple[str, str], ...] | None = None) -> str:
    metric_dict: dict[tuple[str, str], dict[str, Any]] = {}
    for resource_type, metric_name in families or CONNECT_STATUS_METRICS:
        metric_dict[(organization_id, resource_type)] = {metric_name: gauge(status)}
    return "\n".join(convert_to_prometheus(metric_dict)) + "\n"


def failed_collect_output(organization_id: str, *, failed_stage: str, error: Exception) -> str:
    logger.warning(
        "event=meraki_collect_failed monitor_type=%s organization_id=%s failed_stage=%s error_type=%s",
        MONITOR_TYPE,
        safe_log_value(organization_id),
        failed_stage,
        type(error).__name__,
    )
    return connect_status_output(organization_id, 0)


def family_connect_failed(organization_id: str, resource_type: str, metric_name: str) -> dict[tuple[str, str], dict[str, Any]]:
    return {(organization_id, resource_type): {metric_name: gauge(0)}}


async def probe_organization(collector: BaseCollector) -> AccessProbeResult:
    try:
        params = required_params(collector)
    except ValueError:
        return AccessProbeResult(status=AccessProbeStatus.MISCONFIGURED, error_code="misconfigured")
    try:
        async with MerakiDashboardClient(
            base_url=params["base_url"],
            api_key=params["api_key"],
            timeout=params["timeout"],
        ) as client:
            payload = await client.get_json(f"/organizations/{params['organization_id']}")
    except PermissionError:
        return AccessProbeResult(status=AccessProbeStatus.AUTH_FAILED, error_code="authentication_failed")
    except ValueError:
        return AccessProbeResult(status=AccessProbeStatus.MISCONFIGURED, error_code="misconfigured")
    except httpx.TimeoutException:
        return AccessProbeResult(status=AccessProbeStatus.NO_RESPONSE, error_code="no_response")
    except httpx.RequestError:
        return AccessProbeResult(status=AccessProbeStatus.TARGET_UNREACHABLE, error_code="target_unreachable")
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "event=meraki_probe_failed monitor_type=%s failed_stage=probe error_type=%s",
            MONITOR_TYPE,
            type(error).__name__,
        )
        return AccessProbeResult(status=AccessProbeStatus.SERVICE_UNAVAILABLE, error_code="collection_failed")
    if not payload:
        return AccessProbeResult(status=AccessProbeStatus.MISCONFIGURED, error_code="organization_not_found")
    return AccessProbeResult(status=AccessProbeStatus.READY)
