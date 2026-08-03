from dataclasses import dataclass

from rest_framework.exceptions import ValidationError

from apps.operation_analysis.services.canvas_report.types import (
    KNOWN_RESOURCE_TYPES,
    RESOURCE_TYPE_DASHBOARD,
    WRITABLE_RESOURCE_TYPES,
)


@dataclass(frozen=True)
class ResourceBinding:
    resource_type: str
    resource_id: int
    dashboard_id: int | None


def _coerce_dashboard_id(dashboard) -> int | None:
    if dashboard is None:
        return None
    if hasattr(dashboard, "pk"):
        pk = dashboard.pk
        return int(pk) if pk is not None else None
    try:
        return int(dashboard)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"dashboard": "仪表盘 ID 无效"}) from exc


def normalize_resource_binding(
    *,
    dashboard=None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    require_binding: bool = True,
) -> ResourceBinding | None:
    """归一化订阅/执行资源绑定（Phase 3 允许 dashboard 与 screen）。"""
    dashboard_id = _coerce_dashboard_id(dashboard)
    has_resource = resource_type is not None or resource_id is not None

    if has_resource and (resource_type is None or resource_id is None):
        raise ValidationError(
            {
                "resource_type": "resource_type 与 resource_id 必须同时提供",
                "resource_id": "resource_type 与 resource_id 必须同时提供",
            }
        )

    if resource_type is not None:
        if resource_type not in KNOWN_RESOURCE_TYPES:
            raise ValidationError(
                {"resource_type": f"不支持的画布类型: {resource_type}"}
            )
        if resource_type not in WRITABLE_RESOURCE_TYPES:
            raise ValidationError(
                {"resource_type": f"暂不支持创建该画布类型订阅: {resource_type}"}
            )

    if dashboard_id is not None and has_resource:
        if resource_type != RESOURCE_TYPE_DASHBOARD:
            raise ValidationError(
                {"dashboard": "dashboard 仅可与 resource_type=dashboard 同时使用"}
            )
        if int(resource_id) != dashboard_id:
            raise ValidationError(
                {"resource_id": "resource_id 与 dashboard 不一致"}
            )
        return ResourceBinding(
            resource_type=RESOURCE_TYPE_DASHBOARD,
            resource_id=dashboard_id,
            dashboard_id=dashboard_id,
        )

    if dashboard_id is not None:
        return ResourceBinding(
            resource_type=RESOURCE_TYPE_DASHBOARD,
            resource_id=dashboard_id,
            dashboard_id=dashboard_id,
        )

    if has_resource:
        assert resource_type is not None and resource_id is not None
        binding_dashboard_id = (
            int(resource_id)
            if resource_type == RESOURCE_TYPE_DASHBOARD
            else None
        )
        return ResourceBinding(
            resource_type=resource_type,
            resource_id=int(resource_id),
            dashboard_id=binding_dashboard_id,
        )

    if require_binding:
        raise ValidationError(
            {
                "dashboard": (
                    "创建报告订阅必须指定 dashboard 或 resource_type+resource_id"
                )
            }
        )
    return None
