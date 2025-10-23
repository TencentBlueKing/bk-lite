import nats_client
from apps.node_mgmt.models import CloudRegion, Node


@nats_client.register
def get_node_module_data(module, child_module, page, page_size, group_id):
    """
        获取节点模块数据
    """
    if module == "instance":
        queryset = Node.objects.filter(
            cloud_region_id=child_module,
            nodeorganization__organization=group_id
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
def get_node_module_list():
    """
        获取节点模块列表
    """
    objs = CloudRegion.objects.all()

    cloud_list = []
    for obj in objs:
        cloud_list.append({
            "name": obj.id,
            "display_name": obj.name,
            "children": []
        })

    return [
        {
            "name": "instance",
            "display_name": "Instance",
            "children": cloud_list,
        }
    ]
