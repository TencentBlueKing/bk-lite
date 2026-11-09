"""画布引用数据源：存在但当前组织无权时返回 hasAuth=false 桩。"""

from apps.operation_analysis.common.datasource_visibility import can_access_datasource_in_org
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel


def normalize_canvas_datasource_ids(raw_ids) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw in raw_ids or []:
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        if parsed <= 0 or parsed in seen:
            continue
        seen.add(parsed)
        normalized.append(parsed)
    return normalized


def denied_canvas_datasource_stub(datasource_id: int, required_app: str | None = None) -> dict:
    normalized = required_app.strip() if isinstance(required_app, str) else ""
    return {
        "id": datasource_id,
        "hasAuth": False,
        "required_app": normalized or None,
    }


def build_canvas_datasource_payloads(
    *,
    ordered_ids: list[int],
    instances: list[DataSourceAPIModel],
    current_team,
    serialize_allowed,
) -> list[dict]:
    found = {item.id: item for item in instances}
    payloads: list[dict] = []
    for ds_id in ordered_ids:
        instance = found.get(ds_id)
        if instance is None:
            continue
        if can_access_datasource_in_org(instance, current_team):
            data = serialize_allowed(instance)
            data["hasAuth"] = True
            payloads.append(data)
        else:
            payloads.append(denied_canvas_datasource_stub(ds_id, getattr(instance, "required_app", None)))
    return payloads
