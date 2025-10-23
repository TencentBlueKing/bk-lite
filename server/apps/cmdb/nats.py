import nats_client
from apps.cmdb.constants import PERMISSION_MODEL, PERMISSION_INSTANCES, PERMISSION_TASK
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.constants import CollectPluginTypes


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
        queryset = [{"id": str(i['id']), "name": f"{i['model_id']}_{i['name']}"} for i in instances]
    elif module == PERMISSION_INSTANCES:
        instances, count = InstanceManage.instance_list(
            user_groups=[{'id': int(group_id)}],  # 改为列表
            roles=[],  # 空列表
            model_id=child_module,  # 使用实际模型ID
            params=[],  # 空查询条件（或按需添加）
            page=page,
            page_size=page_size,
            order="",
            check_permission=True  # 关闭权限检查
        )
        queryset = []
        for instance in instances:
            queryset.append({
                "name": instance["inst_name"],
                "id": instance["inst_name"]
            })
    elif module == PERMISSION_MODEL:
        models = ModelManage.search_model(classification_ids=[child_module], group_list=[int(group_id)])
        count = len(models)
        queryset = [{"id": model["model_id"], "name": model["model_name"]} for model in models]

    else:
        raise ValueError("Invalid module type")

    result = {
        "count": count,
        "items": list(queryset)
    }
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
        model_children.append({
            "name": classification["classification_id"],
            "display_name": classification["classification_name"],
        })
        classification_list.append({
            "name": classification["classification_id"],
            "display_name": classification["classification_name"],
            "children": []
        })

    """
        根据模型分类id进行数据封装
    """
    models = ModelManage.search_model()
    model_map = {}
    for model in models:
        if model["classification_id"] not in model_map:
            model_map[model["classification_id"]] = []

        model_map[model["classification_id"]].append({
            "name": model["model_id"],
            "display_name": model["model_name"],
        })

    for _classification in classification_list:
        classification_id = _classification["name"]
        if classification_id in model_map:
            _classification["children"] = model_map[classification_id]

    # 任务
    task_children = [{"name": name, "display_name": display_name} for name, display_name in CollectPluginTypes.CHOICE]

    result = [
        {"name": PERMISSION_MODEL, "display_name": "Model", "children": model_children},
        {"name": PERMISSION_INSTANCES, "display_name": "Instance", "children": classification_list},
        {"name": PERMISSION_TASK, "display_name": "Task", "children": task_children}
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
