"""Dashboard 后台 PDF 渲染回归工具。

调用方提供可直接访问的正式 Render URL。工具不负责登录，也不理解 Dashboard、
Execution 或 DataSource；页面是否完成完全由 ``bk-dashboard-render`` 事件决定。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardChromiumRenderer,
    DashboardRenderRequest,
)


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


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()

    render_result = DashboardChromiumRenderer().render(
        DashboardRenderRequest(
            execution_id=0,
            render_url=args.render_url,
            output_path=args.output,
            timeout_ms=args.timeout_ms,
            executable_path=args.executable_path,
        )
    )
    print(
        json.dumps(
            {
                **render_result,
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
