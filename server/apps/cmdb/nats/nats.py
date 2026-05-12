import datetime

import nats_client
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncHour, TruncWeek, TruncMonth
from django.utils import timezone

from apps.cmdb.constants.constants import PERMISSION_MODEL, PERMISSION_INSTANCES, PERMISSION_TASK, CollectPluginTypes
from apps.cmdb.display_field.constants import (
    DISPLAY_SUFFIX,
    FIELD_TYPE_ENUM,
    FIELD_TYPE_ORGANIZATION,
    FIELD_TYPE_TABLE,
    FIELD_TYPE_TAG,
    FIELD_TYPE_USER,
    USER_DISPLAY_FORMAT,
)
from apps.cmdb.display_field.handler import DisplayFieldConverter, DisplayFieldHandler
from apps.cmdb.display_field.cache import ExcludeFieldsCache
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.models.change_record import ChangeRecord, CREATE_INST, UPDATE_INST, DELETE_INST, OPERATE_TYPE_CHOICES
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.constants.constants import INSTANCE
from apps.system_mgmt.models import Group, User
from apps.core.logger import cmdb_logger as logger


def _normalize_to_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


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
def receive_config_file_result(data: dict):
    """接收 Stargazer 回传的配置文件采集结果并落库。"""
    logger.info("==[ConfigFileCollect] 接收配置文件采集结果")
    result = ConfigFileService.process_collect_result(data)
    logger.info("==[ConfigFileCollect] 处理配置文件采集结果完成", )
    return {
        "result": True,
        "changed": bool(result.get("changed", False)),
        "task_updated": bool(result.get("task_updated", False)),
    }


