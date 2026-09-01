import datetime
import os
import time
from datetime import date
from datetime import datetime as _datetime
from datetime import timezone as _timezone
from functools import reduce, wraps
from operator import or_
from types import SimpleNamespace
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMinute, TruncMonth
from django.utils import timezone

import nats_client
from apps.cmdb.constants.constants import (
    APP_NAME,
    ENUM_SELECT_MODE_MULTIPLE,
    PERMISSION_INSTANCES,
    PERMISSION_MODEL,
    PERMISSION_TASK,
    CollectPluginTypes,
    CollectRunStatusType,
)
from apps.cmdb.display_field.cache import ExcludeFieldsCache
from apps.cmdb.display_field.constants import (
    DISPLAY_FIELD_TYPES,
    DISPLAY_SUFFIX,
    FIELD_TYPE_ENUM,
    FIELD_TYPE_ORGANIZATION,
    FIELD_TYPE_TABLE,
    FIELD_TYPE_TAG,
    FIELD_TYPE_USER,
    USER_DISPLAY_FORMAT,
)
from apps.cmdb.display_field.handler import DisplayFieldConverter, DisplayFieldHandler
from apps.cmdb.models.change_record import CREATE_INST, DELETE_INST, OPERATE_TYPE_CHOICES, UPDATE_INST, ChangeRecord
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.config_file_version import ConfigFileVersion, ConfigFileVersionStatus
from apps.cmdb.openapi_serializers import CmdbModuleDataQuerySerializer
from apps.cmdb.services import rack_room
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.module_ingest import CmdbModuleIngestService
from apps.cmdb.services.rack_room import format_rack_location_label, parse_rack_location
from apps.cmdb.services.region_resource_overview import build_region_resource_items, extract_region_options
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.utils.config_file_path import validate_absolute_path
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.logger import cmdb_logger as logger
from apps.core.openapi.decorators import openapi_expose
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.time_util import parse_rfc3339_utc
from apps.core.utils.trend_granularity import resolve_trend_group_by_from_range
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.models.role import Role
from apps.system_mgmt.utils.group_utils import GroupUtils

_MANUAL_CONFIG_FILE_MODELS = frozenset({"host", "switch", "router", "firewall", "loadbalance"})
_MANUAL_CONFIG_FILE_MAX_ITEMS = 50
_MANUAL_CONFIG_FILE_MAX_CONTENTS = 5
_MANUAL_CONFIG_FILE_VERSION_GAP_SECONDS = 0.002

_CHANGE_TREND_MAX_SPAN_SECONDS = {
    "minute": int(os.getenv("CMDB_CHANGE_TREND_MAX_SPAN_MINUTE", str(7 * 24 * 3600))),
    "hour": int(os.getenv("CMDB_CHANGE_TREND_MAX_SPAN_HOUR", str(90 * 24 * 3600))),
    "day": int(os.getenv("CMDB_CHANGE_TREND_MAX_SPAN_DAY", str(730 * 24 * 3600))),
    "month": int(os.getenv("CMDB_CHANGE_TREND_MAX_SPAN_MONTH", str(10 * 365 * 24 * 3600))),
}

_RPC_TRANSPORT_KEYS = {"_timeout", "_raw"}


def _accept_legacy_rpc_kwargs(func):
    """迁移期同时接收 params envelope 与旧版顶层 RPC kwargs。"""

    @wraps(func)
    def wrapper(params=None, **legacy_kwargs):
        legacy_kwargs = {key: value for key, value in legacy_kwargs.items() if key not in _RPC_TRANSPORT_KEYS}
        if params is None:
            normalized = legacy_kwargs
        elif isinstance(params, dict):
            conflicts = sorted(set(params).intersection(legacy_kwargs))
            if conflicts:
                raise ValueError(f"CMDB RPC params conflict: {conflicts}")
            normalized = {**params, **legacy_kwargs}
        elif legacy_kwargs:
            # list_instances 的业务查询条件也名为 params；旧顶层调用会绑定到该形参。
            normalized = {"params": params, **legacy_kwargs}
        else:
            raise ValueError("CMDB RPC params must be an object")
        return func(normalized)

    return wrapper


def _normalize_to_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


def _require_uuid_protocol(params):
    if str((params or {}).get("protocol_version") or "") != "2":
        raise ValueError("unsupported CMDB identity protocol version")


def _reject_legacy_numeric_locators(params, *keys):
    """Reject legacy graph/numeric identity keys with a clear error."""
    params = params or {}
    present = [key for key in keys if params.get(key) not in (None, "", [])]
    if present:
        raise ValueError(f"legacy numeric locators {present} are no longer supported; use UUID params")


def _normalize_permission_user(user, domain=None):
    if hasattr(user, "username") and hasattr(user, "domain"):
        return user
    if isinstance(user, str) and user:
        return SimpleNamespace(username=user, domain=domain)
    return user


def _get_authorized_team_ids(user_obj, current_team, include_children=False):
    user_group_ids = [group["id"] if isinstance(group, dict) else group for group in (user_obj.group_list or [])]

    role_ids = set(getattr(user_obj, "role_list", []) or [])
    if role_ids:
        role_names = {f"{role.app}--{role.name}" if role.app else role.name for role in Role.objects.filter(id__in=role_ids).only("name", "app")}
    else:
        role_names = set()

    if {"admin", "system-manager--admin"}.intersection(role_names):
        return GroupUtils.get_group_with_descendants(current_team) if include_children else [current_team]

    return GroupUtils.get_user_authorized_child_groups(
        user_group_list=user_group_ids,
        target_group_id=current_team,
        include_children=include_children,
    )


def _build_nats_permission_map(user_info, model_id="", permission_type=PERMISSION_INSTANCES):
    user_info = user_info or {}
    team = user_info.get("team")
    user = user_info.get("user")
    domain = user_info.get("domain")
    include_children = user_info.get("include_children", False)

    if not user or team is None:
        return None

    user_obj = _normalize_permission_user(user, domain=domain)
    current_team = int(team)
    user_filters = {"username": user_obj.username}
    if getattr(user_obj, "domain", None):
        user_filters["domain"] = user_obj.domain
    real_user = User.objects.filter(**user_filters).first()
    if not real_user:
        return None

    authorized_team_ids = _get_authorized_team_ids(real_user, current_team, include_children=include_children)
    if not authorized_team_ids:
        return None

    permission_key = f"{permission_type}.{model_id}" if model_id else permission_type
    permission_rules = get_permission_rules(
        user=user_obj,
        current_team=current_team,
        app_name=APP_NAME,
        permission_key=permission_key,
        include_children=include_children,
    )
    if not isinstance(permission_rules, dict):
        permission_rules = {}

    permission_map = CmdbRulesFormatUtil.build_permission_rule_map(
        user_teams=authorized_team_ids,
        permission_rules=permission_rules,
        fallback_team_id=current_team,
    )

    if not permission_map:
        return None

    return permission_map


def _build_nats_model_permission_map(user_info):
    permission_map = _build_nats_permission_map(user_info, permission_type=PERMISSION_MODEL)
    if permission_map is None:
        return None

    default_group_id = get_default_group_id()[0]
    current_team = int((user_info or {}).get("team") or 0)

    if default_group_id != current_team and default_group_id not in permission_map:
        permission_map[default_group_id] = {
            "permission_instances_map": {},
            "inst_names": [],
        }

    return permission_map


def _resolve_nats_cmdb_language(user_info=None):
    user_info = user_info or {}
    user = user_info.get("user")
    raw_language = user_info.get("locale") or user_info.get("language") or getattr(user, "locale", None) or user_info.get("LANGUAGE_CODE") or "zh-CN"
    return "en" if str(raw_language).lower().startswith("en") else "zh-Hans"


def _get_collect_task_queryset(user_info):
    user_info = user_info or {}
    team = user_info.get("team")
    include_children = user_info.get("include_children", False)

    if team is None:
        return CollectModels.objects.none()

    current_team = int(team)
    team_ids = GroupUtils.get_group_with_descendants(current_team) if include_children else [current_team]
    team_queries = [Q(team__contains=[team_id]) | Q(team__contains=[str(team_id)]) for team_id in team_ids]
    if not team_queries:
        return CollectModels.objects.none()

    return CollectModels.objects.filter(is_system=False).filter(reduce(or_, team_queries)).distinct()


def _build_authoritative_maps(instances, attrs):
    org_ids = set()
    user_ids = set()
    enum_name_maps = {}

    for attr in attrs:
        if attr.get("is_display_field"):
            continue

        attr_id = attr.get("attr_id")
        attr_type = attr.get("attr_type")

        if attr_type == FIELD_TYPE_ENUM:
            enum_name_maps[attr_id] = {str(option.get("id")): option.get("name") for option in attr.get("option", []) if option}
            continue

        if attr_type not in {FIELD_TYPE_ORGANIZATION, FIELD_TYPE_USER}:
            continue

        for instance in instances:
            raw_value = instance.get(attr_id)
            values = _normalize_to_list(raw_value)
            if attr_type == FIELD_TYPE_ORGANIZATION:
                org_ids.update(values)
            else:
                user_ids.update(values)

    group_name_map = {group["id"]: group["name"] for group in Group.objects.filter(id__in=org_ids).values("id", "name")}
    user_info_map = {user["id"]: user for user in User.objects.filter(id__in=user_ids).values("id", "username", "display_name")}

    return group_name_map, user_info_map, enum_name_maps


