# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 10:41
# @Author: windyzhao
import time
import uuid
from typing import List

from sanic import Blueprint
from sanic.log import logger
from sanic import response

from core.task_queue import get_task_queue
from plugins.base_utils import expand_ip_range

collect_router = Blueprint("collect", url_prefix="/collect")


def _parse_hosts(hosts_param: str) -> List[str]:
    """
    解析hosts参数，支持逗号分隔和IP段
    
    支持格式：
    - 单个IP/域名: "192.168.1.1" 或 "ecs.cn-beijing.aliyuncs.com"
    - 逗号分隔: "192.168.1.1,192.168.1.2"
    - IP段: "192.168.1.1-192.168.1.10"
    - 混合: "192.168.1.1,192.168.1.5-192.168.1.8"
    
    Args:
        hosts_param: hosts参数字符串
        
    Returns:
        解析后的IP/域名列表
    """
    if not hosts_param or not hosts_param.strip():
        return []
    
    result = []
    segments = [seg.strip() for seg in hosts_param.split(",") if seg.strip()]
    
    for segment in segments:
        if "-" in segment and segment.count(".") >= 3:
            # 可能是IP段（192.168.1.1-192.168.1.10）
            try:
                expanded = expand_ip_range(segment)
                result.extend(expanded)
                logger.debug(f"Expanded IP range '{segment}' to {len(expanded)} IPs")
            except Exception as e:
                logger.warning(f"Failed to expand IP range '{segment}': {e}, treating as literal")
                result.append(segment)
        else:
            # 单个IP/域名/endpoint
            result.append(segment)
    
    return result


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

    # Sanic 要求请求体被消费（即使是 GET 请求），否则可能出现
    # "<Request ...> body not consumed." 日志告警。
    await request.receive_body()

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
        # 3. 构建基础任务参数
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

        # 4. 获取任务队列
        task_queue = get_task_queue()
        
        # 5. 检查是否有hosts参数
        hosts_param = params.get("hosts", "").strip()
        
        if hosts_param:
            # ========== 场景A：有hosts参数 → 拆分任务 ==========
            hosts_list = _parse_hosts(hosts_param)
            
            if not hosts_list:
                # hosts参数解析为空
                current_timestamp = int(time.time() * 1000)
                error_lines = [
                    "# HELP collection_request_error Collection request error",
                    "# TYPE collection_request_error gauge",
                    f'collection_request_error{{model_id="{model_id}",error="Failed to parse hosts parameter"}} 1 {current_timestamp}'
                ]
                return response.raw(
                    "\n".join(error_lines) + "\n",
                    content_type='text/plain; version=0.0.4; charset=utf-8',
                    status=400
                )
            
            # 生成批次ID
            batch_id = f"batch_{uuid.uuid4().hex[:16]}"
            
            logger.info("=" * 70)
            logger.info(f"📦 Task splitting: {len(hosts_list)} host(s) → {len(hosts_list)} task(s)")
            logger.info(f"📋 Batch ID: {batch_id}")
            logger.info(f"🎯 Model: {model_id}")
            logger.info("=" * 70)
            
            task_infos = []
            success_count = 0
            failed_count = 0
            
            # 循环每个host创建任务
            for idx, host in enumerate(hosts_list, 1):
                try:
                    # 构建单个host的任务参数
                    single_host_params = {
                        **task_params,
                        "host": host,  # 单个IP或endpoint
                        "batch_id": batch_id,
                        "batch_index": idx,
                        "batch_total": len(hosts_list)
                    }
                    
                    # 创建任务
                    task_info = await task_queue.enqueue_collect_task(single_host_params)
                    task_infos.append({
                        "host": host,
                        "task_id": task_info["task_id"],
                        "job_id": task_info.get("job_id", ""),
                        "status": task_info["status"]
                    })
                    
                    if task_info["status"] == "queued":
                        success_count += 1
                        logger.info(f"  ✅ [{idx}/{len(hosts_list)}] {host}: {task_info['task_id']}")
                    else:
                        logger.warning(f"  ⚠️  [{idx}/{len(hosts_list)}] {host}: {task_info['status']}")
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"  ❌ [{idx}/{len(hosts_list)}] {host}: {e}")
                    task_infos.append({
                        "host": host,
                        "task_id": "",
                        "status": "failed",
                        "error": str(e)
                    })
            
            # 输出汇总
            skipped_count = len(hosts_list) - success_count - failed_count
            logger.info("=" * 70)
            logger.info(f"📊 Summary: {success_count} queued, {failed_count} failed, {skipped_count} skipped")
            logger.info("=" * 70)
            
            # 返回批次响应
            current_timestamp = int(time.time() * 1000)
            prometheus_lines = [
                "# HELP collection_batch_accepted Indicates that collection batch was accepted",
                "# TYPE collection_batch_accepted gauge",
                f'collection_batch_accepted{{model_id="{model_id}",batch_id="{batch_id}",total="{len(hosts_list)}",queued="{success_count}",failed="{failed_count}"}} 1 {current_timestamp}'
            ]
            
            return response.raw(
                "\n".join(prometheus_lines) + "\n",
                content_type='text/plain; version=0.0.4; charset=utf-8',
                headers={
                    'X-Batch-ID': batch_id,
                    'X-Task-Count': str(len(task_infos)),
                    'X-Success-Count': str(success_count)
                }
            )
        else:
            # ========== 场景B：无hosts参数 → 单任务 ==========
            # 云采集使用默认endpoint，或单IP采集
            logger.info(f"📦 Single task mode: model={model_id}")
            
            task_info = await task_queue.enqueue_collect_task(task_params)
            task_status = task_info.get("status", "unknown")
            logger.info(
                f"Plugin task enqueue result: task_id={task_info['task_id']}, "
                f"status={task_status}, model_id={model_id}, job_id={task_info.get('job_id', '')}"
            )
            
            # 返回单任务响应
            current_timestamp = int(time.time() * 1000)
            prometheus_lines = [
                "# HELP collection_request_accepted Indicates that collection request was accepted",
                "# TYPE collection_request_accepted gauge",
                f'collection_request_accepted{{model_id="{model_id}",task_id="{task_info["task_id"]}",status="{task_status}"}} 1 {current_timestamp}'
            ]
            
            return response.raw(
                "\n".join(prometheus_lines) + "\n",
                content_type='text/plain; version=0.0.4; charset=utf-8',
                headers={
                    'X-Task-ID': task_info['task_id'],
                    'X-Job-ID': task_info.get('job_id', ""),
                    'X-Task-Status': task_status
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
