import nats_client
from apps.cmdb.constants.constants import PERMISSION_MODEL, PERMISSION_INSTANCES, PERMISSION_TASK, CollectPluginTypes
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.instance import InstanceManage


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
            model_id=child_module,  # 使用实际模型ID
            params=[{"field": "organization", "type": "list[]", "value": [int(group_id)]}],  # 空查询条件（或按需添加）
            page=page,
            page_size=page_size,
            order="",
            creator="",
            permission_map={}
        )
        queryset = []
        for instance in instances:
            queryset.append({
                "name": instance["inst_name"],
                "id": instance["inst_name"]
            })
    elif module == PERMISSION_MODEL:
        models = ModelManage.search_model(classification_ids=[child_module])
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
    :return: {data: [...], count: int, page: int, page_size: int}
    """
    if not model_id:
        return {"data": [], "count": 0, "page": 1, "page_size": int(page_size or 20)}

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
                    normalized.append(
                        {"field": field, "type": "time", "start": start, "end": end}
                    )
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

            normalized.append(
                {"field": field, "type": condition_type, "value": value}
            )

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

    return {
        "data": instances,
        "count": count,
        "page": page,
        "page_size": page_size,
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
        organizations=organizations,
        users=users
    )
    
    return result
