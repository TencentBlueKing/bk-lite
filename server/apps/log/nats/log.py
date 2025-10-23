import nats_client
from apps.core.utils.time_util import format_time_iso
from apps.log.utils.query_log import VictoriaMetricsAPI


@nats_client.register
def log_search(query, time_range, limit=10, *args, **kwargs):
    """搜索日志"""
    start_time, end_time = time_range
    start_time = format_time_iso(start_time)
    end_time = format_time_iso(end_time)
    vm_api = VictoriaMetricsAPI()
    data = vm_api.query(query, start_time, end_time, limit)
    return {"result": True, "data": data, "message": ""}


@nats_client.register
def log_hits(query, time_range, field, fields_limit=5, step="5m", *args, **kwargs):
    """搜索日志命中数"""
    start_time, end_time = time_range
    start_time = format_time_iso(start_time)
    end_time = format_time_iso(end_time)
    vm_api = VictoriaMetricsAPI()
    resp = vm_api.hits(query, start_time, end_time, field, fields_limit, step)
    data = []
    for hit_dict in resp["hits"]:
        timestamps = hit_dict.get("timestamps", [])
        values = hit_dict.get("values", [])
        data.extend([{"name": k, "value": v} for k, v in zip(timestamps, values)])

    return {"result": True, "data": data, "message": ""}
