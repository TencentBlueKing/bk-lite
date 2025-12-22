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

    Args:
        ctx: ARQ 上下文
        metrics_data: Prometheus 格式的指标数据
        params: 采集参数（包含 tags）
        task_id: 任务ID
    """
    try:
        from core.nats import NATSClient, NATSConfig

        # 确定 subject
        # 优先使用 node_ip，其次 host
        tags = params.get('tags', {})
        node_ip = tags.get('node_ip') or params.get('host', params.get('node_id', 'unknown'))

        # 过滤特殊字符，只保留字母数字和点、下划线
        host_filtered = ''.join(c if c.isalnum() or c in '._' else '_' for c in str(node_ip))
        subject = f"metrics.{host_filtered}"

        logger.info(f"[NATS Helper] Preparing to publish to subject: {subject}")

        # 将 Prometheus 格式转换为 InfluxDB Line Protocol 格式
        influx_data = convert_prometheus_to_influx(metrics_data, params)

        if not influx_data:
            logger.warning(f"[NATS Helper] No data to publish for task {task_id}")
            return

        logger.info(f"[NATS Helper] Converted {len(metrics_data)} bytes Prometheus data to {len(influx_data)} bytes InfluxDB format")

        # 创建 NATS 配置并打印调试信息
        nats_config = NATSConfig.from_env()
        logger.info(f"[NATS Helper] NATS config: servers={nats_config.servers}, tls_enabled={nats_config.tls_enabled}, user={nats_config.user}")

        # 使用 async with 自动管理连接
        try:
            async with NATSClient(nats_config) as nats_client:
                logger.info(f"[NATS Helper] NATS client connected: {nats_client.is_connected}, nc={nats_client.nc}")

                # 检查连接状态
                if not nats_client.nc:
                    raise ConnectionError("NATS client nc is None after connect")

                if nats_client.nc.is_closed:
                    raise ConnectionError("NATS connection is closed")

                # 直接推送 InfluxDB Line Protocol 格式的字符串（不是 JSON）
                await nats_client.nc.publish(subject, influx_data.encode('utf-8'))

                logger.info(f"[NATS Helper] Metrics published to '{subject}' for task {task_id}, size: {len(influx_data)} bytes")
        except ConnectionError as ce:
            logger.error(f"[NATS Helper] Connection error: {ce}")
            raise
        except Exception as conn_err:
            logger.error(f"[NATS Helper] Failed to connect to NATS: {conn_err}\n{traceback.format_exc()}")
            raise

    except Exception as e:
        logger.error(f"[NATS Helper] Failed to publish metrics: {e}\n{traceback.format_exc()}")


def convert_prometheus_to_influx(prometheus_data: str, params: Dict[str, Any]) -> str:
    """
    将 Prometheus 格式转换为 InfluxDB Line Protocol 格式

    Prometheus 格式:
        metric_name{label1="value1",label2="value2"} value timestamp

    InfluxDB Line Protocol 格式:
        metric_name,tag1=value1,tag2=value2 field=value timestamp

    Args:
        prometheus_data: Prometheus 格式的指标数据
        params: 采集参数（包含从 API 传递的 tags）

    Returns:
        InfluxDB Line Protocol 格式的数据
    """
    if not prometheus_data or not prometheus_data.strip():
        return ""

    lines = []

    # 获取通用 tags（从 API 传递的参数）
    common_tags = _build_common_tags(params)

    for line in prometheus_data.split('\n'):
        line = line.strip()

        # 跳过注释和空行
        if not line or line.startswith('#'):
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

            # 构建 InfluxDB Line Protocol
            # 格式: measurement,tag1=value1,tag2=value2 field=value timestamp
            # 过滤掉空值的 tags
            tag_str = ','.join(f"{k}={v}" for k, v in tags.items() if v)
            influx_line = f"{metric_name},{tag_str} value={value}"

            if timestamp:
                influx_line += f" {timestamp}"

            lines.append(influx_line)

        except Exception as e:
            logger.debug(f"[NATS Helper] Failed to parse line: {line}, error: {e}")
            continue

    return '\n'.join(lines)


def _build_common_tags(params: Dict[str, Any]) -> Dict[str, str]:
    """
    构建通用的 tags（从 API 传递的参数中获取）

    优先使用 params['tags'] 中 Telegraf 传递的标签，
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

    # 如果 API 传递了完整的 tags，直接使用
    if api_tags.get('agent_id'):
        tags = {
            'agent_id': api_tags.get('agent_id', ''),
            'instance_id': api_tags.get('instance_id', ''),
            'instance_type': api_tags.get('instance_type', ''),
            'collect_type': api_tags.get('collect_type', ''),
            'config_type': api_tags.get('config_type', ''),
        }
    else:
        # 兼容旧的调用方式（没有传递 tags）
        host = params.get('host', params.get('node_id', 'unknown'))
        monitor_type = params.get('monitor_type', params.get('plugin_name', 'unknown'))

        tags = {
            'agent_id': f"stargazer-{host}",
            'instance_id': host,
            'instance_type': monitor_type,
            'collect_type': 'monitor',
            'config_type': 'auto',
        }

    # 清理 tags 中的特殊字符
    cleaned_tags = {}
    for k, v in tags.items():
        if v:  # 只保留非空值
            # InfluxDB tags 不能包含空格、逗号、等号
            cleaned_value = str(v).replace(' ', '_').replace(',', '_').replace('=', '_')
            cleaned_tags[k] = cleaned_value

    return cleaned_tags
