from __future__ import annotations

import os
import secrets
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.capacity import CapacityError, OrgConcurrencyLimiter
from app.process_exec import run_transform_in_process

APP_NAME = "ops-analysis-transform-runner"
DEFAULT_ORG_LIMIT = int(os.getenv("TRANSFORM_ORG_CONCURRENCY", "3"))
EXECUTION_TIMEOUT_SECONDS = float(os.getenv("TRANSFORM_TIMEOUT_SECONDS", "5"))
# Shared secret with Server. Empty token rejects all /v1/transform (fail closed).
RUNNER_TOKEN = os.getenv("TRANSFORM_RUNNER_TOKEN", "").strip()

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)
# V1: single replica + single uvicorn worker; in-process limit == global limit.
limiter = OrgConcurrencyLimiter(limit=DEFAULT_ORG_LIMIT)


class TransformRequest(BaseModel):
    request_id: str | None = None
    org_id: str | int | None = None
    script: str
    rows: list[Any] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Transform-Token") or "").strip()


def _authorize(request: Request) -> JSONResponse | None:
    if not RUNNER_TOKEN:
        return _error(
            status_code=503,
            code="transform_runner_misconfigured",
            message="转换服务未配置服务间认证",
            request_id=request.headers.get("X-Request-Id") or str(uuid.uuid4()),
            org_id="default",
            started=time.monotonic(),
            input_rows=0,
        )
    provided = _extract_bearer(request)
    if not provided or not secrets.compare_digest(provided, RUNNER_TOKEN):
        return _error(
            status_code=401,
            code="transform_unauthorized",
            message="转换服务认证失败",
            request_id=request.headers.get("X-Request-Id") or str(uuid.uuid4()),
            org_id="default",
            started=time.monotonic(),
            input_rows=0,
        )
    return None


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": APP_NAME,
        "auth_configured": bool(RUNNER_TOKEN),
        "org_concurrency": DEFAULT_ORG_LIMIT,
    }


@app.post("/v1/transform")
def transform(payload: TransformRequest, request: Request):
    auth_error = _authorize(request)
    if auth_error is not None:
        return auth_error

    request_id = payload.request_id or request.headers.get("X-Request-Id") or str(uuid.uuid4())
    org_id = payload.org_id if payload.org_id is not None else "default"
    started = time.monotonic()
    try:
        # Hold the slot until the child process is killed/reaped.
        with limiter.acquire(str(org_id), timeout=0):
            outcome = run_transform_in_process(
                payload.script,
                payload.rows,
                payload.params if isinstance(payload.params, dict) else {},
                timeout_seconds=EXECUTION_TIMEOUT_SECONDS,
            )
            if not outcome.get("ok"):
                code = outcome.get("code") or "transform_failed"
                status_code = 504 if code == "transform_timeout" else 400
                if code == "transform_internal_error":
                    status_code = 500
                return _error(
                    status_code=status_code,
                    code=code,
                    message=outcome.get("message") or "转换失败",
                    request_id=request_id,
                    org_id=org_id,
                    started=started,
                    input_rows=len(payload.rows),
                    detail=outcome.get("detail"),
                )
            rows = outcome["rows"]
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return {
                "result": True,
                "request_id": request_id,
                "org_id": str(org_id),
                "input_rows": len(payload.rows),
                "output_rows": len(rows),
                "elapsed_ms": elapsed_ms,
                "rows": rows,
            }
    except CapacityError as exc:
        return _error(
            status_code=429,
            code=exc.code,
            message=str(exc),
            request_id=request_id,
            org_id=org_id,
            started=started,
            input_rows=len(payload.rows),
        )
    except Exception as exc:  # noqa: BLE001
        return _error(
            status_code=500,
            code="transform_internal_error",
            message="转换内部错误",
            request_id=request_id,
            org_id=org_id,
            started=started,
            input_rows=len(payload.rows),
            detail=str(exc),
        )


def _error(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    org_id: Any,
    started: float,
    input_rows: int,
    detail: str | None = None,
):
    body = {
        "result": False,
        "request_id": request_id,
        "org_id": str(org_id),
        "code": code,
        "message": message,
        "input_rows": input_rows,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
    # Never echo script/rows; optional short detail for ops only when internal.
    if detail and code == "transform_internal_error":
        body["detail"] = detail[:200]
    return JSONResponse(status_code=status_code, content=body)
