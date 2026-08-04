from apps.operation_analysis.services.canvas_report.base import CanvasReportAdapter
from apps.operation_analysis.services.canvas_report.dashboard import (
    DashboardCanvasReportAdapter,
)
from apps.operation_analysis.services.canvas_report.screen import (
    ScreenCanvasReportAdapter,
)
from apps.operation_analysis.services.canvas_report.types import (
    RESOURCE_TYPE_DASHBOARD,
    RESOURCE_TYPE_SCREEN,
)


class UnknownCanvasReportType(ValueError):
    """未知或不支持的画布报告资源类型。"""


_ADAPTERS: dict[str, CanvasReportAdapter] = {
    RESOURCE_TYPE_DASHBOARD: DashboardCanvasReportAdapter(),
    RESOURCE_TYPE_SCREEN: ScreenCanvasReportAdapter(),
}


def get_canvas_report_adapter(resource_type: str) -> CanvasReportAdapter:
    try:
        return _ADAPTERS[resource_type]
    except KeyError as exc:
        raise UnknownCanvasReportType(resource_type) from exc