def _format_user_value(user_id, user_info_map):
    user_info = user_info_map.get(user_id)
    if not user_info:
        return str(user_id)

    username = user_info.get("username", "")
    display_name = user_info.get("display_name", "")
    if display_name and str(display_name).strip():
        return USER_DISPLAY_FORMAT.format(display_name=display_name, username=username)
    return username or str(user_id)


def _format_instance_for_asset_query(instance, attrs, group_name_map, user_info_map, enum_name_maps):
    formatted = {}
    attr_map = {attr.get("attr_id"): attr for attr in attrs if attr.get("attr_id") and not attr.get("is_display_field")}

    for key, value in instance.items():
        if key.endswith(DISPLAY_SUFFIX):
            continue

        attr = attr_map.get(key)
        if not attr:
            formatted[key] = value
            continue

        attr_type = attr.get("attr_type")

        if attr_type == FIELD_TYPE_ORGANIZATION:
            values = _normalize_to_list(value)
            names = [str(group_name_map.get(org_id, org_id)) for org_id in values]
            formatted[key] = ", ".join(names) if names else ""
        elif attr_type == FIELD_TYPE_USER:
            values = _normalize_to_list(value)
            names = [_format_user_value(user_id, user_info_map) for user_id in values]
            formatted[key] = ", ".join([name for name in names if name]) if names else ""
        elif attr_type == FIELD_TYPE_ENUM:
            enum_name_map = enum_name_maps.get(key, {})
            if isinstance(value, list):
                formatted[key] = ", ".join([str(enum_name_map.get(str(item), item)) for item in value if item is not None])
            elif value in (None, ""):
                formatted[key] = ""
            else:
                formatted[key] = enum_name_map.get(str(value), value)
        elif attr_type == FIELD_TYPE_TAG:
            formatted[key] = DisplayFieldConverter.convert_tag(value)
        elif attr_type == FIELD_TYPE_TABLE:
            formatted[key] = DisplayFieldConverter.convert_table(value)
        else:
            formatted[key] = value

    return DisplayFieldHandler.remove_display_fields(formatted)


def _format_asset_instances_response(model_id, instances):
    if not instances:
        return []

    attrs = ExcludeFieldsCache.get_model_attrs(model_id)
    if not attrs:
        return [DisplayFieldHandler.remove_display_fields(dict(instance)) for instance in instances]

    group_name_map, user_info_map, enum_name_maps = _build_authoritative_maps(instances, attrs)

    return [_format_instance_for_asset_query(dict(instance), attrs, group_name_map, user_info_map, enum_name_maps) for instance in instances]


@nats_client.register
@openapi_expose(
    path="cmdb/module-data",
    method="GET",
    schema=CmdbModuleDataQuerySerializer,
    inject="user_info",
    summary="cmdb 实例模块数据（组织口径：以锚点做子树级联展开，锚点须为直属组织）",
)
def get_cmdb_module_data(module, child_module, page, page_size, group_id, user_info=None):
    """
    获取cmdb模块实例数据

    Args:
        module: 模块类型（PERMISSION_INSTANCES / PERMISSION_MODEL / PERMISSION_TASK）
        child_module: 子模块标识（PERMISSION_INSTANCES 分支下为 model_id）
        page: 页码
        page_size: 每页条目数
        group_id: 组织 ID，用于限定组织范围查询
        user_info: 用户上下文 { user: str, team: int, domain: str }，
                   由调用方（system_mgmt）注入；缺失时 PERMISSION_INSTANCES 分支返回空列表（安全兜底）
    """
    page = int(page)
    page_size = int(page_size)
    if module == PERMISSION_TASK:
        # 计算分页
        start = (page - 1) * page_size
        end = page * page_size
        instances = CollectModels.objects.filter(
            task_type=child_module,
            is_system=False,
        )
        count = instances.count()
        instances = instances.values("id", "name", "model_id")[start:end]
        queryset = [{"id": str(i["id"]), "name": f"{i['model_id']}_{i['name']}"} for i in instances]
    elif module == PERMISSION_INSTANCES:
        # 构建真实权限 map：根据调用方传入的 user_info 查询用户在目标模型上的权限范围
        # 当 user_info 缺失或用户无权限时返回空列表，避免越权泄露实例名称
        permission_map = _build_nats_permission_map(user_info, model_id=child_module)
        if permission_map is None:
            return {"count": 0, "items": []}
        instances, count = InstanceManage.instance_list(
            model_id=child_module,
            params=[{"field": "organization", "type": "list[]", "value": [int(group_id)]}],
            page=page,
            page_size=page_size,
            order="",
            creator="",
            permission_map=permission_map,
        )
        queryset = []
        for instance in instances:
            queryset.append({"name": instance["inst_name"], "id": instance["inst_name"]})
    elif module == PERMISSION_MODEL:
        models = ModelManage.search_model(classification_ids=[child_module])
        count = len(models)
        queryset = [{"id": model["model_id"], "name": model["model_name"]} for model in models]

    else:
        raise ValueError("Invalid module type")

    result = {"count": count, "items": list(queryset)}
    return result


@nats_client.register
def get_cmdb_module_list():
    """
    获取cmdb模块列表
    """
    classifications = ClassificationManage.search_model_classification()
    classification_list = []
    model_children = []
    for classification in classifications:
        model_children.append(
            {
                "name": classification["classification_id"],
                "display_name": classification["classification_name"],
            }
        )
        classification_list.append(
            {"name": classification["classification_id"], "display_name": classification["classification_name"], "children": []}
        )

    """
        根据模型分类id进行数据封装
    """
    models = ModelManage.search_model()
    model_map = {}
    for model in models:
        if model["classification_id"] not in model_map:
            model_map[model["classification_id"]] = []

        model_map[model["classification_id"]].append(
            {
                "name": model["model_id"],
                "display_name": model["model_name"],
            }
        )

    for _classification in classification_list:
        classification_id = _classification["name"]
        if classification_id in model_map:
            _classification["children"] = model_map[classification_id]

    # 任务
    task_children = [{"name": name, "display_name": display_name} for name, display_name in CollectPluginTypes.CHOICE]

    result = [
        {"name": PERMISSION_MODEL, "display_name": "Model", "children": model_children},
        {"name": PERMISSION_INSTANCES, "display_name": "Instance", "children": classification_list},
        {"name": PERMISSION_TASK, "display_name": "Task", "children": task_children},
    ]
    return result


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_instances(params):
    """
    根据参数查询实例
    """
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "_id", "inst_id", "ids")
    allowed_org_ids = set(_normalize_allowed_org_ids_for_scope(params.get("organization_ids")))
    if not allowed_org_ids:
        raise ValueError("organization_ids is required")
    model_id = params["model_id"]
    inst_name = params.get("inst_name", None)
    inst_uuid = params.get("inst_uuid")

    instances, _ = InstanceManage.search_inst(model_id=model_id, inst_name=inst_name, inst_uuid=inst_uuid)
    result = instances[0] if instances else {}
    if result and not allowed_org_ids.intersection(_normalize_allowed_org_ids_for_scope(result.get("organization"))):
        return {}
    return _serialize_instance_for_transport(result)


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_instances_batch(params):
    """批量查询实例。params={"model_id":..,"inst_uuids":[..],"inst_names":[..]}。"""
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "ids", "_id", "inst_ids")
    allowed_org_ids = set(_normalize_allowed_org_ids_for_scope(params.get("organization_ids")))
    if not allowed_org_ids:
        return {}
    result = InstanceManage.search_inst_batch(
        model_id=params["model_id"],
        inst_uuids=params.get("inst_uuids"),
        inst_names=params.get("inst_names"),
    )
    filtered = {}
    for key, instance in result.items():
        instance_org_ids = set()
        for org_id in instance.get("organization") or []:
            try:
                instance_org_ids.add(int(org_id))
            except (TypeError, ValueError):
                continue
        if allowed_org_ids & instance_org_ids:
            filtered[key] = _serialize_instance_for_transport(instance)
    return filtered


