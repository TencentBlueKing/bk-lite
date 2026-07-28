"""Dashboard 后台 PDF 渲染回归工具。

调用方提供可直接访问的正式 Render URL。工具不负责登录，也不理解 Dashboard、
Execution 或 DataSource；页面是否完成完全由 ``bk-dashboard-render`` 事件决定。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import fitz
from patchright.async_api import async_playwright


MIN_PDF_BYTES = 10_000
VIEWPORT = {"width": 1440, "height": 900}
RENDER_EVENT = "bk-dashboard-render"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--render-url",
        required=True,
        help="可直接访问的正式 Render URL；认证由运行环境或该 URL 自身负责",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    parser.add_argument(
        "--executable-path",
        default=os.getenv("EXECUTABLE_PATH"),
        help="Chromium 可执行文件；生产镜像默认读取 EXECUTABLE_PATH",
    )
    return parser.parse_args()


def validate_pdf(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError("PDF file was not created")
    size = path.stat().st_size
    if size < MIN_PDF_BYTES:
        raise RuntimeError(f"PDF is unexpectedly small: {size} bytes")
    with fitz.open(path) as document:
        if document.page_count == 0:
            raise RuntimeError("PDF has no pages")
        return {"bytes": size, "pages": document.page_count}


async def render_pdf(args: argparse.Namespace) -> dict[str, Any]:
    signal_future: asyncio.Future[dict[str, Any]] = (
        asyncio.get_running_loop().create_future()
    )

    async def receive_render_signal(
        _source: dict[str, Any],
        signal: dict[str, Any],
    ) -> None:
        if not signal_future.done():
            signal_future.set_result(signal)

    async with async_playwright() as playwright:
        launch_options = {"headless": True}
        if args.executable_path:
            launch_options["executable_path"] = args.executable_path
        browser = await playwright.chromium.launch(**launch_options)
        context = await browser.new_context(
            viewport=VIEWPORT,
            color_scheme="light",
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.expose_binding("__bkReceiveDashboardRender", receive_render_signal)
        await page.add_init_script(
            f"""
            window.addEventListener({json.dumps(RENDER_EVENT)}, (event) => {{
              window.__bkReceiveDashboardRender(event.detail);
            }});
            """
        )
        try:
            await page.goto(
                args.render_url,
                wait_until="commit",
                timeout=args.timeout_ms,
            )
            received_signal = await asyncio.wait_for(
                signal_future,
                timeout=args.timeout_ms / 1000,
            )

            if received_signal.get("type") != "report-ready":
                raise RuntimeError(
                    "render failed: "
                    f"widget={received_signal.get('widgetId')} "
                    f"error={received_signal.get('error')}"
                )

            evidence = await page.evaluate(
                """() => ({
                  canvases: document.querySelectorAll(
                    '[data-dashboard-render-root="true"] canvas'
                  ).length,
                  tables: document.querySelectorAll(
                    '[data-dashboard-render-root="true"] table'
                  ).length,
                  widgets: document.querySelectorAll(
                    '[data-dashboard-render-root="true"] .widget'
                  ).length,
                })"""
            )
            await page.pdf(
                path=str(args.output),
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()

    return {"signal": received_signal, "domEvidence": evidence}


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()

    render_result = asyncio.run(render_pdf(args))

    pdf = validate_pdf(args.output)
    print(
        json.dumps(
            {
                **render_result,
                "pdf": pdf,
                "output": os.fspath(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
