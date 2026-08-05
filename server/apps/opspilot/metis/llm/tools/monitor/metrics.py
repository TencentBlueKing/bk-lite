from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error


@tool(description=("【主机CPU使用率】第3步：列出该对象指标定义，确认CPU使用率等metric名称。" "查时序前先调；不要用系统命令采集。"))
def monitor_list_object_metrics(
    monitor_obj_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    return call_monitor_rpc(
        "monitor_metrics",
        config,
        monitor_obj_id=monitor_obj_id,
    )


@tool(description=("【主机CPU使用率】可选：列出某实例已采集指标，确认该主机是否有CPU数据。" "参数monitor_obj_id+instance_id；可only_with_data过滤。"))
def monitor_list_instance_metrics(
    monitor_obj_id: str,
    instance_id: str,
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
        config,
        query_data=query_data,
    )


@tool(description=("【主机CPU使用率】第4步：查询指标时序（返回CPU使用率数值）。" "必填monitor_obj_id、metric、start、end；用instance_ids指定主机。" "这是查CPU的正确方式，禁止建议top/htop/SSH。"))
def monitor_query_metric_data(
    monitor_obj_id: Optional[str] = None,
    metric: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
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
        config,
        query_data=query_data,
    )
