import os

import nats_client
from apps.log.models import LogGroup, CollectType, CollectInstance
from apps.log.models.policy import Policy

_PAGE_SIZE_MAX = int(os.getenv("LOG_MODULE_DATA_PAGE_SIZE_MAX", "500"))


@nats_client.register
def get_log_module_data(module, child_module, page, page_size, group_id):
    """
    获取log模块数据
    """
    try:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), _PAGE_SIZE_MAX))
        group_id = int(group_id)
    except (TypeError, ValueError) as exc:
        return {"result": False, "message": f"参数类型错误: {exc}", "data": []}

    if module == "log_group":
        queryset = LogGroup.objects.filter(loggrouporganization__organization=group_id).distinct()
    elif module == "policy":
        queryset = Policy.objects.filter(collect_type_id=child_module, policyorganization__organization=group_id).distinct()
    elif module == "instance":
        queryset = CollectInstance.objects.filter(collect_type_id=child_module, collectinstanceorganization__organization=group_id).distinct()
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
def get_log_module_list():
    """
    获取log模块列表
    """
    objs = CollectType.objects.all().values("id", "name")
    collect_type_list = [{"name": obj["id"], "display_name": obj["name"], "children": []} for obj in objs]
    return [
        {
            "name": "log_group",
            "display_name": "LogGroup",
            "children": [],
        },
        {
            "name": "policy",
            "display_name": "Policy",
            "children": collect_type_list,
        },
        {
            "name": "instance",
            "display_name": "Instance",
            "children": collect_type_list,
        },
    ]
