"""Server-side adapter that calls the isolated transform Runner over HTTP."""

from __future__ import annotations

import os
import uuid
from typing import Any, Callable

import requests

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.services.transform.errors import TransformError

DEFAULT_TIMEOUT_SECONDS = 8
MAX_ROWS = 10_000


class TransformExecutor:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_func: Callable[..., Any] | None = None,
        timeout_seconds: float | None = None,
        token: str | None = None,
    ):
        self.base_url = (base_url if base_url is not None else os.getenv("TRANSFORM_RUNNER_URL", "")).rstrip("/")
        self.request_func = request_func or requests.request
        self.timeout_seconds = float(
            timeout_seconds if timeout_seconds is not None else os.getenv("TRANSFORM_RUNNER_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        )
        self.token = (token if token is not None else os.getenv("TRANSFORM_RUNNER_TOKEN", "")).strip()

    def is_available(self) -> bool:
        return bool(self.base_url) and bool(self.token)

    def execute(
        self,
        rows: list[dict[str, Any]],
        params: dict[str, Any] | None,
        script: str,
        *,
        org_id: str | int | None = None,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.base_url:
            raise TransformError("转换服务不可用", code="transform_runner_unavailable", status_code=503)
        if not self.token:
            raise TransformError("转换服务未配置服务间认证", code="transform_runner_misconfigured", status_code=503)

        if not isinstance(rows, list):
            raise TransformError("rows 必须为数组", code="rows_invalid", status_code=400)
        if len(rows) > MAX_ROWS:
            raise TransformError(f"输入超过 {MAX_ROWS} 行", code="rows_too_many", status_code=400)

        payload = {
            "request_id": request_id or str(uuid.uuid4()),
            "org_id": org_id if org_id is not None else "default",
            "script": script,
            "rows": rows,
            "params": params if isinstance(params, dict) else {},
        }

        url = f"{self.base_url}/v1/transform"
        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": payload["request_id"],
            "Authorization": f"Bearer {self.token}",
        }
        try:
            response = self.request_func(
                "POST",
                url,
                json=payload,
                timeout=self.timeout_seconds,
                headers=headers,
            )
        except requests.Timeout as exc:
            logger.warning(
                "[TransformExecutor] timeout request_id=%s org_id=%s rows=%s",
                payload["request_id"],
                payload["org_id"],
                len(rows),
            )
            raise TransformError("转换执行超时", code="transform_timeout", status_code=504) from exc
        except requests.RequestException as exc:
            logger.warning(
                "[TransformExecutor] unavailable request_id=%s org_id=%s err=%s",
                payload["request_id"],
                payload["org_id"],
                type(exc).__name__,
            )
            raise TransformError("转换服务不可用", code="transform_runner_unavailable", status_code=503) from exc

        body: dict[str, Any]
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        if response.status_code >= 400 or body.get("result") is False:
            code = body.get("code") or "transform_failed"
            message = body.get("message") or "转换失败"
            status_code = response.status_code if response.status_code >= 400 else 400
            if status_code == 429:
                code = body.get("code") or "transform_capacity_exceeded"
            logger.info(
                "[TransformExecutor] failed request_id=%s org_id=%s code=%s status=%s elapsed_ms=%s",
                payload["request_id"],
                payload["org_id"],
                code,
                status_code,
                body.get("elapsed_ms"),
            )
            raise TransformError(message, code=code, status_code=status_code)

        rows_out = body.get("rows")
        if not isinstance(rows_out, list):
            raise TransformError("转换结果无效", code="transform_return_invalid", status_code=502)
        logger.info(
            "[TransformExecutor] ok request_id=%s org_id=%s input_rows=%s output_rows=%s elapsed_ms=%s",
            payload["request_id"],
            payload["org_id"],
            len(rows),
            len(rows_out),
            body.get("elapsed_ms"),
        )
        return rows_out


_default_executor: TransformExecutor | None = None


def get_transform_executor() -> TransformExecutor:
    global _default_executor
    if _default_executor is None:
        _default_executor = TransformExecutor()
    return _default_executor
