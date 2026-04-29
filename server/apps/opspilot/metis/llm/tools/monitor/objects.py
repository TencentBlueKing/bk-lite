from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, resolve_monitor_runtime_params, wrap_error


@tool(description="List available monitor objects.")
def monitor_list_objects(
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    runtime_params = resolve_monitor_runtime_params(config, username=username, password=password, domain=domain, team_id=team_id)
    return call_monitor_rpc("monitor_objects", **runtime_params)


@tool(description="List monitor instances for a monitor object.")
def monitor_list_object_instances(
    monitor_obj_id: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    runtime_params = resolve_monitor_runtime_params(config, username=username, password=password, domain=domain, team_id=team_id)
    return call_monitor_rpc(
        "monitor_object_instances",
        **runtime_params,
        monitor_obj_id=monitor_obj_id,
    )
