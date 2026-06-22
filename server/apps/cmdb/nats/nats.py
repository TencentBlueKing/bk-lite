import datetime
from functools import reduce
from operator import or_
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncHour, TruncMonth, TruncWeek
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
from apps.cmdb.services.collect_credential_result_service import CollectCredentialResultService
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.utils.base import get_default_group_id
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.logger import cmdb_logger as logger
from apps.core.utils.permission_utils import get_permission_rules
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.models.role import Role
from apps.system_mgmt.utils.group_utils import GroupUtils


def _normalize_to_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


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

    return CollectModels.objects.filter(reduce(or_, team_queries)).distinct()


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
def get_cmdb_module_data(module, child_module, page, page_size, group_id):
    """
    获取cmdb模块实例数据
    """
    page = int(page)
    page_size = int(page_size)
    if module == PERMISSION_TASK:
        # 计算分页
        start = (page - 1) * page_size
        end = page * page_size
        instances = CollectModels.objects.filter(task_type=child_module).values("id", "name", "model_id")[start:end]
        count = instances.count()
        queryset = [{"id": str(i["id"]), "name": f"{i['model_id']}_{i['name']}"} for i in instances]
    elif module == PERMISSION_INSTANCES:
        instances, count = InstanceManage.instance_list(
            model_id=child_module,  # 使用实际模型ID
            params=[{"field": "organization", "type": "list[]", "value": [int(group_id)]}],  # 空查询条件（或按需添加）
            page=page,
            page_size=page_size,
            order="",
            creator="",
            permission_map={},
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
def search_instances(params):
    """
    根据参数查询实例
    """
    model_id = params["model_id"]
    inst_name = params.get("inst_name", None)
    _id = params.get("_id", None)

    instances, _ = InstanceManage.search_inst(model_id=model_id, inst_name=inst_name, _id=_id)
    result = instances[0] if instances else {}
    return result


@nats_client.register
def search_instances_batch(params):
    """批量查询实例。params={"model_id":..,"ids":[..],"inst_names":[..]} -> {key: instance}"""
    return InstanceManage.search_inst_batch(
        model_id=params["model_id"],
        ids=params.get("ids"),
        inst_names=params.get("inst_names"),
    )


def _resolve_allowed_org_ids(params, data):
    """解析实例写操作的 organization 范围上下文。

    HTTP 路径下该范围由 view 从请求 cookie（current_team/include_children）+ 用户组织树推导。
    NATS 为可信的机器对机器调用、无用户范围概念：
    - 调用方显式传 allowed_org_ids 时按其限制；
    - 否则默认放行 payload 自带的 organization（即不做范围限制），
      避免实例数据携带 organization 时触发“缺少 organization 范围上下文”。
    """
    allowed = params.get("allowed_org_ids")
    if allowed is not None:
        return allowed
    org_value = (data or {}).get("organization")
    if isinstance(org_value, list):
        return org_value
    return None


@nats_client.register
def update_instance(params):
    """
    修改实例属性

    params={
        "inst_id": 123,            # 实例ID，优先使用；缺省时用 model_id+inst_name 定位
        "model_id": "host",        # 配合 inst_name 定位实例时必填
        "inst_name": "host-01",    # 配合 model_id 定位实例时必填
        "update_attr": {...},      # 待更新的属性键值
        "operator": "admin",       # 操作人，用于变更记录
        "allowed_org_ids": [1, 2]  # 可选；限制 organization 范围，缺省不限制
    }
    -> 更新后的实例数据
    """
    update_attr = params.get("update_attr") or {}
    if not update_attr:
        raise ValueError("update_attr is required")

    inst_id = params.get("inst_id") or params.get("_id")
    if not inst_id:
        model_id = params.get("model_id")
        inst_name = params.get("inst_name")
        if not (model_id and inst_name):
            raise ValueError("inst_id or (model_id and inst_name) is required")
        instances, _ = InstanceManage.search_inst(model_id=model_id, inst_name=inst_name)
        if not instances:
            raise ValueError("实例不存在！")
        inst_id = instances[0]["_id"]

    return InstanceManage.instance_update(
        user_groups=[],
        roles=[],
        inst_id=int(inst_id),
        update_attr=update_attr,
        operator=params.get("operator", ""),
        allowed_org_ids=_resolve_allowed_org_ids(params, update_attr),
        skip_permission_check=True,
    )


@nats_client.register
def create_instance(params):
    """
    创建实例

    params={
        "model_id": "host",        # 模型ID，必填
        "instance_info": {...},    # 实例属性键值，必填
        "operator": "admin",       # 操作人，用于变更记录
        "allowed_org_ids": [1, 2]  # 可选；限制 organization 范围，缺省不限制
    }
    -> 创建后的实例数据
    """
    model_id = params.get("model_id")
    if not model_id:
        raise ValueError("model_id is required")

    instance_info = params.get("instance_info") or {}
    if not instance_info:
        raise ValueError("instance_info is required")

    return InstanceManage.instance_create(
        model_id=model_id,
        instance_info=instance_info,
        operator=params.get("operator", ""),
        allowed_org_ids=_resolve_allowed_org_ids(params, instance_info),
    )


@nats_client.register
def delete_instance(params):
    """
    删除实例（支持单个或批量）

    params={
        "inst_ids": [1, 2],        # 实例ID列表，优先使用
        "inst_id": 1,              # 单个实例ID（兼容 _id）
        "model_id": "host",        # 配合 inst_name 定位单个实例时必填
        "inst_name": "host-01",    # 配合 model_id 定位单个实例时必填
        "operator": "admin"        # 操作人，用于变更记录
    }
    -> {"result": True, "deleted": [<inst_ids>]}
    """
    inst_ids = _normalize_to_list(params.get("inst_ids"))

    if not inst_ids:
        single_id = params.get("inst_id") or params.get("_id")
        if single_id:
            inst_ids = [single_id]
        else:
            model_id = params.get("model_id")
            inst_name = params.get("inst_name")
            if not (model_id and inst_name):
                raise ValueError("inst_ids, inst_id or (model_id and inst_name) is required")
            instances, _ = InstanceManage.search_inst(model_id=model_id, inst_name=inst_name)
            if not instances:
                raise ValueError("实例不存在！")
            inst_ids = [instances[0]["_id"]]

    inst_ids = [int(i) for i in inst_ids]
    InstanceManage.instance_batch_delete(
        user_groups=[],
        roles=[],
        inst_ids=inst_ids,
        operator=params.get("operator", ""),
    )
    return {"result": True, "deleted": inst_ids}


@nats_client.register
def list_instances(params):
    """
    查询单个模型下的实例列表（分页 + 过滤）

    params={
        "model_id": "host",          # 模型ID，必填
        "params": [...],             # 可选；查询条件，格式同 instance_list，如
                                     #   [{"field": "ip_addr", "type": "str*", "value": "10."}]
        "page": 1,                   # 页码，默认 1
        "page_size": 20,             # 每页条数，默认 20
        "order": "",                 # 排序字段，前缀 - 表示倒序
        "format": True               # 可选；True 时把 org/user/enum 等字段转为展示值，默认 True
    }
    -> {"count": <总数>, "items": [<实例>, ...]}
    """
    model_id = params.get("model_id")
    if not model_id:
        raise ValueError("model_id is required")

    page = int(params.get("page") or 1)
    page_size = int(params.get("page_size") or 20)
    query_params = params.get("params") or []
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

    items = _format_asset_instances_response(model_id, instances) if need_format else [dict(i) for i in instances]
    return {"count": count, "items": items}


@nats_client.register
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
def search_models(params=None):
    """
    查询模型列表

    params={
        "classification_id": "host_mgmt",  # 可选；按分类过滤
        "include_hidden": False            # 可选；是否包含已隐藏模型，默认 False
    }
    -> [<模型定义>, ...]
    """
    params = params or {}
    classification_id = params.get("classification_id")
    classification_ids = [classification_id] if classification_id else None
    return ModelManage.search_model(
        classification_ids=classification_ids,
        include_hidden=bool(params.get("include_hidden", False)),
    )


@nats_client.register
def search_classifications(params=None):
    """
    查询模型分类列表

    params={"include_hidden": False}  # 可选；是否包含已隐藏分类，默认 False
    -> [<分类定义>, ...]
    """
    params = params or {}
    return ClassificationManage.search_model_classification(
        include_hidden=bool(params.get("include_hidden", False)),
    )


@nats_client.register
def search_model_associations(params):
    """
    查询模型关联定义（作为源或目标的所有关联）

    params={"model_id": "host"}  # 模型ID，必填
    -> [<模型关联定义>, ...]
    """
    model_id = (params or {}).get("model_id")
    if not model_id:
        raise ValueError("model_id is required")
    return ModelManage.model_association_search(model_id)


@nats_client.register
def search_instance_associations(params):
    """
    查询实例关联列表（某实例关联到的其它实例，按 model_asst_id 分组）

    params={
        "model_id": "host",   # 模型ID，必填
        "inst_id": 123        # 实例ID，必填
    }
    -> [{"src_model_id":..,"dst_model_id":..,"model_asst_id":..,"asst_id":..,"inst_list":[..]}, ...]
    """
    params = params or {}
    model_id = params.get("model_id")
    inst_id = params.get("inst_id") or params.get("_id")
    if not model_id or inst_id in (None, ""):
        raise ValueError("model_id and inst_id are required")
    return InstanceManage.instance_association_instance_list(model_id, int(inst_id))


@nats_client.register
def create_instance_association(params):
    """
    创建实例关联（写）

    params={
        "src_inst_id": 1,                  # 源实例ID，必填
        "dst_inst_id": 2,                  # 目标实例ID，必填
        "model_asst_id": "host_run_app",   # 模型关联ID，必填
        "operator": "admin"                # 操作人，用于变更记录
    }
    -> 创建后的关联边数据
    """
    params = params or {}
    src_inst_id = params.get("src_inst_id")
    dst_inst_id = params.get("dst_inst_id")
    model_asst_id = params.get("model_asst_id")
    if src_inst_id in (None, "") or dst_inst_id in (None, "") or not model_asst_id:
        raise ValueError("src_inst_id, dst_inst_id and model_asst_id are required")

    data = {
        "src_inst_id": int(src_inst_id),
        "dst_inst_id": int(dst_inst_id),
        "model_asst_id": model_asst_id,
    }
    for key in ("asst_id", "src_model_id", "dst_model_id"):
        if params.get(key) is not None:
            data[key] = params[key]

    return InstanceManage.instance_association_create(data, params.get("operator", ""))


@nats_client.register
def delete_instance_association(params):
    """
    删除实例关联（写）

    params={
        "asso_id": 10,        # 关联ID，必填（兼容 inst_asst_id / _id）
        "operator": "admin"   # 操作人，用于变更记录
    }
    -> {"result": True, "deleted": <asso_id>}
    """
    params = params or {}
    asso_id = params.get("asso_id") or params.get("inst_asst_id") or params.get("_id")
    if asso_id in (None, ""):
        raise ValueError("asso_id is required")

    asso_id = int(asso_id)
    InstanceManage.instance_association_delete(asso_id, params.get("operator", ""))
    return {"result": True, "deleted": asso_id}


@nats_client.register
def receive_config_file_result(data: dict):
    """接收 Stargazer 回传的配置文件采集结果并落库。"""
    logger.info("==[ConfigFileCollect] 接收配置文件采集结果")
    result = ConfigFileService.process_collect_result(data)
    logger.info(
        "==[ConfigFileCollect] 处理配置文件采集结果完成",
    )
    return {
        "result": True,
        "changed": bool(result.get("changed", False)),
        "task_updated": bool(result.get("task_updated", False)),
    }

@nats_client.register
def receive_collect_credential_result(data: dict):
    """接收 Stargazer 推送的单条或批量凭据执行结果并回写命中状态。"""
    payload = data or {}
    events = payload.get("events") if isinstance(payload, dict) else None

    if isinstance(events, list):
        logger.info(
            "Received pushed collect credential result batch, count=%s next_since=%s",
            len(events),
            payload.get("next_since") or "",
        )
    else:
        logger.info(
            "Received pushed collect credential result event, task_id=%s host=%s credential_id=%s success=%s",
            payload.get("collect_task_id") or payload.get("task_id") or "",
            payload.get("host") or "",
            payload.get("credential_id") or "",
            bool(payload.get("success")),
        )

    result = CollectCredentialResultService.process_batch(payload, parse_datetime=_parse_nats_datetime)

    if isinstance(events, list):
        logger.info(
            "Processed pushed collect credential result batch, processed=%s failed=%s next_since=%s",
            result.get("processed", 0),
            result.get("failed", 0),
            result.get("next_since") or "",
        )
    else:
        logger.info(
            "Processed pushed collect credential result event, result=%s task_id=%s object_key=%s credential_id=%s",
            result.get("result", False),
            result.get("task_id") or "",
            result.get("object_key") or "",
            result.get("credential_id") or "",
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
                "model_count": 15,
                "instance_count": 1234,
                "classification_count": 5
            },
            "message": ""
        }
    """
    model_permissions_map = _build_nats_model_permission_map(user_info)
    instance_permissions_map = _build_nats_permission_map(user_info)
    if model_permissions_map is None or instance_permissions_map is None:
        return {
            "result": True,
            "data": {"model_count": 0, "instance_count": 0, "classification_count": 0},
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


def _get_trunc_func_and_format(group_by):
    mapping = {
        "hour": (TruncHour, "%Y-%m-%d %H:00"),
        "day": (TruncDate, "%Y-%m-%d"),
        "week": (TruncWeek, "%Y-%m-%d"),
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
    text = str(value).strip()
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")

    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, target_tz)
    return parsed.astimezone(target_tz)


def _parse_nats_datetime(value):
    if value in (None, ""):
        return None
    return _parse_client_datetime(value, timezone.get_current_timezone())


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
    if group_by == "hour":
        current = start_dt.replace(minute=0, second=0, microsecond=0)
        while current < end_dt:
            periods.append(_format_period_value(current, target_tz))
            current += datetime.timedelta(hours=1)
    elif group_by == "day":
        current = start_dt.date()
        end_date = end_dt.date()
        while current <= end_date:
            periods.append(_format_period_value(current, target_tz))
            current += datetime.timedelta(days=1)
    elif group_by == "week":
        current = start_dt - datetime.timedelta(days=start_dt.weekday())
        while current < end_dt:
            periods.append(_format_period_value(current, target_tz))
            current += datetime.timedelta(weeks=1)
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
def get_change_trend(time=None, group_by="day", model_id=None, user_info=None, **kwargs):
    """
    获取 CMDB 变更趋势数据

    Args:
        time: [start_time, end_time] - 时间范围，格式 "YYYY-MM-DD HH:MM:SS"
        group_by: "day" | "hour" | "week" | "month" - 分组方式
        model_id: str | None - 可选，按模型过滤
        user_info: { team: int, user: str }

    Returns:
        {
            "result": True,
            "data": {
                "create": [["2026-04-15", 10], ["2026-04-16", 8]],
                "update": [["2026-04-15", 25], ["2026-04-16", 30]],
                "delete": [["2026-04-15", 2], ["2026-04-16", 1]]
            },
            "message": ""
        }
    """
    if not time or len(time) != 2:
        return {"result": False, "data": {}, "message": "time parameter is required as [start_time, end_time]"}

    target_tz = _resolve_target_timezone((user_info or {}).get("timezone") or kwargs.pop("timezone", None))
    start_time, end_time = time
    aware_start = _parse_client_datetime(start_time, target_tz)
    aware_end = _parse_client_datetime(end_time, target_tz)
    local_start = aware_start.astimezone(target_tz)
    local_end = aware_end.astimezone(target_tz)

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
    classifications = ClassificationManage.search_model_classification()
    classification_map = {c["classification_id"]: c["classification_name"] for c in classifications}

    model_permissions_map = _build_nats_model_permission_map(user_info)
    instance_permissions_map = _build_nats_permission_map(user_info)
    if model_permissions_map is None or instance_permissions_map is None:
        return {"result": True, "data": [], "message": ""}

    models = ModelManage.search_model(permissions_map=model_permissions_map)
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

    classifications = ClassificationManage.search_model_classification()
    classification_map = {c["classification_id"]: c["classification_name"] for c in classifications}

    model_permissions_map = _build_nats_model_permission_map(user_info)
    instance_permissions_map = _build_nats_permission_map(user_info)
    if model_permissions_map is None or instance_permissions_map is None:
        return {"result": True, "data": [], "message": ""}

    models = ModelManage.search_model(permissions_map=model_permissions_map)
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
