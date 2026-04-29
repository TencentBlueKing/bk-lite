from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, resolve_monitor_runtime_params, wrap_error


@tool(description="List metrics for a monitor object.")
def monitor_list_object_metrics(
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
        "monitor_metrics",
        **runtime_params,
        monitor_obj_id=monitor_obj_id,
    )


@tool(description="List monitored metrics for a specific monitor instance.")
def monitor_list_instance_metrics(
    monitor_obj_id: str,
    instance_id: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
    config: RunnableConfig = None,
    only_with_data: bool = False,
    lookback: str = "1h",
    page: int = 1,
    page_size: int = 100,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    if not instance_id:
        return wrap_error("instance_id is required")
    runtime_params = resolve_monitor_runtime_params(config, username=username, password=password, domain=domain, team_id=team_id)
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "instance_id": instance_id,
        "only_with_data": only_with_data,
        "lookback": lookback,
        "page": page,
        "page_size": page_size,
    }
    return call_monitor_rpc(
        "monitor_instance_metrics",
        **runtime_params,
        query_data=query_data,
    )


@tool(description="Query metric data for a monitor object and metric.")
def monitor_query_metric_data(
    monitor_obj_id: Optional[str] = None,
    metric: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
    config: RunnableConfig = None,
    step: str = "5m",
    instance_ids: Optional[List[str]] = None,
    dimensions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    if not metric:
        return wrap_error("metric is required")
    if start in (None, ""):
        return wrap_error("start is required")
    if end in (None, ""):
        return wrap_error("end is required")
    runtime_params = resolve_monitor_runtime_params(config, username=username, password=password, domain=domain, team_id=team_id)
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "metric": metric,
        "start": start,
        "end": end,
        "step": step,
        "instance_ids": instance_ids or [],
        "dimensions": dimensions or {},
    }
    return call_monitor_rpc(
        "query_monitor_data_by_metric",
        **runtime_params,
        query_data=query_data,
    )