def _normalize_allowed_org_ids_for_scope(raw_allowed):
    allowed_org_ids = _normalize_to_list(raw_allowed)
    normalized = []
    for org_id in allowed_org_ids:
        try:
            normalized.append(int(org_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("allowed_org_ids must be an integer array") from exc
    return normalized


def _resolve_user_info_allowed_org_ids(user_info):
    user_info = user_info or {}
    if "allowed_org_ids" in user_info:
        return _normalize_allowed_org_ids_for_scope(user_info.get("allowed_org_ids"))

    team = user_info.get("team")
    user = user_info.get("user")
    domain = user_info.get("domain")
    include_children = user_info.get("include_children", False)
    if not user or team is None:
        return None

    user_obj = _normalize_permission_user(user, domain=domain)
    user_filters = {"username": user_obj.username}
    if getattr(user_obj, "domain", None):
        user_filters["domain"] = user_obj.domain
    real_user = User.objects.filter(**user_filters).first()
    if not real_user:
        return None

    return _get_authorized_team_ids(real_user, int(team), include_children=include_children)


def _resolve_allowed_org_ids(params):
    """解析实例写操作的 organization 范围上下文。

    HTTP 路径下该范围由 view 从请求 cookie（current_team/include_children）+ 用户组织树推导。
    NATS 写入口必须显式携带授权上下文，不能从 payload organization 反推权限范围。
    """
    if "allowed_org_ids" in params:
        return _normalize_allowed_org_ids_for_scope(params.get("allowed_org_ids"))

    for scope_key in ("service_scope", "scope"):
        scope = params.get(scope_key)
        if isinstance(scope, dict) and "allowed_org_ids" in scope:
            return _normalize_allowed_org_ids_for_scope(scope.get("allowed_org_ids"))

    allowed_from_user = _resolve_user_info_allowed_org_ids(params.get("user_info"))
    if allowed_from_user is not None:
        return allowed_from_user

    raise ValueError("authorization scope is required for CMDB NATS writes")


def _build_scope_user_groups(allowed_org_ids):
    return [{"id": org_id} for org_id in allowed_org_ids]


def _ensure_organization_in_scope(data, allowed_org_ids):
    org_value = (data or {}).get("organization")
    target_org_ids = _normalize_to_list(org_value)
    if not target_org_ids:
        return

    target_org_ids = _normalize_allowed_org_ids_for_scope(target_org_ids)
    invalid_org_ids = sorted(set(target_org_ids) - set(allowed_org_ids))
    if invalid_org_ids:
        raise ValueError(f"organization {invalid_org_ids} 不在授权范围内")


def _serialize_instance_for_transport(instance):
    return {key: value for key, value in dict(instance or {}).items() if key not in {"_id", "_labels", "permission"}}


@nats_client.register
def update_instance(params):
    """
    修改实例属性

    params={
        "protocol_version": "2",
        "inst_uuid": "...",       # 实例 UUID，必填
        "update_attr": {...},      # 待更新的属性键值
        "operator": "admin",       # 操作人，用于变更记录
        "allowed_org_ids": [1, 2]  # 必填授权上下文之一；限制 organization 范围
    }
    -> 更新后的实例数据（不含图内部 _id）
    """
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "inst_id", "_id", "inst_ids")
    update_attr = params.get("update_attr") or {}
    if not update_attr:
        raise ValueError("update_attr is required")
    allowed_org_ids = _resolve_allowed_org_ids(params)
    _ensure_organization_in_scope(update_attr, allowed_org_ids)

    inst_uuid = params.get("inst_uuid")
    if not inst_uuid:
        raise ValueError("inst_uuid is required")

    result = InstanceManage.instance_update_by_uuid(
        user_groups=_build_scope_user_groups(allowed_org_ids),
        roles=[],
        inst_uuid=inst_uuid,
        update_attr=update_attr,
        operator=params.get("operator", ""),
        allowed_org_ids=allowed_org_ids,
        skip_permission_check=False,
    )
    return _serialize_instance_for_transport(result)


@nats_client.register
def create_instance(params):
    """
    创建实例

    params={
        "protocol_version": "2",
        "model_id": "host",        # 模型ID，必填
        "instance_info": {...},    # 实例属性键值，必填
        "operator": "admin",       # 操作人，用于变更记录
        "allowed_org_ids": [1, 2]  # 必填授权上下文之一；限制 organization 范围
    }
    -> 创建后的实例数据（不含图内部 _id）
    """
    _require_uuid_protocol(params)
    model_id = params.get("model_id")
    if not model_id:
        raise ValueError("model_id is required")

    instance_info = params.get("instance_info") or {}
    if not instance_info:
        raise ValueError("instance_info is required")
    allowed_org_ids = _resolve_allowed_org_ids(params)
    _ensure_organization_in_scope(instance_info, allowed_org_ids)

    return _serialize_instance_for_transport(
        InstanceManage.instance_create(
            model_id=model_id,
            instance_info=instance_info,
            operator=params.get("operator", ""),
            allowed_org_ids=allowed_org_ids,
        )
    )


@nats_client.register
def ingest_from_source(params):
    """跨模块推送写入 CMDB（host：node_id 优先 + ip/cloud 存量认领）。

    params 为 IngestEnvelope 扩展字段，另需授权上下文之一：
      allowed_org_ids / service_scope.allowed_org_ids / user_info
    """
    params = dict(params or {})
    params["allowed_org_ids"] = _resolve_allowed_org_ids(params)
    return CmdbModuleIngestService.ingest(params)


@nats_client.register
def delete_instance(params):
    """
    删除实例（支持单个或批量）

    params={
        "protocol_version": "2",
        "inst_uuids": ["..."],    # 实例 UUID 列表
        "inst_uuid": "...",       # 单个实例 UUID
        "operator": "admin",       # 操作人，用于变更记录
        "allowed_org_ids": [1, 2]  # 必填授权上下文之一；限制 organization 范围
    }
    -> {"result": True, "deleted": [<inst_uuids>]}
    """
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "inst_ids", "inst_id", "_id")
    allowed_org_ids = _resolve_allowed_org_ids(params)
    if not allowed_org_ids:
        raise ValueError("authorization scope is required for CMDB NATS writes")
    inst_uuids = _normalize_to_list(params.get("inst_uuids"))
    if not inst_uuids and params.get("inst_uuid"):
        inst_uuids = [params["inst_uuid"]]
    if not inst_uuids:
        raise ValueError("inst_uuids or inst_uuid is required")
    InstanceManage.instance_batch_delete_by_uuids(
        user_groups=_build_scope_user_groups(allowed_org_ids),
        roles=[],
        inst_uuids=inst_uuids,
        operator=params.get("operator", ""),
    )
    return {"result": True, "deleted": inst_uuids}


@nats_client.register
@_accept_legacy_rpc_kwargs
def list_instances(params):
    """
    查询单个模型下的实例列表（分页 + 过滤）

    params={
        "protocol_version": "2",
        "model_id": "host",          # 模型ID，必填
        "organization_ids": [1],     # 组织范围，必填
        "params": [...],             # 可选；查询条件，格式同 instance_list，如
                                     #   [{"field": "ip_addr", "type": "str*", "value": "10."}]
        "page": 1,                   # 页码，默认 1
        "page_size": 20,             # 每页条数，默认 20
        "order": "",                 # 排序字段，前缀 - 表示倒序
        "format": True               # 可选；True 时把 org/user/enum 等字段转为展示值，默认 True
    }
    -> {"count": <总数>, "items": [<实例>, ...]}
    """
    _require_uuid_protocol(params)
    model_id = params.get("model_id")
    if not model_id:
        raise ValueError("model_id is required")

    page = int(params.get("page") or 1)
    page_size = int(params.get("page_size") or 20)
    allowed_org_ids = _normalize_allowed_org_ids_for_scope(params.get("organization_ids"))
    if not allowed_org_ids:
        raise ValueError("organization_ids is required")
    query_params = [
        *(params.get("params") or []),
        {"field": "organization", "type": "list[]", "value": allowed_org_ids},
    ]
    order = params.get("order") or ""
    need_format = params.get("format", True)

    instances, count = InstanceManage.instance_list(
        model_id=model_id,
        params=list(query_params),
        page=page,
        page_size=page_size,
        order=order,
        creator="",
        permission_map={},
    )

    raw_items = _format_asset_instances_response(model_id, instances) if need_format else instances
    items = [_serialize_instance_for_transport(item) for item in raw_items]
    return {"count": count, "items": items}


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_model_attrs(params):
    """
    查询模型属性列表

    params={"model_id": "host"}  # 模型ID，必填
    -> [<属性定义>, ...]
    """
    model_id = (params or {}).get("model_id")
    if not model_id:
        raise ValueError("model_id is required")
    return ModelManage.search_model_attr(model_id)


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_models(params=None):
    """
    查询模型列表

    params={
        "classification_id": "host_mgmt",  # 可选；按分类过滤
    }
    -> [<模型定义>, ...]
    """
    params = params or {}
    classification_id = params.get("classification_id")
    classification_ids = [classification_id] if classification_id else None
    return ModelManage.search_model(
        classification_ids=classification_ids,
        include_hidden=False,
    )


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_classifications(params=None):
    """
    查询模型分类列表

    params={}
    -> [<分类定义>, ...]
    """
    return ClassificationManage.search_model_classification(include_hidden=False)


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_model_associations(params):
    """
    查询模型关联定义（作为源或目标的所有关联）

    params={"model_id": "host"}  # 模型ID，必填
    -> [<模型关联定义>, ...]
    """
    model_id = (params or {}).get("model_id")
    if not model_id:
        raise ValueError("model_id is required")
    return ModelManage.model_association_search(model_id, business_only=True)


