from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.cmdb.utils import call_cmdb_params, wrap_error


@tool(description="列出模型关联定义。")
def cmdb_list_model_associations(
    model_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    return call_cmdb_params("search_model_associations", config, model_id=model_id)


@tool(description="列出某实例的关联（按 model_asst_id 分组）。")
def cmdb_list_instance_associations(
    model_id: str,
    inst_uuid: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    return call_cmdb_params("search_instance_associations_for_llm", config, model_id=model_id, inst_uuid=inst_uuid)


@tool(description="列出与某实例关联的其它实例。")
def cmdb_list_associated_instances(
    model_id: str,
    inst_uuid: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    if not inst_uuid:
        return wrap_error("inst_uuid is required")
    return call_cmdb_params("search_instance_associations_for_llm", config, model_id=model_id, inst_uuid=inst_uuid)


@tool(description="创建实例关联。data 需含 src_inst_uuid、dst_inst_uuid、model_asst_id。")
def cmdb_create_instance_association(
    data: Dict[str, Any],
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return wrap_error("data must be a dict")
    required = ("src_inst_uuid", "dst_inst_uuid", "model_asst_id")
    if any(not data.get(key) for key in required):
        return wrap_error("src_inst_uuid, dst_inst_uuid and model_asst_id are required")
    return call_cmdb_params(
        "create_instance_association_for_llm",
        config,
        src_inst_uuid=data["src_inst_uuid"],
        dst_inst_uuid=data["dst_inst_uuid"],
        model_asst_id=data["model_asst_id"],
    )


@tool(description="删除实例关联。")
def cmdb_delete_instance_association(
    src_inst_uuid: str,
    dst_inst_uuid: str,
    model_asst_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not src_inst_uuid or not dst_inst_uuid or not model_asst_id:
        return wrap_error("src_inst_uuid, dst_inst_uuid and model_asst_id are required")
    return call_cmdb_params(
        "delete_instance_association_for_llm",
        config,
        src_inst_uuid=src_inst_uuid,
        dst_inst_uuid=dst_inst_uuid,
        model_asst_id=model_asst_id,
    )
