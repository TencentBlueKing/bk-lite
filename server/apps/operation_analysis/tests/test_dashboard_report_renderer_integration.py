import os
import subprocess
from pathlib import Path

import fitz
import pytest

from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardChromiumRenderer,
    DashboardRenderRequest,
)


pytestmark = pytest.mark.integration


def test_real_chromium_prints_ready_contract_canvas_and_table(tmp_path):
    executable_path = os.getenv("EXECUTABLE_PATH")
    if not executable_path or not Path(executable_path).is_file():
        pytest.skip("EXECUTABLE_PATH 未指向可用 Chromium")
    chromium_version = subprocess.check_output(
        [executable_path, "--version"],
        text=True,
    ).strip()
    cjk_font = subprocess.check_output(
        ["fc-match", "Noto Sans CJK SC"],
        text=True,
    ).strip()
    assert "Chrom" in chromium_version
    assert "NotoSansCJK" in cjk_font.replace(" ", "")

    html_path = tmp_path / "render-contract.html"
    output_path = tmp_path / "render-contract.pdf"
    html_path.write_text(
        """
        <!doctype html>
        <html lang="zh-CN">
          <head><meta charset="utf-8"><title>BK-Lite Render</title></head>
          <body style="font-family: sans-serif">
            <h1>BK-Lite Dashboard Report</h1>
            <p>运营分析仪表盘</p>
            <canvas id="chart" width="900" height="360"></canvas>
            <table border="1" style="width: 100%">
              <tr><th>服务</th><th>状态</th></tr>
              <tr><td>核心服务</td><td>正常</td></tr>
              <tr><td>空数据组件</td><td>暂无数据</td></tr>
            </table>
            <script>
              window.addEventListener('DOMContentLoaded', () => {
                const context = document.getElementById('chart').getContext('2d');
                context.fillStyle = '#2563eb';
                context.fillRect(40, 220, 120, 100);
                context.fillStyle = '#16a34a';
                context.fillRect(220, 140, 120, 180);
                context.fillStyle = '#f59e0b';
                context.fillRect(400, 60, 120, 260);
                requestAnimationFrame(() => requestAnimationFrame(() => {
                  window.dispatchEvent(new CustomEvent('bk-dashboard-render', {
                    detail: {
                      type: 'report-ready',
                      dashboardId: 'integration',
                      widgets: [
                        {widgetId: 'canvas', status: 'ready'},
                        {widgetId: 'table', status: 'ready'},
                        {widgetId: 'empty', status: 'empty'}
                      ]
                    }
                  }));
                }));
              });
            </script>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    result = DashboardChromiumRenderer().render(
        DashboardRenderRequest(
            execution_id=1,
            render_url=html_path.as_uri(),
            output_path=output_path,
            executable_path=executable_path,
        )
    )

    assert result["signal"]["type"] == "report-ready"
    assert result["pdf"]["bytes"] >= 1_024
    with fitz.open(output_path) as document:
        assert document.page_count >= 1
        pixels = document[0].get_pixmap(alpha=False).samples
        assert len(set(pixels)) > 10
        extracted_text = "".join(page.get_text() for page in document)
        assert "运营分析仪表盘" in extracted_text
        assert "核心服务" in extracted_text
        assert "暂无数据" in extracted_text
