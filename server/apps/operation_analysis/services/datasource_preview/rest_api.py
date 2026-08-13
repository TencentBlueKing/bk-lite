import json
from typing import Any, Callable

from apps.core.utils.safe_requests import SafeRequestsError, safe_request
from apps.core.utils.ssrf_validator import SSRFError
from apps.operation_analysis.services.datasource_preview.base import BaseConnectorExecutor, ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.schema import infer_fields
from apps.operation_analysis.services.transform.errors import TransformError
from apps.operation_analysis.services.transform.executor import get_transform_executor

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RESPONSE_CHUNK_BYTES = 64 * 1024
MAX_TRANSFORM_ROWS = 10_000


def read_limited_json(response) -> Any:
    content_length = response.headers.get("content-length")
    try:
        declared_length = int(content_length) if content_length is not None else 0
    except (TypeError, ValueError):
        declared_length = 0
    if declared_length > MAX_RESPONSE_BYTES:
        raise ConnectorError("REST API 响应体过大", code="rest_response_too_large", status_code=400)

    content = bytearray()
    for chunk in response.iter_content(chunk_size=RESPONSE_CHUNK_BYTES):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > MAX_RESPONSE_BYTES:
            raise ConnectorError("REST API 响应体过大", code="rest_response_too_large", status_code=400)
    return json.loads(content)


def extract_response_path(payload: Any, response_path: str | None) -> Any:
    if not response_path:
        return payload

    current = payload
    for part in response_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        raise ConnectorError(f"响应路径不存在: {response_path}", code="rest_response_path_missing", status_code=400)
    return current


