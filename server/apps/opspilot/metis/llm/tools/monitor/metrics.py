from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error


@tool(description=("BK-Lite监控：列出某对象类型下的指标定义（含CPU/内存等）。" "查主机CPU使用率前用此工具确认指标名；" "不要用系统命令采集。"))
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


@tool(description=("BK-Lite监控：列出某实例已采集的指标。" "确认目标主机是否有CPU等指标数据；" "可 only_with_data/lookback 过滤。"))
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


@tool(description=("BK-Lite监控：查询指标时序（CPU使用率等）。" "需 monitor_obj_id、metric、start、end；可用 instance_ids 指定主机。" "这是查主机CPU的正确方式，不要建议top/htop/SSH。"))
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
