from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.cmdb.utils import call_cmdb_kwargs, call_cmdb_params, normalize_query_list, wrap_error


@tool(
    description="按模型分页查询 CMDB 实例。query_list 为字段过滤条件。"
    "model_id 用用户点名的对象模型（如 nginx/mysql）；点名中间件时禁止默认 host，不确定先 cmdb_list_models。"
    "返回 inst_uuid 与已联动的 monitor_id；查监控不要把 inst_uuid/_id 当 instance_ids。"
)
def cmdb_search_instances(
    model_id: str,
    query_list: Optional[List[Dict[str, Any]]] = None,
    page: int = 1,
    page_size: int = 10,
    order: str = "",
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    declared = ""
    if isinstance(config, dict):
        declared = str((config.get("configurable") or {}).get("declared_cmdb_model") or "").strip()
    model_norm = str(model_id).strip()
    if declared and model_norm.casefold() in {"host", "主机"} and declared.casefold() != "host":
        return wrap_error(f"用户已点名 {declared}，cmdb_search_instances 的 model_id 必须用 {declared}，禁止默认 host。" "请改用正确模型后重试；不确定可先 cmdb_list_models。")
    result = call_cmdb_params(
        "list_instances_for_llm",
        config,
        model_id=model_id,
        params=normalize_query_list(query_list),
        page=int(page),
        page_size=int(page_size),
        order=order or "",
        format=True,
    )
    if isinstance(result, dict) and result.get("success") is not False:
        hint = "查监控须用返回的 monitor_id（放 instance_ids），禁止把 inst_uuid/_id 当 instance_ids。"
        if declared:
            hint = f"请核对结果实例类型是否为 {declared}；" + hint
        result = {**result, "_next_step_hint": hint}
    return result


@tool(description="按 UUID 获取一条 CMDB 实例。返回含 inst_uuid 与 monitor_id；查监控须用 monitor_id，不要把 inst_uuid 当 instance_ids。")
def cmdb_get_instance(
    inst_uuid: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    return call_cmdb_params("get_instance_by_uuid", config, inst_uuid=inst_uuid)


@tool(description="按 CMDB inst_uuid 列表取已联动的监控 instance_id（monitor_id）。查监控必须用这个 ID，禁止把 inst_uuid/_id 当 instance_ids。")
def cmdb_get_monitor_ids(
    inst_uuids: List[str],
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuids:
        return wrap_error("inst_uuids is required")
    if not isinstance(inst_uuids, list):
        return wrap_error("inst_uuids must be a list")
    return call_cmdb_kwargs("get_monitor_ids_by_inst_uuids", config, inst_uuids=inst_uuids)


@tool(description="创建 CMDB 实例。instance_info 为属性键值，权限由服务端校验。")
def cmdb_create_instance(
    model_id: str,
    instance_info: Dict[str, Any],
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    if not isinstance(instance_info, dict):
        return wrap_error("instance_info must be a dict")
    return call_cmdb_params("create_instance_for_llm", config, model_id=model_id, instance_info=instance_info)


@tool(description="按 UUID 更新 CMDB 实例属性。")
def cmdb_update_instance(
    inst_uuid: str,
    update_data: Dict[str, Any],
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    if not isinstance(update_data, dict):
        return wrap_error("update_data must be a dict")
    return call_cmdb_params("update_instance_for_llm", config, inst_uuid=inst_uuid, update_attr=update_data)


@tool(description="批量按 UUID 更新 CMDB 实例同一组属性。")
def cmdb_batch_update_instances(
    inst_uuids: List[str],
    update_data: Dict[str, Any],
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuids:
        return wrap_error("inst_uuids is required")
    if not isinstance(update_data, dict):
        return wrap_error("update_data must be a dict")
    return call_cmdb_params("batch_update_instances", config, inst_uuids=inst_uuids, update_attr=update_data)


@tool(description="按 UUID 删除一条 CMDB 实例。")
def cmdb_delete_instance(
    inst_uuid: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    return call_cmdb_params("delete_instance_for_llm", config, inst_uuid=inst_uuid)


@tool(description="按 UUID 列表批量删除 CMDB 实例。")
def cmdb_batch_delete_instances(
    inst_uuids: List[str],
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuids:
        return wrap_error("inst_uuids is required")
    return call_cmdb_params("delete_instance_for_llm", config, inst_uuids=inst_uuids)


@tool(description="从实例 UUID 查询轻量关联拓扑。")
def cmdb_topo_search(
    inst_uuid: str,
    depth: int = 3,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    return call_cmdb_kwargs("topo_search_lite_by_uuid", config, inst_uuid=inst_uuid, depth=int(depth))


@tool(description="从实例 UUID 展开拓扑，排除 parent_uuids。")
def cmdb_topo_expand(
    inst_uuid: str,
    parent_uuids: List[str],
    depth: int = 2,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    if not isinstance(parent_uuids, list):
        return wrap_error("parent_uuids must be a list")
    return call_cmdb_kwargs(
        "topo_search_expand_by_uuid",
        config,
        inst_uuid=inst_uuid,
        parent_uuids=parent_uuids,
        depth=int(depth),
    )