@nats_client.register
@_accept_legacy_rpc_kwargs
def search_instance_associations(params):
    """
    查询实例关联列表（某实例关联到的其它实例，按 model_asst_id 分组）

    params={
        "protocol_version": "2",
        "model_id": "host",   # 模型ID，必填
        "inst_uuid": "...",   # 实例 UUID，必填
        "organization_ids": [1]
    }
    -> [{"src_model_id":..,"dst_model_id":..,"model_asst_id":..,"asst_id":..,"inst_list":[..]}, ...]
    """
    params = params or {}
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "inst_id", "_id")
    allowed_org_ids = set(_normalize_allowed_org_ids_for_scope(params.get("organization_ids")))
    if not allowed_org_ids:
        raise ValueError("organization_ids is required")
    model_id = params.get("model_id")
    inst_uuid = params.get("inst_uuid")
    if not model_id or not inst_uuid:
        raise ValueError("model_id and inst_uuid are required")
    source = InstanceManage.query_entity_by_uuid(inst_uuid)
    if not source or not allowed_org_ids.intersection(_normalize_allowed_org_ids_for_scope(source.get("organization"))):
        return []
    groups = InstanceManage.instance_association_instance_list_by_uuid(
        model_id,
        inst_uuid,
        business_only=True,
    )
    for group in groups:
        group["inst_list"] = [
            _serialize_instance_for_transport(item)
            for item in group.get("inst_list", [])
            if allowed_org_ids.intersection(_normalize_allowed_org_ids_for_scope(item.get("organization")))
        ]
    return groups


@nats_client.register
@_accept_legacy_rpc_kwargs
def create_instance_association(params):
    """
    创建实例关联（写）

    params={
        "protocol_version": "2",
        "src_inst_uuid": "...",           # 源实例 UUID，必填
        "dst_inst_uuid": "...",           # 目标实例 UUID，必填
        "model_asst_id": "host_run_app",   # 模型关联ID，必填
        "operator": "admin"                # 操作人，用于变更记录
    }
    -> 创建后的关联边数据
    """
    params = params or {}
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "src_inst_id", "dst_inst_id", "asso_id", "_id")
    allowed_org_ids = set(_resolve_allowed_org_ids(params))
    src_inst_uuid = params.get("src_inst_uuid")
    dst_inst_uuid = params.get("dst_inst_uuid")
    model_asst_id = params.get("model_asst_id")
    if not src_inst_uuid or not dst_inst_uuid or not model_asst_id:
        raise ValueError("src_inst_uuid, dst_inst_uuid and model_asst_id are required")
    endpoints = InstanceManage.query_entity_by_uuids([src_inst_uuid, dst_inst_uuid])
    if len(endpoints) != 2 or any(
        not allowed_org_ids.intersection(_normalize_allowed_org_ids_for_scope(item.get("organization"))) for item in endpoints
    ):
        raise ValueError("association endpoint is outside authorization scope")
    return InstanceManage.instance_association_create_by_uuid(
        src_inst_uuid=src_inst_uuid,
        dst_inst_uuid=dst_inst_uuid,
        model_asst_id=model_asst_id,
        operator=params.get("operator", ""),
    )


@nats_client.register
@_accept_legacy_rpc_kwargs
def delete_instance_association(params):
    """
    删除实例关联（写）

    params={
        "protocol_version": "2",
        "src_inst_uuid": "...",
        "dst_inst_uuid": "...",
        "model_asst_id": "host_run_app",
        "operator": "admin"   # 操作人，用于变更记录
    }
    -> {"result": True, "deleted": <stable relation key>}
    """
    params = params or {}
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "asso_id", "inst_asst_id", "_id", "src_inst_id", "dst_inst_id")
    allowed_org_ids = set(_resolve_allowed_org_ids(params))
    required = ("src_inst_uuid", "dst_inst_uuid", "model_asst_id")
    if any(not params.get(key) for key in required):
        raise ValueError("src_inst_uuid, dst_inst_uuid and model_asst_id are required")
    endpoints = InstanceManage.query_entity_by_uuids([params["src_inst_uuid"], params["dst_inst_uuid"]])
    if len(endpoints) != 2 or any(
        not allowed_org_ids.intersection(_normalize_allowed_org_ids_for_scope(item.get("organization"))) for item in endpoints
    ):
        raise ValueError("association endpoint is outside authorization scope")
    deleted = InstanceManage.instance_association_delete_by_key(
        src_inst_uuid=params["src_inst_uuid"],
        dst_inst_uuid=params["dst_inst_uuid"],
        model_asst_id=params["model_asst_id"],
        operator=params.get("operator", ""),
    )
    return {"result": True, "deleted": deleted}


@nats_client.register
def receive_config_file_result(data: dict):
    """接收 Stargazer 回传的配置文件采集结果并落库。"""
    result = ConfigFileService.process_collect_result(data)
    payload = ConfigFileService._normalize_collect_payload(data)
    error_lines = str(result.get("error") or "").splitlines()
    error = (error_lines[0] if error_lines else "")[:500]
    response = {
        "result": True,
        "processed": not bool(error),
        "error": error,
        "changed": bool(result.get("changed", False)),
        "task_updated": bool(result.get("task_updated", False)),
    }
    callback_status = str(payload.get("status") or "error").lower()
    if callback_status not in ConfigFileService.STATUS_MAP:
        callback_status = "unknown"
    execution_id = str(payload.get("execution_id") or "-").replace("\r", "\\r").replace("\n", "\\n")[:64]
    callback_failed = callback_status != "success"
    log_terminal = logger.warning if error or callback_failed else logger.info
    log_terminal(
        "event=config_file_callback_finished task_id=%s execution_id=%s " "callback_status=%s processed=%s changed=%s task_updated=%s stale=%s",
        payload.get("collect_task_id") or payload.get("task_id") or "-",
        execution_id,
        callback_status,
        response["processed"],
        response["changed"],
        response["task_updated"],
        bool(result.get("stale", False)),
    )
    return response


def _manual_config_file_already_exists(instance_uuid, file_path) -> bool:
    return ConfigFileVersion.objects.filter(
        instance_uuid=instance_uuid,
        file_path=file_path,
        status=ConfigFileVersionStatus.SUCCESS,
    ).exists()


def _create_one_manual_config_file(item, allowed_org_ids: set[int]) -> dict:
    if not isinstance(item, dict):
        raise ValueError("item must be an object")
    _reject_legacy_numeric_locators(item, "instance_id", "inst_id", "_id")
    instance_uuid = str(item.get("instance_uuid") or "").strip()
    model_id = str(item.get("model_id") or "").strip()
    file_path = str(item.get("file_path") or "").strip()
    contents = item.get("contents")
    if not instance_uuid or not model_id or not file_path:
        raise ValueError("instance_uuid, model_id and file_path are required")
    if model_id not in _MANUAL_CONFIG_FILE_MODELS:
        raise ValueError(f"model_id {model_id} does not support config files")
    if not validate_absolute_path(file_path):
        raise ValueError("file_path must be an absolute file path")
    if not isinstance(contents, list) or not contents:
        raise ValueError("contents must be a non-empty list")
    if len(contents) > _MANUAL_CONFIG_FILE_MAX_CONTENTS:
        raise ValueError(f"contents exceeds max {_MANUAL_CONFIG_FILE_MAX_CONTENTS}")
    normalized_contents = []
    for content in contents:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("contents items must be non-empty strings")
        normalized_contents.append(content)

    instance = InstanceManage.query_entity_by_uuid(instance_uuid) or {}
    graph_id = instance.get("_id")
    instance_org_ids = set(_normalize_allowed_org_ids_for_scope(instance.get("organization")))
    if not instance or graph_id in (None, "") or instance.get("model_id") != model_id:
        raise ValueError("instance is outside authorization scope")
    if not allowed_org_ids.intersection(instance_org_ids):
        raise ValueError("instance is outside authorization scope")
    if _manual_config_file_already_exists(instance_uuid, file_path):
        return {"status": "skipped", "created": 0}

    created = 0
    for index, content in enumerate(normalized_contents):
        if index:
            time.sleep(_MANUAL_CONFIG_FILE_VERSION_GAP_SECONDS)
        result = ConfigFileService.create_manual_version(
            instance_id=str(graph_id),
            model_id=model_id,
            file_path=file_path,
            content=content,
            instance_uuid=instance_uuid,
        )
        if not result.get("unchanged"):
            created += 1
    return {"status": "created", "created": created}


