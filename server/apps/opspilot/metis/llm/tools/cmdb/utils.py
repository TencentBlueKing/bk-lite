import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.contrib.auth import get_user_model

from apps.cmdb.constants.constants import APP_NAME, OPERATE, PERMISSION_INSTANCES, PERMISSION_MODEL, VIEW
from apps.cmdb.utils.base import format_groups_params, get_default_group_id
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.permission_utils import get_permission_rules
from apps.system_mgmt.utils.group_utils import GroupUtils


def _get_configurable(config: Any) -> Dict[str, Any]:
    if not config:
        return {}
    if isinstance(config, dict):
        return config.get("configurable", {})
    return getattr(config, "configurable", {})

def _get_user_from_config(config: Any):
    configurable = _get_configurable(config)
    user_id = configurable.get("user_id")
    if not user_id:
        raise ValueError("user_id is required in tool config")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id must be an integer") from exc
    user_model = get_user_model()
    user = user_model.objects.filter(id=user_id).first()
    if not user:
        raise ValueError("user_id not found")
    return user


def _get_user_group_ids(user) -> List[int]:
    group_list = getattr(user, "group_list", []) or []
    if not group_list:
        return []
    if isinstance(group_list, list) and isinstance(group_list[0], dict):
        return [int(item["id"]) for item in group_list if "id" in item]
    return [int(item) for item in group_list]


def _resolve_team_context(
    user,
    config: Any,
    team_id: Optional[int],
    include_children: Optional[bool],
) -> Tuple[int, bool]:
    configurable = _get_configurable(config)
    resolved_team = team_id or configurable.get("team_id")
    resolved_include_children = (
        include_children if include_children is not None else configurable.get("include_children", False)
    )

    if resolved_team is None:
        group_ids = _get_user_group_ids(user)
        if group_ids:
            resolved_team = group_ids[0]
        else:
            resolved_team = get_default_group_id()[0]

    return int(resolved_team), bool(resolved_include_children)


def _resolve_allow_write(config: Any, allow_write: Optional[bool]) -> bool:
    if allow_write is not None:
        return bool(allow_write)
    configurable = _get_configurable(config)
    return bool(configurable.get("allow_write", False))


def _get_user_teams(current_team: int, include_children: bool, user_group_ids: List[int]) -> List[int]:
    if not current_team:
        return []
    if not user_group_ids:
        return [current_team]
    if include_children:
        return GroupUtils.get_user_authorized_child_groups(user_group_ids, current_team, include_children=True)
    if current_team in user_group_ids:
        return [current_team]
    return []


def build_permission_map(
    user,
    current_team: int,
    include_children: bool,
    permission_type: str,
    model_id: str = "",
) -> Dict[int, Dict[str, Any]]:
    permission_key = f"{permission_type}.{model_id}" if model_id else permission_type
    permission_rules = get_permission_rules(user, current_team, APP_NAME, permission_key, include_children)
    if not isinstance(permission_rules, dict):
        permission_rules = {}

    teams = permission_rules.get("team", [])
    instance_rules = permission_rules.get("instance", [])
    permission_instances_map = CmdbRulesFormatUtil.format_permission_instances_list(instances=instance_rules)
    inst_names = list(permission_instances_map.keys())

    user_group_ids = _get_user_group_ids(user)
    user_teams = _get_user_teams(current_team, include_children, user_group_ids)
    if not user_teams:
        user_teams = [current_team]

    permission_rule_map: Dict[int, Dict[str, Any]] = {}
    for team in user_teams:
        if not include_children and team not in teams:
            continue
        if team in teams:
            permission_rule_map[team] = {"permission_instances_map": {}, "inst_names": []}
        else:
            permission_rule_map[team] = {
                "permission_instances_map": permission_instances_map,
                "inst_names": inst_names,
            }
    return permission_rule_map


def ensure_model_permission(
    user,
    model_info: Dict[str, Any],
    permission_map: Dict[int, Dict[str, Any]],
    operator: str,
) -> None:
    default_group_id = get_default_group_id()[0]
    has_permission = CmdbRulesFormatUtil.has_object_permission(
        obj_type=PERMISSION_MODEL,
        operator=operator,
        model_id=model_info.get("model_id", ""),
        permission_instances_map=permission_map,
        instance=model_info,
        default_group_id=default_group_id,
    )
    if not has_permission:
        logger.warning("Model permission denied: %s", model_info.get("model_id"))
        raise ValueError("insufficient model permission")


def ensure_instance_permission(
    user,
    instance: Dict[str, Any],
    permission_map: Dict[int, Dict[str, Any]],
    operator: str,
) -> None:
    if instance.get("_creator") == getattr(user, "username", ""):
        return
    has_permission = CmdbRulesFormatUtil.has_object_permission(
        obj_type=PERMISSION_INSTANCES,
        operator=operator,
        model_id=instance.get("model_id", ""),
        permission_instances_map=permission_map,
        instance=instance,
    )
    if not has_permission:
        logger.warning("Instance permission denied: %s", instance.get("_id"))
        raise ValueError("insufficient instance permission")


def build_user_groups(user, current_team: int, include_children: bool) -> List[Dict[str, int]]:
    user_group_ids = _get_user_group_ids(user)
    if include_children:
        team_ids = GroupUtils.get_user_authorized_child_groups(user_group_ids, current_team, include_children=True)
    else:
        team_ids = [current_team]
    if not team_ids:
        team_ids = [current_team]
    return format_groups_params(team_ids)


def normalize_query_list(query_list: Any) -> List[Dict[str, Any]]:
    if query_list is None:
        return []
    if isinstance(query_list, dict):
        query_list = [query_list]
    if not isinstance(query_list, list):
        return []

    normalized: List[Dict[str, Any]] = []

    def add_condition(item: Any) -> None:
        if not item or not isinstance(item, dict):
            return
        field = item.get("field")
        _type = item.get("type")
        if not field or not _type:
            return

        if _type == "time":
            start = item.get("start")
            end = item.get("end")
            if not start or not end:
                return
            normalized.append({"field": field, "type": _type, "start": start, "end": end})
            return

        if "value" not in item:
            return
        value = item.get("value")
        if value is None:
            return
        if isinstance(value, str) and value == "":
            return
        if isinstance(value, list) and not value:
            return
        normalized.append({"field": field, "type": _type, "value": value})

    def walk(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, dict):
            add_condition(node)
            return
        if isinstance(node, list):
            for sub in node:
                walk(sub)

    walk(query_list)
    return normalized


def wrap_success(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def wrap_error(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message}


def ensure_write_allowed(user, allow_write: bool) -> None:
    if not allow_write:
        raise ValueError("write operations are disabled (allow_write=false)")
    if not getattr(user, "is_superuser", False):
        raise ValueError("write operations require superuser")


def to_json_safe(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)
