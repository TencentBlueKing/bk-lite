from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, resolve_metric_window, wrap_error


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


@tool(
    description=(
        "【主机CPU使用率】第4步：查询指标时序（返回CPU使用率数值）。"
        "必填monitor_obj_id、metric；用监控instance_ids指定主机（可用主机名或IP）。"
        "禁止CMDB的inst_uuid/_id。可省略start/end（默认近1小时）。禁止建议top/htop/SSH。"
    )
)
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
    try:
        start_ms, end_ms = resolve_metric_window(start, end)
    except ValueError as exc:
        return wrap_error(str(exc))
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "metric": metric,
        "start": start_ms,
        "end": end_ms,
        "step": step,
        "instance_ids": instance_ids or [],
        "dimensions": dimensions or {},
    }
    return call_monitor_rpc(
        "query_monitor_data_by_metric",
        config,
        query_data=query_data,
    )


@tool(description=("【主机CPU使用率】按监控 instance_ids 查询主机 CPU/内存/磁盘均值与最高值快照。" "须用监控 instance_id/主机名/IP，禁止 CMDB 的 inst_uuid/_id。"))
def monitor_get_host_resource_snapshot(
    instance_ids: Optional[List[str]] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not instance_ids:
        return wrap_error("instance_ids is required")
    return call_monitor_rpc(
        "get_host_resource_snapshot",
        config,
        instance_ids=instance_ids,
    )