@nats_client.register
@_accept_legacy_rpc_kwargs
def create_manual_config_files(params):
    """批量手动写入配置文件版本（Demo / 运维灌数）。

    params={
        "protocol_version": "2",
        "allowed_org_ids": [1],
        "items": [
            {
                "instance_uuid": "...",
                "model_id": "host",
                "file_path": "/etc/ssh/sshd_config",
                "contents": ["v1", "v2", "v3"],
            }
        ],
    }

    同一 instance+file_path 已有成功版本时整文件跳过，避免重灌追加版本。
    """
    params = params or {}
    _require_uuid_protocol(params)
    _reject_legacy_numeric_locators(params, "instance_id", "inst_id", "_id", "inst_ids")
    allowed_org_ids = set(_resolve_allowed_org_ids(params))
    if not allowed_org_ids:
        raise ValueError("authorization scope is required for CMDB NATS writes")
    items = params.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items is required")
    if len(items) > _MANUAL_CONFIG_FILE_MAX_ITEMS:
        raise ValueError(f"items exceeds max {_MANUAL_CONFIG_FILE_MAX_ITEMS}")

    created = 0
    versions = 0
    skipped = 0
    failed = 0
    errors = []
    for index, item in enumerate(items):
        try:
            result = _create_one_manual_config_file(item, allowed_org_ids)
        except ValueError as exc:
            failed += 1
            errors.append({"index": index, "error": str(exc)[:300]})
            continue
        except Exception as exc:
            logger.exception("create_manual_config_files item failed index=%s", index)
            failed += 1
            errors.append({"index": index, "error": str(exc)[:300]})
            continue
        if result.get("status") == "skipped":
            skipped += 1
        else:
            created += 1
            versions += int(result.get("created") or 0)
    return {
        "result": True,
        "created": created,
        "versions": versions,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:20],
    }


@nats_client.register
def receive_scan_credential_result(data: dict):
    """接收扫描一枪的凭据结果；不属于 Stargazer 采集状态投影。"""
    from apps.cmdb.services.scan_credential_result_service import ScanCredentialResultService

    payload = data or {}
    if not isinstance(payload, dict):
        logger.warning(
            "Received invalid scan credential result event, type=%s",
            type(payload).__name__,
        )
        return ScanCredentialResultService.process_result(payload, parse_datetime=_parse_nats_datetime)

    result = ScanCredentialResultService.process_batch(payload, parse_datetime=_parse_nats_datetime)
    logger.info(
        "Processed scan credential result, result=%s task_id=%s host=%s",
        result.get("result", False),
        payload.get("collect_task_id") or result.get("task_id") or "",
        payload.get("host") or "",
    )
    return result


@nats_client.register
def sync_display_fields(organizations=None, users=None):
    """
    同步组织/用户的 _display 字段

    Args:
        organizations: 组织变更数据列表 [{"id": 1, "name": "新组织名"}]，可选
        users: 用户变更数据列表 [{"id": 1, "username": "admin", "display_name": "新显示名"}]，可选

    Returns:
        任务提交结果 {"task_id": "uuid", "status": "submitted"}
    """
    from apps.cmdb.display_field.sync import sync_display_fields_for_system_mgmt

    result = sync_display_fields_for_system_mgmt(
        organizations=organizations or [],
        users=users or [],
    )

    return result


@nats_client.register
def get_cmdb_statistics(user_info=None, **kwargs):
    """
    获取 CMDB 统计数据（模型总数、实例总数、分类总数）

    Args:
        user_info: { team: int, user: str } - 由 operation_analysis 自动注入

    Returns:
        {
            "result": True,
            "data": {
                "classification_count": 5,
                "model_count": 15,
                "instance_count": 1234,
                "model_with_instance_count": 12,
                "empty_model_count": 3,
                "model_coverage_rate": 80.0
            },
            "message": ""
        }
    """
    model_permissions_map = _build_nats_model_permission_map(user_info)
    instance_permissions_map = _build_nats_permission_map(user_info)
    if model_permissions_map is None or instance_permissions_map is None:
        return {
            "result": True,
            "data": {
                "classification_count": 0,
                "model_count": 0,
                "instance_count": 0,
                "model_with_instance_count": 0,
                "empty_model_count": 0,
                "model_coverage_rate": 0,
            },
            "message": "",
        }

    classifications = ClassificationManage.search_model_classification()
    visible_models = ModelManage.search_model(permissions_map=model_permissions_map)
    model_counts = InstanceManage.model_inst_count(permissions_map=instance_permissions_map)
    instance_count = sum(model_counts.values())
    model_count = len(visible_models)
    classification_count = len(classifications)
    model_with_instance_count = sum(1 for model in visible_models if model_counts.get(model.get("model_id"), 0) > 0)
    empty_model_count = max(model_count - model_with_instance_count, 0)
    model_coverage_rate = round((model_with_instance_count / model_count) * 100, 1) if model_count else 0

    return {
        "result": True,
        "data": {
            "model_count": model_count,
            "instance_count": instance_count,
            "classification_count": classification_count,
            "model_with_instance_count": model_with_instance_count,
            "empty_model_count": empty_model_count,
            "model_coverage_rate": model_coverage_rate,
        },
        "message": "",
    }


def _room3d_error(message, code=400):
    return {"result": False, "data": {}, "message": message, "code": code}


def _parse_room3d_server_room_locator(value):
    if value in (None, ""):
        return None
    if str(value).isdigit():
        return "id", int(value)
    try:
        inst_uuid = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
    if inst_uuid.version != 4:
        return None
    return "uuid", str(inst_uuid)


def _format_room3d_location_label(row, col):
    return format_rack_location_label(row, col)


def _parse_room3d_rack_location(value):
    return parse_rack_location(value)


def _room3d_rack_identity(rack):
    rack_id = rack.get("inst_uuid")
    return str(rack_id or ""), rack.get("inst_name") or str(rack_id or "")


def _resolve_room3d_locale(user_info=None):
    user_info = user_info or {}
    user = user_info.get("user")
    locale = user_info.get("locale") or user_info.get("language") or getattr(user, "locale", None) or user_info.get("LANGUAGE_CODE") or "zh-CN"
    return str(locale).lower()


def _format_room3d_invalid_location_notice(invalid_racks, locale="zh-CN"):
    if not invalid_racks:
        return ""

    is_english = str(locale).lower().startswith("en")
    rack_descriptions = []
    for rack, location in invalid_racks:
        _, rack_name = _room3d_rack_identity(rack)
        if is_english:
            location_label = "location is empty" if location in (None, "") else f"location is {location}"
            rack_descriptions.append(f"{rack_name} ({location_label})")
        else:
            location_label = "位置为空" if location in (None, "") else f"位置为 {location}"
            rack_descriptions.append(f"{rack_name}（{location_label}）")

    if is_english:
        return f"{len(invalid_racks)} racks have invalid locations and are not shown: " f"{', '.join(rack_descriptions)}. Use the A3 / A03 format."

    return f"{len(invalid_racks)} 个机柜位置格式错误未展示：{'、'.join(rack_descriptions)}。请按 A3 / A03 格式填写。"


def _format_room3d_device(device):
    locator = _parse_room3d_server_room_locator(device.get("inst_uuid"))
    if not locator or locator[0] != "uuid":
        return None
    return {
        "device_id": locator[1],
        "device_name": device.get("inst_name") or "",
        "model_id": device.get("model_id"),
        "rack_u_start": device.get("rack_u_start"),
        "u_size": device.get("u_size"),
        "status": device.get("status"),
    }


def _get_room3d_rack_device_summary(rack_id, permission_map=None, user=None):
    rack_layout = rack_room.get_rack_layout(rack_id, permission_map=permission_map, user=user)
    placed_devices = rack_layout.get("placed") or []
    unplaced_devices = rack_layout.get("unplaced") or []
    formatted_placed = [formatted for device in placed_devices if (formatted := _format_room3d_device(device)) is not None]
    formatted_unplaced = [formatted for device in unplaced_devices if (formatted := _format_room3d_device(device)) is not None]
    return {
        "devices": formatted_placed,
        "device_count": len(formatted_placed) + len(formatted_unplaced),
        "unplaced_device_count": len(formatted_unplaced),
    }


def _empty_room3d_device_summary():
    return {"devices": [], "device_count": 0, "unplaced_device_count": 0}


def _room3d_rack_id_as_int(rack_id):
    try:
        return int(rack_id)
    except (TypeError, ValueError):
        return None


def _get_room3d_rack_type_name_map():
    attrs = ExcludeFieldsCache.get_model_attrs("rack") or []
    for attr in attrs:
        if attr.get("attr_id") != "datacenter_type" or attr.get("attr_type") != FIELD_TYPE_ENUM:
            continue
        return {str(option.get("id")): option.get("name") for option in attr.get("option", []) if option and option.get("name")}
    return {}


