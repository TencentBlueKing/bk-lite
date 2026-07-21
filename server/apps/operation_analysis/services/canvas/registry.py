from dataclasses import dataclass

from apps.operation_analysis.models.models import Architecture, Dashboard, NetworkTopology, Report, Screen, Topology


@dataclass(frozen=True)
class CanvasTypeMeta:
    object_type: str
    model: type
    permission_key: str
    section_name: str
    node_label: str


CANVAS_TYPE_REGISTRY = {
    "dashboard": CanvasTypeMeta("dashboard", Dashboard, "directory.dashboard", "dashboards", "仪表盘"),
    "topology": CanvasTypeMeta("topology", Topology, "directory.topology", "topologies", "拓扑图"),
    "architecture": CanvasTypeMeta("architecture", Architecture, "directory.architecture", "architectures", "架构图"),
    "screen": CanvasTypeMeta("screen", Screen, "directory.screen", "screens", "大屏"),
    "report": CanvasTypeMeta("report", Report, "directory.report", "reports", "报表"),
    "networkTopology": CanvasTypeMeta("networkTopology", NetworkTopology, "directory.networkTopology", "network_topologies", "网络拓扑"),
}
