from celery import shared_task

from apps.core.aggregate_origin import probe_aggregate_origins


@shared_task
def probe_aggregate_metric_origins():
    """运行期探测聚合起点。失败只记日志，不参与启动，也不让任务失败重试。"""

    return probe_aggregate_origins()
