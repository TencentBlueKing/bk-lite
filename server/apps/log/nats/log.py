import nats_client
from apps.log.utils.query_log import VictoriaMetricsAPI


@nats_client.register
def log_search(query, start_time, end_time, limit=10):
    """搜索日志"""
    vm_api = VictoriaMetricsAPI()
    data = vm_api.query(query, start_time, end_time, limit)

    return data


@nats_client.register
def log_hits(query, start_time, end_time, field, fields_limit=5, step="5m"):
    """搜索日志命中数"""
    vm_api = VictoriaMetricsAPI()
    data = vm_api.hits(query, start_time, end_time, field, fields_limit, step)

    return data
