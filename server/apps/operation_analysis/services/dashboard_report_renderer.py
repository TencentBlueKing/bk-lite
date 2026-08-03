from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import fitz
from playwright.async_api import async_playwright

from apps.operation_analysis.services.canvas_report.types import (
    SCREEN_PDF_FORMAT,
    SCREEN_PDF_LANDSCAPE,
)


MIN_PDF_BYTES = 1_024
MAX_PDF_BYTES = 20 * 1024 * 1024
VIEWPORT = {"width": 1440, "height": 900}
RENDER_EVENT = "bk-dashboard-render"
DEFAULT_TIMEOUT_MS = 120_000


class DashboardRenderError(RuntimeError):
    safe_message = "报告 PDF 生成失败"
    error_code = ""

    def __init__(self, message: str | None = None, *, error_code: str = ""):
        if error_code:
            self.error_code = error_code
        super().__init__(message or self.safe_message)


# report-failed.errorCode → data_load（仅白名单；其它仍视为 render contract）
_DATA_LOAD_ERROR_CODES = frozenset(
    {
        "widget_query_timeout",
        "widget_query_transient",
        "widget_data_forbidden",
        "datasource_missing",
    }
)


def resolve_report_failed_semantics(
    signal: dict[str, Any] | None,
) -> tuple[str, str]:
    """从 report-failed 信号解析 (failure_stage, error_code)。

    未携带/未识别的 errorCode → render + render_contract_business_failed。
    """
    raw = ""
    if isinstance(signal, dict):
        raw = str(
            signal.get("errorCode") or signal.get("error_code") or ""
        ).strip()
    if raw in _DATA_LOAD_ERROR_CODES:
        return "data_load", raw
    return "render", "render_contract_business_failed"


class DashboardRenderContractError(DashboardRenderError):
    safe_message = "Dashboard 渲染失败"
    error_code = "render_contract_business_failed"
    failure_stage = "render"

    def __init__(
        self,
        *,
        widget_id: object = None,
        error_code: str | None = None,
        failure_stage: str | None = None,
    ):
        raw_widget_id = str(widget_id or "unknown")
        self.widget_id = re.sub(
            r"[^A-Za-z0-9_.:-]",
            "_",
            raw_widget_id,
        )[:128]
        if failure_stage and error_code:
            self.failure_stage = failure_stage
            resolved_code = error_code
        else:
            stage, resolved_code = resolve_report_failed_semantics(
                {"errorCode": error_code or ""}
            )
            self.failure_stage = stage
        DashboardRenderError.__init__(
            self,
            f"{self.safe_message}: widget={self.widget_id}",
            error_code=resolved_code,
        )


class DashboardPdfValidationError(DashboardRenderError):
    safe_message = "报告 PDF 校验失败"

    def __init__(self, message: str, *, error_code: str = ""):
        if not error_code:
            if "超过 20 MB" in message or "20 MB" in message:
                error_code = "pdf_too_large"
            else:
                error_code = "pdf_generate_failed"
        super().__init__(message, error_code=error_code)


@dataclass(frozen=True)
class DashboardRenderRequest:
    execution_id: int
    render_url: str
    output_path: Path
    render_token: str | None = None
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    executable_path: str | None = None
    resource_type: str = "dashboard"
    viewport_width: int | None = None
    viewport_height: int | None = None


def resolve_render_viewport(
    *,
    resource_type: str,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
) -> dict[str, int]:
    """Dashboard 固定视口；Screen 使用 snapshot viewport。"""
    if resource_type == "screen":
        width = int(viewport_width or VIEWPORT["width"])
        height = int(viewport_height or VIEWPORT["height"])
        if width <= 0 or height <= 0:
            return dict(VIEWPORT)
        return {"width": width, "height": height}
    return dict(VIEWPORT)


def resolve_screen_pdf_scale(
    viewport_width: int,
    viewport_height: int,
) -> float:
    """策略 2：等比缩放完整落入 A4 landscape 单页。"""
    from apps.operation_analysis.services.canvas_report.types import (
        SCREEN_PDF_PAGE_HEIGHT_PX,
        SCREEN_PDF_PAGE_WIDTH_PX,
    )

    if viewport_width <= 0 or viewport_height <= 0:
        return 1.0
    scale = min(
        SCREEN_PDF_PAGE_WIDTH_PX / viewport_width,
        SCREEN_PDF_PAGE_HEIGHT_PX / viewport_height,
    )
    # Playwright scale 允许约 0.1–2.0
    return max(0.1, min(float(scale), 2.0))


