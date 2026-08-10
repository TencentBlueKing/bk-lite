"""Thin HTTP client for external Prometheus datasources."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import urlparse

import requests

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.rest_api import read_limited_json

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60
CONNECT_TIMEOUT_SECONDS = 10
MAX_ERROR_TEXT_LENGTH = 500


def normalize_prometheus_origin(url: str) -> str:
    if not url or not isinstance(url, str):
        raise ConnectorError("Prometheus URL 不能为空", code="prometheus_url_invalid", status_code=400)

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ConnectorError("Prometheus URL 必须是 http 或 https", code="prometheus_url_invalid", status_code=400)
    if parsed.username or parsed.password:
        raise ConnectorError("Prometheus URL 不能包含用户名或密码", code="prometheus_url_invalid", status_code=400)
    if parsed.path and parsed.path not in {"", "/"}:
        raise ConnectorError("Prometheus URL 不能包含路径", code="prometheus_url_invalid", status_code=400)
    if not parsed.netloc:
        raise ConnectorError("Prometheus URL 无效", code="prometheus_url_invalid", status_code=400)

    return f"{parsed.scheme}://{parsed.netloc}"


def build_auth_headers(connection_config: dict[str, Any]) -> dict[str, str]:
    auth_type = str(connection_config.get("auth_type") or "none").lower()
    if auth_type in {"", "none"}:
        return {}

    if auth_type == "basic":
        username = connection_config.get("username")
        password = connection_config.get("password")
        if not username or not password:
            raise ConnectorError(
                "Prometheus Basic 鉴权需要用户名和密码",
                code="prometheus_auth_invalid",
                status_code=400,
            )
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    if auth_type == "bearer":
        token = connection_config.get("token")
        if not token:
            raise ConnectorError(
                "Prometheus Bearer 鉴权需要 token",
                code="prometheus_auth_invalid",
                status_code=400,
            )
        return {"Authorization": f"Bearer {token}"}

    raise ConnectorError(
        f"不支持的 Prometheus 鉴权类型: {auth_type}",
        code="prometheus_auth_invalid",
        status_code=400,
    )


class PrometheusHttpClient:
    def __init__(self, http_client=None):
        self.http_client = http_client or requests

    def query_range(
        self,
        connection_config: dict[str, Any],
        query: str,
        start: str,
        end: str,
        step: str,
    ) -> dict[str, Any]:
        origin = normalize_prometheus_origin(connection_config.get("url", ""))
        url = f"{origin}/api/v1/query_range"
        params = {"query": query, "start": start, "end": end, "step": step}
        return self._request_json(connection_config, "GET", url, params=params)

    def query(
        self,
        connection_config: dict[str, Any],
        query: str,
        time: str | None = None,
    ) -> dict[str, Any]:
        origin = normalize_prometheus_origin(connection_config.get("url", ""))
        url = f"{origin}/api/v1/query"
        params: dict[str, str] = {"query": query}
        if time is not None:
            params["time"] = time
        return self._request_json(connection_config, "GET", url, params=params)

    def healthy(self, connection_config: dict[str, Any]) -> None:
        origin = normalize_prometheus_origin(connection_config.get("url", ""))
        if self._is_successful_get(connection_config, f"{origin}/-/healthy"):
            return
        if self._is_successful_get(connection_config, f"{origin}/api/v1/status/buildinfo"):
            return
        raise ConnectorError("Prometheus 健康检查失败", code="prometheus_unhealthy", status_code=502)

    def _resolve_timeout(self, connection_config: dict[str, Any]) -> tuple[int, int]:
        raw = connection_config.get("timeout_seconds")
        if raw is None:
            read_timeout = DEFAULT_TIMEOUT_SECONDS
        else:
            try:
                read_timeout = int(raw)
            except (TypeError, ValueError):
                raise ConnectorError(
                    "Prometheus timeout_seconds 无效",
                    code="prometheus_timeout_invalid",
                    status_code=400,
                )
        read_timeout = max(1, min(read_timeout, MAX_TIMEOUT_SECONDS))
        return CONNECT_TIMEOUT_SECONDS, read_timeout

    def _build_headers(self, connection_config: dict[str, Any]) -> dict[str, str]:
        return build_auth_headers(connection_config)

    def _is_successful_get(self, connection_config: dict[str, Any], url: str) -> bool:
        try:
            response = self.http_client.request(
                method="GET",
                url=url,
                headers=self._build_headers(connection_config),
                timeout=self._resolve_timeout(connection_config),
                allow_redirects=False,
            )
            try:
                return 200 <= response.status_code < 300
            finally:
                response.close()
        except requests.RequestException as exc:
            logger.debug("Prometheus health check request failed: %s", exc)
            return False

    def _request_json(
        self,
        connection_config: dict[str, Any],
        method: str,
        url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.http_client.request(
                method=method,
                url=url,
                headers=self._build_headers(connection_config),
                params=params,
                timeout=self._resolve_timeout(connection_config),
                allow_redirects=False,
                stream=True,
            )
            try:
                if response.status_code in {401, 403}:
                    raise ConnectorError(
                        "Prometheus 鉴权失败",
                        code="prometheus_auth_failed",
                        status_code=400,
                    )
                if not (200 <= response.status_code < 300):
                    raise ConnectorError(
                        f"Prometheus 请求失败: HTTP {response.status_code}",
                        code="prometheus_request_failed",
                        status_code=502,
                    )
                payload = read_limited_json(response)
            except json.JSONDecodeError as exc:
                raise ConnectorError(
                    f"Prometheus 响应 JSON 无效: {exc}",
                    code="prometheus_invalid_response",
                    status_code=502,
                ) from exc
            finally:
                response.close()
        except ConnectorError:
            raise
        except requests.Timeout as exc:
            raise ConnectorError(
                f"Prometheus 请求超时: {exc}",
                code="prometheus_timeout",
                status_code=502,
            ) from exc
        except requests.RequestException as exc:
            raise ConnectorError(
                f"Prometheus 请求失败: {exc}",
                code="prometheus_request_failed",
                status_code=502,
            ) from exc

        if not isinstance(payload, dict):
            raise ConnectorError(
                "Prometheus 响应格式无效",
                code="prometheus_invalid_response",
                status_code=502,
            )

        if payload.get("status") == "error":
            error_text = str(payload.get("error") or payload.get("errorType") or "unknown error")
            if len(error_text) > MAX_ERROR_TEXT_LENGTH:
                error_text = error_text[:MAX_ERROR_TEXT_LENGTH] + "..."
            raise ConnectorError(
                f"Prometheus 查询错误: {error_text}",
                code="prometheus_query_error",
                status_code=400,
            )

        return payload
