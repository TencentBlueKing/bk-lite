import time

from sanic import Blueprint
from sanic.log import logger
from sanic import response

from core.task_queue import get_task_queue

monitor_router = Blueprint("monitor", url_prefix="/monitor")


@monitor_router.get("/vmware/metrics")
async def vmware_metrics(request):
    """
    VMware 指标采集 - 异步模式
    立即返回请求已接收的指标，实际采集任务放入队列异步执行

    必需参数（Headers）：
        username: VMware vCenter 用户名
        password: VMware vCenter 密码
        host: VMware vCenter 地址

    可选参数（Query）：
        minutes: 采集时间范围（分钟），默认 5

    必需 Tags 参数（Headers，由 Telegraf 传递）：
        X-Agent-ID: 采集代理标识
                    示例: telegraf-10.0.0.1

        X-Instance-ID: 实例标识
                       示例: vcenter.example.com 或 10.0.0.1-cn-beijing

        X-Instance-Type: 实例类型
                         示例: vmware_vcenter, vmware_esxi

        X-Collect-Type: 采集类型
                        示例: monitor, discovery, health

        X-Config-Type: 配置类型
                       示例: auto, manual, template

    示例请求：
        curl -X GET "http://localhost:8083/api/monitor/vmware/metrics?minutes=5" \
             -H "username: admin@vsphere.local" \
             -H "password: ********" \
             -H "host: vcenter.example.com" \
             -H "X-Agent-ID: telegraf-10.0.0.1" \
             -H "X-Instance-ID: vcenter.example.com" \
             -H "X-Instance-Type: vmware_vcenter" \
             -H "X-Collect-Type: monitor" \
             -H "X-Config-Type: auto"

    返回：
        Prometheus 格式的"请求已接收"指标，包含 task_id 用于追踪
    """
    logger.info("=== VMware metrics collection request received ===")

    # 认证参数
    username = request.headers.get("username")
    password = request.headers.get("password")
    host = request.headers.get("host")
    minutes = request.args.get("minutes", 5)

    # 必需的 Tags（由 Telegraf 传递）
    agent_id = request.headers.get("agent_id", "")
    instance_id = request.headers.get("instance_id")
    instance_type = request.headers.get("instance_type")
    collect_type = request.headers.get("collect_type")
    config_type = request.headers.get("config_type")

    logger.info(f"Request: Host={host}, Minutes={minutes}, User={username}")
    logger.info(f"Tags: agent_id={agent_id}, instance_id={instance_id}, instance_type={instance_type}")

    try:
        # 构建任务参数
        task_params = {
            "monitor_type": "vmware",
            "username": username,
            "password": password,
            "host": host,
            "minutes": int(minutes),
            # Tags 参数（5个核心标签）
            "tags": {
                "agent_id": agent_id,
                "instance_id": instance_id,
                "instance_type": instance_type,
                "collect_type": collect_type,
                "config_type": config_type,
            }
        }

        # 获取任务队列并加入任务
        task_queue = get_task_queue()
        task_info = await task_queue.enqueue_collect_task(task_params)
        # 注意：不传 task_id 参数，让系统根据参数自动生成（用于去重）

        logger.info(f"VMware metrics task queued: {task_info['task_id']}")

        # 构建 Prometheus 格式的响应（表示请求已接收）
        current_timestamp = int(time.time() * 1000)
        prometheus_lines = [
            "# HELP monitor_request_accepted Indicates that monitor request was accepted",
            "# TYPE monitor_request_accepted gauge",
            f'monitor_request_accepted{{monitor_type="vmware",host="{host}",task_id="{task_info["task_id"]}",status="queued"}} 1 {current_timestamp}'
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
        logger.error(f"Error queuing VMware metrics task: {e}", exc_info=True)

        # 返回错误指标
        current_timestamp = int(time.time() * 1000)
        error_lines = [
            "# HELP monitor_request_error Monitor request error",
            "# TYPE monitor_request_error gauge",
            f'monitor_request_error{{monitor_type="vmware",host="{host}",error="{str(e)}"}} 1 {current_timestamp}'
        ]

        return response.raw(
            "\n".join(error_lines) + "\n",
            content_type='text/plain; version=0.0.4; charset=utf-8',
            status=500
        )


@monitor_router.get("/qcloud/metrics")
async def qcloud_metrics(request):
    """
    QCloud 指标采集 - 异步模式
    立即返回请求已接收的指标，实际采集任务放入队列异步执行

    必需参数（Headers）：
        username: QCloud SecretId
        password: QCloud SecretKey

    可选参数（Query）：
        minutes: 采集时间范围（分钟），默认 5

    必需 Tags 参数（Headers，由 Telegraf 传递）：
        X-Agent-ID: 采集代理标识
                    示例: telegraf-10.0.0.1

        X-Instance-ID: 实例标识
                       示例: qcloud-account-001 或 10.0.0.1-cn-beijing

        X-Instance-Type: 实例类型
                         示例: qcloud_cvm, qcloud_clb

        X-Collect-Type: 采集类型
                        示例: monitor, discovery, health

        X-Config-Type: 配置类型
                       示例: auto, manual, template

    示例请求：
        curl -X GET "http://localhost:8083/api/monitor/qcloud/metrics?minutes=5" \
             -H "username: AKIDxxxxxxxxxxxxx" \
             -H "password: ********" \
             -H "X-Agent-ID: telegraf-10.0.0.1" \
             -H "X-Instance-ID: qcloud-account-001" \
             -H "X-Instance-Type: qcloud_cvm" \
             -H "X-Collect-Type: monitor" \
             -H "X-Config-Type: auto"

    返回：
        Prometheus 格式的"请求已接收"指标，包含 task_id 用于追踪
    """
    logger.info("=== QCloud metrics collection request received ===")

    # 认证参数
    username = request.headers.get("username")
    password = request.headers.get("password")
    minutes = request.args.get("minutes", 5)

    # 必需的 Tags（由 Telegraf 传递）
    agent_id = request.headers.get("agent_id", "")
    instance_id = request.headers.get("instance_id")
    instance_type = request.headers.get("instance_type")
    collect_type = request.headers.get("collect_type")
    config_type = request.headers.get("config_type")

    logger.info(f"Request: Minutes={minutes}, User={username}")
    logger.info(f"Tags: agent_id={agent_id}, instance_id={instance_id}, instance_type={instance_type}")

    try:
        # 构建任务参数
        task_params = {
            "monitor_type": "qcloud",
            "username": username,
            "password": password,
            "minutes": int(minutes),
            # Tags 参数（5个核心标签）
            "tags": {
                "agent_id": agent_id,
                "instance_id": instance_id,
                "instance_type": instance_type,
                "collect_type": collect_type,
                "config_type": config_type,
            }
        }

        # 获取任务队列并加入任务
        task_queue = get_task_queue()
        task_info = await task_queue.enqueue_collect_task(task_params)
        # 注意：不传 task_id 参数，让系统根据参数自动生成（用于去重）

        logger.info(f"QCloud metrics task queued: {task_info['task_id']}")

        # 构建 Prometheus 格式的响应（表示请求已接收）
        current_timestamp = int(time.time() * 1000)
        prometheus_lines = [
            "# HELP monitor_request_accepted Indicates that monitor request was accepted",
            "# TYPE monitor_request_accepted gauge",
            f'monitor_request_accepted{{monitor_type="qcloud",username="{username}",task_id="{task_info["task_id"]}",status="queued"}} 1 {current_timestamp}'
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
        logger.error(f"Error queuing QCloud metrics task: {e}", exc_info=True)

        # 返回错误指标
        current_timestamp = int(time.time() * 1000)
        error_lines = [
            "# HELP monitor_request_error Monitor request error",
            "# TYPE monitor_request_error gauge",
            f'monitor_request_error{{monitor_type="qcloud",username="{username}",error="{str(e)}"}} 1 {current_timestamp}'
        ]

        return response.raw(
            "\n".join(error_lines) + "\n",
            content_type='text/plain; version=0.0.4; charset=utf-8',
            status=500
        )
