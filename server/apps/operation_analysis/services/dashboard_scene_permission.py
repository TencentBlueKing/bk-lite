"""仪表盘场景组件轻量权限检查（不拉取拓扑正文）。"""

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.instance_identity import normalize_inst_uuid
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import operation_analysis_logger as logger
from apps.core.logger import safe_exception_info
from apps.operation_analysis.common.get_nats_source_data import build_nats_user_info

_SCENE_PERMISSION_DEGRADED = "event=dashboard_scene_permission_degraded failed_stage=%s error_type=%s inst_uuid=%s"


def _log_scene_permission_degraded(failed_stage: str, error: BaseException, inst_uuid: str) -> None:
    logger.warning(
        _SCENE_PERMISSION_DEGRADED,
        failed_stage,
        type(error).__name__,
        inst_uuid,
        exc_info=safe_exception_info(error),
    )


_APPLICATION_TOPOLOGY_MODELS = frozenset({"system"})


def _topology_permission_code(request, inst_uuid: str, *, require_application_system: bool) -> str:
    raw = (inst_uuid or "").strip()
    if not raw:
        return "visible"

    user_info = build_nats_user_info(request)
    try:
        normalized = normalize_inst_uuid(raw)
    except BaseAppException:
        return "visible"

    try:
        instance = InstanceManage.query_entity_by_uuid(normalized)
    except Exception as exc:
        _log_scene_permission_degraded("query_entity", exc, normalized)
        return "visible"

    if not instance:
        return "visible"

    model_id = str(instance.get("model_id") or "")
    if require_application_system and model_id not in _APPLICATION_TOPOLOGY_MODELS:
        return "visible"

    try:
        from apps.cmdb.nats.nats import _build_nats_permission_map, _normalize_permission_user

        permission_map = _build_nats_permission_map(user_info, model_id=model_id)
        user = _normalize_permission_user((user_info or {}).get("user"), domain=(user_info or {}).get("domain"))
        if permission_map is None or not InstanceManage._has_topology_view_permission(
            instance,
            permission_map,
            user=user,
        ):
            return "permission_denied"
    except Exception as exc:
        _log_scene_permission_degraded("permission_map", exc, normalized)
        return "visible"

    return "visible"


def check_related_topology_permission(request, inst_uuid: str) -> str:
    return _topology_permission_code(request, inst_uuid, require_application_system=False)


def check_application_topology_permission(request, inst_uuid: str) -> str:
    return _topology_permission_code(request, inst_uuid, require_application_system=True)


def batch_check_dashboard_scene_permissions(request, checks: list[dict]) -> list[dict]:
    results = []
    for item in checks:
        widget_id = str(item.get("widget_id") or "").strip()
        scene_type = str(item.get("scene_type") or "").strip()
        inst_uuid = str(item.get("inst_uuid") or "").strip()
        if not widget_id:
            continue
        if scene_type == "relatedTopology":
            code = check_related_topology_permission(request, inst_uuid) if inst_uuid else "visible"
        elif scene_type == "applicationTopology":
            code = check_application_topology_permission(request, inst_uuid) if inst_uuid else "visible"
        else:
            code = "visible"
        results.append({"widget_id": widget_id, "code": code})
    return results