@nats_client.register
def get_room3d_layout(server_room_id=None, user_info=None, **kwargs):
    """
    获取运营分析 room3D 图表使用的 CMDB 机房机柜布局数据。

    一个 room3D 组件只展示一个 server_room；机柜列表复用 rack_room.get_room_layout，
    因此机柜权限、U 位统计、位置解析和位置冲突口径与 CMDB 机房视图保持一致。
    """
    room_locator = _parse_room3d_server_room_locator(server_room_id)
    if room_locator is None:
        return _room3d_error("server_room_id 参数必填且必须为 UUIDv4")

    locator_type, locator = room_locator
    room = InstanceManage.query_entity_by_uuid(locator) if locator_type == "uuid" else InstanceManage.query_entity_by_id(locator)
    if not room:
        return _room3d_error("机房实例不存在", code=404)
    if room.get("model_id") != "server_room":
        return _room3d_error("server_room_id 必须指向 server_room 实例")
    room_uuid_locator = _parse_room3d_server_room_locator(room.get("inst_uuid"))
    if not room_uuid_locator or room_uuid_locator[0] != "uuid":
        return _room3d_error("机房实例缺少合法 inst_uuid", code=409)

    permission_map = _build_nats_permission_map(user_info)
    if permission_map is None:
        return _room3d_error("无权限查看当前机房", code=403)

    user_context = user_info or {}
    user = _normalize_permission_user(user_context.get("user"), domain=user_context.get("domain"))
    if not InstanceManage._has_topology_view_permission(room, permission_map, user=user):
        return _room3d_error("无权限查看当前机房", code=403)

    room_id = int(room["_id"])
    layout = rack_room.get_room_layout(room_id, permission_map=permission_map, user=user)
    visible_layout_racks = (layout.get("racks") or []) + (layout.get("unplaced") or [])
    candidate_racks = []
    invalid_location_racks = []
    for rack in visible_layout_racks:
        rack_location = rack.get("location")
        parsed_location = _parse_room3d_rack_location(rack_location)
        if not parsed_location:
            invalid_location_racks.append((rack, rack_location))
            continue

        row, col = parsed_location
        rack_id, rack_name = _room3d_rack_identity(rack)
        candidate = {
            "rack": rack,
            "row": row,
            "col": col,
            "location": _format_room3d_location_label(row, col),
            "rack_id": rack_id,
            "rack_name": rack_name,
        }
        candidate_racks.append(candidate)

    rack_uuids = [item["rack_id"] for item in candidate_racks if item["rack_id"]]
    if hasattr(rack_room, "get_room3d_rack_device_summaries"):
        device_summaries = rack_room.get_room3d_rack_device_summaries(
            rack_uuids,
            permission_map=permission_map,
            user=user,
        )
    else:
        device_summaries = {}
        rack_instances = InstanceManage.query_entity_by_uuids(rack_uuids) if rack_uuids else []
        rack_id_by_uuid = {item.get("inst_uuid"): item.get("_id") for item in rack_instances}
        for rack_uuid in rack_uuids:
            rack_id = rack_id_by_uuid.get(rack_uuid)
            if rack_id is not None:
                device_summaries[rack_uuid] = _get_room3d_rack_device_summary(rack_id, permission_map=permission_map, user=user)

    rack_type_name_map = _get_room3d_rack_type_name_map()
    racks = []
    for item in candidate_racks:
        rack = item["rack"]
        device_summary = device_summaries.get(item["rack_id"], _empty_room3d_device_summary())
        rack_type = rack.get("datacenter_type")
        rack_type_name = rack_type_name_map.get(str(rack_type)) if rack_type not in (None, "") else None
        rack_payload = {
            "rack_id": item["rack_id"],
            "rack_name": item["rack_name"],
            "row": item["row"],
            "col": item["col"],
            "location": item["location"],
            "rack_type": rack_type,
            "u_count": rack.get("u_count"),
            "used_u": rack.get("used_u"),
            "free_u": rack.get("free_u"),
            "device_count": device_summary["device_count"],
            "unplaced_device_count": device_summary["unplaced_device_count"],
            "devices": device_summary["devices"],
        }
        if rack_type_name:
            rack_payload["rack_type_name"] = rack_type_name
        racks.append(rack_payload)

    data = {
        "room": {"id": room_uuid_locator[1], "name": room.get("inst_name") or ""},
        "racks": racks,
    }
    notice = _format_room3d_invalid_location_notice(
        invalid_location_racks,
        _resolve_room3d_locale(user_info),
    )
    if notice:
        data["notice"] = notice

    return {
        "result": True,
        "data": data,
        "message": "",
    }


def _get_trunc_func_and_format(group_by):
    mapping = {
        "minute": (TruncMinute, "%Y-%m-%d %H:%M"),
        "hour": (TruncHour, "%Y-%m-%d %H:00"),
        "day": (TruncDate, "%Y-%m-%d"),
        "month": (TruncMonth, "%Y-%m"),
    }
    return mapping.get(group_by, (TruncDate, "%Y-%m-%d"))


def _resolve_target_timezone(timezone_name=None):
    if isinstance(timezone_name, str) and timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            logger.warning("Invalid timezone provided for get_change_trend: %s", timezone_name)
    return timezone.get_current_timezone()


def _parse_client_datetime(value, target_tz):
    return parse_rfc3339_utc(value).astimezone(target_tz)


def _parse_nats_datetime(value):
    if value in (None, ""):
        return None

    text = str(value).strip()
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")

    current_tz = timezone.get_current_timezone()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, current_tz)
    return parsed.astimezone(current_tz)


def _format_period_value(value, target_tz):
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        value = datetime.datetime.combine(value, datetime.time.min, tzinfo=target_tz)
    elif timezone.is_naive(value):
        value = timezone.make_aware(value, target_tz)
    else:
        value = value.astimezone(target_tz)

    return value.isoformat()


def _generate_time_periods(start_dt, end_dt, group_by, target_tz):
    periods = []
    if group_by == "minute":
        current = start_dt.replace(second=0, microsecond=0)
        while current < end_dt:
            periods.append(_format_period_value(current, target_tz))
            current += datetime.timedelta(minutes=1)
    elif group_by == "hour":
        current = start_dt.replace(minute=0, second=0, microsecond=0)
        while current < end_dt:
            periods.append(_format_period_value(current, target_tz))
            current += datetime.timedelta(hours=1)
    elif group_by == "day":
        current = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        while current < end_dt:
            periods.append(_format_period_value(current, target_tz))
            current += datetime.timedelta(days=1)
    elif group_by == "month":
        current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current < end_dt:
            periods.append(_format_period_value(current, target_tz))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    return periods


@nats_client.register
def get_room_list(user_info=None, **kwargs):
    """获取运营分析参数动态选项源用的机房列表。

    返回 CMDB 原始 server_room 字段（_id, inst_name, model_id, organization, ...），
    不做 _id→id / inst_name→name 等重命名。复用 ``InstanceManage.instance_list``
    的现成权限过滤自动按当前用户可见范围过滤。
    """
    permission_map = _build_nats_permission_map(user_info) or {}
    # 新数据源以 inst_uuid 作为选项值；暂时保留 _id，兼容尚未执行
    # init_source_api_data --force-update 的存量数据源配置。
    items = [item for item in rack_room.list_server_rooms(permission_map=permission_map, user_info=user_info) if item.get("inst_uuid")]
    return {"items": items}


@nats_client.register
def get_monitor_ids_by_inst_uuids(inst_uuids=None, user_info=None, **kwargs):
    from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
    from apps.cmdb.services.instance_identity import normalize_inst_uuid

    raw = inst_uuids if inst_uuids is not None else kwargs.get("inst_uuids")
    if raw in (None, ""):
        raw = []
    if not isinstance(raw, list):
        return {"result": False, "data": {"items": []}, "message": "inst_uuids 必须是列表"}

    unique = []
    seen = set()
    for value in raw:
        if value in (None, ""):
            continue
        normalized = normalize_inst_uuid(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)

    if len(unique) > NETWORK_STATUS_TOPOLOGY_MAX_NODES:
        return {
            "result": False,
            "data": {"items": []},
            "message": f"inst_uuids 不能超过 {NETWORK_STATUS_TOPOLOGY_MAX_NODES}",
        }

    if not unique:
        return {"result": True, "data": {"items": []}, "message": ""}

    permission_map = _build_nats_permission_map(user_info)
    if permission_map is None:
        return {"result": True, "data": {"items": []}, "message": ""}
    user = _normalize_permission_user((user_info or {}).get("user"), domain=(user_info or {}).get("domain"))
    entities = InstanceManage.query_entity_by_uuids(unique)
    items = []
    for entity in entities:
        if not InstanceManage._has_topology_view_permission(entity, permission_map, user=user):
            continue
        monitor_id = entity.get("monitor_id")
        items.append(
            {
                "inst_uuid": entity.get("inst_uuid"),
                "model_id": entity.get("model_id"),
                "monitor_id": "" if monitor_id in (None, "") else str(monitor_id),
            }
        )
    return {"result": True, "data": {"items": items}, "message": ""}