@nats_client.register
def query_asset_instances(
    model_id=None,
    query_list=None,
    page=1,
    page_size=20,
    user_info=None,
    **kwargs,
):
    """
    查询 CMDB 资产实例（最简分页版）
    :param model_id: 模型ID（必填）
    :param query_list: 查询条件列表（可选，格式同 cmdb/api/instance/search）
    :param page: 页码
    :param page_size: 每页条数
    :param user_info: 当前用户信息（由 operation_analysis 自动注入）
    :return: {result: bool, data: {count: int, items: [...]}, message: str}
    """
    if not model_id:
        return {"result": True, "data": {"count": 0, "items": []}, "message": ""}

    page = int(page or 1)
    page_size = int(page_size or 20)
    if page <= 0:
        page = 1
    if page_size <= 0:
        page_size = 20

    user_info = user_info or {}
    team = user_info.get("team")

    def normalize_query_list(raw_query_list):
        if raw_query_list is None:
            return []

        if isinstance(raw_query_list, dict):
            raw_query_list = [raw_query_list]

        if not isinstance(raw_query_list, list):
            return []

        normalized = []

        def add_condition(item):
            if not item or not isinstance(item, dict):
                return

            field = item.get("field")
            condition_type = item.get("type")
            if not field or not condition_type:
                return

            if condition_type == "time":
                start = item.get("start")
                end = item.get("end")
                if start and end:
                    normalized.append({"field": field, "type": "time", "start": start, "end": end})
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

            normalized.append({"field": field, "type": condition_type, "value": value})

        def walk(node):
            if node is None:
                return
            if isinstance(node, dict):
                add_condition(node)
                return
            if isinstance(node, list):
                for sub in node:
                    walk(sub)

        walk(raw_query_list)
        return normalized

    query_params = []
    if team is not None:
        query_params.append({"field": "organization", "type": "list[]", "value": [int(team)]})

    normalized_query_list = normalize_query_list(query_list)
    if normalized_query_list:
        query_params.extend(normalized_query_list)

    instances, count = InstanceManage.instance_list(
        model_id=model_id,
        params=query_params,
        page=page,
        page_size=page_size,
        order="",
        creator="",
        permission_map={},
    )

    formatted_instances = _format_asset_instances_response(model_id, instances)

    return {
        "result": True,
        "data": {
            "count": count,
            "items": formatted_instances,
        },
        "message": "",
    }


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
    user_info = user_info or {}
    team = user_info.get("team")

    classifications = ClassificationManage.search_model_classification()
    classification_count = len(classifications)

    models = ModelManage.search_model()
    model_count = len(models)

    permissions_map = {}
    if team is not None:
        permissions_map[int(team)] = {"inst_names": []}

    model_counts = InstanceManage.model_inst_count(permissions_map=permissions_map)
    instance_count = sum(model_counts.values())

    return {
        "result": True,
        "data": {
            "model_count": model_count,
            "instance_count": instance_count,
            "classification_count": classification_count,
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


def _generate_time_periods(start_dt, end_dt, group_by, date_format):
    periods = []
    if group_by == "hour":
        current = start_dt.replace(minute=0, second=0, microsecond=0)
        while current < end_dt:
            periods.append(current.strftime(date_format))
            current += datetime.timedelta(hours=1)
    elif group_by == "day":
        current = start_dt.date()
        end_date = end_dt.date()
        while current <= end_date:
            periods.append(current.strftime(date_format))
            current += datetime.timedelta(days=1)
    elif group_by == "week":
        current = start_dt - datetime.timedelta(days=start_dt.weekday())
        while current < end_dt:
            periods.append(current.strftime(date_format))
            current += datetime.timedelta(weeks=1)
    elif group_by == "month":
        current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while current < end_dt:
            periods.append(current.strftime(date_format))
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

    start_time, end_time = time
    start_dt = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    end_dt = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    aware_start = timezone.make_aware(start_dt)
    aware_end = timezone.make_aware(end_dt)

    trunc_func, date_format = _get_trunc_func_and_format(group_by)
    all_periods = _generate_time_periods(start_dt, end_dt, group_by, date_format)

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
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(count=Count("id"))
            .order_by("period")
        )

        period_counts = {}
        for item in queryset:
            if item["period"]:
                period_key = item["period"].strftime(date_format)
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

    user_info = user_info or {}
    team = user_info.get("team")

    params = [{"field": "model_id", "type": "str=", "value": model_id}]
    format_permission_dict = {}
    if team is not None:
        format_permission_dict[int(team)] = []

    with GraphClient() as ag:
        instances, _ = ag.query_entity(
            label=INSTANCE,
            params=params,
            format_permission_dict=format_permission_dict,
        )

    display_field = f"{field}{DISPLAY_SUFFIX}"
    group_counts = {}
    for inst in instances:
        value = inst.get(display_field)
        if value in (None, "", []):
            value = inst.get(field)
        if value is None:
            value = "unknown"
        key = str(value)
        group_counts[key] = group_counts.get(key, 0) + 1

    attrs = ModelManage.search_model_attr(model_id)
    field_attr = next((attr for attr in attrs if attr.get("attr_id") == field), None)

    enum_map = {}
    if field_attr and field_attr.get("attr_type") == "enum":
        options = field_attr.get("option", [])
        enum_map = {str(opt.get("id")): opt.get("name") for opt in options if opt}

    result_data = []
    for key, count in group_counts.items():
        display_name = enum_map.get(key, key) if enum_map else key
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
    user_info = user_info or {}
    team = user_info.get("team")

    classifications = ClassificationManage.search_model_classification()
    classification_map = {c["classification_id"]: c["classification_name"] for c in classifications}

    models = ModelManage.search_model()

    permissions_map = {}
    if team is not None:
        permissions_map[int(team)] = {"inst_names": []}

    model_counts = InstanceManage.model_inst_count(permissions_map=permissions_map)

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
def model_inst_count(*args, **kwargs):
    """
    获取模型实例数量
    """
    result = InstanceManage.model_inst_count(permissions_map={}, creator="")
    return {"result": True, "message": "", "data": result}
