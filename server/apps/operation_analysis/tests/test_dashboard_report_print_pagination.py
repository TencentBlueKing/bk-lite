import os
from pathlib import Path

import fitz
import pytest

from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardChromiumRenderer,
    DashboardRenderRequest,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _use_default_playwright_chromium(monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.delenv("EXECUTABLE_PATH", raising=False)


def _chromium_ready() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def _write_dashboard_html(
    path: Path,
    *,
    content_height_px: int,
    widgets: list[dict],
    prepare_print: bool,
) -> None:
    widget_markers = "\n".join(
        (
            f'<section id="{item["widgetId"]}" '
            f'style="height: {content_height_px // max(len(widgets), 1)}px;'
            f' border: 1px solid #333; margin: 8px 0; color: #000;'
            f' background: #fff;">'
            f"WIDGET-{item['widgetId']}</section>"
        )
        for item in widgets
    )
    widgets_json = ", ".join(
        "{"
        f"widgetId: '{item['widgetId']}', status: '{item['status']}'"
        "}"
        for item in widgets
    )
    prepare_script = """
              function preparePrint(root) {
                window.dispatchEvent(new CustomEvent('bk-dashboard-prepare-print', {
                  detail: { phase: 'prepare-print' }
                }));
                const expand = (el) => {
                  if (!el) return;
                  el.style.overflow = 'visible';
                  el.style.height = 'auto';
                  el.style.maxHeight = 'none';
                  el.style.minHeight = 'fit-content';
                  el.style.flex = 'none';
                  if (getComputedStyle(el).position === 'fixed') {
                    el.style.position = 'relative';
                    el.style.inset = 'auto';
                    el.style.width = '100%';
                  }
                };
                expand(root);
                root.querySelectorAll('[data-export-expand="true"]').forEach(expand);
                let ancestor = root.parentElement;
                while (ancestor) {
                  expand(ancestor);
                  ancestor = ancestor.parentElement;
                }
                expand(document.documentElement);
                expand(document.body);
              }
    """ if prepare_print else "function preparePrint(root) {}"
    path.write_text(
        f"""
        <!doctype html>
        <html lang="zh-CN">
          <head><meta charset="utf-8"><title>BK-Lite Pagination</title></head>
          <body style="font-family: sans-serif; color: #000; background: #fff;">
            <div id="clip"
                 style="position: fixed; inset: 0; height: 100vh; overflow: auto; background: #fff;">
              <div data-dashboard-render-root="true" style="min-height: 100%; overflow: auto;">
                <div data-export-expand="true" style="height: 100%; overflow: auto;">
                  <h1>Dashboard Report</h1>
                  {widget_markers}
                </div>
              </div>
            </div>
            <script>
              {prepare_script}
              window.addEventListener('DOMContentLoaded', () => {{
                const root = document.querySelector('[data-dashboard-render-root="true"]');
                preparePrint(root);
                requestAnimationFrame(() => requestAnimationFrame(() => {{
                  window.dispatchEvent(new CustomEvent('bk-dashboard-render', {{
                    detail: {{
                      type: 'report-ready',
                      dashboardId: 'pagination',
                      widgets: [{widgets_json}]
                    }}
                  }}));
                }}));
              }});
            </script>
          </body>
        </html>
        """,
        encoding="utf-8",
    )


def test_long_dashboard_paginates_after_prepare_print(tmp_path):
    if not _chromium_ready():
        pytest.skip("Playwright Chromium 不可用")

    html_path = tmp_path / "long-dashboard.html"
    output_path = tmp_path / "long-dashboard.pdf"
    widgets = [
        {"widgetId": "w1", "status": "ready"},
        {"widgetId": "w2", "status": "ready"},
        {"widgetId": "w3", "status": "empty"},
    ]
    _write_dashboard_html(
        html_path,
        content_height_px=3600,
        widgets=widgets,
        prepare_print=True,
    )

    result = DashboardChromiumRenderer().render(
        DashboardRenderRequest(
            execution_id=101,
            render_url=html_path.as_uri(),
            output_path=output_path,
        )
    )

    assert result["signal"]["type"] == "report-ready"
    assert [item["widgetId"] for item in result["signal"]["widgets"]] == [
        "w1",
        "w2",
        "w3",
    ]
    with fitz.open(output_path) as document:
        assert document.page_count > 1
        extracted = "".join(page.get_text() for page in document)
        assert "WIDGET-w1" in extracted
        assert "WIDGET-w2" in extracted
        assert "WIDGET-w3" in extracted


def test_short_dashboard_stays_single_page_after_prepare_print(tmp_path):
    if not _chromium_ready():
        pytest.skip("Playwright Chromium 不可用")

    html_path = tmp_path / "short-dashboard.html"
    output_path = tmp_path / "short-dashboard.pdf"
    widgets = [
        {"widgetId": "only", "status": "ready"},
    ]
    _write_dashboard_html(
        html_path,
        content_height_px=240,
        widgets=widgets,
        prepare_print=True,
    )

    result = DashboardChromiumRenderer().render(
        DashboardRenderRequest(
            execution_id=102,
            render_url=html_path.as_uri(),
            output_path=output_path,
        )
    )

    assert result["signal"]["type"] == "report-ready"
    with fitz.open(output_path) as document:
        assert document.page_count == 1
        assert "WIDGET-only" in document[0].get_text()


def test_overflow_clip_without_prepare_print_stays_truncated(tmp_path):
    """Control: clipped scroll layout without prepare-print loses lower widgets."""
    if not _chromium_ready():
        pytest.skip("Playwright Chromium 不可用")

    html_path = tmp_path / "clipped-dashboard.html"
    output_path = tmp_path / "clipped-dashboard.pdf"
    widgets = [
        {"widgetId": "top", "status": "ready"},
        {"widgetId": "bottom", "status": "ready"},
    ]
    _write_dashboard_html(
        html_path,
        content_height_px=3600,
        widgets=widgets,
        prepare_print=False,
    )

    result = DashboardChromiumRenderer().render(
        DashboardRenderRequest(
            execution_id=103,
            render_url=html_path.as_uri(),
            output_path=output_path,
        )
    )

    assert result["signal"]["type"] == "report-ready"
    with fitz.open(output_path) as document:
        extracted = "".join(page.get_text() for page in document)
        assert "WIDGET-top" in extracted
        assert document.page_count == 1
        assert "WIDGET-bottom" not in extracted