@nats_client.register
def get_change_trend(time=None, model_id=None, user_info=None, **kwargs):
    """
    获取 CMDB 变更趋势数据。

    聚合粒度按时间窗自动推导：
    ≤6h minute / ≤7d hour / ≤2y day / 更长 month。
    """
    kwargs.pop("group_by", None)
    if not time or len(time) != 2:
        return {"result": False, "data": {}, "message": "time parameter is required as [start_time, end_time]"}

    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))
    start_time, end_time = time
    try:
        aware_start = _parse_client_datetime(start_time, target_tz)
        aware_end = _parse_client_datetime(end_time, target_tz)
    except ValueError:
        return {
            "result": False,
            "data": {},
            "message": "time values must be RFC3339 timestamps with an explicit timezone",
        }
    local_start = aware_start.astimezone(target_tz)
    local_end = aware_end.astimezone(target_tz)

    if aware_start >= aware_end:
        return {"result": False, "data": {}, "message": "start_time must be earlier than end_time"}

    group_by = resolve_trend_group_by_from_range(aware_start, aware_end)
    span_seconds = (aware_end - aware_start).total_seconds()
    max_span = _CHANGE_TREND_MAX_SPAN_SECONDS[group_by]
    if span_seconds > max_span:
        logger.warning(
            "get_change_trend range %.0f seconds exceeds %s limit %d seconds",
            span_seconds,
            group_by,
            max_span,
        )
        return {
            "result": False,
            "data": {},
            "message": (f"Time range exceeds the maximum limit for {group_by} grouping " f"({max_span} seconds). Use a shorter range."),
        }

    trunc_func, _ = _get_trunc_func_and_format(group_by)
    all_periods = _generate_time_periods(local_start, local_end, group_by, target_tz)

    base_queryset = ChangeRecord.objects.filter(created_at__gte=aware_start, created_at__lt=aware_end)
    if model_id:
        base_queryset = base_queryset.filter(model_id=model_id)

    type_mapping = {
        "create": CREATE_INST,
        "update": UPDATE_INST,
        "delete": DELETE_INST,
    }
    operate_type_display = dict(OPERATE_TYPE_CHOICES)
    type_display = {
        "create": operate_type_display.get(CREATE_INST, "创建"),
        "update": operate_type_display.get(UPDATE_INST, "修改"),
        "delete": operate_type_display.get(DELETE_INST, "删除"),
    }

    result_data = {}
    for key, change_type in type_mapping.items():
        queryset = (
            base_queryset.filter(type=change_type)
            .annotate(period=trunc_func("created_at", tzinfo=target_tz))
            .values("period")
            .annotate(count=Count("id"))
            .order_by("period")
        )

        period_counts = {}
        for item in queryset:
            if item["period"]:
                period_key = _format_period_value(item["period"], target_tz)
                period_counts[period_key] = item["count"]

        display_key = type_display.get(key, key)
        result_data[display_key] = [[p, period_counts.get(p, 0)] for p in all_periods]

    return {"result": True, "data": result_data, "message": ""}


@nats_client.register
def get_instance_group_by(model_id=None, field=None, user_info=None, **kwargs):
    """
    获取实例分组统计（饼状图用）

    Args:
        model_id: str - 模型 ID，如 "host"
        field: str - 分组字段，如 "os_type"
        user_info: { team: int, user: str }

    Returns:
        {
            "result": True,
            "data": [
                {"name": "Linux", "value": 100},
                {"name": "Windows", "value": 50}
            ],
            "message": ""
        }
    """
    if not model_id:
        return {"result": False, "data": [], "message": "model_id is required"}
    if not field:
        return {"result": False, "data": [], "message": "field is required"}

    params = [{"field": "model_id", "type": "str=", "value": model_id}]
    permission_map = _build_nats_permission_map(user_info, model_id=model_id)
    if permission_map is None:
        return {"result": True, "data": [], "message": ""}

    attrs = ModelManage.search_model_attr(model_id)
    field_attr = next((attr for attr in attrs if attr.get("attr_id") == field), None)
    group_by_attr = field
    if field_attr:
        attr_type = field_attr.get("attr_type")
        enum_select_mode = field_attr.get("enum_select_mode")
        if attr_type in DISPLAY_FIELD_TYPES and not (attr_type == FIELD_TYPE_ENUM and enum_select_mode != ENUM_SELECT_MODE_MULTIPLE):
            group_by_attr = f"{field}{DISPLAY_SUFFIX}"

    group_counts = InstanceManage.group_inst_count(
        group_by_attr=group_by_attr,
        permissions_map=permission_map,
        params=params,
    )

    enum_map = {}
    if field_attr and field_attr.get("attr_type") == FIELD_TYPE_ENUM and group_by_attr == field:
        options = field_attr.get("option", [])
        enum_map = {str(opt.get("id")): opt.get("name") for opt in options if opt}

    result_data = []
    for key, count in group_counts.items():
        if key in (None, ""):
            display_name = "unknown"
        else:
            normalized_key = str(key)
            display_name = enum_map.get(normalized_key, normalized_key) if enum_map else normalized_key
        result_data.append({"name": display_name, "value": count})

    result_data.sort(key=lambda x: x["value"], reverse=True)

    return {"result": True, "data": result_data, "message": ""}


@nats_client.register
def get_model_classification_options(user_info=None, **kwargs):
    """获取当前用户有权查看的可见模型分类，供数据源参数选项使用。"""
    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    if model_permissions is None:
        return {"items": []}

    models = ModelManage.search_model(
        language=language,
        permissions_map=model_permissions,
    )
    allowed_classification_ids = {model.get("classification_id") for model in models if model.get("classification_id")}
    classifications = ClassificationManage.search_model_classification(language=language)
    return {
        "items": [
            {
                "classification_id": item["classification_id"],
                "classification_name": item["classification_name"],
            }
            for item in classifications
            if item.get("classification_id") in allowed_classification_ids
        ]
    }


@nats_client.register
def get_classification_model_instance_counts(
    classification_id=None,
    user_info=None,
    **kwargs,
):
    """按模型分类返回当前用户可见且实例数大于零的模型统计。"""
    classification_id = str(classification_id or "").strip()
    if not classification_id:
        return {"items": []}

    language = _resolve_nats_cmdb_language(user_info)
    visible_classification_ids = {item.get("classification_id") for item in ClassificationManage.search_model_classification(language=language)}
    if classification_id not in visible_classification_ids:
        return {"items": []}

    model_permissions = _build_nats_model_permission_map(user_info)
    instance_permissions = _build_nats_permission_map(user_info)
    if model_permissions is None or instance_permissions is None:
        return {"items": []}

    models = ModelManage.search_model(
        language=language,
        permissions_map=model_permissions,
        classification_ids=[classification_id],
    )
    counts = InstanceManage.model_inst_count(permissions_map=instance_permissions)
    items = [
        {
            "label": model.get("model_name", ""),
            "value": counts.get(model.get("model_id"), 0),
        }
        for model in models
    ]
    items = [item for item in items if item["value"] > 0]
    items.sort(key=lambda item: (-item["value"], item["label"]))
    return {"items": items}


@nats_client.register
def get_region_options(user_info=None, **kwargs):
    """Return region tag candidates visible to the current user."""
    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    if model_permissions is None:
        return {"items": []}
    models = ModelManage.search_model(language=language, permissions_map=model_permissions)
    classifications = ClassificationManage.search_model_classification(language=language)
    visible_ids = {item.get("classification_id") for item in classifications if item.get("classification_id")}
    return {"items": extract_region_options(models, visible_ids)}


@nats_client.register
def get_region_resource_overview(region=None, user_info=None, **kwargs):
    """Return classification instance totals for one region value."""
    region = str(region or "").strip()
    if not region:
        return {"items": []}
    language = _resolve_nats_cmdb_language(user_info)
    model_permissions = _build_nats_model_permission_map(user_info)
    instance_permissions = _build_nats_permission_map(user_info)
    if model_permissions is None or instance_permissions is None:
        return {"items": []}
    models = ModelManage.search_model(language=language, permissions_map=model_permissions)
    classifications = ClassificationManage.search_model_classification(language=language)
    visible_ids = {item.get("classification_id") for item in classifications if item.get("classification_id")}
    allowed_regions = extract_region_options(models, visible_ids)
    if region not in {item["value"] for item in allowed_regions}:
        return {"items": []}
    counts = InstanceManage.group_inst_count(
        group_by_attr="model_id",
        permissions_map=instance_permissions,
        params=[{"field": "tag", "type": "list[]", "value": [f"region:{region}"]}],
    )
    return {"items": build_region_resource_items(models, classifications, counts)}


@nats_client.register
def get_model_inst_statistics(user_info=None, **kwargs):
    """
    获取模型实例统计（表格用）

    Args:
        user_info: { team: int, user: str }

    Returns:
        {
            "result": True,
            "data": [
                {"classification": "主机管理", "model": "主机", "model_id": "host", "count": 100}
            ],
            "message": ""
        }
    """
    language = _resolve_nats_cmdb_language(user_info)
    classifications = ClassificationManage.search_model_classification(language=language)
    classification_map = {c["classification_id"]: c["classification_name"] for c in classifications}

    model_permissions_map = _build_nats_model_permission_map(user_info)
    instance_permissions_map = _build_nats_permission_map(user_info)
    if model_permissions_map is None or instance_permissions_map is None:
        return {"result": True, "data": [], "message": ""}

    models = ModelManage.search_model(language=language, permissions_map=model_permissions_map)
    model_counts = InstanceManage.model_inst_count(permissions_map=instance_permissions_map)

    result_data = []
    for model in models:
        model_id = model.get("model_id")
        model_name = model.get("model_name")
        classification_id = model.get("classification_id")
        classification_name = classification_map.get(classification_id, classification_id)

        count = model_counts.get(model_id, 0)

        result_data.append(
            {
                "classification": classification_name,
                "model": model_name,
                "model_id": model_id,
                "count": count,
            }
        )

    result_data.sort(key=lambda x: (-x["count"], x["classification"], x["model"]))

    return {"result": True, "data": result_data, "message": ""}