def validate_pdf(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise DashboardPdfValidationError("PDF 文件未生成")
    size = path.stat().st_size
    if size < MIN_PDF_BYTES:
        raise DashboardPdfValidationError(
            f"PDF 文件过小: {size} bytes"
        )
    if size > MAX_PDF_BYTES:
        raise DashboardPdfValidationError(
            f"PDF 文件超过 20 MB: {size} bytes"
        )
    try:
        with fitz.open(path) as document:
            if document.page_count == 0:
                raise DashboardPdfValidationError("PDF 不包含页面")
            return {"bytes": size, "pages": document.page_count}
    except DashboardPdfValidationError:
        raise
    except Exception as exc:
        raise DashboardPdfValidationError("PDF 文件无法打开") from exc


class DashboardChromiumRenderer:
    def __init__(
        self,
        *,
        playwright_factory: Callable[[], Any] = async_playwright,
    ):
        self.playwright_factory = playwright_factory

    def render(self, request: DashboardRenderRequest) -> dict[str, Any]:
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.unlink(missing_ok=True)
        try:
            signal = asyncio.run(self._render(request))
            pdf = validate_pdf(request.output_path)
            return {"signal": signal, "pdf": pdf}
        except Exception:
            request.output_path.unlink(missing_ok=True)
            raise

    async def _render(
        self,
        request: DashboardRenderRequest,
    ) -> dict[str, Any]:
        signal_future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )

        async def receive_render_signal(
            _source: dict[str, Any],
            signal: dict[str, Any],
        ) -> None:
            if not signal_future.done():
                signal_future.set_result(signal)

        async with self.playwright_factory() as playwright:
            launch_options: dict[str, Any] = {"headless": True}
            executable_path = (
                request.executable_path or os.getenv("EXECUTABLE_PATH")
            )
            if executable_path:
                launch_options["executable_path"] = executable_path

            try:
                browser = await playwright.chromium.launch(**launch_options)
            except Exception as exc:
                raise DashboardRenderError(
                    "Chromium 启动失败",
                    error_code="chromium_launch_failed",
                ) from exc
            try:
                viewport = resolve_render_viewport(
                    resource_type=request.resource_type,
                    viewport_width=request.viewport_width,
                    viewport_height=request.viewport_height,
                )
                context = await browser.new_context(
                    viewport=viewport,
                    color_scheme="light",
                    locale="zh-CN",
                )
                if request.render_token is not None:
                    await self._establish_session(
                        context,
                        request.render_url,
                        request.execution_id,
                        request.render_token,
                    )
                page = await context.new_page()
                await page.expose_binding(
                    "__bkReceiveDashboardRender",
                    receive_render_signal,
                )
                await page.add_init_script(
                    f"""
                    window.addEventListener(
                      {json.dumps(RENDER_EVENT)},
                      (event) => {{
                        window.__bkReceiveDashboardRender(event.detail);
                      }},
                      {{ once: true }}
                    );
                    """
                )
                deadline = (
                    asyncio.get_running_loop().time()
                    + request.timeout_ms / 1000
                )
                try:
                    await page.goto(
                        request.render_url,
                        wait_until="commit",
                        timeout=request.timeout_ms,
                    )
                except Exception as exc:
                    raise DashboardRenderError(
                        "渲染页加载失败",
                        error_code="page_load_failed",
                    ) from exc
                remaining_seconds = max(
                    0,
                    deadline - asyncio.get_running_loop().time(),
                )
                try:
                    signal = await asyncio.wait_for(
                        signal_future,
                        timeout=remaining_seconds,
                    )
                except TimeoutError as exc:
                    raise DashboardRenderError(
                        "等待 report-ready 超时",
                        error_code="report_ready_timeout",
                    ) from exc
                if signal.get("type") != "report-ready":
                    stage, code = resolve_report_failed_semantics(signal)
                    raise DashboardRenderContractError(
                        widget_id=signal.get("widgetId"),
                        error_code=code,
                        failure_stage=stage,
                    )
                try:
                    pdf_kwargs: dict[str, Any] = {
                        "path": os.fspath(request.output_path),
                        "format": SCREEN_PDF_FORMAT,
                        "landscape": SCREEN_PDF_LANDSCAPE,
                        "print_background": True,
                        "prefer_css_page_size": False,
                    }
                    if request.resource_type == "screen":
                        pdf_kwargs["scale"] = resolve_screen_pdf_scale(
                            viewport["width"],
                            viewport["height"],
                        )
                    await asyncio.wait_for(
                        page.pdf(**pdf_kwargs),
                        timeout=request.timeout_ms / 1000,
                    )
                except Exception as exc:
                    raise DashboardRenderError(
                        "PDF 生成失败",
                        error_code="pdf_generate_failed",
                    ) from exc
                return signal
            finally:
                await browser.close()

    @staticmethod
    async def _establish_session(
        context,
        render_url: str,
        execution_id: int,
        render_token: str,
    ) -> None:
        parsed = urlsplit(render_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DashboardRenderError("Render URL 配置无效")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        exchange_response = await context.request.post(
            f"{origin}/api/proxy/operation_analysis/api/"
            f"dashboard_execution/{execution_id}/render-token-exchange/",
            data={"token": render_token},
        )
        if not exchange_response.ok:
            raise DashboardRenderError("无法建立 Render 会话")
        exchange_payload = await exchange_response.json()
        session_user = (
            exchange_payload.get("data", exchange_payload)
            .get("session_user")
        )
        if not isinstance(session_user, dict):
            raise DashboardRenderError("无法建立 Render 会话")
        csrf_response = await context.request.get(
            f"{origin}/api/auth/csrf"
        )
        if not csrf_response.ok:
            raise DashboardRenderError("无法建立 Render 会话")
        csrf_payload = await csrf_response.json()
        csrf_token = csrf_payload.get("csrfToken")
        if not csrf_token:
            raise DashboardRenderError("无法建立 Render 会话")

        auth_response = await context.request.post(
            f"{origin}/api/auth/callback/credentials?json=true",
            form={
                "csrfToken": csrf_token,
                "callbackUrl": render_url,
                "json": "true",
                "skipValidation": "true",
                "userData": json.dumps(session_user),
            },
        )
        if not auth_response.ok:
            raise DashboardRenderError("无法建立 Render 会话")
        auth_payload = await auth_response.json()
        if auth_payload.get("error"):
            raise DashboardRenderError("无法建立 Render 会话")
