# -*- coding: utf-8 -*-
"""
WeOps OpenAPI adapter for network topology canvases.

Contract follows design.md §5 / §10 / proposal.md "WeOps OpenAPI contract".

Hard invariants:

* All requests go under ``/open_api/bklite/network_topology/``.
* All requests carry the ``x-token`` header (design.md §5.3).
* Responses are uniformly wrapped ``{"result": true, "data": <payload>}``;
  we peel exactly one layer to get ``data`` (see design.md §5.2).
* ``node_ref`` is the JSON of the node dict, encoded via
  ``encodeURIComponent(JSON.stringify(node_ref))`` when it appears in the
  URL path (services.py / views.py line 56 — confirms it goes in the
  ``{node_ref}`` segment, not as a query string).
* Item-level ``error_code`` strings from WeOps are mapped onto the
  internal enum :class:`NetworkTopologyErrorType`. Unknown codes fall back
  to ``UNKNOWN``.

This module intentionally hides requests behind a swappable ``http_client``
so the test suite can run without a live WeOps service.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from urllib.parse import quote, urljoin

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #


class NetworkTopologyErrorType(str, Enum):
    """Internal canonical error codes surfaced from item-level WeOps errors."""

    SOURCE_NOT_FOUND = "source_not_found"
    NODE_MISMATCH = "node_mismatch"
    SOURCE_INACTIVE = "source_inactive"
    TEMPLATE_MISMATCH = "template_mismatch"
    TEMPLATE_NOT_FOUND = "template_not_found"
    NODE_REF_INVALID = "node_ref_invalid"
    METRIC_NOT_FOUND = "metric_not_found"
    METRIC_QUERY_FAILED = "metric_query_failed"
    METRIC_NO_DATA = "metric_no_data"
    INTERFACE_RELATION_QUERY_FAILED = "interface_relation_query_failed"
    INTERFACE_QUERY_FAILED = "interface_query_failed"
    INTERFACE_NOT_FOUND = "interface_not_found"
    STATUS_METRIC_NOT_FOUND = "status_metric_not_found"
    STATUS_QUERY_FAILED = "status_query_failed"
    STATUS_NO_DATA = "status_no_data"
    UNKNOWN = "unknown"


# Each WeOps error_code is mapped to an internal type. Unknown codes fall
# back to UNKNOWN so the adapter never crashes when WeOps rolls out new
# codes (design.md §10 / spec §"Adapter handles unknown error_code
# gracefully").
_ITEM_ERROR_MAP: dict[str, NetworkTopologyErrorType] = {
    "source_not_found": NetworkTopologyErrorType.SOURCE_NOT_FOUND,
    "node_mismatch": NetworkTopologyErrorType.NODE_MISMATCH,
    "source_inactive": NetworkTopologyErrorType.SOURCE_INACTIVE,
    "template_mismatch": NetworkTopologyErrorType.TEMPLATE_MISMATCH,
    "template_not_found": NetworkTopologyErrorType.TEMPLATE_NOT_FOUND,
    "node_ref_invalid": NetworkTopologyErrorType.NODE_REF_INVALID,
    "metric_not_found": NetworkTopologyErrorType.METRIC_NOT_FOUND,
    "metric_query_failed": NetworkTopologyErrorType.METRIC_QUERY_FAILED,
    "metric_no_data": NetworkTopologyErrorType.METRIC_NO_DATA,
    "interface_relation_query_failed": NetworkTopologyErrorType.INTERFACE_RELATION_QUERY_FAILED,
    "interface_query_failed": NetworkTopologyErrorType.INTERFACE_QUERY_FAILED,
    "interface_not_found": NetworkTopologyErrorType.INTERFACE_NOT_FOUND,
    "status_metric_not_found": NetworkTopologyErrorType.STATUS_METRIC_NOT_FOUND,
    "status_query_failed": NetworkTopologyErrorType.STATUS_QUERY_FAILED,
    "status_no_data": NetworkTopologyErrorType.STATUS_NO_DATA,
}


def map_item_error_code(code: str | None) -> NetworkTopologyErrorType:
    """Normalize a WeOps item-level ``error_code`` to the internal enum."""
    if not code:
        return NetworkTopologyErrorType.UNKNOWN
    return _ITEM_ERROR_MAP.get(code, NetworkTopologyErrorType.UNKNOWN)


# Auth failure detected at the HTTP layer rather than item-level.
# design.md §10.2 + spec "WeOps returns 403 due to missing or invalid
# token during runtime refresh".
WEOPS_TOKEN_INVALID = "weops_token_invalid"


class WeOpsTopologyAdapterError(Exception):
    """Raised when the adapter cannot produce a usable response.

    ``code`` is one of the internal error codes above. ``status_code`` mirrors
    the upstream HTTP status when applicable so views can return a faithful
    response.
    """

    def __init__(self, message: str, code: str = "weops_request_failed", status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class _EnvelopeBusinessError(Exception):
    """Internal signal: a nested WeOps envelope carries ``result: False``.

    Raised by :meth:`WeOpsTopologyAdapter._unwrap_envelope` and translated
    into a :class:`WeOpsTopologyAdapterError` by the caller. Kept private
    because it is an implementation detail of the response parser.
    """


@dataclass
class AdapterSettings:
    """Bundle of adapter tunables; mirrors columns on the canvas row."""

    base_url: str
    token: str
    timeout: int = 30
    retry: int = 1


# --------------------------------------------------------------------------- #
# Adapter                                                                      #
# --------------------------------------------------------------------------- #


def encode_node_ref(node_ref: dict[str, Any]) -> str:
    """URL-encode a node_ref dict for use as a single URL path segment."""
    return quote(json.dumps(node_ref, separators=(",", ":"), ensure_ascii=False), safe="")


class WeOpsTopologyAdapter:
    """Encapsulates the 8 WeOps OpenAPI endpoints listed in design.md §5.4."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 30,
        retry: int = 1,
        http_client: Any = None,
        trace_id_factory: Callable[[], str] | None = None,
    ):
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.token = token or ""
        self.timeout = max(int(timeout or 30), 1)
        self.retry = max(int(retry or 1), 1)
        # Lazy import ``requests`` so unit tests can pass a fake without
        # pulling the real network stack.
        self.http_client = http_client if http_client is not None else _default_http_client()
        self.trace_id_factory = trace_id_factory or (lambda: uuid.uuid4().hex)

    # ------------------------------------------------------------------ #
    # Endpoints                                                           #
    # ------------------------------------------------------------------ #
    def list_node_models(self) -> list[dict[str, Any]]:
        return self._request("GET", "open_api/bklite/network_topology/node_models/")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "open_api/bklite/network_topology/health/")

    def list_nodes(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        query = {
            "bk_obj_id": (filters or {}).get("bk_obj_id", ""),
            "keyword": (filters or {}).get("keyword", ""),
            "all": "true",
        }
        return self._request(
            "GET",
            "open_api/bklite/network_topology/nodes/",
            params=query,
        )

    def list_interfaces(self, node_ref: dict[str, Any]) -> dict[str, Any]:
        ref_segment = encode_node_ref(node_ref)
        return self._request(
            "GET",
            f"open_api/bklite/network_topology/nodes/{ref_segment}/interfaces/",
        )

    def list_metrics(self, node_ref: dict[str, Any]) -> dict[str, Any]:
        ref_segment = encode_node_ref(node_ref)
        return self._request(
            "GET",
            f"open_api/bklite/network_topology/nodes/{ref_segment}/metrics/",
        )

    def list_dimension_values(
        self,
        node_ref: dict[str, Any],
        metric_ref: dict[str, Any],
        dimension_keys: list[str],
    ) -> dict[str, Any]:
        payload = {
            "node_ref": node_ref,
            "metric_ref": metric_ref,
            "dimension_keys": list(dimension_keys or []),
        }
        return self._request(
            "POST",
            "open_api/bklite/network_topology/dimension_values/",
            json=payload,
        )

    def batch_metric_values(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request(
            "POST",
            "open_api/bklite/network_topology/metric_values/batch/",
            json={"items": list(items or [])},
        )

    def batch_interface_status(
        self,
        items: list[dict[str, Any]],
        include_summary: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "open_api/bklite/network_topology/interface_status/batch/",
            json={"items": list(items or []), "include_summary": include_summary},
        )

    def test_connection(self) -> None:
        """Probe WeOps ``health`` for the New/Edit canvas form.

        Raises :class:`WeOpsTopologyAdapterError` with a precise code on
        failure. Used by ``POST /network_topology/test_connection/`` in the
        view layer.
        """
        try:
            self.health()
        except WeOpsTopologyAdapterError:
            raise
        except Exception as exc:  # pragma: no cover - defensive only
            raise WeOpsTopologyAdapterError(f"WeOps 请求失败: {exc}", code="weops_unavailable", status_code=502) from exc

    # ------------------------------------------------------------------ #
    # Request plumbing                                                    #
    # ------------------------------------------------------------------ #
    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        headers = {
            "x-token": self.token,
            "x-bklite-trace-id": self.trace_id_factory(),
        }
        last_error: Exception | None = None
        for attempt in range(self.retry):
            try:
                response = self.http_client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
                last_error = None
                break
            except WeOpsTopologyAdapterError:
                raise
            except Exception as exc:  # requests.RequestException or similar
                last_error = exc
                logger.warning(
                    "WeOps topology adapter transient error attempt=%s/%s err=%s",
                    attempt + 1,
                    self.retry,
                    exc,
                )
        if last_error is not None:
            raise WeOpsTopologyAdapterError(
                f"WeOps 请求失败: {last_error}",
                code="weops_unavailable",
                status_code=502,
            ) from last_error

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: Any) -> Any:
        status_code = getattr(response, "status_code", 200)

        # Auth-layer failures (design.md §5.3 — missing x-token maps to 403).
        # Treat 401 and 403 as the same adapter-level token error so the
        # frontend always gets the same user-facing message.
        if status_code in (401, 403):
            raise WeOpsTopologyAdapterError(
                "WeOps Token 已失效，请更新画布配置",
                code=WEOPS_TOKEN_INVALID,
                status_code=status_code,
            )

        # Non-2xx with no JSON body — surface as a generic failure.
        if status_code >= 400:
            payload: dict[str, Any] = {}
            try:
                payload = response.json() or {}
            except Exception:
                text = getattr(response, "text", "")
                raise WeOpsTopologyAdapterError(
                    f"WeOps HTTP {status_code}: {text or '请求失败'}",
                    code="weops_request_failed",
                    status_code=status_code,
                )
            message = payload.get("message") or payload.get("detail") or "WeOps 返回错误"
            raise WeOpsTopologyAdapterError(
                str(message),
                code="weops_request_failed",
                status_code=status_code,
            )

        try:
            payload = response.json()  # noqa: F841 — read below for envelope checks
        except Exception as exc:
            raise WeOpsTopologyAdapterError(
                f"WeOps 返回非 JSON 数据: {exc}",
                code="weops_unavailable",
                status_code=502,
            ) from exc

        # Top-level business error (``{"result": False, "message": "..."}``) —
        # surface as a request failure. We delegate envelope peeling to
        # ``_unwrap_envelope`` so any nested ``result: False`` (which would
        # be unusual but not impossible for a custom WeOps endpoint) is
        # also surfaced instead of being silently swallowed.
        if isinstance(payload, dict) and payload.get("result") is False:
            raise WeOpsTopologyAdapterError(
                str(payload.get("message") or "WeOps 返回 result=false"),
                code="weops_request_failed",
                status_code=status_code,
            )

        # WeOps wraps every successful response in ``CustomRenderer`` which
        # adds a top-level ``{result, code, message, data}`` envelope AND the
        # view layer adds a nested ``{result: True, data: <real>}`` envelope
        # around the service payload. We recursively peel both so callers
        # receive the actual data shape (list / dict / {items, ...}).
        try:
            return WeOpsTopologyAdapter._unwrap_envelope(payload)
        except _EnvelopeBusinessError as exc:
            raise WeOpsTopologyAdapterError(
                str(exc) or "WeOps 返回 result=false",
                code="weops_request_failed",
                status_code=status_code,
            ) from exc

    @staticmethod
    def _unwrap_envelope(payload: Any) -> Any:
        """Recursively peel ``{result: True, data: <inner>}`` envelopes.

        Stops as soon as the payload is not a dict with ``result is True``
        AND a ``data`` field. A nested ``{result: False, ...}`` is treated
        as a business error and raised as ``_EnvelopeBusinessError`` so the
        caller can translate it into a WeOpsTopologyAdapterError.
        """
        if not isinstance(payload, dict):
            return payload
        result = payload.get("result")
        if result is False:
            raise _EnvelopeBusinessError(str(payload.get("message") or "WeOps 返回 result=false"))
        if result is True and "data" in payload:
            return WeOpsTopologyAdapter._unwrap_envelope(payload["data"])
        return payload


def _default_http_client() -> Any:
    """Lazy default so tests can override without importing requests early."""
    import requests as _requests

    return _requests
