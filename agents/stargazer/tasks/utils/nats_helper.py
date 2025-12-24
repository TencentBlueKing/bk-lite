# -- coding: utf-8 --
# @File: nats_helper.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
NATS 推送辅助工具
处理指标数据推送到 NATS（InfluxDB Line Protocol 格式）
"""
import traceback
from typing import Dict, Any
from sanic.log import logger


async def publish_metrics_to_nats(
    ctx: Dict,
    metrics_data: str,
    params: Dict[str, Any],
    task_id: str
):
    """
    将采集结果推送到 NATS 的 metrics 主题

    推送格式：InfluxDB Line Protocol（与 Telegraf 保持一致）
    每条指标数据单独发送一次消息

    Args:
        ctx: ARQ 上下文
        metrics_data: Prometheus 格式的指标数据
        params: 采集参数（包含 tags）
        task_id: 任务ID
    """
    try:
        from core.nats import NATSClient, NATSConfig
        import os

        # 获取 NATS Metric Topic 前缀（从环境变量读取，默认为 metrics）
        metric_topic_prefix = os.getenv('NATS_METRIC_TOPIC', 'metrics')

        # 获取任务类型（monitor_type 或 plugin_name）
        task_type = params.get('monitor_type') or params.get('plugin_name', 'unknown')

        # 构建 subject: {prefix}.{task_type}
        # 例如: metrics.vmware, metrics.mysql, metrics.host 等
        subject = f"{metric_topic_prefix}.{task_type}"

        logger.info(f"[NATS Helper] Preparing to publish to subject: {subject}")

        # 将 Prometheus 格式转换为 InfluxDB Line Protocol 格式
        influx_lines = convert_prometheus_to_influx(metrics_data, params)

        if not influx_lines:
            logger.warning(f"[NATS Helper] No data to publish for task {task_id}")
            return

        # 统计信息
        total_lines = len(influx_lines)
        total_bytes = sum(len(line.encode('utf-8')) for line in influx_lines)

        logger.info(f"[NATS Helper] Converted {len(metrics_data)} bytes Prometheus data to {total_lines} lines ({total_bytes} bytes)")

        # 打印前3行指标数据预览
        preview_count = min(3, len(influx_lines))
        if preview_count > 0:
            logger.info(f"[NATS Helper] Metrics preview (first {preview_count} lines):")
            for i, line in enumerate(influx_lines[:preview_count], 1):
                logger.info(f"[NATS Helper]   {i}. {line[:150]}{'...' if len(line) > 150 else ''}")
            if total_lines > preview_count:
                logger.info(f"[NATS Helper] ... and {total_lines - preview_count} more lines")

        # 创建 NATS 配置
        nats_config = NATSConfig.from_env()
        logger.info(f"[NATS Helper] NATS config: servers={nats_config.servers}, tls_enabled={nats_config.tls_enabled}, user={nats_config.user}")

        # 使用 async with 自动管理连接
        try:
            logger.info(f"[NATS Helper] Attempting to connect to NATS...")
            async with NATSClient(nats_config) as nats_client:
                logger.info(f"[NATS Helper] NATS client connected: {nats_client.is_connected}")

                # 检查连接状态
                if not nats_client.nc:
                    raise ConnectionError("NATS client nc is None after connect")

                if nats_client.nc.is_closed:
                    raise ConnectionError("NATS connection is closed")

                # 逐行发送消息（与 Telegraf 保持一致）
                success_count = 0
                for line in influx_lines:
                    try:
                        await nats_client.nc.publish(subject, line.encode('utf-8'))
                        success_count += 1
                    except Exception as pub_err:
                        logger.error(f"[NATS Helper] Failed to publish line: {line[:100]}, error: {pub_err}")

                logger.info(f"[NATS Helper] Successfully published {success_count}/{total_lines} metrics to '{subject}' for task {task_id}")

                if success_count < total_lines:
                    logger.warning(f"[NATS Helper] Failed to publish {total_lines - success_count} metrics")

        except ConnectionError as ce:
            logger.error(f"[NATS Helper] Connection error: {ce}")
            raise
        except Exception as conn_err:
            logger.error(f"[NATS Helper] Failed to connect to NATS: {conn_err}\n{traceback.format_exc()}")
            raise

    except Exception as e:
        logger.error(f"[NATS Helper] Failed to publish metrics: {e}\n{traceback.format_exc()}")


def convert_prometheus_to_influx(prometheus_data: str, params: Dict[str, Any]) -> list:
    """
    将 Prometheus 格式转换为 InfluxDB Line Protocol 格式

    Prometheus 格式:
        # TYPE metric_name gauge
        metric_name{label1="value1",label2="value2"} value timestamp

    InfluxDB Line Protocol 格式:
        metric_name,tag1=value1,tag2=value2 gauge=value timestamp
        (field 名称从 TYPE 注释中提取，保持与 Telegraf 行为一致)

    Args:
        prometheus_data: Prometheus 格式的指标数据
        params: 采集参数（包含从 API 传递的 tags）

    Returns:
        InfluxDB Line Protocol 格式的数据列表（每行一条）
    """
    if not prometheus_data or not prometheus_data.strip():
        return []

    lines = []

    # 获取通用 tags（从 API 传递的参数）
    common_tags = _build_common_tags(params)

    # 用于记录每个指标的类型（从 TYPE 注释中提取）
    metric_types = {}  # {metric_name: field_type}
    current_type = None

    for line in prometheus_data.split('\n'):
        line = line.strip()

        # 跳过空行
        if not line:
            continue

        # 解析 TYPE 注释，提取指标类型
        if line.startswith('# TYPE '):
            # 格式: # TYPE metric_name gauge|counter|histogram|summary
            parts = line.split()
            if len(parts) >= 4:
                metric_name = parts[2]
                metric_type = parts[3]  # gauge, counter, histogram, summary 等
                metric_types[metric_name] = metric_type
                current_type = metric_type
            continue

        # 跳过其他注释（HELP 等）
        if line.startswith('#'):
            continue

        try:
            # 解析 Prometheus 格式
            # 格式: metric_name{labels} value timestamp
            if '{' in line:
                # 有 labels
                metric_name = line[:line.index('{')]
                rest = line[line.index('{') + 1:]
                labels_part = rest[:rest.index('}')]
                value_part = rest[rest.index('}') + 1:].strip()
            else:
                # 无 labels
                parts = line.split()
                if len(parts) < 2:
                    continue
                metric_name = parts[0]
                labels_part = ""
                value_part = ' '.join(parts[1:])

            # 解析 value 和 timestamp
            value_parts = value_part.split()
            if len(value_parts) >= 1:
                value = value_parts[0]
                timestamp = value_parts[1] if len(value_parts) > 1 else ""
            else:
                continue

            # 构建 tags（common_tags 优先级最高）
            tags = common_tags.copy()

            # 解析 Prometheus labels 作为 tags（会被 common_tags 覆盖）
            if labels_part:
                for label in labels_part.split(','):
                    label = label.strip()
                    if '=' in label:
                        key, val = label.split('=', 1)
                        key = key.strip()
                        val = val.strip().strip('"')
                        # 只有 common_tags 中不存在的才添加
                        if key not in tags or not tags[key]:
                            tags[key] = val

            # 格式化字段值（InfluxDB 需要类型标识）
            # 整数加 'i' 后缀，浮点数保持原样
            try:
                # 尝试转换为数字
                if '.' in value or 'e' in value.lower():
                    # 浮点数
                    float(value)  # 验证是否有效
                    field_value = value
                else:
                    # 整数 - 需要添加 'i' 后缀
                    int(value)  # 验证是否有效
                    field_value = f"{value}i"
            except ValueError:
                # 字符串值 - 需要引号
                field_value = f'"{value}"'

            # 转换时间戳：毫秒 -> 纳秒（InfluxDB 默认精度）
            if timestamp:
                try:
                    # 如果是毫秒时间戳（13位），转换为纳秒（19位）
                    ts = int(timestamp)
                    if len(timestamp) == 13:
                        # 毫秒 -> 纳秒：乘以 1000000
                        timestamp = str(ts * 1000000)
                    elif len(timestamp) == 10:
                        # 秒 -> 纳秒：乘以 1000000000
                        timestamp = str(ts * 1000000000)
                    elif len(timestamp) == 19:
                        # 已经是纳秒，不需要转换
                        timestamp = str(ts)
                    else:
                        # 其他长度的时间戳，尝试标准化为纳秒
                        if ts > 9999999999999:  # 大于13位，可能是纳秒或更高精度
                            # 截断到纳秒精度（19位）
                            timestamp = str(ts)[:19].ljust(19, '0')
                        else:
                            # 小于等于13位，按毫秒处理
                            timestamp = str(ts * 1000000)
                except ValueError:
                    logger.warning(f"[NATS Helper] Invalid timestamp: {timestamp}")
                    timestamp = ""

            # 确定 field 名称：
            # 1. 优先使用 TYPE 注释中声明的类型（gauge, counter 等）
            # 2. 如果没有 TYPE 注释，使用 "value"
            # 这样可以保持与 Telegraf 的行为一致：cpu_usage_average + gauge = cpu_usage_average_gauge
            field_name = metric_types.get(metric_name, current_type if current_type else "value")

            # 构建 InfluxDB Line Protocol
            # 格式: measurement,tag1=value1,tag2=value2 field=value timestamp
            tag_str = ','.join(f"{k}={v}" for k, v in tags.items() if v)
            influx_line = f"{metric_name},{tag_str} {field_name}={field_value}"

            if timestamp:
                influx_line += f" {timestamp}"

            lines.append(influx_line)

        except Exception as e:
            logger.debug(f"[NATS Helper] Failed to parse line: {line}, error: {e}")
            continue

    return lines


def _build_common_tags(params: Dict[str, Any]) -> Dict[str, str]:
    """
    构建通用的 tags（从 API 传递的参数中获取）

    优先使用 params['tags'] 中传递的标签，
    如果没有则使用默认值

    核心 Tags（5个）：
    - agent_id: 采集代理标识
    - instance_id: 实例标识
    - instance_type: 实例类型
    - collect_type: 采集类型
    - config_type: 配置类型

    Args:
        params: 采集参数

    Returns:
        tags 字典
    """
    # 从 API 传递的 tags
    api_tags = params.get('tags', {})

    # 获取基础参数用于生成默认值
    host = params.get('host', params.get('node_id', 'unknown'))
    monitor_type = params.get('monitor_type', params.get('plugin_name', 'unknown'))

    # 构建 tags：优先使用用户传递的值，没有的用默认值
    tags = {
        'agent_id': api_tags.get('agent_id') or f"stargazer-{host}",
        'instance_id': api_tags.get('instance_id') or host,
        'instance_type': api_tags.get('instance_type') or monitor_type,
        'collect_type': api_tags.get('collect_type') or 'monitor',
        'config_type': api_tags.get('config_type') or 'auto',
    }

    # 清理 tags 中的特殊字符
    cleaned_tags = {}
    for k, v in tags.items():
        if v:  # 只保留非空值
            # InfluxDB tags 不能包含空格、逗号、等号
            cleaned_value = str(v).replace(' ', '_').replace(',', '_').replace('=', '_')
            cleaned_tags[k] = cleaned_value

    return cleaned_tags
