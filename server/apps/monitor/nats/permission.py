import nats_client
from apps.monitor.models import MonitorInstance, MonitorObject, MonitorPolicy


@nats_client.register
def get_monitor_module_data(module, child_module, page, page_size, group_id):
    """
        获取监控模块数据
    """
    if module == "instance":
        queryset = MonitorInstance.objects.filter(
            monitor_object_id=child_module,
            monitorinstanceorganization__organization=group_id
        ).distinct("id")
    elif module == "policy":
        queryset = MonitorPolicy.objects.filter(
            monitor_object_id=child_module,
            policyorganization__organization=group_id
        ).distinct("id")
    else:
        raise ValueError("Invalid module type")
    # 计算总数
    total_count = queryset.count()
    # 计算分页
    start = (page - 1) * page_size
    end = page * page_size
    # 获取当前页的数据
    data_list = queryset.values("id", "name")[start:end]
    return {"count": total_count,"items": list(data_list)}


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
        type_list.append({
            "name": obj_type,
            "display_name": obj_type,
            "children": items
        })

    return [
        {
            "name": "instance",
            "display_name": "Instance",
            "children": type_list,
        },
        {
            "name": "policy",
            "display_name": "Policy",
            "children": type_list
        }
    ]
