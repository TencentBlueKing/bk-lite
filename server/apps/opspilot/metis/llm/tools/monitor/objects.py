from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error


@tool(description="List available monitor objects.")
def monitor_list_objects(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    return call_monitor_rpc("monitor_objects", config)


@tool(description="List monitor instances for a monitor object.")
def monitor_list_object_instances(
    monitor_obj_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    return call_monitor_rpc(
        "monitor_object_instances",
        config,
        monitor_obj_id=monitor_obj_id,
    )
