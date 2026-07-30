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


MIN_PDF_BYTES = 1_024
MAX_PDF_BYTES = 20 * 1024 * 1024
VIEWPORT = {"width": 1440, "height": 900}
RENDER_EVENT = "bk-dashboard-render"
DEFAULT_TIMEOUT_MS = 120_000


class DashboardRenderError(RuntimeError):
    safe_message = "报告 PDF 生成失败"


class DashboardRenderContractError(DashboardRenderError):
    safe_message = "Dashboard 渲染失败"

    def __init__(self, *, widget_id: object = None):
        raw_widget_id = str(widget_id or "unknown")
        self.widget_id = re.sub(
            r"[^A-Za-z0-9_.:-]",
            "_",
            raw_widget_id,
        )[:128]
        super().__init__(
            f"{self.safe_message}: widget={self.widget_id}"
        )


class DashboardPdfValidationError(DashboardRenderError):
    safe_message = "报告 PDF 校验失败"


@dataclass(frozen=True)
class DashboardRenderRequest:
    execution_id: int
    render_url: str
    output_path: Path
    render_token: str | None = None
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    executable_path: str | None = None


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

            browser = await playwright.chromium.launch(**launch_options)
            try:
                context = await browser.new_context(
                    viewport=VIEWPORT,
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
                await page.goto(
                    request.render_url,
                    wait_until="commit",
                    timeout=request.timeout_ms,
                )
                remaining_seconds = max(
                    0,
                    deadline - asyncio.get_running_loop().time(),
                )
                signal = await asyncio.wait_for(
                    signal_future,
                    timeout=remaining_seconds,
                )
                if signal.get("type") != "report-ready":
                    raise DashboardRenderContractError(
                        widget_id=signal.get("widgetId")
                    )
                await asyncio.wait_for(
                    page.pdf(
                        path=os.fspath(request.output_path),
                        format="A4",
                        landscape=True,
                        print_background=True,
                        prefer_css_page_size=False,
                    ),
                    timeout=request.timeout_ms / 1000,
                )
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