@nats_client.register
def get_cmdb_model_instance_top(limit=5, classification_id=None, user_info=None, **kwargs):
    """
    获取模型实例数 TOP N（用于 TopN / 柱状图）
    """
    try:
        limit = int(limit or 5)
    except (TypeError, ValueError):
        limit = 5
    if limit <= 0:
        limit = 5

    language = _resolve_nats_cmdb_language(user_info)
    classifications = ClassificationManage.search_model_classification(language=language)
    classification_map = {c["classification_id"]: c["classification_name"] for c in classifications}

    model_permissions_map = _build_nats_model_permission_map(user_info)
    instance_permissions_map = _build_nats_permission_map(user_info)
    if model_permissions_map is None or instance_permissions_map is None:
        return {"result": True, "data": [], "message": ""}

    models = ModelManage.search_model(language=language, permissions_map=model_permissions_map)
    if classification_id:
        models = [model for model in models if model.get("classification_id") == classification_id]

    model_counts = InstanceManage.model_inst_count(permissions_map=instance_permissions_map)

    result_data = []
    for model in models:
        model_id = model.get("model_id")
        count = model_counts.get(model_id, 0)
        result_data.append(
            {
                "model": model.get("model_name"),
                "model_id": model_id,
                "classification": classification_map.get(model.get("classification_id"), model.get("classification_id")),
                "classification_id": model.get("classification_id"),
                "count": count,
            }
        )

    result_data.sort(key=lambda x: (-x["count"], x["classification"], x["model"]))

    return {"result": True, "data": result_data[:limit], "message": ""}


@nats_client.register
def get_cmdb_collect_statistics(user_info=None, **kwargs):
    """
    获取 CMDB 采集健康概览
    """
    task_queryset = _get_collect_task_queryset(user_info)
    status_counts = dict(task_queryset.values("exec_status").annotate(count=Count("id")).values_list("exec_status", "count"))

    task_count = task_queryset.count()
    interval_task_count = task_queryset.filter(is_interval=True).count()

    return {
        "result": True,
        "data": {
            "task_count": task_count,
            "interval_task_count": interval_task_count,
            "success_count": status_counts.get(CollectRunStatusType.SUCCESS, 0),
            "error_count": status_counts.get(CollectRunStatusType.ERROR, 0),
            "running_count": status_counts.get(CollectRunStatusType.RUNNING, 0),
            "timeout_count": status_counts.get(CollectRunStatusType.TIME_OUT, 0),
            "never_run_count": status_counts.get(CollectRunStatusType.NOT_START, 0),
            "partial_success_count": status_counts.get(CollectRunStatusType.PARTIAL_SUCCESS, 0),
        },
        "message": "",
    }


@nats_client.register
def model_inst_count(*args, **kwargs):
    """
    获取模型实例数量
    """
    result = InstanceManage.model_inst_count(permissions_map={}, creator="")
    return {"result": True, "message": "", "data": result}


# === 云资源成本分析 Report Responder ===
# 前端数据源通过 rest_api "cmdb/get_cloud_resource_cost_*" 路由到这里。
# 入参约定:user_info(由 GetNatsData 注入) + 过滤项 kwargs。
# 过滤项 department 映射到 bill 维度 user_department;billing_period 为 [start, end] 字符串列表。
#
# 注意:本段使用 stdlib 的 `date` / `_datetime` / `_timezone`(与模块顶部 Django
# `timezone` 工具区分),以及 `Optional`(typing)。调用 apps.cmdb.services.cloud_cost
# 下的业务聚合服务,数据走 CMDB 动态模型 resource_bill / transaction_log。

# Python date.max = 9999-12-31。超过该值 fromisoformat 会抛 OverflowError,在此统一收口。
_MAX_DATE = date(9999, 12, 31)


def _to_date(value) -> Optional[date]:
    """把单个原始值解析为 UTC 日历日。

    支持的输入(均为字符串):
      - ``"YYYY-MM-DD"``  纯 date
      - ``"YYYY-MM-DDTHH:mm:ss[.ffffff]"``  naive ISO datetime
      - ``"YYYY-MM-DDTHH:mm:ss[.ffffff]Z"``  UTC ISO datetime
      - ``"YYYY-MM-DDTHH:mm:ss[.ffffff]±HH:MM"``  带偏移 ISO datetime

    时区策略:**naive 输入视为 UTC;带时区输入先 astimezone(UTC) 再取 .date()**。
    这一约定对齐 ``transaction_log.billing_date`` 的存储层语义(纯 ``YYYY-MM-DD``,无时区)。

    非字符串、数字时间戳、无法解析的字符串、超过 ``date.max`` 的日期均返回 ``None``。
    """
    if not isinstance(value, str) or not value:
        return None

    # 1. 纯 date 路径:date.fromisoformat 拒绝任何时间部分。
    try:
        d = date.fromisoformat(value)
        return d if d <= _MAX_DATE else None
    except ValueError:
        pass

    # 2. ISO datetime 路径。把 'Z' 标准化为 '+00:00'(datetime.fromisoformat 在 3.11+ 才接受 Z,
    # 显式替换兼容 3.10 及以下)。
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = _datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if dt.tzinfo is None:
        # naive 视为 UTC,与纯 date 路径保持同一日历语义。
        dt = dt.replace(tzinfo=_timezone.utc)
    else:
        dt = dt.astimezone(_timezone.utc)

    d = dt.date()
    return d if d <= _MAX_DATE else None


def _parse_billing_period(raw) -> Optional[tuple]:
    """[start, end] → (date, date)(UTC 日历日)。

    - 接受纯 date / naive ISO datetime / Z 后缀 / 带偏移量 4 种输入形态。
    - ``start > end`` 时自动 swap,允许前端 RangePicker 反向选区。
    - 数组长度不对、元素不是字符串、字符串无法解析时返回 ``None`` 并 ``logger.warning``。
    - 数字时间戳(秒级/毫秒级)**不支持** → ``None``(避免歧义)。

    时区策略:naive 当 UTC,带时区转 UTC → 与 ``transaction_log.billing_date``
    存储层语义对齐。详见 ``_to_date`` docstring。
    """
    if not raw or not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None

    start = _to_date(raw[0])
    end = _to_date(raw[1])
    if start is None or end is None:
        logger.warning(
            "billing_period 解析失败 raw=%r;要求每端为 'YYYY-MM-DD' 或 ISO datetime(naive 当 UTC)",
            raw,
        )
        return None

    if start > end:
        start, end = end, start
    return start, end


def _jsonable(value):
    """Decimal → str,便于 JSON 序列化。"""
    return str(value) if hasattr(value, "quantize") else value


@nats_client.register
def get_cloud_resource_cost_summary(user_info=None, **kwargs):
    """云资源成本 KPI 汇总卡。kwargs: department / applying_user / inst_type / billing_period。"""
    from apps.cmdb.services.cloud_cost.service import CloudCostService

    data = CloudCostService.summary(
        user_info or {},
        inst_type=kwargs.get("inst_type"),
        user_department=kwargs.get("department"),
        applying_user=kwargs.get("applying_user"),
        billing_period=_parse_billing_period(kwargs.get("billing_period")),
    )
    data = {k: _jsonable(v) for k, v in data.items()}
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_cloud_resource_cost_distribution(user_info=None, **kwargs):
    """云资源费用分布。kwargs: department / applying_user / inst_type / billing_period / group_by。"""
    from apps.cmdb.services.cloud_cost.service import CloudCostService

    data = CloudCostService.distribution(
        user_info or {},
        inst_type=kwargs.get("inst_type"),
        user_department=kwargs.get("department"),
        applying_user=kwargs.get("applying_user"),
        billing_period=_parse_billing_period(kwargs.get("billing_period")),
        group_by=kwargs.get("group_by", "instance_type"),
    )
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def get_cloud_resource_cost_bill_detail(user_info=None, **kwargs):
    """云资源账单明细。kwargs: department / applying_user / inst_type / billing_period / page / page_size / sort_by / order。"""
    from apps.cmdb.services.cloud_cost.service import CloudCostService

    data = CloudCostService.instance_list(
        user_info or {},
        inst_type=kwargs.get("inst_type"),
        user_department=kwargs.get("department"),
        applying_user=kwargs.get("applying_user"),
        billing_period=_parse_billing_period(kwargs.get("billing_period")),
        page=int(kwargs.get("page", 1)),
        page_size=int(kwargs.get("page_size", 20)),
        sort_by=kwargs.get("sort_by", "total_cost_incurred"),
        order=kwargs.get("order", "desc"),
    )
    data["items"] = [{k: _jsonable(v) for k, v in item.items()} for item in data["items"]]
    return {"result": True, "data": data, "message": ""}
