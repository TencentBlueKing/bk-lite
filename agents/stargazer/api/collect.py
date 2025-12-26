# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 10:41
# @Author: windyzhao
import time

from sanic import Blueprint
from sanic.log import logger
from sanic import response

from core.task_queue import get_task_queue

collect_router = Blueprint("collect", url_prefix="/collect")


@collect_router.get("/collect_info")
async def collect(request):
    """
    配置采集 - 异步模式
    立即返回请求已接收的指标，实际采集任务放入队列异步执行

    参数来源：
    - Headers: cmdb* 开头的参数
    - Query: URL 参数（向后兼容）

    必需参数：
        plugin_name: 插件名称 (mysql_info, redis_info 等)

    可选 Tags 参数（Headers，由 Telegraf 传递）：
        X-Instance-ID: 实例标识
        X-Instance-Type: 实例类型
        X-Collect-Type: 采集类型（默认 discovery）
        X-Config-Type: 配置类型

    示例请求：
        curl -X GET "http://localhost:8083/api/collect/collect_info" \
             -H "cmdbplugin_name: mysql_info" \
             -H "cmdbhostname: 192.168.1.100" \
             -H "cmdbport: 3306" \
             -H "cmdbusername: root" \
             -H "cmdbpassword: ********" \
             -H "X-Instance-ID: mysql-192.168.1.100" \
             -H "X-Instance-Type: mysql" \
             -H "X-Collect-Type: discovery" \
             -H "X-Config-Type: auto"

    返回：
        Prometheus 格式的"请求已接收"指标，包含 task_id 用于追踪
    """
    logger.info("=== Plugin collection request received ===")

    # 1. 解析参数（兼容旧逻辑）
    params = {k.split("cmdb", 1)[-1]: v for k, v in dict(request.headers).items() if k.startswith("cmdb")}
    if not params:
        params = {i[0]: i[1] for i in request.query_args}

    # 2. 提取 Tags（从 Headers）
    instance_id = request.headers.get("instance_id")
    instance_type = request.headers.get("instance_type")
    collect_type = request.headers.get("collect_type")
    config_type = request.headers.get("config_type")

    model_id = params.get("model_id")
    if not model_id:
        # 返回错误指标
        current_timestamp = int(time.time() * 1000)
        error_lines = [
            "# HELP collection_request_error Collection request error",
            "# TYPE collection_request_error gauge",
            f'collection_request_error{{model_id="",instance_id="{instance_id}",error="model_id is Null"}} 1 {current_timestamp}'
        ]

        return response.raw(
            "\n".join(error_lines) + "\n",
            content_type='text/plain; version=0.0.4; charset=utf-8',
            status=500
        )


    try:
        # 3. 构建任务参数
        task_params = {
            **params,  # 原有参数（包含 plugin_name）
            # Tags 参数（5个核心标签）
            "tags": {
                "instance_id": instance_id,
                "instance_type": instance_type,
                "collect_type": collect_type,
                "config_type": config_type,
            }
        }

        # 4. 获取任务队列并加入任务
        task_queue = get_task_queue()
        task_info = await task_queue.enqueue_collect_task(task_params)
        # 注意：不传 task_id 参数，让系统根据参数自动生成（用于去重）

        logger.info(f"Plugin task queued: {task_info['task_id']}, model_id: {model_id}")

        # 5. 构建 Prometheus 格式的响应（表示请求已接收）
        current_timestamp = int(time.time() * 1000)
        prometheus_lines = [
            "# HELP collection_request_accepted Indicates that collection request was accepted",
            "# TYPE collection_request_accepted gauge",
            f'collection_request_accepted{{model_id="{model_id}",task_id="{task_info["task_id"]}",status="queued"}} 1 {current_timestamp}'
        ]

        metrics_response = "\n".join(prometheus_lines) + "\n"

        # 返回指标格式的响应
        return response.raw(
            metrics_response,
            content_type='text/plain; version=0.0.4; charset=utf-8',
            headers={
                'X-Task-ID': task_info['task_id'],
                'X-Job-ID': task_info['job_id']
            }
        )

    except Exception as e:
        logger.error(f"Error queuing plugin task: {e}", exc_info=True)

        # 返回错误指标
        current_timestamp = int(time.time() * 1000)
        error_lines = [
            "# HELP collection_request_error Collection request error",
            "# TYPE collection_request_error gauge",
            f'collection_request_error{{model_id="{model_id}",error="{str(e)}"}} 1 {current_timestamp}'
        ]

        return response.raw(
            "\n".join(error_lines) + "\n",
            content_type='text/plain; version=0.0.4; charset=utf-8',
            status=500
        )
