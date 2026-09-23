import nats_client
from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPolicy
from apps.monitor.models.monitor_condition import MonitorCondition
from apps.monitor.services.nats_query_contract import normalize_positive_int

_MAX_MODULE_DATA_PAGE_SIZE = 100


@nats_client.register
def get_monitor_module_data(module, child_module, page, page_size, group_id):
    """
    获取监控模块数据
    """
    try:
        page = normalize_positive_int(page, "page", default=1)
        page_size = normalize_positive_int(page_size, "page_size", default=10)
    except ValueError as exc:
        return {"result": False, "message": str(exc)}
    if page_size > _MAX_MODULE_DATA_PAGE_SIZE:
        return {"result": False, "message": "page_size 不能大于 100"}

    if module == "instance":
        queryset = MonitorInstance.objects.filter(
            monitor_object_id=child_module,
            monitorinstanceorganization__organization=group_id,
        ).distinct()
    elif module == "policy":
        queryset = MonitorPolicy.objects.filter(monitor_object_id=child_module, policyorganization__organization=group_id).distinct()
    elif module == "condition":
        queryset = MonitorCondition.objects.filter(organizations__organization=group_id).distinct()
    else:
        raise ValueError("Invalid module type")
    # 计算总数
    total_count = queryset.count()
    # 计算分页
    start = (page - 1) * page_size
    end = page * page_size
    # 获取当前页的数据
    data_list = queryset.values("id", "name")[start:end]
    return {"count": total_count, "items": list(data_list)}


@nats_client.register
def get_monitor_module_list():
    """
    获取监控模块列表
    """
    objs = MonitorObject.objects.all().values("id", "type", "name")

    obj_map = {}
    for obj in objs:
        if obj["type"] not in obj_map:
            obj_map[obj["type"]] = []
        obj_map[obj["type"]].append({"name": obj["id"], "display_name": obj["name"]})

    type_list = []
    for obj_type, items in obj_map.items():
        type_list.append({"name": obj_type, "display_name": obj_type, "children": items})

    return [
        {
            "name": "instance",
            "display_name": "Instance",
            "children": type_list,
        },
        {"name": "policy", "display_name": "Policy", "children": type_list},
        {"name": "condition", "display_name": "Condition", "children": []},
    ]
