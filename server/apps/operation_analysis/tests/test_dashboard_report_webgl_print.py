from pathlib import Path

import fitz
import pytest

from apps.operation_analysis.services.dashboard_report_renderer import DashboardChromiumRenderer, DashboardRenderRequest

pytestmark = pytest.mark.integration

WEBGL_FILL = (255, 32, 160)


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


def _write_webgl_snapshot_html(path: Path) -> None:
    r, g, b = [channel / 255 for channel in WEBGL_FILL]
    path.write_text(
        f"""
        <!doctype html>
        <html lang="zh-CN">
          <head><meta charset="utf-8"><title>BK-Lite WebGL Print</title></head>
          <body style="margin:0; background:#08111f;">
            <div data-dashboard-render-root="true" style="width:720px;height:480px;">
              <canvas id="room" width="720" height="480"></canvas>
            </div>
            <script>
              const canvas = document.getElementById('room');
              const gl = canvas.getContext('webgl', {{
                preserveDrawingBuffer: true,
                alpha: false,
              }});
              gl.viewport(0, 0, canvas.width, canvas.height);
              gl.clearColor({r}, {g}, {b}, 1);
              gl.clear(gl.COLOR_BUFFER_BIT);
              const image = document.createElement('img');
              image.src = canvas.toDataURL('image/png');
              image.width = canvas.width;
              image.height = canvas.height;
              image.style.width = canvas.width + 'px';
              image.style.height = canvas.height + 'px';
              image.dataset.printSnapshot = 'true';
              canvas.replaceWith(image);
              const ready = image.decode ? image.decode() : Promise.resolve();
              ready.catch(() => undefined).then(() => {{
                requestAnimationFrame(() => requestAnimationFrame(() => {{
                  window.dispatchEvent(new CustomEvent('bk-dashboard-render', {{
                    detail: {{
                      type: 'report-ready',
                      dashboardId: 'webgl',
                      widgets: [{{ widgetId: 'room', status: 'ready' }}]
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


def _pdf_has_rgb(path: Path, target: tuple[int, int, int], tolerance: int = 48) -> bool:
    tr, tg, tb = target
    with fitz.open(path) as document:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            samples = pixmap.samples
            channels = pixmap.n
            for index in range(0, len(samples), channels):
                if abs(samples[index] - tr) <= tolerance and abs(samples[index + 1] - tg) <= tolerance and abs(samples[index + 2] - tb) <= tolerance:
                    return True
    return False


def test_webgl_scene_survives_pdf_after_canvas_snapshot(tmp_path):
    if not _chromium_ready():
        pytest.skip("Playwright Chromium 不可用")

    html_path = tmp_path / "webgl-room.html"
    output_path = tmp_path / "webgl-room.pdf"
    _write_webgl_snapshot_html(html_path)

    result = DashboardChromiumRenderer().render(
        DashboardRenderRequest(
            execution_id=202,
            render_url=html_path.as_uri(),
            output_path=output_path,
            resource_type="screen",
            viewport_width=720,
            viewport_height=480,
        )
    )

    assert result["signal"]["type"] == "report-ready"
    assert _pdf_has_rgb(output_path, WEBGL_FILL)