def normalize_rest_items(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if isinstance(payload, list):
        items = payload
        count = len(items)
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
        count = int(payload.get("count") or len(items))
    else:
        raise ConnectorError("REST API 响应必须是对象数组或包含 items 数组的对象", code="rest_response_not_list", status_code=400)

    normalized = []
    for item in items:
        normalized.append(item if isinstance(item, dict) else {"value": item})
    return normalized, count


class SafeRequestsHttpClient:
    """Adapter so RestApiConnectorExecutor can call safe_request via `.request`."""

    def __init__(self, request_func: Callable[..., Any] | None = None, *, allow_redirects: bool = True):
        self.request_func = request_func or safe_request
        self.allow_redirects = allow_redirects

    def request(self, method: str, url: str, **kwargs: Any):
        timeout = kwargs.pop("timeout", 30)
        # stream is supported by underlying requests call inside safe_request.
        return self.request_func(
            method,
            url,
            allow_redirects=self.allow_redirects,
            timeout=timeout,
            **kwargs,
        )


def maybe_apply_transform(
    items: list[dict[str, Any]],
    transform_config: dict[str, Any] | None,
    *,
    org_id: str | int | None = None,
    transform_executor=None,
) -> list[dict[str, Any]]:
    config = transform_config if isinstance(transform_config, dict) else {}
    if not config.get("enabled"):
        return items
    language = (config.get("language") or "python").lower()
    if language != "python":
        raise ConnectorError("仅支持 Python 转换", code="transform_language_unsupported", status_code=400)
    script = config.get("script")
    if not isinstance(script, str) or not script.strip():
        raise ConnectorError("已启用转换但脚本为空", code="transform_script_required", status_code=400)

    executor = transform_executor or get_transform_executor()
    try:
        return executor.execute(items, {}, script, org_id=org_id)
    except TransformError as exc:
        raise ConnectorError(exc.message, code=exc.code, status_code=exc.status_code) from exc


class RestApiConnectorExecutor(BaseConnectorExecutor):
    source_type = "rest_api"

    def __init__(self, http_client=None, transform_executor=None):
        self.http_client = http_client or SafeRequestsHttpClient()
        self.transform_executor = transform_executor

    def test_connection(self, connection_config: dict[str, Any]) -> None:
        """测连只验证可达与鉴权，不要求响应体可预览为 JSON 行集。"""
        url = connection_config.get("url")
        if not url:
            raise ConnectorError("REST API URL 不能为空", code="rest_url_required", status_code=400)

        method = str(connection_config.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ConnectorError("REST API 测连仅支持 GET/POST", code="rest_method_not_supported", status_code=400)

        timeout = min(int(connection_config.get("timeout") or 10), 30)
        headers = connection_config.get("headers") if isinstance(connection_config.get("headers"), dict) else {}

        try:
            response = self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                timeout=timeout,
                stream=True,
            )
            try:
                response.raise_for_status()
            finally:
                response.close()
        except ConnectorError:
            raise
        except (SSRFError, SafeRequestsError) as exc:
            raise ConnectorError(
                f"REST API 请求不安全或被拒绝: {exc}",
                code="rest_request_blocked",
                status_code=400,
            ) from exc
        except Exception as exc:
            raise ConnectorError(
                f"REST API 请求失败: {exc}",
                code="rest_request_failed",
                status_code=502,
            ) from exc

    def preview(
        self,
        connection_config: dict[str, Any],
        query_config: dict[str, Any],
        limit: int = 100,
        *,
        transform_config: dict[str, Any] | None = None,
        org_id: str | int | None = None,
    ) -> PreviewResult:
        url = connection_config.get("url")
        if not url:
            raise ConnectorError("REST API URL 不能为空", code="rest_url_required", status_code=400)

        method = str(connection_config.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            raise ConnectorError("REST API 预览仅支持 GET/POST", code="rest_method_not_supported", status_code=400)

        timeout = min(int(connection_config.get("timeout") or 10), 30)
        headers = connection_config.get("headers") if isinstance(connection_config.get("headers"), dict) else {}
        params = query_config.get("params") if isinstance(query_config.get("params"), dict) else {}
        body = query_config.get("body") if isinstance(query_config.get("body"), dict) else None

        try:
            response = self.http_client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body if method == "POST" else None,
                timeout=timeout,
                stream=True,
            )
            try:
                response.raise_for_status()
                payload = read_limited_json(response)
            finally:
                response.close()
        except ConnectorError:
            raise
        except (SSRFError, SafeRequestsError) as exc:
            raise ConnectorError(f"REST API 请求不安全或被拒绝: {exc}", code="rest_request_blocked", status_code=400) from exc
        except Exception as exc:
            raise ConnectorError(f"REST API 请求失败: {exc}", code="rest_request_failed", status_code=502)

        selected = extract_response_path(payload, query_config.get("response_path"))
        items, count = normalize_rest_items(selected)
        if len(items) > MAX_TRANSFORM_ROWS:
            raise ConnectorError(
                f"REST 行数超过 {MAX_TRANSFORM_ROWS}，拒绝执行",
                code="rest_rows_too_many",
                status_code=400,
            )

        # Single outbound request: sample raw, then transform the same full row set.
        raw_limited = items[:limit]
        raw_fields = infer_fields(raw_limited)
        effective_transform = transform_config if transform_config is not None else query_config.get("transform_config")
        enabled = bool(isinstance(effective_transform, dict) and effective_transform.get("enabled"))
        if not enabled:
            return PreviewResult(items=raw_limited, count=len(items), fields=raw_fields)

        try:
            transformed = maybe_apply_transform(
                items,
                effective_transform,
                org_id=org_id,
                transform_executor=self.transform_executor,
            )
        except ConnectorError as exc:
            return PreviewResult(
                items=raw_limited,
                count=len(items),
                fields=raw_fields,
                raw_items=raw_limited,
                raw_count=len(items),
                raw_fields=raw_fields,
                transform_error={"code": exc.code, "message": exc.message},
            )

        limited_items = transformed[:limit]
        return PreviewResult(
            items=limited_items,
            count=len(transformed),
            fields=infer_fields(limited_items),
            raw_items=raw_limited,
            raw_count=len(items),
            raw_fields=raw_fields,
        )
