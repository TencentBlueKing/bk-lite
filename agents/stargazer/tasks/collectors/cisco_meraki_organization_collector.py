"""Cisco Meraki Dashboard API v1 organization collector."""

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
MONITOR_TYPE = "cisco_meraki_organization"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _gauge(value: Any) -> list[tuple[int, Any]]:
    return [(_now_ms(), value)]


def _dim_gauge(dims: list[tuple[str, str]], value: Any) -> dict:
    return {tuple(dims): _gauge(value)}


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    parsed = _as_float(value)
    if parsed is None:
        return default
    return int(parsed)


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    parsed = _as_int(value, default)
    return max(minimum, min(parsed, maximum))


def _status_code(status: str | None, mapping: dict[str, int], default: int = 0) -> int:
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
                retry_after = _as_int(response.headers.get("Retry-After"), 1)
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


def _connect_status_output(organization_id: str, status: int) -> str:
    metric_dict = {
        (organization_id, "meraki_org"): {
            "meraki_org_connect_status": _gauge(status),
        }
    }
    return "\n".join(convert_to_prometheus(metric_dict)) + "\n"


def _failed_collect_output(organization_id: str, *, failed_stage: str, error: Exception) -> str:
    logger.warning(
        "event=meraki_collect_failed monitor_type=%s organization_id=%s failed_stage=%s error_type=%s",
        MONITOR_TYPE,
        safe_log_value(organization_id),
        failed_stage,
        type(error).__name__,
    )
    return _connect_status_output(organization_id, 0)


class CiscoMerakiOrganizationCollector(BaseCollector):
    """Collect organization inventory, networks, and API health."""

    async def probe(self) -> AccessProbeResult:
        return await _probe_organization(self)

    async def collect(self) -> str:
        try:
            params = _required_params(self)
        except ValueError as error:
            organization_id = str(self.params.get("organization_id") or "").strip() or "unknown"
            return _failed_collect_output(organization_id, failed_stage="params", error=error)
        organization_id = params["organization_id"]
        logger.info(
            "event=meraki_collect_start monitor_type=%s organization_id=%s",
            MONITOR_TYPE,
            safe_log_value(organization_id),
        )
        try:
            async with MerakiDashboardClient(
                base_url=params["base_url"],
                api_key=params["api_key"],
                timeout=params["timeout"],
            ) as client:
                organization = await _require_organization(client, organization_id)
                networks = await _require_list(
                    client,
                    f"/organizations/{organization_id}/networks",
                    {"perPage": 1000},
                )
        except Exception as error:  # noqa: BLE001 - 失败仍导出 connect_status=0，供告警策略消费
            return _failed_collect_output(organization_id, failed_stage="collect", error=error)
        api_enabled = 1 if ((organization.get("api") or {}).get("enabled") is True) else 0
        metric_dict = {
            (organization_id, "meraki_org"): {
                "meraki_org_connect_status": _gauge(1),
                "meraki_org_api_enabled": _gauge(api_enabled),
                "meraki_org_network_count": _gauge(len(networks)),
            }
        }
        for network in networks:
            if not isinstance(network, dict):
                continue
            network_id = str(network.get("id") or "").strip()
            if not network_id:
                continue
            product_types = ",".join(str(item) for item in (network.get("productTypes") or []) if item)
            metric_dict[(network_id, "meraki_network")] = {
                "meraki_network_present": _dim_gauge(
                    [
                        ("network_name", str(network.get("name") or "")),
                        ("product_types", product_types),
                    ],
                    1,
                )
            }
        output = "\n".join(convert_to_prometheus(metric_dict)) + "\n"
        logger.info(
            "event=meraki_collect_success monitor_type=%s network_count=%s",
            MONITOR_TYPE,
            len(networks),
        )
        return output


async def _probe_organization(collector: BaseCollector) -> AccessProbeResult:
    try:
        params = _required_params(collector)
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


def _required_params(collector: BaseCollector) -> dict[str, Any]:
    api_key = str(collector.params.get("password") or collector.params.get("token") or "").strip()
    organization_id = str(collector.params.get("organization_id") or "").strip()
    base_url = str(collector.params.get("base_url") or collector.params.get("host") or DEFAULT_ORIGIN).strip()
    if not api_key:
        raise ValueError("missing Meraki Dashboard API key")
    if not organization_id:
        raise ValueError("missing organization_id")
    try:
        timeout = float(collector.params.get("timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60.0
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


async def _require_organization(client: MerakiDashboardClient, organization_id: str) -> dict[str, Any]:
    organization = await client.get_json(f"/organizations/{organization_id}")
    if not organization:
        raise RuntimeError("Meraki organization not found")
    if not isinstance(organization, dict):
        raise RuntimeError("Meraki organization payload is invalid")
    return organization


async def _require_list(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> list:
    payload = await client.get_json(path, params)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    raise RuntimeError("Meraki required endpoint returned a non-list payload")


async def _optional_list(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> list:
    payload = await _optional_json(client, path, params)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return [payload] if payload else []


async def _optional_json(client: MerakiDashboardClient, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return await client.get_json(path, params)
    except PermissionError:
        raise
    except RuntimeError as error:
        logger.warning(
            "event=meraki_optional_endpoint_skipped path=%s failed_stage=collect error_type=%s",
            safe_log_value(path.split("?")[0]),
            type(error).__name__,
        )
        return None
